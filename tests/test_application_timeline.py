import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import application_timeline
import db
import profile_paths


class TestApplicationTimeline(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "profiles", "test_user", "data.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = db.get_db("test_user")

    def tearDown(self):
        import shutil

        if hasattr(self, "conn"):
            self.conn.close()
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_single_application_timeline_reconstruction(self):
        with profile_paths.isolate_for_tests(self.tmp_dir):
            # Seed a job
            conn = db.get_db("test_user")
            conn.execute(
                """
                INSERT INTO jobs (id, title, company, location, raw_text, status, capability_score, recruiter_score, final_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job_123",
                    "Lead Systems Architect",
                    "Acme Labs",
                    "Remote",
                    "Raw JD",
                    "interview",
                    88.0,
                    92.0,
                    90.0,
                    "2026-08-20 10:00:00",
                ),
            )
            # Seed application log
            conn.execute(
                """
                INSERT INTO application_log (job_id, company, role, status, applied_at, responded_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job_123",
                    "Acme Labs",
                    "Lead Systems Architect",
                    "interview",
                    "2026-08-21 14:00:00",
                    "2026-08-23 09:30:00",
                    "Invited to technical round",
                ),
            )
            # Seed contact
            conn.execute(
                """
                INSERT INTO contacts (id, company, name, title, email, linkedin_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "cont_1",
                    "Acme Labs",
                    "Jane Smith",
                    "Lead Recruiter",
                    "jane@acme.com",
                    "https://linkedin.com/in/janesmith",
                ),
            )
            conn.commit()
            conn.close()

            timeline = application_timeline.get_single_application_timeline(
                "job_123", profile="test_user"
            )
            self.assertIsNotNone(timeline)
            self.assertEqual(timeline["job_id"], "job_123")
            self.assertEqual(timeline["company"], "Acme Labs")
            self.assertEqual(timeline["score"], 90.0)

            # Milestones: DISCOVERED, EVALUATED, APPLIED, RESPONDED, INTERVIEW
            event_types = [m["event_type"] for m in timeline["milestones"]]
            self.assertIn("DISCOVERED", event_types)
            self.assertIn("EVALUATED", event_types)
            self.assertIn("APPLIED", event_types)
            self.assertIn("RESPONDED", event_types)

            self.assertEqual(len(timeline["contacts"]), 1)
            self.assertEqual(timeline["contacts"][0]["name"], "Jane Smith")

    def test_agency_relationships_detection(self):
        with profile_paths.isolate_for_tests(self.tmp_dir):
            conn = db.get_db("test_user")
            conn.execute(
                """
                INSERT INTO jobs (id, title, company, location, raw_text, status, final_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job_cc_1",
                    "Senior DevOps Engineer",
                    "CyberCoders",
                    "Remote",
                    "JD",
                    "expired",
                    82.0,
                    "2026-08-10 10:00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO jobs (id, title, company, location, raw_text, status, final_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job_cc_2",
                    "Principal Cloud Engineer",
                    "CyberCoders",
                    "Remote",
                    "JD",
                    "applied",
                    86.0,
                    "2026-08-15 10:00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO jobs (id, title, company, location, raw_text, status, final_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job_direct",
                    "Staff Architect",
                    "Stripe",
                    "Remote",
                    "JD",
                    "applied",
                    95.0,
                    "2026-08-18 10:00:00",
                ),
            )
            conn.commit()
            conn.close()

            agencies = application_timeline.get_agency_relationships(
                profile="test_user"
            )
            self.assertEqual(len(agencies), 1)
            self.assertEqual(agencies[0]["agency_name"], "CyberCoders")
            self.assertEqual(agencies[0]["total_roles"], 2)
            self.assertEqual(agencies[0]["avg_score"], 84.0)
            self.assertEqual(agencies[0]["ghost_rate"], 50.0)  # 1 of 2 is expired


if __name__ == "__main__":
    unittest.main()
