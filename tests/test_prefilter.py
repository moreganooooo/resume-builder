"""Unit tests for prefilter.py."""

import unittest

from scripts import prefilter


class TestPrefilter(unittest.TestCase):
    def test_remote_only_failure(self):
        job_text = (
            "We are looking for a Senior Engineer. This position is 100% on-site in Chicago. "
            "Compensation: $180,000 - $220,000."
        )
        passes, reasons = prefilter.evaluate_preflight_gate(
            job_text, required_remote=True
        )
        self.assertFalse(passes)
        self.assertTrue(any("on-site" in r.lower() for r in reasons))

    def test_salary_floor_failure(self):
        job_text = "Remote Frontend Engineer. Compensation: $80,000 - $95,000 per year."
        passes, reasons = prefilter.evaluate_preflight_gate(
            job_text, salary_floor=120000
        )
        self.assertFalse(passes)
        self.assertTrue(any("salary" in r.lower() for r in reasons))

    def test_banned_keyword_failure(self):
        job_text = "Senior Python Dev. Must hold active Top Secret Polygraph Clearance."
        passes, reasons = prefilter.evaluate_preflight_gate(
            job_text, banned_keywords=["Top Secret Polygraph"]
        )
        self.assertFalse(passes)
        self.assertTrue(any("banned keyword" in r.lower() for r in reasons))

    def test_passing_criteria(self):
        job_text = (
            "Remote Staff Engineer. Full benefits. Compensation: $190,000 - $230,000."
        )
        passes, reasons = prefilter.evaluate_preflight_gate(
            job_text, required_remote=True, salary_floor=150000
        )
        self.assertTrue(passes)
        self.assertEqual(len(reasons), 0)


if __name__ == "__main__":
    unittest.main()
