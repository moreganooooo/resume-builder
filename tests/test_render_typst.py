"""Tests for render_typst.py's escaping and markup generation."""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import render_typst  # noqa: E402


class TestEscapeTypst(unittest.TestCase):

    def test_escapes_all_six_special_characters(self):
        raw = "Senior Manager [Growth] @ Acme_Corp ($100k #1)"
        escaped = render_typst._escape_typst(raw)
        self.assertIn("\\[Growth\\]", escaped)
        self.assertIn("Acme\\_Corp", escaped)
        self.assertIn("\\$100k", escaped)
        self.assertIn("\\#1", escaped)
        self.assertIn("\\@", escaped)

    def test_strips_html_tags(self):
        self.assertEqual(render_typst._escape_typst("<b>bold</b> text"), "bold text")

    def test_converts_markdown_bold_to_typst_bold(self):
        self.assertEqual(render_typst._escape_typst("**important**"), "*important*")

    def test_empty_and_none_input_returns_empty_string(self):
        self.assertEqual(render_typst._escape_typst(""), "")
        self.assertEqual(render_typst._escape_typst(None), "")

    def test_plain_text_with_no_special_chars_is_unchanged(self):
        self.assertEqual(
            render_typst._escape_typst("Marketing Manager"), "Marketing Manager"
        )

    def test_bold_conversion_happens_before_escaping_so_asterisks_survive(self):
        # ** -> * conversion must not itself get escaped afterward.
        result = render_typst._escape_typst("**Q4_2025**")
        self.assertEqual(result, "*Q4\\_2025*")


class TestGenerateTypstMarkup(unittest.TestCase):

    def test_minimal_resume_produces_no_raw_unescaped_special_chars_in_bullets(self):
        data = {
            "NAME": "Jane Doe",
            "SUMMARY_TEXT": "Growth marketer [B2B] focused on $1M+ pipelines.",
            "SKILLS": ["SQL", "A/B_Testing"],
            "EXPERIENCE": [
                {
                    "title": "Marketing Manager",
                    "company": "Acme_Corp",
                    "period": "2020-2023",
                    "location": "Remote",
                    "achievements": [
                        "Grew pipeline by $500K [enterprise segment] #1 team"
                    ],
                }
            ],
            "EDUCATION": [{"degree": "B.A.", "institution": "State U", "year": "2015"}],
        }
        markup = render_typst.generate_typst_markup(data)
        self.assertIn("Jane Doe", markup)
        # The bullet's raw special characters must appear only in escaped form.
        self.assertIn("\\$500K \\[enterprise segment\\] \\#1", markup)
        self.assertIn("Acme\\_Corp", markup)

    def test_handles_missing_optional_sections_gracefully(self):
        markup = render_typst.generate_typst_markup({"NAME": "Jane Doe"})
        self.assertIn("Jane Doe", markup)
        self.assertNotIn("== Professional Experience", markup)
        self.assertNotIn("== Education", markup)

    def test_contact_line_joins_only_present_fields(self):
        markup = render_typst.generate_typst_markup(
            {
                "NAME": "Jane Doe",
                "EMAIL": "jane@example.com",
                "PHONE": "",
                "LOCATION": "Austin, TX",
                "LINKEDIN": "",
            }
        )
        # @ is one of the six escaped Typst symbols, so it's escaped here too.
        self.assertIn("jane\\@example.com | Austin, TX", markup)


if __name__ == "__main__":
    unittest.main()
