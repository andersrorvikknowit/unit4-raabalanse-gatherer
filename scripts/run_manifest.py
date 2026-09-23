#!/usr/bin/env python3
"""Maintain a private, resumable Unit4 report-order run manifest.

The manifest deliberately contains only report-order identity and workflow
state.  It has no fields for customer rows, names, or monetary amounts.  Every
command emits exactly one machine-readable JSON object on stdout.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
MANIFEST_NAME = "run-manifest.json"
LOCK_NAME = ".run-manifest.lock"
RECORD_KEYS = ("raw_balance", "1510", "1560")
RECORD_STATES = {
    "PLANNED",
    "SUBMITTING",
    "RETRY_ALLOWED",
    "UNKNOWN",
    "CONFIRMED",
    "TRACKING",
    "FINISHED",
}
RUN_STATES = {"ACTIVE", "BLOCKED", "COMPLETE"}
TOP_LEVEL_KEYS = {
    "schema_version",
    "run_state",
    "company",
    "period",
    "blocked_reason",
    "records",
}
RECORD_FIELD_KEYS = {
    "state",
    "attempts",
    "baseline_orders",
    "candidate_orders",
    "order_number",
    "filename",
    "filename_kind",
    "visible_status",
}
FILENAME_KINDS = {"NONE", "FULL", "PREFIX"}
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MACHINE_REASON = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
COMPANY_CODE = re.compile(r"^\d{2,10}$")
MAX_MANIFEST_BYTES = 64 * 1024


class ManifestError(Exception):
    """Expected failure that can be reported without leaking input data."""

    exit_code = 1

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class InputError(ManifestError):
    exit_code = 1


class UnsafeError(ManifestError):
    exit_code = 3


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise InputError("invalid_cli_arguments")


def _emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _current_uid() -> int | None:
    if os.name == "nt":
        return None
    getter = getattr(os, "getuid", None)
    return getter() if getter is not None else None


def _enforce_posix_permissions() -> bool:
    return os.name != "nt"


def _is_link_or_reparse(result: os.stat_result) -> bool:
    if stat.S_ISLNK(result.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(result, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _require_owned(stat_result: os.stat_result) -> None:
    uid = _current_uid()
    if uid is not None and stat_result.st_uid != uid:
        raise UnsafeError("path_not_owned_by_current_user")


def _directory_stat(directory: Path, *, require_private: bool = True) -> os.stat_result:
    try:
        result = os.lstat(directory)
    except FileNotFoundError as error:
        raise InputError("directory_not_found") from error
    if _is_link_or_reparse(result) or not stat.S_ISDIR(result.st_mode):
        raise UnsafeError("unsafe_manifest_directory")
    _require_owned(result)
    if (
        require_private
        and _enforce_posix_permissions()
        and stat.S_IMODE(result.st_mode) != 0o700
    ):
        raise UnsafeError("manifest_directory_not_private")
    return result


def _prepare_directory(requested: str | None) -> Path:
    if requested is None:
        directory = Path(tempfile.mkdtemp(prefix="unit4-raabalanse-run-"))
        if _enforce_posix_permissions():
            os.chmod(directory, 0o700)
        _directory_stat(directory)
        return directory

    directory = Path(requested).expanduser().absolute()
    try:
        result = os.lstat(directory)
    except FileNotFoundError:
        parent = directory.parent
        _directory_stat(parent, require_private=False)
        try:
            directory.mkdir(mode=0o700)
        except OSError as error:
            raise UnsafeError("cannot_create_manifest_directory") from error
    else:
        del result
        # The directory belongs to this run and may be removed by `cleanup`.
        # Never chmod, reuse, or later delete a caller's pre-existing path.
        raise UnsafeError("manifest_directory_already_exists")

    _directory_stat(directory)
    return directory


def _manifest_stat(path: Path) -> os.stat_result:
    try:
        result = os.lstat(path)
    except FileNotFoundError as error:
        raise InputError("manifest_not_found") from error
    if _is_link_or_reparse(result):
        raise UnsafeError("symlink_manifest_rejected")
    if not stat.S_ISREG(result.st_mode):
        raise UnsafeError("manifest_not_regular_file")
    _require_owned(result)
    if _enforce_posix_permissions() and stat.S_IMODE(result.st_mode) != 0o600:
        raise UnsafeError("manifest_permissions_not_private")
    return result


def _fingerprint(result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        result.st_dev,
        result.st_ino,
        result.st_size,
        result.st_mtime_ns,
    )


def _lock_descriptor(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
    except (ImportError, OSError) as error:
        raise UnsafeError("cannot_lock_run_manifest") from error


def _unlock_descriptor(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except (ImportError, OSError) as error:
        raise UnsafeError("cannot_unlock_run_manifest") from error


@contextmanager
def _exclusive_run_lock(directory: Path):
    _directory_stat(directory)
    lock_path = directory / LOCK_NAME

    def validate_lock(result: os.stat_result) -> None:
        if _is_link_or_reparse(result) or not stat.S_ISREG(result.st_mode):
            raise UnsafeError("unsafe_manifest_lock")
        _require_owned(result)
        if (
            _enforce_posix_permissions()
            and stat.S_IMODE(result.st_mode) != 0o600
        ):
            raise UnsafeError("manifest_lock_permissions_not_private")

    existing: os.stat_result | None = None
    if os.path.lexists(lock_path):
        existing = os.lstat(lock_path)
        validate_lock(existing)

    base_flags = (
        os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        if existing is None:
            try:
                descriptor = os.open(
                    lock_path,
                    base_flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                existing = os.lstat(lock_path)
                validate_lock(existing)
                descriptor = os.open(lock_path, base_flags)
        else:
            descriptor = os.open(lock_path, base_flags)
    except OSError as error:
        raise UnsafeError("cannot_open_manifest_lock") from error

    locked = False
    try:
        opened = os.fstat(descriptor)
        validate_lock(opened)
        if existing is not None and (
            existing.st_dev,
            existing.st_ino,
        ) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise UnsafeError("manifest_lock_changed_during_open")
        if _enforce_posix_permissions():
            os.fchmod(descriptor, 0o600)
        _lock_descriptor(descriptor)
        locked = True
        yield lock_path
    finally:
        unlock_error: UnsafeError | None = None
        if locked:
            try:
                _unlock_descriptor(descriptor)
            except UnsafeError as error:
                unlock_error = error
        os.close(descriptor)
        if unlock_error is not None and sys.exc_info()[0] is None:
            raise unlock_error


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise UnsafeError("duplicate_manifest_key")
        result[key] = value
    return result


def _load_manifest(path_value: str) -> tuple[Path, dict[str, Any], tuple[int, int, int, int]]:
    path = Path(path_value).expanduser().absolute()
    _directory_stat(path.parent)
    before = _manifest_stat(path)
    if before.st_size > MAX_MANIFEST_BYTES:
        raise UnsafeError("manifest_too_large")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise UnsafeError("cannot_open_manifest_safely") from error

    try:
        opened = os.fstat(descriptor)
        if _fingerprint(opened) != _fingerprint(before):
            raise UnsafeError("manifest_changed_during_read")
        if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode):
            raise UnsafeError("manifest_not_regular_file")
        _require_owned(opened)
        if _enforce_posix_permissions() and stat.S_IMODE(opened.st_mode) != 0o600:
            raise UnsafeError("manifest_permissions_not_private")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            try:
                data = json.load(handle, object_pairs_hook=_reject_duplicate_json_keys)
            except (UnicodeError, json.JSONDecodeError) as error:
                raise UnsafeError("invalid_manifest_json") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if not isinstance(data, dict):
        raise UnsafeError("invalid_manifest_schema")
    _validate_manifest(data)
    return path, data, _fingerprint(before)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as error:
        raise UnsafeError("directory_fsync_open_failed") from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise UnsafeError("directory_fsync_failed") from error
    finally:
        os.close(descriptor)


def _atomic_write(
    path: Path,
    data: dict[str, Any],
    *,
    expected: tuple[int, int, int, int] | None,
) -> None:
    _validate_manifest(data)
    _directory_stat(path.parent)
    serialized = (
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if len(serialized.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise UnsafeError("manifest_too_large")
    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        if _enforce_posix_permissions():
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        if expected is None:
            if os.path.lexists(path):
                raise UnsafeError("manifest_already_exists")
        else:
            current = _manifest_stat(path)
            if _fingerprint(current) != expected:
                raise UnsafeError("manifest_changed_during_update")

        os.replace(temporary_name, path)
        temporary_name = None
        if _enforce_posix_permissions():
            os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _valid_period(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{6}", value):
        return False
    month = int(value[4:])
    return 1 <= month <= 12


def _safe_order(value: Any) -> bool:
    return isinstance(value, str) and SAFE_TOKEN.fullmatch(value) is not None


def _safe_filename(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 255:
        return False
    if value in {".", ".."} or "/" in value or "\\" in value:
        return False
    return not any(ord(character) < 32 or ord(character) == 127 for character in value)


def _safe_status(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 128:
        return False
    return not any(ord(character) < 32 or ord(character) == 127 for character in value)


def _validate_record(key: str, record: Any) -> None:
    del key
    if not isinstance(record, dict) or set(record) != RECORD_FIELD_KEYS:
        raise UnsafeError("unexpected_record_schema")

    state = record["state"]
    attempts = record["attempts"]
    baseline = record["baseline_orders"]
    candidates = record["candidate_orders"]
    order_number = record["order_number"]
    filename = record["filename"]
    filename_kind = record["filename_kind"]
    visible_status = record["visible_status"]

    if not isinstance(state, str) or state not in RECORD_STATES:
        raise UnsafeError("invalid_record_state")
    if type(attempts) is not int or not 0 <= attempts <= 2:
        raise UnsafeError("invalid_attempt_count")
    if (
        not isinstance(baseline, list)
        or any(not _safe_order(item) for item in baseline)
        or len(set(baseline)) != len(baseline)
    ):
        raise UnsafeError("invalid_baseline_orders")
    if (
        not isinstance(candidates, list)
        or any(not _safe_order(item) for item in candidates)
        or len(set(candidates)) != len(candidates)
    ):
        raise UnsafeError("invalid_candidate_orders")
    if state != "UNKNOWN" and candidates:
        raise UnsafeError("candidate_orders_require_unknown_state")
    if order_number is not None and not _safe_order(order_number):
        raise UnsafeError("invalid_order_number")
    if filename is not None and not _safe_filename(filename):
        raise UnsafeError("invalid_filename")
    if not isinstance(filename_kind, str) or filename_kind not in FILENAME_KINDS:
        raise UnsafeError("invalid_filename_kind")
    if (filename is None) != (filename_kind == "NONE"):
        raise UnsafeError("incoherent_filename_identity")
    if visible_status is not None and not _safe_status(visible_status):
        raise UnsafeError("invalid_visible_status")

    if state == "PLANNED":
        if attempts != 0 or baseline or any(
            value is not None for value in (order_number, filename, visible_status)
        ):
            raise UnsafeError("incoherent_planned_record")
    elif state in {"SUBMITTING", "RETRY_ALLOWED", "UNKNOWN"}:
        allowed_attempts = {1, 2} if state in {"SUBMITTING", "UNKNOWN"} else {1}
        if attempts not in allowed_attempts or any(
            value is not None for value in (order_number, filename, visible_status)
        ):
            raise UnsafeError("incoherent_submission_record")
    elif state == "CONFIRMED":
        if attempts not in {1, 2} or order_number is None:
            raise UnsafeError("incoherent_confirmed_record")
        if filename is not None or visible_status is not None:
            raise UnsafeError("incoherent_confirmed_record")
    elif state == "TRACKING":
        if attempts not in {1, 2} or order_number is None:
            raise UnsafeError("incoherent_tracking_record")
        if filename is None and visible_status is None:
            raise UnsafeError("empty_tracking_record")
    elif state == "FINISHED":
        if (
            attempts not in {1, 2}
            or order_number is None
            or filename is None
            or filename_kind not in {"FULL", "PREFIX"}
            or visible_status != "Ferdig"
        ):
            raise UnsafeError("incoherent_finished_record")


def _validate_manifest(data: dict[str, Any]) -> None:
    if set(data) != TOP_LEVEL_KEYS:
        raise UnsafeError("unexpected_manifest_schema")
    if data["schema_version"] != SCHEMA_VERSION or type(data["schema_version"]) is not int:
        raise UnsafeError("unsupported_manifest_schema")
    if not isinstance(data["run_state"], str) or data["run_state"] not in RUN_STATES:
        raise UnsafeError("invalid_run_state")
    if not isinstance(data["company"], str) or COMPANY_CODE.fullmatch(data["company"]) is None:
        raise UnsafeError("invalid_company_code")
    if not _valid_period(data["period"]):
        raise UnsafeError("invalid_period")
    if not isinstance(data["records"], dict) or set(data["records"]) != set(RECORD_KEYS):
        raise UnsafeError("unexpected_record_set")

    blocked_reason = data["blocked_reason"]
    if blocked_reason is not None and (
        not isinstance(blocked_reason, str)
        or MACHINE_REASON.fullmatch(blocked_reason) is None
    ):
        raise UnsafeError("invalid_block_reason")

    for key in RECORD_KEYS:
        _validate_record(key, data["records"][key])

    numbers = [
        record["order_number"]
        for record in data["records"].values()
        if record["order_number"] is not None
    ]
    if len(numbers) != len(set(numbers)):
        raise UnsafeError("duplicate_order_numbers")

    if data["run_state"] == "ACTIVE" and blocked_reason is not None:
        raise UnsafeError("active_run_has_block_reason")
    if data["run_state"] == "ACTIVE" and any(
        record["state"] == "UNKNOWN" for record in data["records"].values()
    ):
        raise UnsafeError("unknown_record_requires_blocked_run")
    if data["run_state"] == "BLOCKED" and blocked_reason is None:
        raise UnsafeError("blocked_run_missing_reason")
    if data["run_state"] == "COMPLETE":
        if blocked_reason is not None or any(
            record["state"] != "FINISHED" for record in data["records"].values()
        ):
            raise UnsafeError("incoherent_complete_run")

    raw_state = data["records"]["raw_balance"]["state"]
    account_1510_state = data["records"]["1510"]["state"]
    account_1560_state = data["records"]["1560"]["state"]
    if account_1510_state != "PLANNED" and raw_state != "FINISHED":
        raise UnsafeError("account_1510_requires_finished_raw_balance")
    if account_1560_state != "PLANNED" and (
        raw_state != "FINISHED"
        or account_1510_state not in {"CONFIRMED", "TRACKING", "FINISHED"}
    ):
        raise UnsafeError("account_1560_requires_identified_account_1510")


def _new_record() -> dict[str, Any]:
    return {
        "state": "PLANNED",
        "attempts": 0,
        "baseline_orders": [],
        "candidate_orders": [],
        "order_number": None,
        "filename": None,
        "filename_kind": "NONE",
        "visible_status": None,
    }


def _normalize_company(value: str) -> str:
    value = value.strip()
    if COMPANY_CODE.fullmatch(value) is None:
        raise InputError("invalid_company_code")
    return value


def _normalize_period(value: str) -> str:
    value = value.strip()
    if not _valid_period(value):
        raise InputError("invalid_period")
    return value


def _normalize_orders(values: Sequence[str], reason: str) -> list[str]:
    normalized = [value.strip() for value in values]
    if any(not _safe_order(value) for value in normalized):
        raise InputError(reason)
    if len(normalized) != len(set(normalized)):
        raise InputError(reason)
    return normalized


def _normalize_filename(value: str) -> str:
    value = value.strip()
    if not _safe_filename(value):
        raise InputError("invalid_filename")
    return value


def _normalize_status(value: str) -> str:
    value = value.strip()
    if not _safe_status(value):
        raise InputError("invalid_visible_status")
    return value


def _normalize_reason(value: str) -> str:
    value = value.strip()
    if MACHINE_REASON.fullmatch(value) is None:
        raise InputError("invalid_machine_reason")
    return value


def _require_active(data: dict[str, Any]) -> None:
    if data["run_state"] != "ACTIVE":
        raise UnsafeError("run_not_active")
    if any(record["state"] == "UNKNOWN" for record in data["records"].values()):
        raise UnsafeError("unknown_record_requires_blocked_run")


Mutation = Callable[[dict[str, Any]], dict[str, Any]]


def _update_manifest(path_value: str, mutation: Mutation) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_value).expanduser().absolute()
    with _exclusive_run_lock(path.parent):
        path, current, fingerprint = _load_manifest(path_value)
        updated = copy.deepcopy(current)
        result = mutation(updated)
        _validate_manifest(updated)
        _atomic_write(path, updated, expected=fingerprint)
        return updated, result


def _record_result(command: str, key: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "key": key,
        "run_state": data["run_state"],
        "record": data["records"][key],
    }


def _command_create(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    company = _normalize_company(args.company)
    period = _normalize_period(args.period)
    directory = _prepare_directory(args.directory)
    path = directory / MANIFEST_NAME
    with _exclusive_run_lock(directory):
        if os.path.lexists(path):
            raise UnsafeError("manifest_already_exists")
        data = {
            "schema_version": SCHEMA_VERSION,
            "run_state": "ACTIVE",
            "company": company,
            "period": period,
            "blocked_reason": None,
            "records": {key: _new_record() for key in RECORD_KEYS},
        }
        _atomic_write(path, data, expected=None)
    return {
        "ok": True,
        "command": "create",
        "manifest": str(path),
        "run_state": "ACTIVE",
        "record_keys": list(RECORD_KEYS),
    }, 0


def _command_show(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    requested = Path(args.manifest).expanduser().absolute()
    with _exclusive_run_lock(requested.parent):
        path, data, _ = _load_manifest(args.manifest)
    return {
        "ok": True,
        "command": "show",
        "manifest_path": str(path),
        "manifest": data,
    }, 0


def _command_begin(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    baseline = _normalize_orders(args.baseline, "invalid_baseline_orders")

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        record = data["records"][args.key]
        if record["state"] not in {"PLANNED", "RETRY_ALLOWED"}:
            raise UnsafeError("invalid_begin_transition")
        if args.key == "1510" and data["records"]["raw_balance"]["state"] != "FINISHED":
            raise UnsafeError("raw_balance_must_finish_first")
        if args.key == "1560" and data["records"]["1510"]["state"] not in {
            "CONFIRMED",
            "TRACKING",
            "FINISHED",
        }:
            raise UnsafeError("account_1510_must_be_identified_first")
        if record["attempts"] >= 2:
            raise UnsafeError("maximum_attempts_reached")
        if record["state"] == "RETRY_ALLOWED" and baseline != record["baseline_orders"]:
            raise UnsafeError("retry_baseline_changed")
        record["baseline_orders"] = baseline
        record["attempts"] += 1
        record["state"] = "SUBMITTING"
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return _record_result("begin", args.key, updated), 0


def _command_confirm(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    order_number = _normalize_orders([args.order_number], "invalid_order_number")[0]

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        record = data["records"][args.key]
        if record["state"] != "SUBMITTING":
            raise UnsafeError("invalid_confirm_transition")
        if order_number in record["baseline_orders"]:
            raise UnsafeError("confirmed_order_was_in_baseline")
        for other_key, other in data["records"].items():
            if other_key != args.key and other["order_number"] == order_number:
                raise UnsafeError("duplicate_order_number")
        record["order_number"] = order_number
        record["state"] = "CONFIRMED"
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return _record_result("confirm", args.key, updated), 0


def _command_retry_allowed(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    observed = _normalize_orders(args.observed, "invalid_observed_orders")
    submission_observed = args.submission_state_observed == "true"

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        record = data["records"][args.key]
        if record["state"] != "SUBMITTING" or record["attempts"] != 1:
            raise UnsafeError("invalid_retry_transition")
        observed_set = set(observed)
        baseline_set = set(record["baseline_orders"])
        new_candidates = sorted(observed_set - baseline_set)
        baseline_missing = not baseline_set.issubset(observed_set)
        if new_candidates or baseline_missing or submission_observed:
            record["state"] = "UNKNOWN"
            record["candidate_orders"] = new_candidates
            data["run_state"] = "BLOCKED"
            data["blocked_reason"] = "submission_outcome_unknown"
            return {"unknown": True}
        record["state"] = "RETRY_ALLOWED"
        return {"unknown": False}

    updated, result = _update_manifest(args.manifest, mutate)
    if result["unknown"]:
        return {
            "ok": False,
            "command": "retry-allowed",
            "error": "submission_outcome_unknown",
            "key": args.key,
            "run_state": updated["run_state"],
            "record_state": "UNKNOWN",
        }, 3
    return _record_result("retry-allowed", args.key, updated), 0


def _command_track(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.filename is None and args.visible_status is None:
        raise InputError("track_requires_update")
    if (args.filename is None) != (args.filename_kind is None):
        raise InputError("filename_and_kind_required_together")
    filename = _normalize_filename(args.filename) if args.filename is not None else None
    visible_status = (
        _normalize_status(args.visible_status)
        if args.visible_status is not None
        else None
    )

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        record = data["records"][args.key]
        if record["state"] not in {"CONFIRMED", "TRACKING"}:
            raise UnsafeError("invalid_track_transition")
        if filename is not None:
            if record["filename"] is not None and record["filename"] != filename:
                raise UnsafeError("filename_identity_changed")
            if (
                record["filename_kind"] != "NONE"
                and record["filename_kind"] != args.filename_kind
            ):
                raise UnsafeError("filename_kind_changed")
            record["filename"] = filename
            record["filename_kind"] = args.filename_kind
        if visible_status is not None:
            record["visible_status"] = visible_status
        record["state"] = "TRACKING"
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return _record_result("track", args.key, updated), 0


def _command_finish_order(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        record = data["records"][args.key]
        if record["state"] not in {"CONFIRMED", "TRACKING"}:
            raise UnsafeError("invalid_finish_transition")
        if (
            record["order_number"] is None
            or record["filename"] is None
            or record["visible_status"] != "Ferdig"
        ):
            raise UnsafeError("order_not_ready_to_finish")
        record["state"] = "FINISHED"
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return _record_result("finish-order", args.key, updated), 0


def _command_complete(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        if any(record["state"] != "FINISHED" for record in data["records"].values()):
            raise UnsafeError("orders_not_all_finished")
        data["run_state"] = "COMPLETE"
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return {
        "ok": True,
        "command": "complete",
        "run_state": updated["run_state"],
    }, 0


def _command_mark_unknown(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    reason = _normalize_reason(args.reason)
    observed = _normalize_orders(args.observed, "invalid_observed_orders")

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _require_active(data)
        record = data["records"][args.key]
        if record["state"] not in {"SUBMITTING", "RETRY_ALLOWED"}:
            raise UnsafeError("invalid_mark_unknown_transition")
        record["state"] = "UNKNOWN"
        record["candidate_orders"] = sorted(
            set(observed) - set(record["baseline_orders"])
        )
        data["run_state"] = "BLOCKED"
        data["blocked_reason"] = reason
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return {
        "ok": False,
        "command": "mark-unknown",
        "error": "submission_outcome_unknown",
        "key": args.key,
        "run_state": updated["run_state"],
        "record_state": updated["records"][args.key]["state"],
        "reason": updated["blocked_reason"],
    }, 3


def _command_resume(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        if data["run_state"] != "BLOCKED":
            raise UnsafeError("run_not_blocked")
        states = {record["state"] for record in data["records"].values()}
        if "UNKNOWN" in states:
            raise UnsafeError("unknown_submission_cannot_resume")
        if "SUBMITTING" in states:
            raise UnsafeError("submitting_record_cannot_resume")
        data["run_state"] = "ACTIVE"
        data["blocked_reason"] = None
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return {
        "ok": True,
        "command": "resume",
        "run_state": updated["run_state"],
    }, 0


def _command_block(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    reason = _normalize_reason(args.reason)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        if data["run_state"] == "COMPLETE":
            raise UnsafeError("complete_run_cannot_be_blocked")
        if any(
            record["state"] == "SUBMITTING" for record in data["records"].values()
        ):
            raise UnsafeError("submitting_order_must_be_marked_unknown")
        if data["run_state"] == "BLOCKED" and data["blocked_reason"] != reason:
            raise UnsafeError("blocked_reason_cannot_change")
        data["run_state"] = "BLOCKED"
        data["blocked_reason"] = reason
        return {}

    updated, _ = _update_manifest(args.manifest, mutate)
    return {
        "ok": True,
        "command": "block",
        "run_state": updated["run_state"],
        "reason": updated["blocked_reason"],
    }, 0


def _command_cleanup(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    requested = Path(args.manifest).expanduser().absolute()
    if requested.name != MANIFEST_NAME:
        raise UnsafeError("unexpected_manifest_filename")
    with _exclusive_run_lock(requested.parent) as lock_path:
        path, data, expected = _load_manifest(str(requested))
        if data["run_state"] != "COMPLETE":
            raise UnsafeError("cleanup_requires_complete_run")

        current = _manifest_stat(path)
        if _fingerprint(current) != expected:
            raise UnsafeError("manifest_changed_during_cleanup")
        os.unlink(path)
        _fsync_directory(path.parent)

    try:
        lock_stat = os.lstat(lock_path)
        if _is_link_or_reparse(lock_stat) or not stat.S_ISREG(lock_stat.st_mode):
            raise UnsafeError("unsafe_manifest_lock")
        _require_owned(lock_stat)
        os.unlink(lock_path)
    except FileNotFoundError:
        pass

    directory_removed = False
    try:
        os.rmdir(path.parent)
    except OSError:
        # The manifest is the only file owned by this helper.  Preserve any
        # unrelated entries rather than guessing whether they are disposable.
        _fsync_directory(path.parent)
    else:
        directory_removed = True
        _fsync_directory(path.parent.parent)

    return {
        "ok": True,
        "command": "cleanup",
        "manifest_removed": True,
        "directory_removed": directory_removed,
    }, 0


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="run_manifest.py")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("--company", required=True)
    create.add_argument("--period", required=True)
    create.add_argument("--directory")
    create.set_defaults(handler=_command_create)

    show = commands.add_parser("show")
    show.add_argument("--manifest", required=True)
    show.set_defaults(handler=_command_show)

    begin = commands.add_parser("begin")
    begin.add_argument("--manifest", required=True)
    begin.add_argument("--key", choices=RECORD_KEYS, required=True)
    begin.add_argument("--baseline", nargs="*", default=[])
    begin.set_defaults(handler=_command_begin)

    confirm = commands.add_parser("confirm")
    confirm.add_argument("--manifest", required=True)
    confirm.add_argument("--key", choices=RECORD_KEYS, required=True)
    confirm.add_argument("--order-number", required=True)
    confirm.set_defaults(handler=_command_confirm)

    retry = commands.add_parser("retry-allowed")
    retry.add_argument("--manifest", required=True)
    retry.add_argument("--key", choices=RECORD_KEYS, required=True)
    retry.add_argument("--observed", nargs="*", default=[])
    retry.add_argument(
        "--submission-state-observed",
        choices=("true", "false"),
        required=True,
    )
    retry.set_defaults(handler=_command_retry_allowed)

    track = commands.add_parser("track")
    track.add_argument("--manifest", required=True)
    track.add_argument("--key", choices=RECORD_KEYS, required=True)
    track.add_argument("--filename")
    track.add_argument("--filename-kind", choices=("FULL", "PREFIX"))
    track.add_argument("--visible-status")
    track.set_defaults(handler=_command_track)

    finish = commands.add_parser("finish-order")
    finish.add_argument("--manifest", required=True)
    finish.add_argument("--key", choices=RECORD_KEYS, required=True)
    finish.set_defaults(handler=_command_finish_order)

    complete = commands.add_parser("complete")
    complete.add_argument("--manifest", required=True)
    complete.set_defaults(handler=_command_complete)

    unknown = commands.add_parser("mark-unknown")
    unknown.add_argument("--manifest", required=True)
    unknown.add_argument("--key", choices=RECORD_KEYS, required=True)
    unknown.add_argument("--reason", required=True)
    unknown.add_argument("--observed", nargs="*", default=[])
    unknown.set_defaults(handler=_command_mark_unknown)

    resume = commands.add_parser("resume")
    resume.add_argument("--manifest", required=True)
    resume.set_defaults(handler=_command_resume)

    block = commands.add_parser("block")
    block.add_argument("--manifest", required=True)
    block.add_argument("--reason", required=True)
    block.set_defaults(handler=_command_block)

    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--manifest", required=True)
    cleanup.set_defaults(handler=_command_cleanup)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        payload, exit_code = args.handler(args)
    except ManifestError as error:
        payload = {"ok": False, "error": error.reason}
        exit_code = error.exit_code
    except OSError:
        payload = {"ok": False, "error": "filesystem_operation_failed"}
        exit_code = 3
    except Exception:
        # Keep malformed or adversarial local input from producing a traceback
        # containing filesystem details. Expected failures use ManifestError.
        payload = {"ok": False, "error": "internal_validation_failure"}
        exit_code = 3
    _emit(payload)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
