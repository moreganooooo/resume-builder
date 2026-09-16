import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


class TestWordCountFixGuidance(unittest.TestCase):
    def test_short_letter_gets_explicit_target(self):
        g = orchestrator._word_count_fix_guidance(
            ["Expected 240-360 words across body paragraphs, got 184"]
        )
        self.assertIn("about 300", g)
        self.assertIn("roughly 116", g)

    def test_long_letter_gets_cut_target(self):
        g = orchestrator._word_count_fix_guidance(
            ["Expected 240-360 words across body paragraphs, got 420"]
        )
        self.assertIn("remove roughly 120", g)

    def test_other_violations_add_nothing(self):
        self.assertEqual(orchestrator._word_count_fix_guidance(["Forbidden phrase"]), "")


if __name__ == "__main__":
    unittest.main()
