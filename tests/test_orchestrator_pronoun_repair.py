"""Targeted Pronoun Removal repair -- see orchestrator._micro_strip_pronoun /
repair_violations_surgically's "9. Targeted Pronoun Removal Repair" block.

Covers a real failure mode observed live 2026-09-04: after the previous
session's temperature-forcing fix plus the metric-dedup, keyword-density,
and bullet-count repairs resolved everything else in a real build, a
"Pronoun found outside the Why section" violation (a bullet reading
"...to lead brand design at his next venture...") alone survived all 4
attempts unchanged, because validate_resume._check_pronouns_outside_why()
had no corresponding repair at all -- same gap class as bullet count.

Uses synthetic resume content throughout -- not the active profile's real
employers/bullets -- per tests/test_no_operator_identity.py's "use
synthetic data, not the operator's own history" rule.
"""

import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402


class TestPronounRepairBullet(unittest.TestCase):

    def _resume(self):
        return {
            "SUMMARY_TEXT": "Generalist marketer with a track record of measurable growth.",
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Recruited by the CEO to lead brand design at his next venture.",
                        "Did other unrelated work.",
                    ],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }

    @patch("orchestrator.GeminiClient.generate")
    def test_bullet_pronoun_is_rewritten(self, mock_generate):
        resume_data = self._resume()
        violations = validate_resume._check_pronouns_outside_why(resume_data)
        self.assertTrue(any(v.startswith("Pronoun found outside") for v in violations))

        mock_generate.return_value = (
            "Recruited by the CEO to lead brand design at Acme Robotics' next venture.",
            {},
        )

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        achievements = fixed["EXPERIENCE"][0]["achievements"]
        self.assertNotIn(
            "Recruited by the CEO to lead brand design at his next venture.",
            achievements,
        )
        self.assertEqual(achievements[1], "Did other unrelated work.")
        self.assertFalse(any(v.startswith("Pronoun found outside") for v in remaining))

    @patch("orchestrator.GeminiClient.generate")
    def test_unparseable_response_leaves_resume_unchanged(self, mock_generate):
        resume_data = self._resume()
        violations = validate_resume._check_pronouns_outside_why(resume_data)

        mock_generate.side_effect = Exception("simulated API failure")

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        self.assertEqual(
            fixed["EXPERIENCE"][0]["achievements"],
            resume_data["EXPERIENCE"][0]["achievements"],
        )
        self.assertTrue(any(v.startswith("Pronoun found outside") for v in remaining))


class TestPronounRepairSummary(unittest.TestCase):

    @patch("orchestrator.GeminiClient.generate")
    def test_summary_pronoun_is_rewritten(self, mock_generate):
        resume_data = {
            "SUMMARY_TEXT": "Content strategist who built her own agency's playbook.",
            "EXPERIENCE": [],
            "SKILLS": [],
        }
        violations = validate_resume._check_pronouns_outside_why(resume_data)
        self.assertTrue(any(v.startswith("Pronoun found outside") for v in violations))

        mock_generate.return_value = (
            "Content strategist who built the agency's playbook.",
            {},
        )

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        self.assertEqual(
            fixed["SUMMARY_TEXT"], "Content strategist who built the agency's playbook."
        )
        self.assertFalse(any(v.startswith("Pronoun found outside") for v in remaining))


if __name__ == "__main__":
    unittest.main()
