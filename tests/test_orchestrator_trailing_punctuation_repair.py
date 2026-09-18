"""Deterministic trailing-punctuation repair -- see
validate_resume._check_bullet_trailing_punctuation and
repair_violations_surgically's "1b. Deterministic Trailing-Punctuation
Strip" block.

Covers a real 2026-09-17 sample build: a builder-produced bullet shipped
ending in a period ("...beating company reply rate benchmarks."). The Step
3 critique enforces the ends-with-period rule on bank bullets, but nothing
on the builder path re-checked it, and the strip is pure text surgery, so
the repair must never cost an LLM call.

Uses synthetic resume content throughout -- not the active profile's real
employers/bullets -- per tests/test_no_operator_identity.py's "use
synthetic data, not the operator's own history" rule.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402


class TestTrailingPunctuationCheck(unittest.TestCase):

    def _resume(self, bullet):
        return {
            "SUMMARY_TEXT": "Generalist marketer with measurable growth.",
            "SKILLS": [],
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [bullet],
                    "career_note": "",
                }
            ],
            "EDUCATION": [],
        }


class TestTrailingPunctuationRepair(unittest.TestCase):

    def test_period_is_stripped_without_an_llm_call(self):
        resume_data = {
            "SUMMARY_TEXT": "Generalist marketer with measurable growth.",
            "SKILLS": [],
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Coached a pod of SDRs on messaging, beating reply benchmarks.",
                        "Led unrelated work with no punctuation problem",
                    ],
                    "career_note": "",
                }
            ],
            "EDUCATION": [],
        }
        violations = validate_resume._check_bullet_trailing_punctuation(resume_data)
        self.assertEqual(len(violations), 1)

        repaired, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, style_rules={}
        )
        self.assertEqual(
            repaired["EXPERIENCE"][0]["achievements"][0],
            "Coached a pod of SDRs on messaging, beating reply benchmarks",
        )
        # The clean bullet passes through untouched.
        self.assertEqual(
            repaired["EXPERIENCE"][0]["achievements"][1],
            "Led unrelated work with no punctuation problem",
        )
        self.assertEqual(remaining, [])

    def test_education_bullet_is_stripped_too(self):
        resume_data = {
            "SUMMARY_TEXT": "Generalist marketer with measurable growth.",
            "SKILLS": [],
            "EXPERIENCE": [],
            "EDUCATION": [
                {
                    "institution": "State University",
                    "bullets": ["Produced editorial content across channels."],
                }
            ],
        }
        violations = validate_resume._check_bullet_trailing_punctuation(resume_data)
        self.assertEqual(len(violations), 1)
        repaired, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, style_rules={}
        )
        self.assertEqual(
            repaired["EDUCATION"][0]["bullets"][0],
            "Produced editorial content across channels",
        )
        self.assertEqual(remaining, [])

    def test_question_mark_and_semicolon_are_stripped(self):
        resume_data = {
            "SUMMARY_TEXT": "Generalist marketer with measurable growth.",
            "SKILLS": [],
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Ran the webinar program; doubled attendance",
                    ],
                    "career_note": "",
                }
            ],
            "EDUCATION": [],
        }
        # Feed the violation the validator would emit for a semicolon-ending
        # bullet to prove the repair loop handles the full punctuation class.
        violations = [
            "Bullet ends with trailing punctuation: 'Ran the webinar program; doubled attendance;' -- strip it."
        ]
        resume_data["EXPERIENCE"][0]["achievements"] = [
            "Ran the webinar program; doubled attendance;"
        ]
        repaired, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, style_rules={}
        )
        self.assertEqual(
            repaired["EXPERIENCE"][0]["achievements"][0],
            "Ran the webinar program; doubled attendance",
        )
        self.assertEqual(remaining, [])


class TestSkillsFragmentRepair(unittest.TestCase):

    def test_fragment_item_is_dropped_without_an_llm_call(self):
        resume_data = {
            "SUMMARY_TEXT": "Generalist marketer with measurable growth.",
            "SKILLS": [
                "**Content Strategy:** Content Marketing, Campaign Messaging, Content Operations, Assets"
            ],
            "EXPERIENCE": [],
        }
        violations = validate_resume._check_skills_item_fragments(resume_data)
        self.assertEqual(len(violations), 1)

        repaired, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, style_rules={}
        )
        self.assertEqual(
            repaired["SKILLS"][0],
            "**Content Strategy:** Content Marketing, Campaign Messaging, Content Operations",
        )
        self.assertEqual(remaining, [])

    def test_qualified_compound_items_survive_the_repair(self):
        resume_data = {
            "SUMMARY_TEXT": "Generalist marketer with measurable growth.",
            "SKILLS": [
                "**Creative & Content:** Brand Assets, Copywriting, CMS Platforms"
            ],
            "EXPERIENCE": [],
        }
        repaired, remaining = orchestrator.repair_violations_surgically(
            resume_data, [], style_rules={}
        )
        self.assertEqual(
            repaired["SKILLS"][0],
            "**Creative & Content:** Brand Assets, Copywriting, CMS Platforms",
        )
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()
