import os
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")


def _load(dir_path, filename):
    with open(os.path.join(dir_path, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestBannedPhraseConsistency(unittest.TestCase):

    def setUp(self):
        self.style_rules = _load(RULES_DIR, "style_rules.yaml")
        self.language_quality = _load(RULES_DIR, "language_quality.yaml")
        self.summary_score = _load(SCORING_DIR, "summary_score.yaml")
        self.master_list = set(self.style_rules["forbidden_phrases"])

    def test_summary_score_buzzword_openers_are_a_subset_of_style_rules(self):
        missing = set(self.summary_score["buzzword_openers"]) - self.master_list
        self.assertEqual(
            missing,
            set(),
            f"summary_score.yaml bans phrases not in style_rules.yaml: {missing}",
        )

    def test_language_quality_high_risk_buzzwords_are_a_subset_of_style_rules(self):
        missing = (
            set(self.language_quality["buzzwords"]["high_risk"]) - self.master_list
        )
        self.assertEqual(
            missing,
            set(),
            f"language_quality.yaml's high_risk bans phrases not in style_rules.yaml: {missing}",
        )

    def test_language_quality_severe_ai_patterns_are_a_subset_of_style_rules(self):
        missing = (
            set(self.language_quality["ai_language_patterns"]["severe"])
            - self.master_list
        )
        self.assertEqual(
            missing,
            set(),
            f"language_quality.yaml's severe ai_language_patterns ban phrases not in style_rules.yaml: {missing}",
        )

    def test_style_guide_derived_phrases_are_present(self):
        # From AlexWritingStyleGuide.txt's "Anti-Voice Red Flags",
        # distilled 2026-07-07 -- not already covered by the pre-existing list.
        self.assertIn("wear many hats", self.style_rules["forbidden_phrases"])
        self.assertIn("to whom it may concern", self.style_rules["forbidden_phrases"])


if __name__ == "__main__":
    unittest.main()
