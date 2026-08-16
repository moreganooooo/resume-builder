import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_resume  # noqa: E402


class TestStarQualityGrader(unittest.TestCase):

    def setUp(self):
        self.style_rules = {
            "forbidden_phrases": [],
            "forbidden_openers": [],
            "bullet_structure": {"one_liner_max_chars": 120, "two_liner_max_chars": 220, "max_printed_lines": 2},
            "skills_section": {"line_max_chars": 110},
        }

    def test_flawless_star_bullet_passes_grader(self):
        resume = {
            "SUMMARY_TEXT": "<strong>Campaign strategist with 8+ years experience.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "title": "Campaign Strategist",
                    "period": "08/2016 – 08/2024",
                    "achievements": [
                        "Architected automated email sequence workflows across 60+ accounts, driving a 24% increase in customer reply rates"
                    ]
                }
            ],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        self.assertEqual(violations, [])

    def test_weak_bullet_lacking_metric_and_outcome_triggers_star_violation(self):
        resume = {
            "SUMMARY_TEXT": "<strong>Campaign strategist with 8+ years experience.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "title": "Campaign Strategist",
                    "period": "08/2016 – 08/2024",
                    "achievements": [
                        "Worked on email templates and helped the sales team with outreach"
                    ]
                }
            ],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        self.assertTrue(any("STAR/XYZ Quality Grader" in v for v in violations))

    def test_detects_ai_cliche_phrases(self):
        resume = {
            "SUMMARY_TEXT": "<strong>Results-oriented professional with a proven track record of driving cross-functional collaboration.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        self.assertTrue(any("Voice Authenticity Guardrail" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
