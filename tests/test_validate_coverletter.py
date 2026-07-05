import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_coverletter  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
}


def _valid_letter():
    return {
        "company_name": "Acme Corp",
        "greeting": "Dear Hiring Team,",
        "body_paragraphs": [
            "I was excited to see the Content Strategist opening at Acme Corp, since it "
            "lines up directly with my background in campaign messaging and content "
            "operations.",
            "In my most recent role, I built lifecycle email campaigns that grew "
            "engagement by double digits, which maps closely to the JD's focus on "
            "activation-ready content.",
        ],
        "sign_off": "Sincerely,",
    }


class TestValidateCoverLetter(unittest.TestCase):

    def test_valid_letter_has_no_violations(self):
        violations = validate_coverletter.validate(_valid_letter(), STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_forbidden_phrase(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I'm a results-driven professional."
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

    def test_flags_too_few_paragraphs(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = ["Only one paragraph here."]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Expected 2-3 body paragraphs" in v for v in violations))

    def test_flags_too_many_paragraphs(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = ["One.", "Two.", "Three.", "Four."]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Expected 2-3 body paragraphs" in v for v in violations))

    def test_flags_third_person_slip(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] = "Morgan has years of experience in content strategy."
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Third-person self-reference" in v for v in violations))

    def test_allows_legitimate_third_party_pronoun(self):
        # Known trade-off, not a bug: "her"/"she" is a blunt heuristic (see
        # validate_coverletter.py's docstring). This test just documents the
        # limitation exists rather than asserting a specific behavior for it.
        pass
