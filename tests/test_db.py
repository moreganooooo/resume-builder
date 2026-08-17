"""Tests for db.py's SQLite layer. Every test here patches profile_paths
so db.get_db() resolves to a temp directory -- never the real
profiles/<name>/data.db (see F4's cleanup story in
docs/review/master_audit_document.md for why that isolation matters)."""

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


class TestDbSchema(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        patcher = patch("profile_paths.profile_root", return_value=self._tmpdir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: shutil.rmtree(self._tmpdir, ignore_errors=True))

    def test_get_db_creates_all_three_tables(self):
        conn = db.get_db("isolated")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        self.assertTrue({"jobs", "bullet_bank", "application_log"}.issubset(tables))

    def test_get_db_sets_wal_journal_mode_and_busy_timeout(self):
        conn = db.get_db("isolated")
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")
        self.assertEqual(timeout, 5000)

    def test_upsert_job_round_trips_a_record(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_001",
                "title": "Marketing Manager",
                "company": "Acme",
                "status": "pending",
                "jd_text": "sample text",
            },
            conn=conn,
        )
        rows = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Marketing Manager")
        self.assertEqual(rows[0]["company"], "Acme")

    def test_upsert_job_on_conflict_updates_existing_row_not_duplicates(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_001",
                "title": "A",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "job_001",
                "title": "B",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        rows = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "B")

    def test_upsert_job_accepts_every_check_constraint_status(self):
        """Regression pin for the CHECK constraint fix -- every pipeline
        status the app actually uses must be insertable without raising
        sqlite3.IntegrityError."""
        conn = db.get_db("isolated")
        statuses = [
            "pending",
            "evaluating",
            "completed",
            "applied",
            "interview",
            "offer",
            "responded",
            "rejected",
            "discarded",
            "expired",
            "archived",
            "skip",
        ]
        for i, status in enumerate(statuses):
            db.upsert_job(
                {
                    "id": f"job_{i}",
                    "title": "T",
                    "company": "C",
                    "status": status,
                    "jd_text": "x",
                },
                conn=conn,
            )
        conn.close()  # would raise IntegrityError on commit if any status were rejected

    def test_update_job_status_only_touches_the_targeted_row(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_a",
                "title": "A",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "job_b",
                "title": "B",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )

        db.update_job_status("job_a", "completed", conn=conn)

        completed = db.get_jobs_by_status("completed", conn=conn)
        still_pending = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual([r["id"] for r in completed], ["job_a"])
        self.assertEqual([r["id"] for r in still_pending], ["job_b"])

    def test_get_jobs_by_status_returns_empty_list_not_none_when_no_matches(self):
        conn = db.get_db("isolated")
        rows = db.get_jobs_by_status("offer", conn=conn)
        conn.close()
        self.assertEqual(rows, [])

    def test_get_db_path_is_scoped_under_the_given_profile_root(self):
        path = db.get_db_path("isolated")
        self.assertTrue(path.startswith(self._tmpdir))
        self.assertTrue(path.endswith("data.db"))

    def test_checkpoint_truncates_the_wal_file(self):
        """F6: writes sitting in the local -wal file (Syncthing-excluded
        via .stignore) never reach a second machine until checkpointed
        into data.db itself."""
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_001",
                "title": "T",
                "company": "C",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        conn.close()

        db.checkpoint("isolated")

        wal_path = db.get_db_path("isolated") + "-wal"
        wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
        self.assertEqual(wal_size, 0)

        # And the write is still there, safely in the main file.
        conn2 = db.get_db("isolated")
        rows = db.get_jobs_by_status("pending", conn=conn2)
        conn2.close()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
