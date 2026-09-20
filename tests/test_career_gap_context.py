"""The recruiter evaluator's gap assessment is driven by each profile's own
career_gap: entry, not one candidate's gap hardcoded for every profile."""

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import orchestrator  # noqa: E402

PROFILE = """narrative:
  headline: "Analyst."
career_gap:
  period: "2021-22"
  resume_coverage: "Visible."
compensation:
  floor: 1
"""


class TestCareerGapContext(unittest.TestCase):
    def test_prompt_hardcodes_no_candidate_gap(self):
        with open(
            os.path.join(ROOT, "resume-engine", "prompts", "evaluate_recruiter.md")
        ) as f:
            prompt = f.read()
        self.assertNotIn("2024-25", prompt)
        self.assertIn("career_gap:", prompt)

    def test_trimmed_profile_keeps_career_gap(self):
        trimmed = orchestrator._trim_profile_yaml(PROFILE)
        self.assertIn('period: "2021-22"', trimmed)
        self.assertNotIn("floor", trimmed)


if __name__ == "__main__":
    unittest.main()
