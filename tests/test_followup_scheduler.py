"""Unit tests for followup_scheduler.py."""

import datetime
import os
import sqlite3
import tempfile
import unittest

from scripts import followup_scheduler


class TestFollowupScheduler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_followups.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company TEXT,
                status TEXT,
                updated_at TEXT,
                created_at TEXT
            )
        """)

        old_date = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        recent_date = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat()

        self.conn.execute(
            "INSERT INTO jobs (title, company, status, updated_at) VALUES (?, ?, ?, ?)",
            ("Staff Eng", "Slack", "applied", old_date),
        )
        self.conn.execute(
            "INSERT INTO jobs (title, company, status, updated_at) VALUES (?, ?, ?, ?)",
            ("Senior Eng", "Figma", "applied", recent_date),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_get_pending_followups(self):
        pending = followup_scheduler.get_pending_followups(self.conn, threshold_days=7)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["company"], "Slack")
        self.assertGreaterEqual(pending[0]["elapsed_days"], 9)

    def test_draft_followup_email(self):
        draft_7d = followup_scheduler.draft_followup_email(
            "Staff Eng", "Slack", elapsed_days=8
        )
        self.assertIn("Following up on Staff Eng Application", draft_7d)
        self.assertIn("Slack", draft_7d)

        draft_14d = followup_scheduler.draft_followup_email(
            "Staff Eng", "Slack", elapsed_days=15
        )
        self.assertIn("Checking In: Staff Eng Application Status", draft_14d)


if __name__ == "__main__":
    unittest.main()
