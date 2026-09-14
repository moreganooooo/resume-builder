"""Patents section, opt-in header links, and the cover letter's role title
(named and bolded in paragraph one), bold addressee line, and filler check."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402
import render_coverletter  # noqa: E402
import render_html  # noqa: E402
import validate_coverletter  # noqa: E402

PATENTS = [{"title": "Method for Sensing a Thing", "number": "U.S. Patent 1,234,567 B2"}]
RESUME = {"NAME": "Test Person", "TAGLINE": "ANALYST | REPORTING", "SUMMARY_TEXT": "Analyst.",
          "SKILLS": [], "EXPERIENCE": [], "EDUCATION": []}


def rendered(resume):
    with tempfile.TemporaryDirectory() as tmp, patch.object(render_html, "_profile_layout", return_value="compact"):
        path = os.path.join(tmp, "out.html")
        render_html.render_html(resume, path)
        with open(path, encoding="utf-8") as f:
            return f.read()


class TestResumeParts(unittest.TestCase):
    def test_link_display_strips_scheme_www_and_slash(self):
        self.assertEqual(render_html.link_display("https://www.linkedin.com/in/x/"), "linkedin.com/in/x")
        self.assertEqual(render_html.link_display("linkedin.com/in/y"), "linkedin.com/in/y")

    def test_patents_section_only_when_present(self):
        self.assertEqual(render_html.build_patents_section_html([]), "")
        html = rendered(dict(RESUME, PATENTS=PATENTS, HEADER_LINKS=[]))
        self.assertIn(">Patents<", html)
        self.assertIn("U.S. Patent 1,234,567 B2", html)
        self.assertNotIn(">Patents<", rendered(dict(RESUME, PATENTS=[], HEADER_LINKS=[])))

    def test_header_links_row_only_when_opted_in(self):
        html = rendered(dict(RESUME, HEADER_LINKS=["https://github.com/someone/"]))
        self.assertIn("<span>github.com/someone</span>", html)
        self.assertEqual(rendered(dict(RESUME, HEADER_LINKS=[])).count('class="contact-row"'), 1)
        self.assertNotIn("{{", rendered(dict(RESUME, HEADER_LINKS=[])))


class TestCoverLetterParts(unittest.TestCase):
    def test_first_address_line_is_bold(self):
        html = render_coverletter.build_recipient_block_html("Acme", location="Austin, TX")
        self.assertTrue(html.startswith('<div class="letter-address"><strong>Acme Hiring Team</strong><br>'))

    def test_role_title_bolded_once_in_first_paragraph_only(self):
        html = render_coverletter.build_body_paragraphs_html(
            ["As a data scientist applying for the Data Scientist role, I bring data.", "Data Scientist again."],
            "Data Scientist",
        )
        first, second = html.split("\n")
        self.assertEqual(first.count("<strong>"), 1)
        self.assertIn("<strong>data scientist</strong>", first)
        self.assertNotIn("<strong>", second)

    def test_role_title_check(self):
        letter = {"body_paragraphs": ["I am applying for the Senior Analyst role.", "More."]}
        self.assertEqual(validate_coverletter._check_role_title(letter, "Senior Analyst"), [])
        self.assertEqual(len(validate_coverletter._check_role_title(letter, "Data Engineer")), 1)
        self.assertEqual(validate_coverletter._check_role_title(letter, ""), [])

    def test_filler_lines_are_flagged(self):
        letter = {"body_paragraphs": ["I cut latency 30% at Acme. I thrive in high-stakes environments."]}
        flagged = validate_coverletter._check_filler_lines(letter)
        self.assertEqual(len(flagged), 1)
        self.assertIn("thrive", flagged[0])
        self.assertEqual(validate_coverletter._check_filler_lines({"body_paragraphs": ["I cut latency 30%."]}), [])


class TestRoleTitle(unittest.TestCase):
    def test_posting_title_is_trimmed(self):
        self.assertEqual(orchestrator._coverletter_role_title({"job_title": "Content Strategist (Remote)"}, "x"),
                         "Content Strategist")

    def test_falls_back_to_resume_tagline_in_title_case(self):
        with patch.object(orchestrator, "_read_matching_resume_tagline", return_value="SENIOR DATA SCIENTIST | ML"):
            self.assertEqual(orchestrator._coverletter_role_title({}, "x"), "Senior Data Scientist")
        with patch.object(orchestrator, "_read_matching_resume_tagline", return_value="ML ENGINEER | X"):
            self.assertEqual(orchestrator._coverletter_role_title({}, "x"), "ML Engineer")


if __name__ == "__main__":
    unittest.main()
