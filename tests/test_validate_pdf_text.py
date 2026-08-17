import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import validate_pdf_text  # noqa: E402


def _resume():
    # The SKILLS label carries the "**Label:**" markdown the builder actually
    # emits -- an earlier version of this fixture omitted it, which is why the
    # markdown false-positive below went unnoticed in real runs.
    return {
        "SKILLS": [
            "**Lifecycle & Retention Marketing:** Email Automation, Segmentation"
        ],
        "EXPERIENCE": [
            {
                "achievements": [
                    "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
                ]
            },
        ],
    }


class TestValidatePdfText(unittest.TestCase):
    """B17: validate_pdf_text() now returns (fatal, advisories) instead of one
    warnings list, so a missing/unparseable PDF (fatal) can no longer read as
    just another soft advisory. Every case below except the extraction-failure
    one still expects fatal == [] and asserts against advisories."""

    def test_no_warnings_when_everything_survives_intact(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows\n"
                "Lifecycle & Retention Marketing: Email Automation, Segmentation"
            ),
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", _resume()), ([], [])
            )

    def test_flags_a_bullet_missing_from_the_pdf_text_layer(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Lifecycle & Retention Marketing: Email Automation, Segmentation"
            ),
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text(
                "fake.pdf", _resume()
            )
            self.assertEqual(fatal, [])
            self.assertEqual(len(advisories), 1)
            self.assertIn("Recovered 3M", advisories[0])

    def test_flags_a_dropped_summary_and_tagline(self):
        resume = {
            **_resume(),
            "TAGLINE": "Lifecycle Marketing Strategist",
            "SUMMARY_TEXT": "<strong>Drives</strong> retention through data-led campaigns.",
        }
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows\n"
                "Lifecycle & Retention Marketing: Email Automation, Segmentation"
            ),
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(fatal, [])
            self.assertEqual(len(advisories), 2)
            self.assertTrue(any("Tagline" in a for a in advisories))
            self.assertTrue(any("Summary" in a for a in advisories))

    def test_blank_why_text_is_not_flagged(self):
        # WHY_TEXT is intentionally '' on most builds (section omitted to save
        # space) -- that must never be reported as dropped content.
        resume = {**_resume(), "WHY_TEXT": ""}
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows\n"
                "Lifecycle & Retention Marketing: Email Automation, Segmentation"
            ),
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", resume), ([], [])
            )

    def test_tolerates_a_line_break_splitting_a_bullet_mid_sentence(self):
        # Real rendering can wrap a bullet across lines; that alone shouldn't
        # look like dropped content once whitespace is collapsed.
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Recovered 3M in dormant pipeline\nthrough CRM audits and reactivation workflows\n"
                "Lifecycle & Retention Marketing: Email Automation, Segmentation"
            ),
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", _resume()), ([], [])
            )

    def test_tolerates_typographic_substitutions(self):
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [{"achievements": ["Owned the team's 20-person rollout"]}],
        }
        # PDF extraction renders a curly apostrophe where the source JSON has a straight one.
        with patch(
            "validate_pdf_text.extract_text",
            return_value="Owned the team’s 20-person rollout",
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", resume), ([], [])
            )

    def test_markdown_emphasis_is_not_mistaken_for_dropped_content(self):
        # The renderer turns "**Label:**" into <strong>, so no asterisk ever
        # reaches the PDF text layer. Comparing the raw JSON string against it
        # flagged all four real skills lines on every single run.
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows\n"
                "Lifecycle & Retention Marketing: Email Automation, Segmentation"
            ),
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", _resume()), ([], [])
            )

    def test_html_emphasis_is_not_mistaken_for_dropped_content(self):
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [
                {"achievements": ["Owned the <strong>full</strong> rollout"]}
            ],
        }
        with patch(
            "validate_pdf_text.extract_text", return_value="Owned the full rollout"
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", resume), ([], [])
            )

    def test_ligature_corruption_is_reported_as_its_own_named_warning(self):
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [{"achievements": ["Built AI-assisted workflows"]}],
        }
        with patch(
            "validate_pdf_text.extract_text", return_value="Built AI-assisted workﬂows"
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(fatal, [])
            self.assertEqual(len(advisories), 1)
            # Must name the actual defect -- "not found intact" sent a previous
            # reviewer hunting for missing text that was never missing.
            self.assertIn("ligature", advisories[0].lower())
            self.assertIn("workflows", advisories[0])

    def test_ligature_corruption_does_not_also_report_content_as_missing(self):
        # The content IS present; only its encoding is wrong. Reporting it as
        # missing too would double-count and re-bury the real signal.
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [{"achievements": ["Built AI-assisted workflows"]}],
        }
        with patch(
            "validate_pdf_text.extract_text", return_value="Built AI-assisted workﬂows"
        ):
            _, advisories = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertFalse([w for w in advisories if "not found intact" in w])

    def test_repeated_ligature_words_are_listed_once(self):
        resume = {"SKILLS": [], "EXPERIENCE": [{"achievements": ["Ran workflows"]}]}
        with patch(
            "validate_pdf_text.extract_text",
            return_value="Ran workﬂows and more workﬂows and workﬂows",
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(fatal, [])
            self.assertEqual(len(advisories), 1)
            self.assertEqual(advisories[0].count("workflows"), 1)

    def test_clean_pdf_reports_no_ligature_warning(self):
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [{"achievements": ["Built AI-assisted workflows"]}],
        }
        with patch(
            "validate_pdf_text.extract_text", return_value="Built AI-assisted workflows"
        ):
            self.assertEqual(
                validate_pdf_text.validate_pdf_text("fake.pdf", resume), ([], [])
            )

    def test_genuinely_missing_content_is_still_flagged(self):
        # Guard against the normalization above becoming so permissive that
        # real dropped content stops being caught.
        resume = {
            "SKILLS": [],
            "EXPERIENCE": [{"achievements": ["Recovered 3M in dormant pipeline"]}],
        }
        with patch(
            "validate_pdf_text.extract_text", return_value="Something else entirely"
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text("fake.pdf", resume)
            self.assertEqual(fatal, [])
            self.assertEqual(len(advisories), 1)
            self.assertIn("not found intact", advisories[0])

    def test_extraction_failure_is_reported_as_fatal_not_an_advisory(self):
        # B17: a missing/unparseable PDF is categorically different from a
        # soft "line not found" note -- it must come back as `fatal`, not
        # buried in `advisories` where a caller could print it and proceed.
        with patch(
            "validate_pdf_text.extract_text", side_effect=RuntimeError("corrupt PDF")
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text(
                "fake.pdf", _resume()
            )
            self.assertEqual(advisories, [])
            self.assertEqual(len(fatal), 1)
            self.assertIn("corrupt PDF", fatal[0])

    def test_no_keyword_warning_when_keywords_not_corrupted(self):
        resume = {
            "SKILLS": ["**Lifecycle Marketing:** Salesforce, Hubspot"],
            "EXPERIENCE": [],
        }
        jd_keywords = {"tools": ["Salesforce"], "hard_skills": [], "core_functions": []}
        with patch(
            "validate_pdf_text.extract_text",
            return_value="Lifecycle Marketing: Salesforce, Hubspot",
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text(
                "fake.pdf", resume, jd_keywords
            )
            self.assertEqual(fatal, [])
            self.assertEqual(advisories, [])

    def test_flags_corrupted_keyword_in_pdf(self):
        resume = {
            "SKILLS": ["**Lifecycle Marketing:** Salesforce, Hubspot"],
            "EXPERIENCE": [],
        }
        jd_keywords = {"tools": ["Salesforce"], "hard_skills": [], "core_functions": []}
        with patch(
            "validate_pdf_text.extract_text",
            return_value="Lifecycle Marketing: Salesf0rce, Hubspot",
        ):
            fatal, advisories = validate_pdf_text.validate_pdf_text(
                "fake.pdf", resume, jd_keywords
            )
            self.assertEqual(fatal, [])
            self.assertEqual(len(advisories), 2)
            keyword_corrupt_warns = [
                w for w in advisories if "ATS Keyword corrupted" in w
            ]
            self.assertEqual(len(keyword_corrupt_warns), 1)
            self.assertIn("Salesforce", keyword_corrupt_warns[0])


def _letter():
    return {
        "company_name": "Abnormal AI",
        "greeting": "Dear Hiring Team,",
        "body_paragraphs": [
            "I have spent the last decade building content workflows that hold up under audit.",
            "Your certification program is the part of the role I would want to own first.",
        ],
        "sign_off": "Sincerely,",
    }


class TestValidateCoverletterPdfText(unittest.TestCase):
    """B9: the cover letter is half of every application package and had no
    text-layer verification at all. It cannot reuse the resume-shaped check --
    letter_data has no EXPERIENCE or SKILLS key, so that function would find
    nothing to look for and return clean on a corrupt file."""

    def test_no_warnings_when_everything_survives_intact(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Dear Hiring Team,\n"
                "I have spent the last decade building content workflows that hold up under audit.\n"
                "Your certification program is the part of the role I would want to own first.\n"
            ),
        ):
            self.assertEqual(
                validate_pdf_text.validate_coverletter_pdf_text("fake.pdf", _letter()),
                [],
            )

    def test_flags_a_dropped_paragraph(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Dear Hiring Team,\n"
                "I have spent the last decade building content workflows that hold up under audit.\n"
            ),
        ):
            warnings = validate_pdf_text.validate_coverletter_pdf_text(
                "fake.pdf", _letter()
            )
            self.assertEqual(len(warnings), 1)
            self.assertIn("Your certification program", warnings[0])

    def test_flags_a_dropped_greeting(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "I have spent the last decade building content workflows that hold up under audit.\n"
                "Your certification program is the part of the role I would want to own first.\n"
            ),
        ):
            warnings = validate_pdf_text.validate_coverletter_pdf_text(
                "fake.pdf", _letter()
            )
            self.assertEqual(len(warnings), 1)
            self.assertIn("Dear Hiring Team", warnings[0])

    def test_ligature_corruption_is_reported_first(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Dear Hiring Team,\n"
                "I have spent the last decade building content workﬂows that hold up under audit.\n"
                "Your certiﬁcation program is the part of the role I would want to own first.\n"
            ),
        ):
            warnings = validate_pdf_text.validate_coverletter_pdf_text(
                "fake.pdf", _letter()
            )
            self.assertTrue(warnings)
            self.assertIn("ligature", warnings[0].lower())

    def test_wrapped_paragraph_is_not_reported_as_missing(self):
        with patch(
            "validate_pdf_text.extract_text",
            return_value=(
                "Dear Hiring Team,\n"
                "I have spent the last decade building\ncontent workflows that hold up under audit.\n"
                "Your certification program is the part\nof the role I would want to own first.\n"
            ),
        ):
            self.assertEqual(
                validate_pdf_text.validate_coverletter_pdf_text("fake.pdf", _letter()),
                [],
            )

    def test_extraction_failure_returns_single_warning_not_an_exception(self):
        with patch("validate_pdf_text.extract_text", side_effect=RuntimeError("boom")):
            warnings = validate_pdf_text.validate_coverletter_pdf_text(
                "fake.pdf", _letter()
            )
            self.assertEqual(len(warnings), 1)
            self.assertIn("cover-letter", warnings[0])

    def test_no_coverletter_keyword_warning_when_not_corrupted(self):
        letter = {
            "body_paragraphs": ["I have experience with Salesforce."],
        }
        jd_keywords = {"tools": ["Salesforce"], "hard_skills": [], "core_functions": []}
        with patch(
            "validate_pdf_text.extract_text",
            return_value="I have experience with Salesforce.",
        ):
            warnings = validate_pdf_text.validate_coverletter_pdf_text(
                "fake.pdf", letter, jd_keywords
            )
            self.assertEqual(warnings, [])

    def test_flags_corrupted_coverletter_keyword(self):
        letter = {
            "body_paragraphs": ["I have experience with Salesforce."],
        }
        jd_keywords = {"tools": ["Salesforce"], "hard_skills": [], "core_functions": []}
        with patch(
            "validate_pdf_text.extract_text",
            return_value="I have experience with Salesf0rce.",
        ):
            warnings = validate_pdf_text.validate_coverletter_pdf_text(
                "fake.pdf", letter, jd_keywords
            )
            self.assertEqual(len(warnings), 2)
            keyword_corrupt_warns = [
                w for w in warnings if "ATS Keyword corrupted in Cover Letter" in w
            ]
            self.assertEqual(len(keyword_corrupt_warns), 1)
            self.assertIn("Salesforce", keyword_corrupt_warns[0])


if __name__ == "__main__":
    unittest.main()
