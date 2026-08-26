import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import interview_prep


class TestInterviewPrep(unittest.TestCase):
    def test_synthesize_star_story(self):
        bullet_dict = {
            "bullet": "Architected event-driven data pipeline cutting latency 45%",
            "company": "Shopify",
            "metrics": "45% latency cut",
        }
        star = interview_prep.synthesize_star_story(bullet_dict)
        self.assertEqual(star["title"], "Project at Shopify")
        self.assertIn("Architected event-driven", star["task"])
        self.assertIn("45% latency cut", star["result"])

    def test_generate_interview_prep_dossier(self):
        bullets = [
            {
                "bullet": "Built telemetry subsystem used by 500k DAUs",
                "company": "Datadog",
            }
        ]
        skills = ["Distributed Systems", "Go", "Kubernetes"]
        dossier = interview_prep.generate_interview_prep_dossier(
            "Principal SRE", "Datadog", bullets, skills
        )
        self.assertIn("Interview Preparation Dossier: Principal SRE", dossier)
        self.assertIn("Distributed Systems", dossier)
        self.assertIn("Story #1", dossier)
        self.assertIn("Reverse-Interview Questions", dossier)

    def test_write_interview_prep_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            temp_path = f.name

        try:
            out_file = interview_prep.write_interview_prep_file(
                "Staff Eng", "Apple", [], ["Swift"], temp_path
            )
            self.assertEqual(out_file, temp_path)
            self.assertTrue(os.path.exists(temp_path))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
