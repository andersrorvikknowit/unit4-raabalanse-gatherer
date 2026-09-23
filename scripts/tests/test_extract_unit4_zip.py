from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import extract_unit4_zip  # noqa: E402


VALID_ENTRIES = {
    "gl09a_123.xlsx": b"raw balance",
    "cu05_124.xlsx": b"account 1510",
    "cu05_125.xlsx": b"account 1560",
    "supplier_126.xlsx": b"account 2440",
    "supplier_127.xlsx": b"account 2444",
    "supplier_128.xlsx": b"account 2460",
}
CONTROLLED_TARGETS = [
    "raw-balance.xlsx",
    "account-1510.xlsx",
    "account-1560.xlsx",
    "account-2440.xlsx",
    "account-2444.xlsx",
    "account-2460.xlsx",
]


def padded_entries(
    entries: list[tuple[zipfile.ZipInfo | str, bytes]],
) -> list[tuple[zipfile.ZipInfo | str, bytes]]:
    padded = list(entries)
    while len(padded) < extract_unit4_zip.EXPECTED_ENTRY_COUNT:
        padded.append((f"filler-{len(padded)}.xlsx", b"safe"))
    return padded


class ExtractUnit4ZipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        os.chmod(self.root, 0o700)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_zip(
        self, entries: dict[str, bytes] | list[tuple[zipfile.ZipInfo | str, bytes]]
    ) -> Path:
        archive_path = self.root / "Rapporter.zip"
        items = entries.items() if isinstance(entries, dict) else entries
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(
                archive_path, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for name_or_info, content in items:
                    archive.writestr(name_or_info, content)
        return archive_path

    def _run(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = extract_unit4_zip.main(argv)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        return exit_code, json.loads(lines[0])

    def test_happy_inspect_and_extract(self) -> None:
        archive = self._write_zip(VALID_ENTRIES)

        code, inspected = self._run(["inspect", "--zip", str(archive)])
        self.assertEqual(code, 0)
        self.assertEqual(inspected["status"], "SAFE")
        self.assertEqual(
            inspected["entry_count"], extract_unit4_zip.EXPECTED_ENTRY_COUNT
        )

        output_dir = self.root / "extracted"
        output_dir.mkdir(mode=0o700)
        args = ["extract", "--zip", str(archive), "--output-dir", str(output_dir)]
        for entry, target in zip(VALID_ENTRIES, CONTROLLED_TARGETS):
            args.extend(["--entry", entry, "--target", target])

        code, extracted = self._run(args)
        self.assertEqual(code, 0)
        self.assertEqual(extracted["status"], "EXTRACTED")
        for entry, target in zip(VALID_ENTRIES, CONTROLLED_TARGETS):
            self.assertEqual((output_dir / target).read_bytes(), VALID_ENTRIES[entry])
            self.assertEqual(stat.S_IMODE((output_dir / target).stat().st_mode), 0o600)

    def test_rejects_traversal_absolute_drive_and_unc_paths(self) -> None:
        unsafe_names = [
            "../evil.xlsx",
            "/absolute.xlsx",
            r"C:\evil.xlsx",
            r"\\server\share\evil.xlsx",
        ]
        for index, unsafe_name in enumerate(unsafe_names):
            with self.subTest(name=unsafe_name):
                archive = self.root / f"unsafe-{index}.zip"
                with zipfile.ZipFile(archive, mode="w") as zip_file:
                    for name, content in padded_entries([(unsafe_name, b"bad")]):
                        zip_file.writestr(name, content)
                code, result = self._run(["inspect", "--zip", str(archive)])
                self.assertEqual(code, 3)
                self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_extra_entry(self) -> None:
        archive = self._write_zip(
            list(VALID_ENTRIES.items()) + [("unexpected.xlsx", b"extra")]
        )
        code, result = self._run(["inspect", "--zip", str(archive)])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_exact_duplicate_and_case_collision(self) -> None:
        scenarios = [
            padded_entries([
                ("same.xlsx", b"one"),
                ("same.xlsx", b"two"),
            ]),
            padded_entries([
                ("Report.xlsx", b"one"),
                ("report.XLSX", b"two"),
            ]),
            padded_entries([
                ("caf\u00e9.xlsx", b"one"),
                ("cafe\u0301.xlsx", b"two"),
            ]),
        ]
        for index, entries in enumerate(scenarios):
            with self.subTest(index=index):
                archive = self.root / f"collision-{index}.zip"
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(archive, mode="w") as zip_file:
                        for name, content in entries:
                            zip_file.writestr(name, content)
                code, result = self._run(["inspect", "--zip", str(archive)])
                self.assertEqual(code, 3)
                self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_control_characters_in_entry_names(self) -> None:
        for index, invalid_character in enumerate(("\n", "\u0085", "\u2028")):
            with self.subTest(character=repr(invalid_character)):
                archive = self.root / f"control-{index}.zip"
                with zipfile.ZipFile(archive, mode="w") as zip_file:
                    for name, content in padded_entries(
                        [(f"unsafe{invalid_character}name.xlsx", b"bad")]
                    ):
                        zip_file.writestr(name, content)

                code, result = self._run(["inspect", "--zip", str(archive)])
                self.assertEqual(code, 3)
                self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_cli_option_like_entry_name(self) -> None:
        archive = self._write_zip(
            padded_entries([("--entry.xlsx", b"bad")])
        )

        code, result = self._run(["inspect", "--zip", str(archive)])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_symbolic_link_mode(self) -> None:
        link = zipfile.ZipInfo("linked.xlsx")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self._write_zip(
            padded_entries([
                (link, b"target.xlsx"),
            ])
        )

        code, result = self._run(["inspect", "--zip", str(archive)])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "BLOCKED")

    def test_rejects_high_compression_ratio(self) -> None:
        archive = self._write_zip(
            padded_entries(
                [("compressed.xlsx", b"0" * (11 * 1024 * 1024))]
            )
        )

        code, result = self._run(["inspect", "--zip", str(archive)])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "BLOCKED")

    def test_overwrite_refusal_leaves_existing_and_creates_nothing_else(self) -> None:
        archive = self._write_zip(VALID_ENTRIES)
        output_dir = self.root / "extracted"
        output_dir.mkdir(mode=0o700)
        existing = output_dir / "account-1510.xlsx"
        existing.write_bytes(b"keep me")
        os.chmod(existing, 0o600)

        args = ["extract", "--zip", str(archive), "--output-dir", str(output_dir)]
        for entry, target in zip(VALID_ENTRIES, CONTROLLED_TARGETS):
            args.extend(["--entry", entry, "--target", target])
        code, result = self._run(args)

        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(existing.read_bytes(), b"keep me")
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), [existing.name])

    def test_windows_path_extracts_with_controlled_basenames(self) -> None:
        archive = self._write_zip(VALID_ENTRIES)
        output_dir = self.root / "windows-extracted"
        output_dir.mkdir(mode=0o700)
        args = ["extract", "--zip", str(archive), "--output-dir", str(output_dir)]
        for entry, target in zip(VALID_ENTRIES, CONTROLLED_TARGETS):
            args.extend(["--entry", entry, "--target", target])

        with mock.patch.object(extract_unit4_zip, "_is_windows", return_value=True):
            code, extracted = self._run(args)

        self.assertEqual(code, 0)
        self.assertEqual(extracted["status"], "EXTRACTED")
        for entry, target in zip(VALID_ENTRIES, CONTROLLED_TARGETS):
            self.assertEqual((output_dir / target).read_bytes(), VALID_ENTRIES[entry])

    def test_windows_path_refuses_existing_target_without_partial_files(self) -> None:
        archive = self._write_zip(VALID_ENTRIES)
        output_dir = self.root / "windows-extracted"
        output_dir.mkdir(mode=0o700)
        existing = output_dir / "account-1510.xlsx"
        existing.write_bytes(b"keep me")
        args = ["extract", "--zip", str(archive), "--output-dir", str(output_dir)]
        for entry, target in zip(VALID_ENTRIES, CONTROLLED_TARGETS):
            args.extend(["--entry", entry, "--target", target])

        with mock.patch.object(extract_unit4_zip, "_is_windows", return_value=True):
            code, result = self._run(args)

        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(existing.read_bytes(), b"keep me")
        self.assertEqual(sorted(path.name for path in output_dir.iterdir()), [existing.name])

    def test_reparse_point_detection_uses_windows_file_attributes(self) -> None:
        fake_stat = mock.Mock(st_file_attributes=0x400)
        self.assertTrue(extract_unit4_zip._is_reparse_point(fake_stat))


if __name__ == "__main__":
    unittest.main()
