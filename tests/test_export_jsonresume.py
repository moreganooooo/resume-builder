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

import export_jsonresume


class TestExportJsonResume(unittest.TestCase):
    def setUp(self):
        self.resume_data = {
            "CONTACT": {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "555-1234",
                "location": "New York, NY",
                "linkedin": "https://linkedin.com/in/janedoe",
            },
            "SUMMARY_TEXT": "<strong>Experienced systems engineer with 8+ years experience.</strong>",
            "EXPERIENCE": [
                {
                    "company": "Acme Corp",
                    "role": "Lead Architect",
                    "dates": "2020 - Present",
                    "bullets": ["Designed distributed queue reducing latency."],
                }
            ],
            "EDUCATION": [
                {
                    "institution": "MIT",
                    "degree": "B.S. Computer Science",
                    "dates": "2018",
                }
            ],
            "SKILLS": [{"category": "Languages", "items": ["Python", "Rust"]}],
        }

    def test_convert_to_json_resume(self):
        json_res = export_jsonresume.convert_to_json_resume(self.resume_data)
        self.assertEqual(json_res["basics"]["name"], "Jane Doe")
        self.assertEqual(json_res["basics"]["email"], "jane@example.com")
        self.assertNotIn("<strong>", json_res["basics"]["summary"])
        self.assertEqual(len(json_res["work"]), 1)
        self.assertEqual(json_res["work"][0]["name"], "Acme Corp")
        self.assertEqual(len(json_res["skills"]), 1)
        self.assertEqual(json_res["skills"][0]["name"], "Languages")

    def test_export_json_resume_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            out_file = export_jsonresume.export_json_resume_file(
                self.resume_data, temp_path
            )
            self.assertEqual(out_file, temp_path)
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                self.assertEqual(loaded["basics"]["name"], "Jane Doe")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
