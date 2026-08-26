"""Unit tests for mission_control.py."""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from mission_control import get_mission_control_summary, render_mission_control_ascii


class TestMissionControl(unittest.TestCase):

    def test_get_mission_control_summary_no_db(self):
        summary = get_mission_control_summary("/nonexistent/data.db")
        self.assertEqual(summary["total_jobs"], 0)
        self.assertEqual(summary["system_health"], "No Database Found")

    def test_render_mission_control_ascii(self):
        summary = {
            "total_jobs": 42,
            "pending_eval": 10,
            "applied_count": 8,
            "interview_count": 3,
            "offer_count": 1,
            "contacts_count": 15,
            "system_health": "Healthy",
        }
        output = render_mission_control_ascii(summary)
        self.assertIn("MISSION CONTROL COCKPIT", output)
        self.assertIn("Total Ingested : 42", output)
        self.assertIn("Interviews    : 3", output)
        self.assertIn("Integrity     : Healthy", output)


if __name__ == "__main__":
    unittest.main()
