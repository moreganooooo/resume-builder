import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_resume  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
    "forbidden_openers": ["responsible for", "helped with", "worked on", "assisted with", "participated in"],
    "bullet_structure": {"one_liner_max_chars": 120, "two_liner_max_chars": 220, "max_printed_lines": 2},
    "skills_section": {"line_max_chars": 110},
}


def _valid_resume():
    return {
        "SUMMARY_TEXT": "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Returning to full-time work after a caregiving pause.",
        "SKILLS": ["**Lifecycle & Retention Marketing:** Email Automation, Segmentation, Drip Campaigns"],
        "EXPERIENCE": [
            {"company": "Treering", "achievements": [
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
                "Architected the SDR onboarding program used company-wide for three years",
            ]},
        ],
        "WHY_TEXT": "",
    }


class TestValidateResume(unittest.TestCase):

    def test_valid_resume_has_no_violations(self):
        violations = validate_resume.validate(_valid_resume(), STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_forbidden_phrase_in_summary(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>A results-driven lifecycle marketer.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

    def test_flags_forbidden_opener_in_bullet(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append("Responsible for CRM data hygiene")
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("forbidden opener" in v.lower() for v in violations))

    def test_flags_duplicate_opening_verb_across_bullets(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Architected the SDR onboarding program used company-wide for three years",
            "Architected the CRM data model powering territory reporting",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("architected" in v.lower() and "unique" in v.lower() for v in violations))

    def test_flags_bullet_exceeding_two_liner_max_chars(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append("X" * 221)
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("exceeds" in v.lower() and "220" in v for v in violations))

    def test_flags_skills_line_exceeding_max_chars(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**Category:** " + ", ".join(["Item"] * 40)]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("110" in v for v in violations))

    def test_flags_pronoun_outside_why_section(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>I am a lifecycle marketer.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_allows_pronoun_inside_why_section(self):
        resume = _valid_resume()
        resume["WHY_TEXT"] = "<p><em>I built the SDR Process Map at Treering for exactly this reason.</em></p>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_duplicate_metric_across_summary_and_bullets(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>Recovered 3M in dormant pipeline as a lifecycle marketer.</strong>"
        # _valid_resume() already has "Recovered 3M" in a bullet -- now it's in both places.
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("3m" in v.lower() and ("once" in v.lower() or "duplicate" in v.lower()) for v in violations))


if __name__ == "__main__":
    unittest.main()
