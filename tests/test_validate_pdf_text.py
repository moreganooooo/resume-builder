import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_pdf_text  # noqa: E402


def _resume():
    # The SKILLS label carries the "**Label:**" markdown the builder actually
    # emits -- an earlier version of this fixture omitted it, which is why the
    # markdown false-positive below went unnoticed in real runs.
    return {
        "SKILLS": ["**Lifecycle & Retention Marketing:** Email Automation, Segmentation"],
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

    def test_markdown_emphasis_is_not_mistaken_for_dropped_content(self):
        # The renderer turns "**Label:**" into <strong>, so no asterisk ever
        # reaches the PDF text layer. Comparing the raw JSON string against it
        # flagged all four real skills lines on every single run.
        with patch("validate_pdf_text.extract_text", return_value=(
            "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows\n"
            "Lifecycle & Retention Marketing: Email Automation, Segmentation"
        )):
            self.assertEqual(validate_pdf_text.validate_pdf_text("fake.pdf", _resume()), [])

    def test_html_emphasis_is_not_mistaken_for_dropped_content(self):
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Owned the <strong>full</strong> rollout"]}]}
        with patch("validate_pdf_text.extract_text", return_value="Owned the full rollout"):
            self.assertEqual(validate_pdf_text.validate_pdf_text("fake.pdf", resume), [])

    def test_ligature_corruption_is_reported_as_its_own_named_warning(self):
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Built AI-assisted workflows"]}]}
        with patch("validate_pdf_text.extract_text", return_value="Built AI-assisted workﬂows"):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(len(warnings), 1)
            # Must name the actual defect -- "not found intact" sent a previous
            # reviewer hunting for missing text that was never missing.
            self.assertIn("ligature", warnings[0].lower())
            self.assertIn("workflows", warnings[0])

    def test_ligature_corruption_does_not_also_report_content_as_missing(self):
        # The content IS present; only its encoding is wrong. Reporting it as
        # missing too would double-count and re-bury the real signal.
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Built AI-assisted workflows"]}]}
        with patch("validate_pdf_text.extract_text", return_value="Built AI-assisted workﬂows"):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertFalse([w for w in warnings if "not found intact" in w])

    def test_repeated_ligature_words_are_listed_once(self):
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Ran workflows"]}]}
        with patch("validate_pdf_text.extract_text", return_value="Ran workﬂows and more workﬂows and workﬂows"):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].count("workflows"), 1)

    def test_clean_pdf_reports_no_ligature_warning(self):
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Built AI-assisted workflows"]}]}
        with patch("validate_pdf_text.extract_text", return_value="Built AI-assisted workflows"):
            self.assertEqual(validate_pdf_text.validate_pdf_text("fake.pdf", resume), [])

    def test_genuinely_missing_content_is_still_flagged(self):
        # Guard against the normalization above becoming so permissive that
        # real dropped content stops being caught.
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Recovered 3M in dormant pipeline"]}]}
        with patch("validate_pdf_text.extract_text", return_value="Something else entirely"):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(len(warnings), 1)
            self.assertIn("not found intact", warnings[0])

    def test_extraction_failure_returns_single_warning_not_an_exception(self):
        with patch("validate_pdf_text.extract_text", side_effect=RuntimeError("corrupt PDF")):
            warnings = validate_pdf_text.validate_pdf_text("fake.pdf", _resume())
            self.assertEqual(len(warnings), 1)
            self.assertIn("corrupt PDF", warnings[0])


if __name__ == "__main__":
    unittest.main()
