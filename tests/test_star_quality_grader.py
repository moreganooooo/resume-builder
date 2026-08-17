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

    def test_qualitative_bullet_with_strong_verb_and_outcome_still_fails_without_a_metric(self):
        """Pins F9 (docs/review/master_audit_document.md): the metric check
        alone costs 40 of 100 points, so a bullet with a perfect verb and
        clear outcome language but zero numbers scores exactly 60 --
        always below the 70 threshold. This isn't an unlikely edge case,
        it's the mathematical ceiling for every purely qualitative bullet.
        Once the qualitative-evidence fallback (F9 Task 2.1) ships, this
        assertion should flip to expect a pass."""
        resume = {
            "SUMMARY_TEXT": "<strong>Campaign strategist with 8+ years experience.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "title": "Campaign Strategist",
                    "period": "08/2016 – 08/2024",
                    "achievements": [
                        "Spearheaded a cross-functional trust rebuild with a disengaged VP "
                        "stakeholder, resulting in the team selecting me to lead go-to-market "
                        "strategy for the region"
                    ]
                }
            ],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        star_violations = [v for v in violations if "STAR/XYZ Quality Grader" in v]
        self.assertEqual(len(star_violations), 1)
        self.assertIn("Score 60/100", star_violations[0])

    def test_qualitative_bullet_with_evidence_phrase_and_outcome_language_now_passes(self):
        """F9 Task 2.1: a purely qualitative bullet with strong evidence
        phrasing AND explicit outcome language should clear the 70-point
        threshold even with zero numbers -- this is the case the fix was
        built for."""
        resume = {
            "SUMMARY_TEXT": "<strong>Campaign strategist with 8+ years experience.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "title": "Campaign Strategist",
                    "period": "08/2016 – 08/2024",
                    "achievements": [
                        "Rebuilt trust with a disengaged VP stakeholder, resulting in being "
                        "selected to lead go-to-market strategy for the region"
                    ]
                }
            ],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        star_violations = [v for v in violations if "STAR/XYZ Quality Grader" in v]
        self.assertEqual(star_violations, [])

    def test_genuinely_weak_bullet_still_fails_after_the_qualitative_fallback(self):
        """The fallback must not become a loophole -- a bullet with no
        verb, no metric, no qualitative evidence, and no outcome language
        should still fail."""
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
        star_violations = [v for v in violations if "STAR/XYZ Quality Grader" in v]
        self.assertEqual(len(star_violations), 1)

    def test_detects_ai_cliche_phrases(self):
        resume = {
            "SUMMARY_TEXT": "<strong>Results-oriented professional with a proven track record of driving cross-functional collaboration.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        self.assertTrue(any("Voice Authenticity Guardrail" in v for v in violations))

    def test_career_break_entry_skipped_from_star_grading(self):
        resume = {
            "SUMMARY_TEXT": "<strong>Campaign strategist with 8+ years experience.</strong>",
            "SKILLS": ["**Marketing:** CRM"],
            "EXPERIENCE": [
                {
                    "company": "Career Break — Professional Development & Retraining",
                    "title": "Upskilling & Caregiver",
                    "period": "08/2024 – 08/2025",
                    "achievements": [
                        "Completed comprehensive certifications in Google Data Analytics and HubSpot Lifecycle Marketing Software.",
                        "Developed personal data pipelines and campaign flow automation projects applying Python and SQL."
                    ]
                }
            ],
            "WHY_TEXT": ""
        }
        violations = validate_resume.validate(resume, self.style_rules, enforce_star=True)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
