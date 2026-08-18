import json
import os
import tempfile
import unittest

from scripts.render_txt import main, render_txt_from_json


class TestRenderTxt(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sample_data = {
            "NAME": "Morgan Escott",
            "TAGLINE": "Principal Systems Engineer",
            "LOCATION": "San Francisco, CA",
            "EMAIL": "morgan@example.com",
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
        self.assertIn("MORGAN ESCOTT", text.upper())
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
