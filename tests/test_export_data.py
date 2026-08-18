"""Unit tests for export_data.py."""

import os
import sqlite3
import tempfile
import unittest

from scripts import export_data


class TestExportData(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute(
            "INSERT INTO jobs (title, company, status) VALUES (?, ?, ?)",
            ("Staff Engineer", "Acme", "evaluated"),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_fetch_all_jobs(self):
        jobs = export_data.fetch_all_jobs(self.conn)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Staff Engineer")

    def test_export_data_lake(self):
        out_dir = os.path.join(self.temp_dir.name, "export")
        results = export_data.export_data_lake(self.db_path, out_dir)
        self.assertIn("jsonl", results)
        self.assertIn("csv", results)
        self.assertTrue(os.path.exists(results["jsonl"]))
        self.assertTrue(os.path.exists(results["csv"]))

        with open(results["jsonl"], "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("Staff Engineer", lines[0])


if __name__ == "__main__":
    unittest.main()
