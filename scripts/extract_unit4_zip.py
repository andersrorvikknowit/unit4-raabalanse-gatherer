#!/usr/bin/env python3
"""Inspect and safely extract the three workbooks in a Unit4 report ZIP."""

from __future__ import annotations

import argparse
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata
import zipfile


MAX_ENTRY_SIZE = 100 * 1024 * 1024
MAX_TOTAL_SIZE = 250 * 1024 * 1024
RATIO_CHECK_SIZE = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
COPY_CHUNK_SIZE = 1024 * 1024
TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.xlsx\Z", re.ASCII)


class InputError(Exception):
    """The command line or a local input path is invalid."""


class BlockedError(Exception):
    """The archive or extraction request cannot be handled safely."""


class HelpRequested(Exception):
    """Argparse requested help without emitting non-JSON output."""

    def __init__(self, help_text: str) -> None:
        super().__init__(help_text)
        self.help_text = help_text


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)

    def print_help(self, file=None) -> None:  # noqa: ANN001 - argparse signature
        raise HelpRequested(self.format_help())


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _normalized_name(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _is_windows() -> bool:
    return os.name == "nt"


def _is_reparse_point(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _validate_entry_name(name: str) -> None:
    if not name or any(
        unicodedata.category(character) == "Cc" or character in {"\u2028", "\u2029"}
        for character in name
    ):
        raise BlockedError("archive contains an empty or invalid entry name")
    if name.startswith("-"):
        raise BlockedError("archive entry name cannot be passed safely to the extractor CLI")
    if name.startswith(("/", "\\")) or PurePosixPath(name).is_absolute():
        raise BlockedError("archive contains an absolute entry path")
    drive, _ = ntpath.splitdrive(name)
    if drive:
        raise BlockedError("archive contains a Windows drive or UNC path")

    portable_parts = name.replace("\\", "/").split("/")
    if any(part == ".." for part in portable_parts):
        raise BlockedError("archive contains parent-directory traversal")


def _validate_regular_file(info: zipfile.ZipInfo) -> None:
    if info.is_dir() or info.filename.endswith(("/", "\\")):
        raise BlockedError("archive contains a directory entry")
    if info.flag_bits & 0x1:
        raise BlockedError("archive contains an encrypted entry")
    if not info.filename.casefold().endswith(".xlsx"):
        raise BlockedError("archive contains a non-xlsx entry")

    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if info.create_system == 3 and file_type not in (0, stat.S_IFREG):
        raise BlockedError("archive contains a symbolic link or special file")

    if info.file_size > MAX_ENTRY_SIZE:
        raise BlockedError("archive entry exceeds the 100 MiB safety limit")
    if info.file_size > RATIO_CHECK_SIZE:
        if info.compress_size == 0:
            raise BlockedError("archive entry has an unsafe compression ratio")
        if info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise BlockedError("archive entry has an unsafe compression ratio")


def _read_and_validate(zip_path: Path) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    if not zip_path.exists() or not zip_path.is_file():
        raise InputError("ZIP path must identify an existing regular file")

    try:
        archive = zipfile.ZipFile(zip_path, mode="r")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise BlockedError("ZIP is not readable") from exc

    try:
        infos = archive.infolist()
        if len(infos) != 3:
            raise BlockedError("archive must contain exactly three entries")

        normalized_names: set[str] = set()
        total_size = 0
        for info in infos:
            _validate_entry_name(info.filename)
            _validate_regular_file(info)

            normalized = _normalized_name(info.filename)
            if normalized in normalized_names:
                raise BlockedError("archive contains duplicate or case-colliding names")
            normalized_names.add(normalized)

            total_size += info.file_size
            if total_size > MAX_TOTAL_SIZE:
                raise BlockedError("archive exceeds the 250 MiB total safety limit")

        bad_entry = archive.testzip()
        if bad_entry is not None:
            raise BlockedError("archive contains an entry with an invalid checksum")
        return archive, infos
    except Exception:
        archive.close()
        raise


def inspect_archive(zip_path: Path) -> dict[str, object]:
    archive, infos = _read_and_validate(zip_path)
    try:
        return {
            "status": "SAFE",
            "entry_count": len(infos),
            "entries": [
                {
                    "name": info.filename,
                    "compressed_size": info.compress_size,
                    "uncompressed_size": info.file_size,
                }
                for info in infos
            ],
        }
    finally:
        archive.close()


def _validate_output_dir(output_dir: Path) -> Path:
    try:
        requested_stat = os.lstat(output_dir)
    except FileNotFoundError as exc:
        raise InputError("output directory must already exist") from exc
    if not stat.S_ISDIR(requested_stat.st_mode):
        raise InputError("output directory must already exist")
    if stat.S_ISLNK(requested_stat.st_mode) or _is_reparse_point(requested_stat):
        raise BlockedError("output directory must not be a symbolic link or reparse point")

    resolved = output_dir.resolve(strict=True)
    directory_stat = os.lstat(resolved)
    if stat.S_ISLNK(directory_stat.st_mode) or _is_reparse_point(directory_stat):
        raise BlockedError("resolved output directory is a symbolic link or reparse point")
    if not _is_windows():
        if hasattr(os, "getuid") and directory_stat.st_uid != os.getuid():
            raise BlockedError("output directory must be owned by the current user")
        if stat.S_IMODE(directory_stat.st_mode) & 0o077:
            raise BlockedError("output directory must not be accessible by group or others")
    return resolved


def _validate_mappings(
    infos: list[zipfile.ZipInfo], entries: list[str] | None, targets: list[str] | None
) -> list[tuple[zipfile.ZipInfo, str]]:
    if entries is None or targets is None or len(entries) != 3 or len(targets) != 3:
        raise InputError("extract requires exactly three --entry and three --target values")

    info_by_name = {info.filename: info for info in infos}
    if len(set(entries)) != 3 or set(entries) != set(info_by_name):
        raise BlockedError("entry mappings must select every archive entry exactly once")

    normalized_targets: set[str] = set()
    mappings: list[tuple[zipfile.ZipInfo, str]] = []
    for entry, target in zip(entries, targets, strict=True):
        if not TARGET_RE.fullmatch(target):
            raise InputError("targets must be controlled ASCII .xlsx basenames")
        normalized = _normalized_name(target)
        if normalized in normalized_targets:
            raise InputError("target names must be unique ignoring case")
        normalized_targets.add(normalized)
        mappings.append((info_by_name[entry], target))
    return mappings


def extract_archive(
    zip_path: Path,
    output_dir: Path,
    entries: list[str] | None,
    targets: list[str] | None,
) -> dict[str, object]:
    resolved_output = _validate_output_dir(output_dir)
    archive, infos = _read_and_validate(zip_path)
    if _is_windows():
        return _extract_archive_windows(archive, infos, resolved_output, entries, targets)

    return _extract_archive_posix(archive, infos, resolved_output, entries, targets)


def _copy_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, target_fd: int
) -> int:
    copied = 0
    with os.fdopen(target_fd, mode="wb") as destination:
        with archive.open(info, mode="r") as source:
            while True:
                chunk = source.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                destination.write(chunk)
                copied += len(chunk)
    return copied


def _extract_archive_windows(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    resolved_output: Path,
    entries: list[str] | None,
    targets: list[str] | None,
) -> dict[str, object]:
    created_targets: list[Path] = []
    try:
        mappings = _validate_mappings(infos, entries, targets)
        target_paths = [(info, resolved_output / target, target) for info, target in mappings]

        for _, target_path, _ in target_paths:
            if target_path.parent != resolved_output:
                raise BlockedError("extraction target escapes the output directory")
            try:
                os.lstat(target_path)
            except FileNotFoundError:
                continue
            raise BlockedError("refusing to overwrite an existing extraction target")

        extracted: list[dict[str, object]] = []
        open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        open_flags |= getattr(os, "O_BINARY", 0)
        open_flags |= getattr(os, "O_NOINHERIT", 0)

        for info, target_path, target in target_paths:
            try:
                target_fd = os.open(target_path, open_flags, 0o600)
            except FileExistsError as exc:
                raise BlockedError("refusing to overwrite an existing extraction target") from exc
            created_targets.append(target_path)

            copied = _copy_entry(archive, info, target_fd)
            if copied != info.file_size:
                raise BlockedError("extracted size does not match ZIP metadata")
            extracted.append(
                {
                    "entry": info.filename,
                    "target": target,
                    "uncompressed_size": copied,
                }
            )

        return {"status": "EXTRACTED", "entry_count": 3, "entries": extracted}
    except Exception:
        for target_path in created_targets:
            try:
                os.unlink(target_path)
            except FileNotFoundError:
                pass
        raise
    finally:
        archive.close()


def _extract_archive_posix(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    resolved_output: Path,
    entries: list[str] | None,
    targets: list[str] | None,
) -> dict[str, object]:
    dir_fd: int | None = None
    created_targets: list[str] = []
    try:
        mappings = _validate_mappings(infos, entries, targets)

        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        dir_fd = os.open(resolved_output, directory_flags)

        for _, target in mappings:
            try:
                os.stat(target, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise BlockedError("refusing to overwrite an existing extraction target")

        extracted: list[dict[str, object]] = []
        open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            open_flags |= os.O_NOFOLLOW

        for info, target in mappings:
            try:
                target_fd = os.open(target, open_flags, 0o600, dir_fd=dir_fd)
            except FileExistsError as exc:
                raise BlockedError("refusing to overwrite an existing extraction target") from exc
            created_targets.append(target)

            copied = _copy_entry(archive, info, target_fd)

            if copied != info.file_size:
                raise BlockedError("extracted size does not match ZIP metadata")
            extracted.append(
                {
                    "entry": info.filename,
                    "target": target,
                    "uncompressed_size": copied,
                }
            )

        return {"status": "EXTRACTED", "entry_count": 3, "entries": extracted}
    except Exception:
        if dir_fd is not None:
            for target in created_targets:
                try:
                    os.unlink(target, dir_fd=dir_fd)
                except FileNotFoundError:
                    pass
        raise
    finally:
        if dir_fd is not None:
            os.close(dir_fd)
        archive.close()


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        prog="extract_unit4_zip.py",
        description="Inspect or safely extract a three-workbook Unit4 ZIP.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--zip", required=True, type=Path)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--zip", required=True, type=Path)
    extract_parser.add_argument("--output-dir", required=True, type=Path)
    extract_parser.add_argument("--entry", action="append")
    extract_parser.add_argument("--target", action="append")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        if args.command == "inspect":
            payload = inspect_archive(args.zip)
        else:
            payload = extract_archive(
                args.zip, args.output_dir, args.entry, args.target
            )
        _emit(payload)
        return 0
    except HelpRequested as exc:
        _emit({"status": "HELP", "help": exc.help_text})
        return 0
    except InputError as exc:
        _emit({"status": "INPUT_ERROR", "error": str(exc)})
        return 1
    except BlockedError as exc:
        _emit({"status": "BLOCKED", "error": str(exc)})
        return 3
    except Exception:
        _emit({"status": "BLOCKED", "error": "unexpected validation failure"})
        return 3


if __name__ == "__main__":
    sys.exit(main())
