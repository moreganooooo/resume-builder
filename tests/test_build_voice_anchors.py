import csv
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import build_voice_anchors  # noqa: E402


class TestBuildVoiceAnchors(unittest.TestCase):

    def setUp(self):
        self.tmp_csv = os.path.join(
            os.path.dirname(__file__), "_tmp_application_answers_index.csv"
        )
        with open(self.tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "Filename",
                    "Prompt / Topic",
                    "Themes & Highlights",
                    "Reusability Tags",
                    "Answer Length",
                    "Strong For",
                    "Quote Worth Pulling",
                ],
            )
            w.writeheader()
            w.writerow(
                {
                    "Filename": "x.pdf",
                    "Prompt / Topic": "Why a good fit",
                    "Themes & Highlights": "Systems + storytelling.",
                    "Reusability Tags": "CRM",
                    "Answer Length": "",
                    "Strong For": "",
                    "Quote Worth Pulling": "I love building systems that work quietly in the background.",
                }
            )
            w.writerow(
                {
                    "Filename": "x.pdf",
                    "Prompt / Topic": "Prioritizing tasks",
                    "Themes & Highlights": "Calm execution under pressure.",
                    "Reusability Tags": "Ops",
                    "Answer Length": "",
                    "Strong For": "",
                    "Quote Worth Pulling": "",
                }
            )

    def tearDown(self):
        if os.path.exists(self.tmp_csv):
            os.remove(self.tmp_csv)

    def test_quote_line_included_when_present(self):
        content = build_voice_anchors.build_voice_anchors(self.tmp_csv)
        self.assertIn("### Why a good fit", content)
        self.assertIn(
            "> I love building systems that work quietly in the background.", content
        )

    def test_third_person_paraphrase_is_dropped(self):
        # "Themes & Highlights" is written for a human skimming the index,
        # not a specimen of this candidate's actual voice -- it teaches a
        # model nothing and shouldn't survive into the output (B30,
        # phase-9-backlog.md).
        content = build_voice_anchors.build_voice_anchors(self.tmp_csv)
        self.assertNotIn("Systems + storytelling.", content)
        self.assertNotIn("Calm execution under pressure.", content)

    def test_topic_with_no_quote_is_omitted_entirely(self):
        # No verbatim signal to offer -- this file's job is specimens, not
        # topical coverage, so a quote-less row contributes nothing here.
        content = build_voice_anchors.build_voice_anchors(self.tmp_csv)
        self.assertNotIn("### Prioritizing tasks", content)

    def test_main_missing_index(self):
        from unittest.mock import patch

        with patch.object(build_voice_anchors, "INDEX_CSV", "/nonexistent/answers.csv"):
            with self.assertRaises(SystemExit) as cm:
                build_voice_anchors.main()
            self.assertEqual(cm.exception.code, 1)

    def test_main_success(self):
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "application-answers-index.csv")
            output = os.path.join(tmpdir, "voice-anchors.md")
            with open(source, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "Filename",
                        "Prompt / Topic",
                        "Themes & Highlights",
                        "Reusability Tags",
                        "Answer Length",
                        "Strong For",
                        "Quote Worth Pulling",
                    ],
                )
                w.writeheader()
                w.writerow(
                    {
                        "Prompt / Topic": "Teamwork",
                        "Quote Worth Pulling": "I value team velocity.",
                    }
                )

            with (
                patch.object(build_voice_anchors, "INDEX_CSV", source),
                patch.object(build_voice_anchors, "OUTPUT_MD", output),
            ):
                build_voice_anchors.main()
                self.assertTrue(os.path.exists(output))
                with open(output, "r", encoding="utf-8") as f:
                    text = f.read()
                    self.assertIn("### Teamwork", text)
                    self.assertIn("I value team velocity.", text)


if __name__ == "__main__":
    unittest.main()
