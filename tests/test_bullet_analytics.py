import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bullet_analytics import analyze_bullet_tag_performance


class TestBulletAnalytics(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "data.db")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY,
                title TEXT,
                description TEXT
            )
            """)
        cursor.execute("""
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY,
                job_id INTEGER,
                status TEXT
            )
            """)
        cursor.execute(
            "INSERT INTO jobs (id, title, description) VALUES (1, 'Lead Python Engineer', 'Build cloud infra and APIs')"
        )
        cursor.execute(
            "INSERT INTO applications (id, job_id, status) VALUES (1, 1, 'interview')"
        )
        cursor.execute(
            "INSERT INTO jobs (id, title, description) VALUES (2, 'Frontend React Developer', 'UI design')"
        )
        cursor.execute(
            "INSERT INTO applications (id, job_id, status) VALUES (2, 2, 'rejected')"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_analyze_bullet_tag_performance(self):
        stats = analyze_bullet_tag_performance(self.db_path)
        self.assertIn("lead", stats)
        self.assertEqual(stats["lead"]["interviews"], 1)
        self.assertEqual(stats["lead"]["interview_rate_pct"], 100.0)

        self.assertIn("frontend", stats)
        self.assertEqual(stats["frontend"]["rejections"], 1)
        self.assertEqual(stats["frontend"]["interview_rate_pct"], 0.0)

    def test_no_db(self):
        stats = analyze_bullet_tag_performance("/nonexistent/data.db")
        self.assertEqual(stats, {})

    def test_empty_db_tables(self):
        empty_db = os.path.join(self.tmp_dir.name, "empty.db")
        conn = sqlite3.connect(empty_db)
        conn.execute("CREATE TABLE jobs (id INT, title TEXT, description TEXT)")
        conn.execute("CREATE TABLE applications (id INT, job_id INT, status TEXT)")
        conn.commit()
        conn.close()
        stats = analyze_bullet_tag_performance(empty_db)
        self.assertEqual(stats, {})

    def test_corrupted_or_missing_schema_db(self):
        bad_db = os.path.join(self.tmp_dir.name, "bad.db")
        with open(bad_db, "wb") as f:
            f.write(b"not a valid sqlite file")
        stats = analyze_bullet_tag_performance(bad_db)
        self.assertEqual(stats, {})


if __name__ == "__main__":
    unittest.main()
