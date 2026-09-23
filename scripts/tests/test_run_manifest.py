from contextlib import redirect_stdout
from io import StringIO
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

import importlib.util


SCRIPT = Path(__file__).parents[1] / "run_manifest.py"
SPEC = importlib.util.spec_from_file_location("run_manifest", SCRIPT)
assert SPEC and SPEC.loader
run_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_manifest)


class RunManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "run"
        created = self.run_command(
            "create",
            "--company",
            "999999",
            "--period",
            "209912",
            "--directory",
            str(self.directory),
        )
        self.assertEqual(created.returncode, 0, created.stdout)
        self.created = json.loads(created.stdout)
        self.manifest = Path(self.created["manifest"])

    def run_command(self, *arguments):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stderr, "")
        json.loads(result.stdout)
        return result

    def run_main(self, *arguments):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = run_manifest.main(list(arguments))
        payload = json.loads(output.getvalue())
        return exit_code, payload

    def show(self):
        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stdout)["manifest"]

    def begin(self, key, *baseline):
        return self.run_command(
            "begin",
            "--manifest",
            str(self.manifest),
            "--key",
            key,
            "--baseline",
            *baseline,
        )

    def confirm(self, key, order_number):
        return self.run_command(
            "confirm",
            "--manifest",
            str(self.manifest),
            "--key",
            key,
            "--order-number",
            order_number,
        )

    def finish(self, key, order_number):
        self.assertEqual(self.begin(key).returncode, 0)
        self.assertEqual(self.confirm(key, order_number).returncode, 0)
        tracked = self.run_command(
            "track",
            "--manifest",
            str(self.manifest),
            "--key",
            key,
            "--filename",
            f"report-{order_number}.xlsx",
            "--filename-kind",
            "FULL",
            "--visible-status",
            "Ferdig",
        )
        self.assertEqual(tracked.returncode, 0, tracked.stdout)
        finished = self.run_command(
            "finish-order",
            "--manifest",
            str(self.manifest),
            "--key",
            key,
        )
        self.assertEqual(finished.returncode, 0, finished.stdout)

    def test_create_uses_private_permissions_and_exact_records(self):
        self.assertEqual(self.manifest.name, "run-manifest.json")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.directory).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(self.manifest).st_mode), 0o600)
        data = self.show()
        self.assertEqual(set(data["records"]), {"raw_balance", "1510", "1560"})
        self.assertTrue(all(record["state"] == "PLANNED" for record in data["records"].values()))

    def test_create_defaults_to_a_private_unique_temp_directory(self):
        result = self.run_command(
            "create",
            "--company",
            "999999",
            "--period",
            "209912",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        manifest = Path(json.loads(result.stdout)["manifest"])
        directory = manifest.parent
        try:
            self.assertEqual(manifest.name, "run-manifest.json")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(directory).st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(os.stat(manifest).st_mode), 0o600)
            self.assertNotEqual(directory, self.directory)
        finally:
            if manifest.exists():
                manifest.unlink()
            lock = directory / run_manifest.LOCK_NAME
            if lock.exists():
                lock.unlink()
            if directory.exists():
                directory.rmdir()

    def test_create_rejects_invalid_company_codes(self):
        for index, company in enumerate(("A2", "1", "12345678901")):
            with self.subTest(company=company):
                result = self.run_command(
                    "create",
                    "--company",
                    company,
                    "--period",
                    "209912",
                    "--directory",
                    str(self.root / f"invalid-{index}"),
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["error"], "invalid_company_code")

    def test_create_does_not_reuse_or_chmod_existing_directory(self):
        existing = self.root / "existing"
        existing.mkdir(mode=0o755)
        if os.name != "nt":
            os.chmod(existing, 0o755)
        marker = existing / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        result = self.run_command(
            "create",
            "--company",
            "999999",
            "--period",
            "209912",
            "--directory",
            str(existing),
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "manifest_directory_already_exists",
        )
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(existing).st_mode), 0o755)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_invalid_transition_is_atomic(self):
        self.assertEqual(self.begin("raw_balance", "10", "11").returncode, 0)
        before = self.manifest.read_bytes()
        invalid = self.begin("raw_balance", "10", "11")
        self.assertEqual(invalid.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(json.loads(invalid.stdout)["error"], "invalid_begin_transition")

    def test_concurrent_begin_is_serialized_and_only_one_succeeds(self):
        command = [
            sys.executable,
            str(SCRIPT),
            "begin",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--baseline",
            "10",
        ]
        processes = []
        try:
            with run_manifest._exclusive_run_lock(self.directory):
                processes = [
                    subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    for _ in range(2)
                ]
                time.sleep(0.2)
                self.assertTrue(all(process.poll() is None for process in processes))

            results = [process.communicate(timeout=10) for process in processes]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)

        self.assertEqual(sorted(process.returncode for process in processes), [0, 3])
        payloads = []
        for stdout, stderr in results:
            self.assertEqual(stderr, "")
            payloads.append(json.loads(stdout))
        self.assertEqual(
            [payload["error"] for payload in payloads if not payload["ok"]],
            ["invalid_begin_transition"],
        )
        record = self.show()["records"]["raw_balance"]
        self.assertEqual(record["state"], "SUBMITTING")
        self.assertEqual(record["attempts"], 1)

    def test_replace_failure_leaves_manifest_unchanged(self):
        before = self.manifest.read_bytes()
        with mock.patch.object(
            run_manifest.os,
            "replace",
            side_effect=OSError("simulated replace failure"),
        ):
            exit_code, payload = self.run_main(
                "begin",
                "--manifest",
                str(self.manifest),
                "--key",
                "raw_balance",
                "--baseline",
                "10",
            )
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["error"], "filesystem_operation_failed")
        self.assertEqual(self.manifest.read_bytes(), before)
        leftovers = list(self.directory.glob(".run-manifest.json.*.tmp"))
        self.assertEqual(leftovers, [])

    def test_directory_fsync_failure_is_reported_after_safe_transition(self):
        with mock.patch.object(
            run_manifest,
            "_fsync_directory",
            side_effect=run_manifest.UnsafeError("directory_fsync_failed"),
        ):
            exit_code, payload = self.run_main(
                "begin",
                "--manifest",
                str(self.manifest),
                "--key",
                "raw_balance",
                "--baseline",
                "10",
            )
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["error"], "directory_fsync_failed")
        record = self.show()["records"]["raw_balance"]
        self.assertEqual(record["state"], "SUBMITTING")
        self.assertEqual(record["attempts"], 1)

    @unittest.skipIf(os.name == "nt", "directory fsync is POSIX-only")
    def test_directory_fsync_open_and_sync_errors_are_not_suppressed(self):
        with mock.patch.object(
            run_manifest.os,
            "open",
            side_effect=OSError("simulated directory open failure"),
        ):
            with self.assertRaisesRegex(
                run_manifest.UnsafeError,
                "directory_fsync_open_failed",
            ):
                run_manifest._fsync_directory(self.directory)

        with mock.patch.object(
            run_manifest.os,
            "fsync",
            side_effect=OSError("simulated directory sync failure"),
        ):
            with self.assertRaisesRegex(
                run_manifest.UnsafeError,
                "directory_fsync_failed",
            ):
                run_manifest._fsync_directory(self.directory)

    def test_oversized_transition_is_rejected_without_stranding_manifest(self):
        baseline = [f"O{index:04d}{'x' * 110}" for index in range(600)]
        before = self.manifest.read_bytes()
        result = self.begin("raw_balance", *baseline)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["error"], "manifest_too_large")
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(self.show()["records"]["raw_balance"]["state"], "PLANNED")

    def test_maximum_two_attempts(self):
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        retry = self.run_command(
            "retry-allowed",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--observed",
            "10",
            "--submission-state-observed",
            "false",
        )
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        before = self.manifest.read_bytes()
        third = self.begin("raw_balance", "10")
        self.assertEqual(third.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)
        record = self.show()["records"]["raw_balance"]
        self.assertEqual(record["attempts"], 2)
        self.assertEqual(record["state"], "SUBMITTING")

    def test_new_candidate_forces_unknown(self):
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        result = self.run_command(
            "retry-allowed",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--observed",
            "10",
            "12",
            "--submission-state-observed",
            "false",
        )
        self.assertEqual(result.returncode, 3)
        data = self.show()
        self.assertEqual(data["records"]["raw_balance"]["state"], "UNKNOWN")
        self.assertEqual(data["records"]["raw_balance"]["candidate_orders"], ["12"])
        self.assertEqual(data["run_state"], "BLOCKED")
        self.assertEqual(data["blocked_reason"], "submission_outcome_unknown")

    def test_observed_submission_state_forces_unknown(self):
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        result = self.run_command(
            "retry-allowed",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--observed",
            "10",
            "--submission-state-observed",
            "true",
        )
        self.assertEqual(result.returncode, 3)
        data = self.show()
        self.assertEqual(data["records"]["raw_balance"]["state"], "UNKNOWN")
        self.assertEqual(data["records"]["raw_balance"]["candidate_orders"], [])
        self.assertEqual(data["run_state"], "BLOCKED")

    def test_incomplete_post_click_observation_forces_unknown(self):
        self.assertEqual(self.begin("raw_balance", "10", "11").returncode, 0)
        result = self.run_command(
            "retry-allowed",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--observed",
            "10",
            "--submission-state-observed",
            "false",
        )
        self.assertEqual(result.returncode, 3)
        data = self.show()
        self.assertEqual(data["run_state"], "BLOCKED")
        self.assertEqual(data["records"]["raw_balance"]["state"], "UNKNOWN")
        self.assertEqual(data["records"]["raw_balance"]["candidate_orders"], [])

    def test_second_attempt_without_confirmation_is_marked_unknown(self):
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        retry = self.run_command(
            "retry-allowed",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--observed",
            "10",
            "--submission-state-observed",
            "false",
        )
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        unknown = self.run_command(
            "mark-unknown",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--reason",
            "confirmation_missing_after_second_attempt",
        )
        self.assertEqual(unknown.returncode, 3)
        data = self.show()
        self.assertEqual(data["run_state"], "BLOCKED")
        self.assertEqual(data["records"]["raw_balance"]["state"], "UNKNOWN")
        self.assertEqual(data["records"]["raw_balance"]["attempts"], 2)
        self.assertEqual(data["records"]["raw_balance"]["candidate_orders"], [])

    def test_mark_unknown_preserves_candidates_but_cannot_confirm_them(self):
        self.assertEqual(self.begin("raw_balance", "10").returncode, 0)
        unknown = self.run_command(
            "mark-unknown",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--reason",
            "confirmation_missing",
            "--observed",
            "10",
            "12",
            "11",
        )
        self.assertEqual(unknown.returncode, 3)
        data = self.show()
        self.assertEqual(
            data["records"]["raw_balance"]["candidate_orders"],
            ["11", "12"],
        )
        before = self.manifest.read_bytes()
        confirm = self.confirm("raw_balance", "11")
        self.assertEqual(confirm.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_order_numbers_must_be_unique(self):
        self.finish("raw_balance", "1001")
        self.assertEqual(self.begin("1510").returncode, 0)
        before = self.manifest.read_bytes()
        duplicate = self.confirm("1510", "1001")
        self.assertEqual(duplicate.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(json.loads(duplicate.stdout)["error"], "duplicate_order_number")

    def test_complete_requires_all_orders_finished(self):
        self.finish("raw_balance", "1001")
        incomplete = self.run_command("complete", "--manifest", str(self.manifest))
        self.assertEqual(incomplete.returncode, 3)
        self.finish("1510", "1002")
        self.finish("1560", "1003")
        completed = self.run_command("complete", "--manifest", str(self.manifest))
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(self.show()["run_state"], "COMPLETE")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.manifest).st_mode), 0o600)

    def test_begin_enforces_report_sequence(self):
        before = self.manifest.read_bytes()
        early_1510 = self.begin("1510")
        self.assertEqual(early_1510.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.finish("raw_balance", "1001")
        before = self.manifest.read_bytes()
        early_1560 = self.begin("1560")
        self.assertEqual(early_1560.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(self.begin("1510").returncode, 0)
        self.assertEqual(self.confirm("1510", "1002").returncode, 0)
        self.assertEqual(self.begin("1560").returncode, 0)

    def test_schema_rejects_1510_state_without_finished_raw_balance(self):
        self.finish("raw_balance", "1001")
        self.assertEqual(self.begin("1510").returncode, 0)
        self.assertEqual(self.confirm("1510", "1002").returncode, 0)
        data = self.show()
        data["records"]["raw_balance"] = run_manifest._new_record()
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)

        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "account_1510_requires_finished_raw_balance",
        )

    def test_schema_rejects_1560_state_without_identified_1510(self):
        self.finish("raw_balance", "1001")
        self.assertEqual(self.begin("1510").returncode, 0)
        self.assertEqual(self.confirm("1510", "1002").returncode, 0)
        self.assertEqual(self.begin("1560").returncode, 0)
        self.assertEqual(self.confirm("1560", "1003").returncode, 0)
        data = self.show()
        data["records"]["1510"] = run_manifest._new_record()
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)

        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "account_1560_requires_identified_account_1510",
        )

    def test_filename_kind_is_required_and_immutable(self):
        self.assertEqual(self.begin("raw_balance").returncode, 0)
        self.assertEqual(self.confirm("raw_balance", "1001").returncode, 0)
        missing_kind = self.run_command(
            "track",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--filename",
            "raw.xlsx",
        )
        self.assertEqual(missing_kind.returncode, 1)
        tracked = self.run_command(
            "track",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--filename",
            "raw.xlsx",
            "--filename-kind",
            "PREFIX",
        )
        self.assertEqual(tracked.returncode, 0, tracked.stdout)
        before = self.manifest.read_bytes()
        changed = self.run_command(
            "track",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--filename",
            "raw.xlsx",
            "--filename-kind",
            "FULL",
        )
        self.assertEqual(changed.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_track_rejects_unicode_control_format_and_line_separators(self):
        self.assertEqual(self.begin("raw_balance").returncode, 0)
        self.assertEqual(self.confirm("raw_balance", "1001").returncode, 0)
        before = self.manifest.read_bytes()

        unsafe_characters = ("\u0085", "\u2028", "\u2029", "\u202e")
        for character in unsafe_characters:
            with self.subTest(field="filename", character=repr(character)):
                result = self.run_command(
                    "track",
                    "--manifest",
                    str(self.manifest),
                    "--key",
                    "raw_balance",
                    "--filename",
                    f"report{character}spoof.xlsx",
                    "--filename-kind",
                    "FULL",
                )
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(json.loads(result.stdout)["error"], "invalid_filename")
                self.assertEqual(self.manifest.read_bytes(), before)

            with self.subTest(field="visible_status", character=repr(character)):
                result = self.run_command(
                    "track",
                    "--manifest",
                    str(self.manifest),
                    "--key",
                    "raw_balance",
                    "--visible-status",
                    f"Fer{character}dig",
                )
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["error"],
                    "invalid_visible_status",
                )
                self.assertEqual(self.manifest.read_bytes(), before)

    def test_manifest_rejects_escaped_lone_surrogate(self):
        self.assertEqual(self.begin("raw_balance").returncode, 0)
        self.assertEqual(self.confirm("raw_balance", "1001").returncode, 0)
        data = self.show()
        record = data["records"]["raw_balance"]
        record["state"] = "TRACKING"
        record["filename"] = "report-\ud800.xlsx"
        record["filename_kind"] = "FULL"
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)

        result = self.run_command("show", "--manifest", str(self.manifest))

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(json.loads(result.stdout)["error"], "invalid_filename")

    def test_resume_allows_recoverable_block_but_not_unknown(self):
        blocked = self.run_command(
            "block",
            "--manifest",
            str(self.manifest),
            "--reason",
            "browser_disconnected",
        )
        self.assertEqual(blocked.returncode, 0, blocked.stdout)
        resumed = self.run_command("resume", "--manifest", str(self.manifest))
        self.assertEqual(resumed.returncode, 0, resumed.stdout)
        self.assertEqual(self.show()["run_state"], "ACTIVE")

        self.assertEqual(self.begin("raw_balance").returncode, 0)
        unknown = self.run_command(
            "mark-unknown",
            "--manifest",
            str(self.manifest),
            "--key",
            "raw_balance",
            "--reason",
            "confirmation_missing",
        )
        self.assertEqual(unknown.returncode, 3)
        before = self.manifest.read_bytes()
        refused = self.run_command("resume", "--manifest", str(self.manifest))
        self.assertEqual(refused.returncode, 3)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_cleanup_refuses_active_and_blocked_runs(self):
        active = self.run_command("cleanup", "--manifest", str(self.manifest))
        self.assertEqual(active.returncode, 3)
        self.assertTrue(self.manifest.exists())
        blocked = self.run_command(
            "block",
            "--manifest",
            str(self.manifest),
            "--reason",
            "browser_disconnected",
        )
        self.assertEqual(blocked.returncode, 0, blocked.stdout)
        refused = self.run_command("cleanup", "--manifest", str(self.manifest))
        self.assertEqual(refused.returncode, 3)
        self.assertTrue(self.manifest.exists())

    def test_generic_block_refuses_submitting_record(self):
        self.assertEqual(self.begin("raw_balance").returncode, 0)
        before = self.manifest.read_bytes()
        blocked = self.run_command(
            "block",
            "--manifest",
            str(self.manifest),
            "--reason",
            "browser_disconnected",
        )
        self.assertEqual(blocked.returncode, 3)
        self.assertEqual(
            json.loads(blocked.stdout)["error"],
            "submitting_order_must_be_marked_unknown",
        )
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_cleanup_removes_completed_manifest_and_empty_directory(self):
        self.finish("raw_balance", "1001")
        self.finish("1510", "1002")
        self.finish("1560", "1003")
        completed = self.run_command("complete", "--manifest", str(self.manifest))
        self.assertEqual(completed.returncode, 0, completed.stdout)
        cleaned = self.run_command("cleanup", "--manifest", str(self.manifest))
        self.assertEqual(cleaned.returncode, 0, cleaned.stdout)
        payload = json.loads(cleaned.stdout)
        self.assertTrue(payload["manifest_removed"])
        self.assertTrue(payload["directory_removed"])
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.directory.exists())

    def test_cleanup_preserves_unrelated_files_and_directory(self):
        self.finish("raw_balance", "1001")
        self.finish("1510", "1002")
        self.finish("1560", "1003")
        completed = self.run_command("complete", "--manifest", str(self.manifest))
        self.assertEqual(completed.returncode, 0, completed.stdout)
        unrelated = self.directory / "keep.txt"
        unrelated.write_text("keep", encoding="utf-8")
        cleaned = self.run_command("cleanup", "--manifest", str(self.manifest))
        self.assertEqual(cleaned.returncode, 0, cleaned.stdout)
        payload = json.loads(cleaned.stdout)
        self.assertFalse(payload["directory_removed"])
        self.assertFalse(self.manifest.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_manifest_is_rejected(self):
        link = self.root / "manifest-link.json"
        try:
            os.symlink(self.manifest, link)
        except (NotImplementedError, OSError):
            self.skipTest("symlink creation unavailable")
        result = self.run_command("show", "--manifest", str(link))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["error"], "symlink_manifest_rejected")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_manifest_directory_is_rejected(self):
        link = self.root / "run-link"
        try:
            os.symlink(self.directory, link, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("directory symlink creation unavailable")
        result = self.run_command(
            "show",
            "--manifest",
            str(link / run_manifest.MANIFEST_NAME),
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "unsafe_manifest_directory",
        )

    @unittest.skipIf(os.name == "nt", "POSIX mode checks are not portable")
    def test_non_private_manifest_mode_is_rejected(self):
        os.chmod(self.manifest, 0o644)
        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "manifest_permissions_not_private",
        )

    @unittest.skipIf(os.name == "nt", "POSIX mode checks are not portable")
    def test_non_private_directory_mode_is_rejected(self):
        os.chmod(self.directory, 0o755)
        try:
            result = self.run_command("show", "--manifest", str(self.manifest))
        finally:
            os.chmod(self.directory, 0o700)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "manifest_directory_not_private",
        )

    def test_duplicate_json_keys_are_rejected(self):
        original = self.manifest.read_text(encoding="utf-8")
        polluted = original.replace(
            "{\n",
            '{\n  "schema_version": 1,\n',
            1,
        )
        self.manifest.write_text(polluted, encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)
        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "duplicate_manifest_key",
        )

    def test_schema_pollution_is_rejected(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["customer_rows"] = []
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)
        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["error"], "unexpected_manifest_schema")

    def test_malformed_schema_types_return_private_json_error(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["records"]["raw_balance"]["state"] = []
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)
        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["error"], "invalid_record_state")

    def test_active_manifest_with_unknown_record_is_rejected(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        record = data["records"]["raw_balance"]
        record["state"] = "UNKNOWN"
        record["attempts"] = 1
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.manifest, 0o600)
        result = self.run_command("show", "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(
            json.loads(result.stdout)["error"],
            "unknown_record_requires_blocked_run",
        )

    def test_windows_policy_skips_posix_identity_and_mode_enforcement(self):
        with mock.patch.object(run_manifest.os, "name", "nt"):
            self.assertFalse(run_manifest._enforce_posix_permissions())
            self.assertIsNone(run_manifest._current_uid())

    def test_windows_policy_skips_directory_fsync_and_fchmod(self):
        with (
            mock.patch.object(run_manifest.os, "name", "nt"),
            mock.patch.object(run_manifest.os, "open") as open_mock,
        ):
            run_manifest._fsync_directory(self.directory)
            open_mock.assert_not_called()

        with (
            mock.patch.object(run_manifest.os, "name", "nt"),
            mock.patch.object(run_manifest.os, "fchmod") as fchmod_mock,
            mock.patch.object(run_manifest, "_lock_descriptor"),
            mock.patch.object(run_manifest, "_unlock_descriptor"),
        ):
            with run_manifest._exclusive_run_lock(self.directory):
                pass
            fchmod_mock.assert_not_called()

    def test_windows_lock_uses_msvcrt_byte_range_locking(self):
        fake_msvcrt = SimpleNamespace(
            LK_LOCK=1,
            LK_UNLCK=2,
            locking=mock.Mock(),
        )
        fake_stat = SimpleNamespace(st_size=1)
        with (
            mock.patch.object(run_manifest.os, "name", "nt"),
            mock.patch.object(run_manifest.os, "fstat", return_value=fake_stat),
            mock.patch.object(run_manifest.os, "lseek"),
            mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}),
        ):
            run_manifest._lock_descriptor(91)
            run_manifest._unlock_descriptor(91)
        self.assertEqual(
            fake_msvcrt.locking.call_args_list,
            [
                mock.call(91, fake_msvcrt.LK_LOCK, 1),
                mock.call(91, fake_msvcrt.LK_UNLCK, 1),
            ],
        )

    def test_windows_reparse_point_is_rejected(self):
        reparse_flag = 0x400
        fake = SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600,
            st_file_attributes=reparse_flag,
        )
        with mock.patch.object(
            run_manifest.stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            reparse_flag,
            create=True,
        ):
            self.assertTrue(run_manifest._is_link_or_reparse(fake))


if __name__ == "__main__":
    unittest.main()
