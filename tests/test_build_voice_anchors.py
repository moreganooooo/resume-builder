import csv
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import build_voice_anchors  # noqa: E402


class TestBuildVoiceAnchors(unittest.TestCase):

    def setUp(self):
        self.tmp_csv = os.path.join(os.path.dirname(__file__), "_tmp_application_answers_index.csv")
        with open(self.tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "Filename", "Prompt / Topic", "Themes & Highlights",
                "Reusability Tags", "Answer Length", "Strong For", "Quote Worth Pulling",
            ])
            w.writeheader()
            w.writerow({
                "Filename": "x.pdf", "Prompt / Topic": "Why a good fit",
                "Themes & Highlights": "Systems + storytelling.",
                "Reusability Tags": "CRM", "Answer Length": "", "Strong For": "",
                "Quote Worth Pulling": "I love building systems that work quietly in the background.",
            })
            w.writerow({
                "Filename": "x.pdf", "Prompt / Topic": "Prioritizing tasks",
                "Themes & Highlights": "Calm execution under pressure.",
                "Reusability Tags": "Ops", "Answer Length": "", "Strong For": "",
                "Quote Worth Pulling": "",
            })

    def tearDown(self):
        if os.path.exists(self.tmp_csv):
            os.remove(self.tmp_csv)

    def test_quote_line_included_when_present(self):
        content = build_voice_anchors.build_voice_anchors(self.tmp_csv)
        self.assertIn("### Why a good fit", content)
        self.assertIn("Systems + storytelling.", content)
        self.assertIn("> I love building systems that work quietly in the background.", content)

    def test_quote_line_omitted_when_absent(self):
        content = build_voice_anchors.build_voice_anchors(self.tmp_csv)
        self.assertIn("### Prioritizing tasks", content)
        section = content.split("### Prioritizing tasks")[1].split("###")[0]
        self.assertNotIn(">", section)


if __name__ == "__main__":
    unittest.main()
