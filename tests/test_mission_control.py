"""Unit tests for mission_control.py."""

import unittest

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
