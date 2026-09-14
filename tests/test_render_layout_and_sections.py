"""An empty Training & Certifications section is dropped entirely, and a
profile's resume_layout: relaxed adds spacing without touching the default."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import render_html  # noqa: E402

RESUME = {
    "NAME": "Test Person",
    "TAGLINE": "ANALYST | REPORTING",
    "SUMMARY_TEXT": "<strong>Analyst.</strong> Builds reports.",
    "SKILLS": [],
    "EXPERIENCE": [],
    "EDUCATION": [],
}


def rendered(resume, layout="compact"):
    with tempfile.TemporaryDirectory() as tmp, patch.object(render_html, "_profile_layout", return_value=layout):
        path = os.path.join(tmp, "out.html")
        render_html.render_html(resume, path)
        with open(path, encoding="utf-8") as f:
            return f.read()


class TestCertificationsSection(unittest.TestCase):
    def test_no_certifications_means_no_heading(self):
        self.assertNotIn("Training &amp; Certifications", rendered(dict(RESUME, CERTIFICATIONS=[])))
        self.assertNotIn("Training & Certifications", rendered(dict(RESUME, CERTIFICATIONS=[{"title": " "}])))
        self.assertNotIn("{{", rendered(RESUME))

    def test_certifications_render_under_their_heading(self):
        html = rendered(dict(RESUME, CERTIFICATIONS=[{"title": "AWS ML Specialty", "org": "AWS", "year": "2024"}]))
        self.assertIn("Training &amp; Certifications", html)
        self.assertIn("AWS ML Specialty", html)


class TestLayout(unittest.TestCase):
    def test_default_layout_adds_nothing(self):
        self.assertNotIn("line-height: 1.25", rendered(RESUME))

    def test_relaxed_layout_adds_spacing(self):
        self.assertIn("line-height: 1.25", rendered(RESUME, "relaxed"))

    def test_balanced_layout_raises_leading_only(self):
        html = rendered(RESUME, "balanced")
        self.assertIn("line-height: 1.2;", html)
        self.assertNotIn("line-height: 1.25", html)
        self.assertNotIn(".section { margin-bottom: 16px; }", html)

    def test_unknown_layout_falls_back_to_default(self):
        self.assertNotIn("line-height: 1.25", rendered(RESUME, "roomy"))


if __name__ == "__main__":
    unittest.main()
