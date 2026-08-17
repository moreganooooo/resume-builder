import datetime
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import followup  # noqa: E402


def _iso_days_ago(days: int) -> str:
    return (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(
        timespec="seconds"
    )


class TestComputeUrgency(unittest.TestCase):

    def test_none_when_no_application(self):
        self.assertIsNone(followup.compute_urgency(None))
        self.assertIsNone(followup.compute_urgency({}))

    def test_none_for_terminal_statuses(self):
        for status in ("Offer", "Rejected", "Withdrawn"):
            app = {
                "status": status,
                "status_changed_at": _iso_days_ago(30),
                "follow_up_count": 0,
            }
            self.assertIsNone(followup.compute_urgency(app), status)

    def test_applied_waiting_before_first_threshold(self):
        app = {
            "status": "Applied",
            "status_changed_at": _iso_days_ago(3),
            "follow_up_count": 0,
        }
        self.assertEqual(followup.compute_urgency(app), "waiting")

    def test_applied_overdue_at_seven_days_with_no_followup(self):
        app = {
            "status": "Applied",
            "status_changed_at": _iso_days_ago(7),
            "follow_up_count": 0,
        }
        self.assertEqual(followup.compute_urgency(app), "overdue")

    def test_applied_waiting_after_one_recent_followup(self):
        app = {
            "status": "Applied",
            "status_changed_at": _iso_days_ago(10),
            "follow_up_count": 1,
            "last_followup_at": _iso_days_ago(2),
        }
        self.assertEqual(followup.compute_urgency(app), "waiting")

    def test_applied_overdue_again_after_subsequent_gap(self):
        app = {
            "status": "Applied",
            "status_changed_at": _iso_days_ago(20),
            "follow_up_count": 1,
            "last_followup_at": _iso_days_ago(7),
        }
        self.assertEqual(followup.compute_urgency(app), "overdue")

    def test_applied_cold_after_max_followups(self):
        app = {
            "status": "Applied",
            "status_changed_at": _iso_days_ago(30),
            "follow_up_count": 2,
            "last_followup_at": _iso_days_ago(1),
        }
        self.assertEqual(followup.compute_urgency(app), "cold")

    def test_responded_waiting_then_overdue(self):
        waiting = {
            "status": "Responded",
            "status_changed_at": _iso_days_ago(1),
            "follow_up_count": 0,
        }
        overdue = {
            "status": "Responded",
            "status_changed_at": _iso_days_ago(3),
            "follow_up_count": 0,
        }
        self.assertEqual(followup.compute_urgency(waiting), "waiting")
        self.assertEqual(followup.compute_urgency(overdue), "overdue")

    def test_interview_overdue_after_one_day(self):
        fresh = {
            "status": "Interview",
            "status_changed_at": _iso_days_ago(0),
            "follow_up_count": 0,
        }
        stale = {
            "status": "Interview",
            "status_changed_at": _iso_days_ago(1),
            "follow_up_count": 0,
        }
        self.assertEqual(followup.compute_urgency(fresh), "waiting")
        self.assertEqual(followup.compute_urgency(stale), "overdue")

    def test_missing_status_changed_at_returns_none(self):
        app = {"status": "Applied", "follow_up_count": 0}
        self.assertIsNone(followup.compute_urgency(app))


if __name__ == "__main__":
    unittest.main()
