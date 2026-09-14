"""One filler list, shared by the cover letter and the resume's Why section;
the resume check is soft (a rewrite attempt, never a failed build)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import filler_phrases  # noqa: E402
import orchestrator  # noqa: E402
import validate_coverletter  # noqa: E402
import validate_resume  # noqa: E402


class TestFillerPhrases(unittest.TestCase):
    def test_softer_phrasings_are_caught(self):
        text = (
            "I cut latency 30%. These technical achievements underscore my commitment to reliable systems. "
            "Clear communication remains a core priority in my work."
        )
        self.assertEqual(len(filler_phrases.filler_sentences(text)), 2)

    def test_html_is_stripped_and_plain_facts_pass(self):
        self.assertEqual(filler_phrases.filler_sentences("<p><em>Cut processing time 30%.</em></p>"), [])
        self.assertEqual(len(filler_phrases.filler_sentences("<em>This is the core of my professional mission.</em>")), 1)

    def test_cover_letter_uses_the_shared_list(self):
        letter = {"body_paragraphs": ["This work underscores my commitment to quality."]}
        self.assertEqual(len(validate_coverletter._check_filler_lines(letter)), 1)

    def test_resume_why_filler_is_soft(self):
        v = validate_resume._check_why_filler({"WHY_TEXT": "<p>I am a team player who thrives. It is a testament to grit.</p>"})
        self.assertEqual(len(v), 2)
        fatal, soft = orchestrator.partition_violations(v)
        self.assertEqual(fatal, [])
        self.assertEqual(len(soft), 2)


if __name__ == "__main__":
    unittest.main()
