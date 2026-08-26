import json
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from render_txt import main, render_txt_from_json


class TestRenderTxt(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sample_data = {
            "NAME": "Alex Rivera",
            "TAGLINE": "Principal Systems Engineer",
            "LOCATION": "San Francisco, CA",
            "EMAIL": "alex.rivera@example.com",
            "SUMMARY_TEXT": "Experienced engineering leader with deep systems expertise.",
            "SKILLS": ["Languages: Python, Go, Rust", "Cloud: AWS, GCP"],
            "EXPERIENCE": [
                {
                    "title": "Lead Architect",
                    "company": "Tech Corp",
                    "period": "2021 - Present",
                    "location": "Remote",
                    "achievements": ["Scaled database cluster to 10k nodes."],
                }
            ],
            "EDUCATION": [
                {
                    "degree": "B.S. Computer Science",
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

    def test_render_txt_from_json(self):
        out_path = os.path.join(self.temp_dir.name, "resume.txt")
        text = render_txt_from_json(self.json_path, out_path)
        self.assertIn("ALEX RIVERA", text.upper())
        self.assertIn("Lead Architect", text)
        self.assertIn("TECH CORP", text)
        self.assertTrue(os.path.exists(out_path))

    def test_main_cli(self):
        out_path = os.path.join(self.temp_dir.name, "cli_resume.txt")
        code = main([self.json_path, "-o", out_path])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out_path))


if __name__ == "__main__":
    unittest.main()
