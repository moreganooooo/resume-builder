import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import job_eval_heuristics  # noqa: E402


class TestJobEvalHeuristics(unittest.TestCase):

    def test_extract_salary_range_standard(self):
        text = "The base salary range for this position is $130,000 - $165,000 per year plus equity."
        res = job_eval_heuristics.extract_salary_range(text)
        self.assertEqual(res["min_salary"], 130000.0)
        self.assertEqual(res["max_salary"], 165000.0)
        self.assertEqual(res["currency"], "USD")
        self.assertEqual(res["period"], "annual")

    def test_extract_salary_range_k_format(self):
        text = "Compensation: $140k - $180k depending on experience."
        res = job_eval_heuristics.extract_salary_range(text)
        self.assertEqual(res["min_salary"], 140000.0)
        self.assertEqual(res["max_salary"], 180000.0)
        self.assertEqual(res["period"], "annual")

    def test_extract_salary_hourly(self):
        text = "Rate: $65 - $85 / hour on W2 contract."
        res = job_eval_heuristics.extract_salary_range(text)
        self.assertEqual(res["min_salary"], 65.0)
        self.assertEqual(res["max_salary"], 85.0)
        self.assertEqual(res["period"], "hourly")

    def test_extract_salary_empty(self):
        text = "We offer competitive benefits and generous PTO."
        res = job_eval_heuristics.extract_salary_range(text)
        self.assertIsNone(res["min_salary"])
        self.assertIsNone(res["max_salary"])

    def test_compute_ghost_job_probability_stale_and_evergreen(self):
        text = (
            "Join our ongoing talent community for future opportunities across teams."
        )
        res = job_eval_heuristics.compute_ghost_job_probability(
            jd_text=text, posting_age_days=65, repost_count=3
        )
        self.assertGreaterEqual(res["ghost_probability"], 0.70)
        self.assertTrue(res["is_ghost_risk"])
        self.assertTrue(any("very old" in f for f in res["risk_flags"]))
        self.assertTrue(any("Frequently reposted" in f for f in res["risk_flags"]))

    def test_compute_ghost_job_probability_fresh_concrete_role(self):
        text = (
            "We are hiring a Senior Product Manager to lead our Core Infrastructure team. "
            "You will report directly to the VP of Product and manage 3 direct reports. "
            "Qualifications: 7+ years PM experience in distributed cloud systems."
        )
        res = job_eval_heuristics.compute_ghost_job_probability(
            jd_text=text, posting_age_days=3, repost_count=0
        )
        self.assertLess(res["ghost_probability"], 0.30)
        self.assertFalse(res["is_ghost_risk"])

    def test_classify_visa_sponsorship_no_sponsorship(self):
        text = "Applicants must be authorized to work in the US without the need for visa sponsorship."
        res = job_eval_heuristics.classify_visa_sponsorship(text)
        self.assertEqual(res["status"], "no_sponsorship")
        self.assertFalse(res["us_citizenship_required"])

    def test_classify_visa_sponsorship_security_clearance(self):
        text = "Must be a U.S. Citizen with active Secret clearance."
        res = job_eval_heuristics.classify_visa_sponsorship(text)
        self.assertEqual(res["status"], "no_sponsorship")
        self.assertTrue(res["us_citizenship_required"])

    def test_classify_visa_sponsorship_available(self):
        text = "Visa sponsorship is available for qualified candidates; H-1B transfer supported."
        res = job_eval_heuristics.classify_visa_sponsorship(text)
        self.assertEqual(res["status"], "sponsors")
        self.assertFalse(res["us_citizenship_required"])

    def test_classify_visa_sponsorship_unknown(self):
        text = "Great compensation, flexible remote schedule, and 401(k) match."
        res = job_eval_heuristics.classify_visa_sponsorship(text)
        self.assertEqual(res["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
