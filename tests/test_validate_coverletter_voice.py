import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import validate_coverletter  # noqa: E402


class TestValidateCoverletterVoice(unittest.TestCase):

    def setUp(self):
        self.style_rules = {"forbidden_phrases": []}
        self.voice_rules = {
            "thresholds": {
                "sentence_std_dev_min": 4.5,
                "sentence_span_min": 12,
                "type_token_ratio_min": 0.46,
                "max_consecutive_same_opener": 2,
            }
        }

    def test_validate_includes_voice_metrics_violations(self):
        # Monotonous repetitive body paragraphs
        letter_data = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                "The quick brown fox jumps over the very lazy sleeping dog today. "
                "Another quick brown fox jumps over another very lazy sleeping dog. "
                "A third quick brown fox jumps over that same lazy sleeping dog. "
                "Every single sentence has almost the exact same number of words.",
                "I managed the team yesterday. I managed the team today. I managed the team tomorrow.",
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(
            letter_data,
            self.style_rules,
            voice_rules=self.voice_rules,
        )
        self.assertTrue(
            any(
                "monotonous" in v.lower() or "sentence starters" in v.lower()
                for v in violations
            )
        )

    def test_validate_passes_on_high_variance_natural_prose(self):
        letter_data = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                "I love building systems that work quietly in the background — so people don’t have to. "
                "Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. "
                "Clarity and empathy win every time.",
                "That loop of ideate, execute, and optimize is where I do my best work. "
                "Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader's time while earning their trust.",
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(
            letter_data,
            self.style_rules,
            voice_rules=self.voice_rules,
        )
        voice_violations = [
            v
            for v in violations
            if "monotonous" in v.lower()
            or "lexical" in v.lower()
            or "starters" in v.lower()
        ]
        self.assertEqual(voice_violations, [])

    def test_validate_handles_none_voice_rules_gracefully(self):
        letter_data = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                "I love building systems that work quietly in the background — so people don’t have to. "
                "Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. "
                "Clarity and empathy win every time.",
                "That loop of ideate, execute, and optimize is where I do my best work. "
                "Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader's time while earning their trust.",
            ],
            "sign_off": "Sincerely,",
        }
        # Calling validate without voice_rules should use default thresholds
        violations = validate_coverletter.validate(
            letter_data,
            self.style_rules,
            voice_rules=None,
        )
        voice_violations = [
            v
            for v in violations
            if "monotonous" in v.lower()
            or "lexical" in v.lower()
            or "starters" in v.lower()
        ]
        self.assertEqual(voice_violations, [])


if __name__ == "__main__":
    unittest.main()
