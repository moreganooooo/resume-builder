import os
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORING_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")


class TestSummaryScoreYaml(unittest.TestCase):

    def setUp(self):
        with open(
            os.path.join(SCORING_DIR, "summary_score.yaml"), "r", encoding="utf-8"
        ) as f:
            self.data = yaml.safe_load(f)

    def test_readability_uses_line_count_not_word_count(self):
        readability = self.data["scoring_rules"]["readability"]
        excellent = readability["excellent"]
        poor = readability["poor"]
        self.assertNotIn("under_80_words", excellent)
        self.assertNotIn("over_120_words", poor)
        self.assertIn("within_5_line_limit", excellent)
        self.assertIn("exceeds_5_line_limit", poor)


if __name__ == "__main__":
    unittest.main()
