import json
import os
import tempfile
import unittest

from scripts.render_typst import generate_typst_markup, render_typst


class TestRenderTypst(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sample_data = {
            "NAME": "Alex Rivera",
            "TAGLINE": "Principal Systems Engineer",
            "PHONE": "555-0199",
            "EMAIL": "alex.rivera@example.com",
            "LOCATION": "San Francisco, CA",
            "LINKEDIN": "linkedin.com/in/alexrivera",
            "SUMMARY_TEXT": "Experienced engineering leader.",
            "SKILLS": ["Python", "Go", "Distributed Systems"],
            "EXPERIENCE": [
                {
                    "title": "Principal Architect",
                    "company": "Acme Corp",
                    "period": "2020 - Present",
                    "location": "San Francisco, CA",
                    "achievements": ["Scaled backend infrastructure."],
                }
            ],
            "EDUCATION": [
                {
                    "degree": "B.S. in Computer Science",
                    "institution": "Stanford University",
                    "year": "2018",
                }
            ],
        }
        self.json_path = os.path.join(self.temp_dir.name, "resume.json")
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.sample_data, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_typst_markup_standard(self):
        markup = generate_typst_markup(self.sample_data, template="standard")
        self.assertIn("Alex Rivera", markup)
        self.assertIn("Principal Systems Engineer", markup)
        self.assertIn("Acme Corp", markup)
        self.assertIn("Stanford University", markup)

    def test_generate_typst_markup_executive(self):
        markup = generate_typst_markup(self.sample_data, template="executive")
        self.assertIn("EXECUTIVE PROFILE", markup)
        self.assertIn("Libertinus Serif", markup)

    def test_generate_typst_markup_compact(self):
        markup = generate_typst_markup(self.sample_data, template="compact")
        self.assertIn("0.4in", markup)
        self.assertIn("SUMMARY", markup)

    def test_generate_typst_markup_tech(self):
        markup = generate_typst_markup(self.sample_data, template="tech")
        self.assertIn("01 // TECHNICAL SUMMARY", markup)
        self.assertIn("02 // CORE TECHNOLOGIES", markup)

    def test_render_typst_generates_source(self):
        pdf_path = os.path.join(self.temp_dir.name, "resume.pdf")
        typ_path = os.path.join(self.temp_dir.name, "resume.typ")
        result = render_typst(self.json_path, pdf_path, template="tech")
        self.assertTrue(result)
        self.assertTrue(os.path.exists(typ_path))


if __name__ == "__main__":
    unittest.main()
