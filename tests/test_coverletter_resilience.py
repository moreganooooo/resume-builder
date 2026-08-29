import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import validate_coverletter  # noqa: E402


class TestCoverLetterResilience(unittest.TestCase):
    def setUp(self):
        self.style_rules = {"forbidden_phrases": ["proven track record"]}

    def test_word_count_tolerance_band_240_to_360(self):
        # 245 words: within tolerance band (240-360), must pass
        letter_245 = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                " ".join(["word"] * 120),
                " ".join(["word"] * 125),
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(letter_245, self.style_rules)
        self.assertFalse(any("words across body paragraphs" in v for v in violations))

        # 355 words: within tolerance band (240-360), must pass
        letter_355 = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                " ".join(["word"] * 175),
                " ".join(["word"] * 180),
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(letter_355, self.style_rules)
        self.assertFalse(any("words across body paragraphs" in v for v in violations))

        # 230 words: below 240 floor, must flag violation
        letter_230 = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                " ".join(["word"] * 115),
                " ".join(["word"] * 115),
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(letter_230, self.style_rules)
        self.assertTrue(any("240-360 words" in v for v in violations))

        # 370 words: above 360 ceiling, must flag violation
        letter_370 = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                " ".join(["word"] * 185),
                " ".join(["word"] * 185),
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(letter_370, self.style_rules)
        self.assertTrue(any("240-360 words" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
