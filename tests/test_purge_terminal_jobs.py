"""Tests for scripts/purge_terminal_jobs.py."""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402
import profile_paths  # noqa: E402
import purge_terminal_jobs  # noqa: E402


class TestPurgeTerminalJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.iso_cm = profile_paths.isolate_for_tests(self.tmp)
        self.iso_cm.__enter__()

        self.profile = "testpurge"
        self.profile_dir = profile_paths.profile_root(self.profile)
        os.makedirs(self.profile_dir, exist_ok=True)

        self.jds_dir = profile_paths.jds_dir(self.profile)
        for subdir in ("", "expired", "archived", "pending", "applied"):
            os.makedirs(os.path.join(self.jds_dir, subdir), exist_ok=True)

        self.db_path = os.path.join(self.profile_dir, "data.db")
        conn = sqlite3.connect(self.db_path)
        db.init_db(conn)
        conn.execute("DELETE FROM jobs")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.iso_cm.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_jd_file(self, subdir: str, filename: str, content: str = "{}") -> str:
        path = (
            os.path.join(self.jds_dir, subdir, filename)
            if subdir
            else os.path.join(self.jds_dir, filename)
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _insert_job(
        self, job_id: str, status: str, title: str = "Engineer", company: str = "Acme"
    ):
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO jobs (id, title, company, status, raw_text) VALUES (?, ?, ?, ?, ?)",
                (job_id, title, company, status, "{}"),
            )
        conn.close()

    def test_terminal_files_discovers_only_expired_and_archived(self):
        f_root = self._write_jd_file("", "root.json")
        f_exp1 = self._write_jd_file("expired", "job1.json")
        f_exp2 = self._write_jd_file("expired", "job2.json")
        f_arc = self._write_jd_file("archived", "job3.json")
        f_pen = self._write_jd_file("pending", "job4.json")

        discovered = purge_terminal_jobs.terminal_files(self.jds_dir)
        self.assertIn(f_exp1, discovered)
        self.assertIn(f_exp2, discovered)
        self.assertIn(f_arc, discovered)
        self.assertNotIn(f_root, discovered)
        self.assertNotIn(f_pen, discovered)
        self.assertEqual(len(discovered), 3)

    def test_purge_dry_run_preserves_db_and_files(self):
        self._insert_job("job_exp", "expired")
        self._insert_job("job_arc", "archived")
        self._insert_job("job_pen", "pending")
        self._insert_job("job_app", "applied")

        f_exp = self._write_jd_file("expired", "job_exp.json", '{"job": 1}')
        f_arc = self._write_jd_file("archived", "job_arc.json", '{"job": 2}')

        stats = purge_terminal_jobs.purge(
            self.db_path, self.jds_dir, apply_changes=False
        )

        self.assertEqual(stats["files"], 2)
        self.assertEqual(stats["rows"], 2)
        self.assertEqual(stats["remaining_rows"], 2)
        self.assertGreater(stats["bytes"], 0)

        # Files must still exist
        self.assertTrue(os.path.exists(f_exp))
        self.assertTrue(os.path.exists(f_arc))

        # DB rows must still exist
        conn = sqlite3.connect(self.db_path)
        all_rows = conn.execute("SELECT id, status FROM jobs").fetchall()
        conn.close()
        self.assertEqual(len(all_rows), 4)

    def test_purge_apply_removes_terminal_rows_and_files(self):
        self._insert_job("job_exp", "expired")
        self._insert_job("job_arc", "archived")
        self._insert_job("job_pen", "pending")
        self._insert_job("job_app", "applied")

        f_exp = self._write_jd_file("expired", "job_exp.json", '{"job": 1}')
        f_arc = self._write_jd_file("archived", "job_arc.json", '{"job": 2}')
        f_pen = self._write_jd_file("pending", "job_pen.json", '{"job": 3}')

        stats = purge_terminal_jobs.purge(
            self.db_path, self.jds_dir, apply_changes=True
        )

        self.assertEqual(stats["files"], 2)
        self.assertEqual(stats["rows"], 2)
        self.assertEqual(stats["remaining_rows"], 2)

        # Terminal files must be deleted
        self.assertFalse(os.path.exists(f_exp))
        self.assertFalse(os.path.exists(f_arc))

        # Non-terminal file must remain
        self.assertTrue(os.path.exists(f_pen))

        # Terminal DB rows deleted, non-terminal kept
        conn = sqlite3.connect(self.db_path)
        remaining = conn.execute("SELECT id, status FROM jobs").fetchall()
        conn.close()
        self.assertEqual(len(remaining), 2)
        remaining_ids = {r[0] for r in remaining}
        self.assertEqual(remaining_ids, {"job_pen", "job_app"})

    def test_purge_missing_files_graceful(self):
        self._insert_job("job_exp_nofile", "expired")
        stats = purge_terminal_jobs.purge(
            self.db_path, self.jds_dir, apply_changes=True
        )
        self.assertEqual(stats["files"], 0)
        self.assertEqual(stats["rows"], 1)
        self.assertEqual(stats["remaining_rows"], 0)

        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_main_missing_db(self):
        with patch(
            "sys.argv",
            ["purge_terminal_jobs.py", "--profile", "nonexistent_profile_xyz"],
        ):
            code = purge_terminal_jobs.main()
            self.assertEqual(code, 1)

    def test_main_dry_run_and_apply_with_backup(self):
        self._insert_job("job_exp", "expired")
        self._write_jd_file("expired", "job_exp.json", "dummy content")

        # Dry run via main()
        with patch("sys.argv", ["purge_terminal_jobs.py", "--profile", self.profile]):
            code = purge_terminal_jobs.main()
            self.assertEqual(code, 0)

        # Verify no backup was created during dry run
        backups = [f for f in os.listdir(self.profile_dir) if "backup" in f]
        self.assertEqual(len(backups), 0)

        # Apply via main()
        with patch(
            "sys.argv", ["purge_terminal_jobs.py", "--profile", self.profile, "--apply"]
        ):
            code = purge_terminal_jobs.main()
            self.assertEqual(code, 0)

        # Verify backup was created
        backups = [f for f in os.listdir(self.profile_dir) if "backup" in f]
        self.assertEqual(len(backups), 1)

        # Verify DB and file were purged
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
