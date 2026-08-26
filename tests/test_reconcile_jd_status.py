"""A JD's directory is its status; data.db drifted out of sync with it.

The subtle half is id matching: jobs.id is a filename for most rows but a
compute_job_key() content hash for the rest, so basename matching alone
silently skips the hashed ones. The first version of this script did
that and left 740 reconcilable rows untouched.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402
import jd_manager  # noqa: E402
import reconcile_jd_status as rjs  # noqa: E402


class TestReconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jds = os.path.join(self.tmp, "jds")
        for sub in ("", "expired", "archived"):
            os.makedirs(os.path.join(self.jds, sub), exist_ok=True)

        self.db_path = os.path.join(self.tmp, "data.db")
        conn = sqlite3.connect(self.db_path)
        db.init_db(conn)
        conn.close()

    def _write_jd(self, subdir, name, **fields):
        path = (
            os.path.join(self.jds, subdir, name)
            if subdir
            else os.path.join(self.jds, name)
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"job_title": "Analyst", "company_name": "Acme", **fields}, f)
        return path

    def _insert(self, job_id, status):
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute(
                "INSERT INTO jobs (id, title, company, status, raw_text)"
                " VALUES (?, ?, ?, ?, ?)",
                (job_id, "Analyst", "Acme", status, "{}"),
            )
        conn.close()

    def _status(self, job_id):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        return row[0]

    def test_filename_id_row_is_corrected_to_its_directory(self):
        self._write_jd("archived", "job.json")
        self._insert("job.json", "pending")

        rjs.reconcile(self.db_path, self.jds, apply_changes=True)

        self.assertEqual(self._status("job.json"), "archived")

    def test_hash_id_row_is_also_corrected(self):
        """The bug: a content-hash id still has a file, and matching on
        basename alone skips it entirely."""
        path = self._write_jd("expired", "hashed.json")
        key = jd_manager.compute_job_key(path)
        self.assertFalse(key.endswith(".json"), "fixture should be a hash id")
        self._insert(key, "pending")

        stats = rjs.reconcile(self.db_path, self.jds, apply_changes=True)

        self.assertEqual(self._status(key), "expired")
        self.assertEqual(stats["no_file"], 0)

    def test_row_with_no_file_is_left_alone(self):
        self._insert("deadbeef" * 8, "pending")

        stats = rjs.reconcile(self.db_path, self.jds, apply_changes=True)

        self.assertEqual(stats["no_file"], 1)
        self.assertEqual(stats["updates"], 0)
        self.assertEqual(self._status("deadbeef" * 8), "pending")

    def test_already_correct_row_is_not_touched(self):
        self._write_jd("", "fine.json")
        self._insert("fine.json", "pending")

        stats = rjs.reconcile(self.db_path, self.jds, apply_changes=True)

        self.assertEqual(stats["updates"], 0)

    def test_dry_run_writes_nothing(self):
        self._write_jd("archived", "job.json")
        self._insert("job.json", "pending")

        stats = rjs.reconcile(self.db_path, self.jds, apply_changes=False)

        self.assertEqual(stats["updates"], 1)
        self.assertEqual(self._status("job.json"), "pending")

    def test_reconcile_is_idempotent(self):
        self._write_jd("expired", "job.json")
        self._insert("job.json", "pending")

        rjs.reconcile(self.db_path, self.jds, apply_changes=True)
        second = rjs.reconcile(self.db_path, self.jds, apply_changes=True)

        self.assertEqual(second["updates"], 0)


class TestCliReconcileCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.profile_dir = os.path.join(self.tmp, "test_prof")
        os.makedirs(self.profile_dir, exist_ok=True)
        self.db_path = os.path.join(self.profile_dir, "data.db")
        conn = sqlite3.connect(self.db_path)
        db.init_db(conn)
        conn.close()

    def test_cli_reconcile_dry_run_invokes_cleanly(self):
        from unittest.mock import patch

        import cli
        from click.testing import CliRunner

        fake_stats = {
            "scanned": 10,
            "files_on_disk": 10,
            "no_file": 0,
            "updates": 2,
            "transitions": Counter({"pending -> archived": 2}),
            "status_after": Counter({"archived": 2, "pending": 8}),
        }
        runner = CliRunner()
        with (
            patch("reconcile_jd_status.reconcile", return_value=fake_stats) as mock_rec,
            patch("profile_paths.PROFILES_DIR", self.tmp),
            patch("profile_paths.active_profile", return_value="test_prof"),
            patch(
                "profile_paths.jds_dir",
                return_value=os.path.join(self.profile_dir, "jds"),
            ),
        ):
            result = runner.invoke(cli.cli, ["reconcile"])
            self.assertEqual(result.exit_code, 0, f"Error: {result.output}")
            mock_rec.assert_called_once()
            self.assertIn("Job Status Reconciliation", result.output)
            self.assertIn("Dry run only", result.output)

    def test_cli_reconcile_apply_invokes_with_apply_true(self):
        from unittest.mock import patch

        import cli
        from click.testing import CliRunner

        fake_stats = {
            "scanned": 10,
            "files_on_disk": 10,
            "no_file": 0,
            "updates": 2,
            "transitions": Counter({"pending -> archived": 2}),
            "status_after": Counter({"archived": 2, "pending": 8}),
        }
        runner = CliRunner()
        with (
            patch("reconcile_jd_status.reconcile", return_value=fake_stats) as mock_rec,
            patch("profile_paths.PROFILES_DIR", self.tmp),
            patch("profile_paths.active_profile", return_value="test_prof"),
            patch(
                "profile_paths.jds_dir",
                return_value=os.path.join(self.profile_dir, "jds"),
            ),
            patch("shutil.copy2"),
        ):
            result = runner.invoke(cli.cli, ["reconcile", "--apply"])
            self.assertEqual(result.exit_code, 0, f"Error: {result.output}")
            mock_rec.assert_called_once()
            self.assertTrue(mock_rec.call_args[1].get("apply_changes"))
            self.assertIn("Reconciliation complete", result.output)


if __name__ == "__main__":
    unittest.main()
