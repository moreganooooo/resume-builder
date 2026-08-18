"""Unit tests for eval_audit.py."""

import os
import tempfile
import unittest

from scripts import eval_audit


class TestEvalAudit(unittest.TestCase):
    def test_generate_evaluation_audit_markdown(self):
        job_data = {"title": "Principal Architect", "company": "Stripe"}
        evaluation = {
            "composite_score": 92,
            "tier": "Tier 1: Excellent Match",
            "interview_odds": "35%",
            "capability_score": 95,
            "recruiter_friction": 10,
            "pros": ["10+ years backend experience", "Led distributed teams"],
            "cons": ["Requires 2 days in-office"],
            "missing_skills": ["Kafka"],
            "tailoring_tips": ["Highlight payment processing metrics"],
        }

        md = eval_audit.generate_evaluation_audit_markdown(job_data, evaluation)
        self.assertIn("Principal Architect @ Stripe", md)
        self.assertIn("Composite Fit Score:** `92`", md)
        self.assertIn("10+ years backend experience", md)
        self.assertIn("Kafka", md)

    def test_write_evaluation_audit(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            temp_path = f.name

        try:
            job_data = {"title": "Staff SRE", "company": "Vercel"}
            evaluation = {"composite_score": 88}
            out_file = eval_audit.write_evaluation_audit(
                job_data, evaluation, temp_path
            )
            self.assertEqual(out_file, temp_path)
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Staff SRE @ Vercel", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
