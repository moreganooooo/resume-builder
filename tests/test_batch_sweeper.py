"""Unit tests for batch_sweeper.py."""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from batch_sweeper import sweep_job_record, sweep_pending_jobs


class TestBatchSweeper(unittest.TestCase):

    def test_sweep_job_record_valid(self):
        job = {
            "id": "job-1",
            "title": "Senior Python Engineer",
            "company": "Tech Corp",
            "raw_text": "Remote Senior Python Engineer. Salary: $160,000 - $190,000. Full benefits.",
        }
        res = sweep_job_record(job)
        self.assertTrue(res["passed_prefilter"])
        self.assertEqual(res["status"], "ready_for_eval")
        self.assertIsNotNone(res["salary_range"]["min_salary"])

    def test_sweep_job_record_dealbreaker(self):
        job = {
            "id": "job-2",
            "title": "Onsite Engineer",
            "company": "Legacy Corp",
            "raw_text": "Strictly 5 days on-site required. No remote work permitted.",
        }
        filters = {"require_remote": True}
        res = sweep_job_record(job, filters=filters)
        self.assertFalse(res["passed_prefilter"])
        self.assertEqual(res["status"], "skip")

    def test_sweep_pending_jobs(self):
        jobs = [
            {"id": "j1", "title": "Dev 1", "raw_text": "Python Remote Engineer"},
            {"id": "j2", "title": "Dev 2", "raw_text": "Golang Remote Engineer"},
        ]
        results = sweep_pending_jobs(jobs, max_workers=2)
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
