"""Tests for migrate_filesystem_to_db.py against a small fixture directory
tree -- never the real profiles/<name>/ tree. Covers: correct import of
JSON JDs across pending/completed/expired, bullet bank CSV import, and
idempotency (running twice must not duplicate or corrupt rows)."""

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402
import migrate_filesystem_to_db as migrate  # noqa: E402
import profile_paths  # noqa: E402


class TestMigrateJobs(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._jd_base = os.path.join(self._tmpdir, "jds", "isolated")
        os.makedirs(os.path.join(self._jd_base, "completed"))
        os.makedirs(os.path.join(self._jd_base, "expired"))

        with open(os.path.join(self._jd_base, "acme_pm.json"), "w") as f:
            json.dump({"company": "Acme", "title": "PM", "jd_text": "x"}, f)
        with open(
            os.path.join(self._jd_base, "completed", "globex_eng.json"), "w"
        ) as f:
            json.dump({"company": "Globex", "title": "Engineer", "jd_text": "x"}, f)
        with open(
            os.path.join(self._jd_base, "expired", "initech_sales.json"), "w"
        ) as f:
            json.dump({"company": "Initech", "title": "Sales", "jd_text": "x"}, f)

        patcher = patch("profile_paths.jd_dir", return_value=self._jd_base, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        root_patcher = patch("profile_paths.profile_root", return_value=self._tmpdir)
        root_patcher.start()
        self.addCleanup(root_patcher.stop)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_migrates_every_json_file_across_all_three_subdirectories(self):
        conn = db.get_db("isolated")
        count = migrate.migrate_jobs("isolated", conn=conn)
        self.assertEqual(count, 3)

        pending = db.get_jobs_by_status("pending", conn=conn)
        completed = db.get_jobs_by_status("completed", conn=conn)
        expired = db.get_jobs_by_status("expired", conn=conn)
        conn.close()

        self.assertEqual([r["company"] for r in pending], ["Acme"])
        self.assertEqual([r["company"] for r in completed], ["Globex"])
        self.assertEqual([r["company"] for r in expired], ["Initech"])

    def test_running_migrate_jobs_twice_does_not_duplicate_rows(self):
        conn = db.get_db("isolated")
        migrate.migrate_jobs("isolated", conn=conn)
        migrate.migrate_jobs("isolated", conn=conn)  # run again, same fixture tree

        all_rows = (
            db.get_jobs_by_status("pending", conn=conn)
            + db.get_jobs_by_status("completed", conn=conn)
            + db.get_jobs_by_status("expired", conn=conn)
        )
        conn.close()
        self.assertEqual(
            len(all_rows),
            3,
            "re-running the migration duplicated rows instead of updating them",
        )

    def test_skips_non_json_files_without_raising(self):
        with open(os.path.join(self._jd_base, "notes.txt"), "w") as f:
            f.write("not a JD")
        conn = db.get_db("isolated")
        count = migrate.migrate_jobs("isolated", conn=conn)
        conn.close()
        self.assertEqual(count, 3)  # still just the 3 real .json files


class TestMigrateBulletBank(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._kb_dir = os.path.join(self._tmpdir, "knowledge_base")
        os.makedirs(self._kb_dir)
        self._csv_path = os.path.join(self._kb_dir, "bullet-bank-keepers-audited.csv")
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["company", "title", "bullet", "category", "audit_status"]
            )
            writer.writeheader()
            writer.writerow(
                {
                    "company": "Acme",
                    "title": "PM",
                    "bullet": "Led launch",
                    "category": "leadership",
                    "audit_status": "CLEAN",
                }
            )
            writer.writerow(
                {
                    "company": "Globex",
                    "title": "Eng",
                    "bullet": "Shipped API",
                    "category": "technical",
                    "audit_status": "CLEAN",
                }
            )

        patcher = patch("profile_paths.kb_dir", return_value=self._kb_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        root_patcher = patch("profile_paths.profile_root", return_value=self._tmpdir)
        root_patcher.start()
        self.addCleanup(root_patcher.stop)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_migrates_every_csv_row(self):
        count = migrate.migrate_bullet_bank("isolated")
        self.assertEqual(count, 2)

        conn = db.get_db("isolated")
        rows = conn.execute("SELECT * FROM bullet_bank ORDER BY id").fetchall()
        conn.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["company"] for r in rows}, {"Acme", "Globex"})

    def test_running_migrate_bullet_bank_twice_on_unchanged_csv_does_not_duplicate(
        self,
    ):
        migrate.migrate_bullet_bank("isolated")
        migrate.migrate_bullet_bank("isolated")

        conn = db.get_db("isolated")
        rows = conn.execute("SELECT * FROM bullet_bank").fetchall()
        conn.close()
        self.assertEqual(
            len(rows), 2, "re-running on an unchanged CSV duplicated bullet_bank rows"
        )

    def test_missing_csv_returns_zero_without_raising(self):
        os.remove(self._csv_path)
        count = migrate.migrate_bullet_bank("isolated")
        self.assertEqual(count, 0)

    def test_fallback_to_bullet_bank_keepers_csv(self):
        os.remove(self._csv_path)
        fallback_path = os.path.join(self._kb_dir, "bullet-bank-keepers.csv")
        with open(fallback_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["company", "title", "bullet", "category", "audit_status"]
            )
            writer.writeheader()
            writer.writerow(
                {
                    "company": "Initech",
                    "title": "Ops",
                    "bullet": "Automated workflow",
                    "category": "ops",
                    "audit_status": "CLEAN",
                }
            )
        count = migrate.migrate_bullet_bank("isolated")
        self.assertEqual(count, 1)


class TestMigrateJobsErrorsAndMain(unittest.TestCase):
    def test_corrupted_json_handled_gracefully(self):
        tmpdir = tempfile.mkdtemp()
        try:
            jd_base = os.path.join(tmpdir, "jds", "isolated")
            os.makedirs(jd_base)
            with open(os.path.join(jd_base, "bad.json"), "w") as f:
                f.write("invalid json")
            with (
                patch("profile_paths.jd_dir", return_value=jd_base, create=True),
                patch("profile_paths.profile_root", return_value=tmpdir),
            ):
                conn = db.get_db("isolated")
                count = migrate.migrate_jobs("isolated", conn=conn)
                conn.close()
                self.assertEqual(count, 0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_main_cli_execution(self):
        tmpdir = tempfile.mkdtemp()
        try:
            jd_base = os.path.join(tmpdir, "jds", "testprof")
            kb_dir = os.path.join(tmpdir, "knowledge_base")
            os.makedirs(jd_base)
            os.makedirs(kb_dir)
            with (
                patch("profile_paths.active_profile", return_value="testprof"),
                patch("profile_paths.jd_dir", return_value=jd_base, create=True),
                patch("profile_paths.kb_dir", return_value=kb_dir),
                patch("profile_paths.profile_root", return_value=tmpdir),
            ):
                migrate.main()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
