"""What the fit evaluation is allowed to know about the candidate.

_trim_profile_yaml() decides which slices of profile.yml reach
evaluate_capability.md and evaluate_recruiter.md. That makes it a
correctness surface, not a formatting detail: a section left out is a
question the prompt asks with no data to answer it, and the model
answers anyway.

The concrete case: evaluate_recruiter.md lists "a required degree the
candidate doesn't hold" as a hard_blocker, while the candidate's degrees
and certifications live under fixed_credentials -- which the trim
dropped.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

SAMPLE = """\
candidate:
  full_name: "Someone Else"
  email: "nobody@example.com"
target_roles:
  primary:
    - "Content Strategist"
deal_breakers:
  - "Requires a clearance"
proof_points:
  - "Should not be sent"
compensation:
  minimum: "$45K"
cv:
  page_size: letter
fixed_credentials:
  certifications:
    - name: "Email Marketing Software Certification"
  education:
    - institution: "State University"
      credential: "BS, Journalism"
voice_calibration_example: "Should not be sent either"
"""


class TestTrimProfileYaml(unittest.TestCase):
    def setUp(self):
        self.trimmed = orchestrator._trim_profile_yaml(SAMPLE)

    def test_credentials_reach_the_evaluator(self):
        """Otherwise the degree hard_blocker check has nothing to compare to."""
        self.assertIn("fixed_credentials:", self.trimmed)
        self.assertIn("BS, Journalism", self.trimmed)
        self.assertIn("Email Marketing Software Certification", self.trimmed)

    def test_identity_and_bulk_sections_are_still_dropped(self):
        for value in ("nobody@example.com", "Should not be sent"):
            with self.subTest(value=value):
                self.assertNotIn(value, self.trimmed)

    def test_credentials_are_bounded_at_the_end_of_the_file(self):
        """fixed_credentials is the last top-level key.

        Without a stop after it the trim runs to EOF and quietly grows
        what every evaluation sends.
        """
        self.assertNotIn("Should not be sent either", self.trimmed)

    def test_deal_breakers_still_survive(self):
        self.assertIn("Requires a clearance", self.trimmed)


if __name__ == "__main__":
    unittest.main()
