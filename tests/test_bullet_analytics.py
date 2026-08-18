"""Unit tests for bullet_analytics.py."""

import os
import sqlite3
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
