import copy
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402


class TestValidationResilience(unittest.TestCase):
    def setUp(self):
        self.style_rules = {
            "bullet_structure": {
                "one_liner_max_chars": 108,
                "two_liner_max_chars": 220,
                "widow_min_words": 5,
            },
            "skills_section": {
                "line_max_chars": 110,
                "widow_min_chars": 25,
            },
            "verb_upgrades": {
                "data_and_ops": {
                    "description": "CRM hygiene, reporting, systems administration",
                    "upgrades": [
                        {
                            "weak": "developed [a process/system/workflow]",
                            "strong": [
                                "Engineered",
                                "Architected",
                                "Systematized",
                                "Standardized",
                                "Overhauled",
                                "Built",
                            ],
                        },
                        {
                            "weak": "managed [accounts/records/data]",
                            "strong": [
                                "Administered",
                                "Audited",
                                "Migrated",
                                "Reconciled",
                                "Maintained",
                                "Governed",
                            ],
                        },
                    ],
                },
                "content_and_comms": {
                    "description": "Writing, email, campaigns",
                    "upgrades": [
                        {
                            "weak": "developed [content/copy/campaign]",
                            "strong": [
                                "Authored",
                                "Produced",
                                "Drafted",
                                "Crafted",
                                "Launched",
                                "Wrote",
                            ],
                        }
                    ],
                },
            },
            "recommended_verbs": [
                "Architected",
                "Authored",
                "Launched",
                "Recovered",
                "Systematized",
                "Audited",
                "Spearheaded",
                "Negotiated",
                "Synthesized",
                "Produced",
                "Streamlined",
                "Championed",
                "Deployed",
                "Expanded",
                "Coordinated",
                "Mentored",
                "Built",
                "Implemented",
                "Delivered",
                "Drove",
                "Engineered",
                "Established",
                "Executed",
                "Generated",
                "Identified",
                "Led",
                "Managed",
                "Orchestrated",
                "Overhauled",
                "Piloted",
                "Redesigned",
                "Reduced",
                "Secured",
                "Trained",
                "Unified",
            ],
        }
        self.role_roster = ["Mercor", "Treering Yearbooks"]
        self.role_minimums = {"Mercor": 2, "Treering Yearbooks": 6}

    def test_build_verb_synonym_graph_extracts_from_style_rules(self):
        graph = orchestrator.build_verb_synonym_graph(self.style_rules)
        self.assertIn("architected", graph)
        self.assertIn("engineered", graph["architected"])
        self.assertIn("authored", graph)
        self.assertIn("produced", graph["authored"])

    def test_auto_fix_duplicate_opening_verbs_swaps_deterministically(self):
        data = {
            "EXPERIENCE": [
                {
                    "company": "Mercor",
                    "achievements": [
                        "Architected a QA checklist for sequences.",
                        "Architected a pipeline tool for account scoring.",
                    ],
                },
            ]
        }
        fixed_data, modified = orchestrator.auto_fix_duplicate_opening_verbs(
            data, self.style_rules
        )
        self.assertTrue(modified)
        all_verbs = validate_resume.get_opening_verbs(fixed_data)
        self.assertEqual(len(all_verbs), 2)
        self.assertEqual(all_verbs[0].lower(), "architected")
        self.assertNotEqual(all_verbs[1].lower(), "architected")
        # Ensure capitalization was preserved
        self.assertTrue(fixed_data["EXPERIENCE"][0]["achievements"][1][0].isupper())

    def test_auto_fix_duplicate_opening_verbs_preserves_unique_verbs(self):
        data = {
            "EXPERIENCE": [
                {
                    "company": "Mercor",
                    "achievements": [
                        "Architected a QA checklist for sequences.",
                        "Engineered a pipeline tool for account scoring.",
                    ],
                },
            ]
        }
        fixed_data, modified = orchestrator.auto_fix_duplicate_opening_verbs(
            data, self.style_rules
        )
        self.assertFalse(modified)
        self.assertEqual(data, fixed_data)

    def test_auto_fix_duplicate_opening_verbs_handles_multiple_duplicates(self):
        data = {
            "EXPERIENCE": [
                {
                    "company": "Mercor",
                    "achievements": [
                        "Architected a QA checklist for sequences.",
                        "Architected a pipeline tool for account scoring.",
                    ],
                },
                {
                    "company": "Treering Yearbooks",
                    "achievements": [
                        "Authored 21 multi-channel outbound sequences.",
                        "Authored a full onboarding handbook for sales reps.",
                    ],
                },
            ]
        }
        fixed_data, modified = orchestrator.auto_fix_duplicate_opening_verbs(
            data, self.style_rules
        )
        self.assertTrue(modified)
        all_verbs = validate_resume.get_opening_verbs(fixed_data)
        self.assertEqual(len(all_verbs), 4)
        self.assertEqual(len(set(all_verbs)), 4, f"Duplicates remain: {all_verbs}")

    def test_surgical_repair_preserves_unaffected_sections(self):
        initial_data = {
            "SUMMARY_TEXT": "<strong>Strategist with 10+ years of experience.</strong> Built CRM systems.",
            "SKILLS": ["**Content Strategy:** Campaign Design, B2B Copywriting"],
            "EXPERIENCE": [
                {
                    "company": "Mercor",
                    "achievements": [
                        "Architected a 14-category sequence QA checklist.",
                        "Audited 2,933+ accounts across Salesforce.",
                    ],
                },
                {
                    "company": "Treering Yearbooks",
                    "achievements": [
                        # 112-char bullet with short widow (2 words on 2nd line past 108 chars)
                        "Designed a 14-step district outreach program for PTA councils to increase engagement and overall reply rates today",
                    ],
                },
            ],
        }
        original_summary = initial_data["SUMMARY_TEXT"]
        original_skills = list(initial_data["SKILLS"])
        original_mercor = copy.deepcopy(initial_data["EXPERIENCE"][0])

        with patch("orchestrator.GeminiClient.generate") as mock_generate:
            mock_generate.return_value = (
                "Designed a 14-step district outreach program for PTA councils to increase engagement and reply rates",
                {"total_tokens": 50},
            )

            repaired, violations = orchestrator.repair_violations_surgically(
                initial_data,
                [
                    "Bullet is 112 chars and wraps to a 2nd line at the 108-char mark but leaves only a 2-word widow"
                ],
                self.style_rules,
                self.role_roster,
                self.role_minimums,
                [],
            )

            # Unaffected sections must be 100% byte-for-byte identical
            self.assertEqual(repaired["SUMMARY_TEXT"], original_summary)
            self.assertEqual(repaired["SKILLS"], original_skills)
            self.assertEqual(repaired["EXPERIENCE"][0], original_mercor)
            # The target bullet must be updated
            self.assertNotEqual(
                repaired["EXPERIENCE"][1]["achievements"][0],
                initial_data["EXPERIENCE"][1]["achievements"][0],
            )

    def test_partition_violations_separates_hard_from_soft(self):
        violations = [
            "Role roster check: 'Callahan Creek' is missing from EXPERIENCE",
            "Role order check: 'VML' appears before 'Mercor' in EXPERIENCE",
            "Role bullet count for 'Mercor' is 1 (minimum is 2)",
            "Bullet is 112 chars and wraps to a 2nd line at the 108-char mark but leaves only a 2-word widow",
            "Skills line is 114 chars, which lands in the 111-134 dead band",
            "Pronoun 'I' found outside the Why section, in SUMMARY_TEXT: 'I built'",
            "Forbidden phrase 'best-in-class' found in bullet",
            "Hallucinated tool 'TensorFlow' found in bullet",
        ]
        fatal, soft = orchestrator.partition_violations(violations)
        self.assertEqual(len(fatal), 6)
        self.assertEqual(len(soft), 2)
        self.assertIn("Callahan Creek", fatal[0])
        self.assertIn("Role order", fatal[1])
        self.assertIn("Role bullet count", fatal[2])
        self.assertIn("Pronoun", fatal[3])
        self.assertIn("Forbidden phrase", fatal[4])
        self.assertIn("widow", soft[0])
        self.assertIn("Skills line", soft[1])

    def test_auto_fix_experience_order_restores_reverse_chronological(self):
        # Shuffled roles: Treering before Mercor
        shuffled_data = {
            "EXPERIENCE": [
                {"company": "Treering Yearbooks", "achievements": ["Achievement 1"]},
                {"company": "Mercor", "achievements": ["Achievement 2"]},
            ]
        }
        fixed_data, modified = orchestrator.auto_fix_experience_order(
            shuffled_data, self.role_roster
        )
        self.assertTrue(modified)
        self.assertEqual(fixed_data["EXPERIENCE"][0]["company"], "Mercor")
        self.assertEqual(fixed_data["EXPERIENCE"][1]["company"], "Treering Yearbooks")

    def test_auto_fix_forbidden_openers_strips_openers(self):
        style_rules_with_openers = {
            "forbidden_openers": ["Responsible for", "Helped with", "Assisted with"]
        }
        data = {
            "EXPERIENCE": [
                {
                    "company": "Mercor",
                    "achievements": [
                        "Responsible for designing the QA workflow.",
                        "Helped with customer onboarding.",
                    ],
                }
            ]
        }
        fixed_data, modified = orchestrator.auto_fix_forbidden_openers(
            data, style_rules_with_openers
        )
        self.assertTrue(modified)
        self.assertEqual(
            fixed_data["EXPERIENCE"][0]["achievements"][0],
            "Designing the QA workflow.",
        )
        self.assertEqual(
            fixed_data["EXPERIENCE"][0]["achievements"][1],
            "Customer onboarding.",
        )

    def test_partition_violations_exhaustive_taxonomy(self):
        soft_sample = [
            "Bullet is 112 chars and wraps to a 2nd line at the 108-char mark but leaves only a 2-word widow ('reply rates')",
            "SKILLS line 'Tools: Python, SQL' is 114 chars, which lands in the 111-134 dead band where it wraps to a 2nd line",
            "SKILLS line 'Frameworks: React' is 225 chars (limit is 220 chars: wrap to a 3rd line is never allowed)",
        ]
        fatal_sample = [
            "Role roster check: 'Callahan Creek' is missing from EXPERIENCE",
            "Work history order: EXPERIENCE entries are not in the profile's declared reverse-chronological order",
            "Role bullet count for 'Mercor' is 1 (minimum is 2)",
            "Pronoun 'I' found outside the Why section",
            "Forbidden phrase 'best-in-class' found in bullet",
            "Strict Semantic Guardrail: Hallucinated skill or tool detected: 'TensorFlow'",
            "Demographic/Bias Linter: Age proxy detected",
            "SUMMARY_TEXT is 420 chars (limit is 380 chars)",
            "Opening verb 'Led' is not unique across the CV",
            "Metric '$20M' should appear only once across the resume",
        ]
        fatal, soft = orchestrator.partition_violations(soft_sample + fatal_sample)
        self.assertEqual(len(soft), len(soft_sample))
        self.assertEqual(len(fatal), len(fatal_sample))
        for item in soft_sample:
            self.assertIn(item, soft)
        for item in fatal_sample:
            self.assertIn(item, fatal)


if __name__ == "__main__":
    unittest.main()
