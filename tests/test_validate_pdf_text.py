import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_pdf_text  # noqa: E402


def _resume():
    return {
        "SKILLS": ["Lifecycle & Retention Marketing: Email Automation, Segmentation"],
        "EXPERIENCE": [
            {"achievements": [
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
            ]},
        ],
    }


class TestValidatePdfText(unittest.TestCase):

    def test_no_warnings_when_everything_survives_intact(self):
        with patch("validate_pdf_text.extract_text", return_value=(
            "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows\n"
            "Lifecycle & Retention Marketing: Email Automation, Segmentation"
        )):
            self.assertEqual(validate_pdf_text.validate_pdf_text("fake.pdf", _resume()), [])

    def test_flags_a_bullet_missing_from_the_pdf_text_layer(self):
        with patch("validate_pdf_text.extract_text", return_value=(
            "Lifecycle & Retention Marketing: Email Automation, Segmentation"
        )):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", _resume())
            self.assertEqual(len(warnings), 1)
            self.assertIn("Recovered 3M", warnings[0])

    def test_tolerates_a_line_break_splitting_a_bullet_mid_sentence(self):
        # Real rendering can wrap a bullet across lines; that alone shouldn't
        # look like dropped content once whitespace is collapsed.
        with patch("validate_pdf_text.extract_text", return_value=(
            "Recovered 3M in dormant pipeline\nthrough CRM audits and reactivation workflows\n"
            "Lifecycle & Retention Marketing: Email Automation, Segmentation"
        )):
            self.assertEqual(validate_pdf_text.validate_pdf_text("fake.pdf", _resume()), [])

    def test_tolerates_typographic_substitutions(self):
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [{"achievements": ["Owned the team's 20-person rollout"]}],
        }
        # PDF extraction renders a curly apostrophe where the source JSON has a straight one.
        with patch("validate_pdf_text.extract_text", return_value="Owned the team’s 20-person rollout"):
            self.assertEqual(validate_pdf_text.validate_pdf_text("fake.pdf", resume), [])

    def test_extraction_failure_returns_single_warning_not_an_exception(self):
        with patch("validate_pdf_text.extract_text", side_effect=RuntimeError("corrupt PDF")):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", _resume())
            self.assertEqual(len(warnings), 1)
            self.assertIn("corrupt PDF", warnings[0])


if __name__ == "__main__":
    unittest.main()
