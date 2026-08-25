"""Unit tests for skill_radar.py."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import skill_radar


class TestSkillRadar(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "radar_test.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company TEXT,
                raw_json TEXT
            )
        """)

        job1_json = json.dumps(
            {"_evaluation": {"missing_skills": ["Kubernetes", "Rust", "Go"]}}
        )
        job2_json = json.dumps(
            {"_evaluation": {"missing_skills": ["Kubernetes", "AWS"]}}
        )
        job3_json = json.dumps(
            {"_evaluation": {"missing_skills": ["Kubernetes", "Rust"]}}
        )

        self.conn.execute(
            "INSERT INTO jobs (title, company, raw_json) VALUES (?, ?, ?)",
            ("DevOps", "Acme", job1_json),
        )
        self.conn.execute(
            "INSERT INTO jobs (title, company, raw_json) VALUES (?, ?, ?)",
            ("Cloud Arch", "Beta", job2_json),
        )
        self.conn.execute(
            "INSERT INTO jobs (title, company, raw_json) VALUES (?, ?, ?)",
            ("Backend Eng", "Gamma", job3_json),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_compute_skill_radar(self):
        radar = skill_radar.compute_skill_radar_from_db(self.conn)
        self.assertEqual(len(radar), 4)
        # Kubernetes was in 3/3 jobs (100%)
        self.assertEqual(radar[0][0], "kubernetes")
        self.assertEqual(radar[0][1], 3)
        self.assertEqual(radar[0][2], 100.0)

        # Rust in 2/3 jobs (66.7%)
        self.assertEqual(radar[1][0], "rust")
        self.assertEqual(radar[1][1], 2)

    def test_render_skill_radar_ascii(self):
        radar = skill_radar.compute_skill_radar_from_db(self.conn)
        ascii_chart = skill_radar.render_skill_radar_ascii(radar)
        self.assertIn("SKILL-GAP PRIORITY RADAR", ascii_chart)
        self.assertIn("kubernetes", ascii_chart)
        self.assertIn("█", ascii_chart)


if __name__ == "__main__":
    unittest.main()
