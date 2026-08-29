import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestDeterministicTrim(unittest.TestCase):
    def test_trim_surplus_bullet_respects_flex_priority_and_floors(self):
        profile_data = {
            "roles": [
                {"name": "Treering Yearbooks", "min_bullets": 6, "flex_priority": 1},
                {"name": "Mercor", "min_bullets": 2, "flex_priority": 2},
                {"name": "Callahan Creek", "min_bullets": 2, "flex_priority": 2},
            ],
            "protected_bullets": ["Hero CRM scrub"],
        }
        role_minimums = {"Treering Yearbooks": 6, "Mercor": 2, "Callahan Creek": 2}

        # Setup: Mercor is at floor (2), Callahan Creek has surplus (3), Treering has surplus (7)
        resume_data = {
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "achievements": ["T1", "T2", "T3", "T4", "T5", "T6", "T7"],
                },
                {"company": "Mercor", "achievements": ["M1", "M2"]},
                {"company": "Callahan Creek", "achievements": ["C1", "C2", "C3"]},
            ]
        }

        # flex_priority 2 (Callahan Creek) should be trimmed before flex_priority 1 (Treering)
        new_data, trimmed = orchestrator.trim_surplus_bullet_deterministically(
            resume_data, profile_data, role_minimums
        )
        self.assertTrue(trimmed)

        cc_job = next(
            j for j in new_data["EXPERIENCE"] if j["company"] == "Callahan Creek"
        )
        self.assertEqual(len(cc_job["achievements"]), 2)

        # Next trim should now target Treering (since CC and Mercor are both at floor 2)
        new_data2, trimmed2 = orchestrator.trim_surplus_bullet_deterministically(
            new_data, profile_data, role_minimums
        )
        self.assertTrue(trimmed2)
        tr_job = next(
            j for j in new_data2["EXPERIENCE"] if j["company"] == "Treering Yearbooks"
        )
        self.assertEqual(len(tr_job["achievements"]), 6)

    def test_trim_surplus_bullet_protects_protected_bullets(self):
        profile_data = {
            "roles": [
                {"name": "Treering Yearbooks", "min_bullets": 1, "flex_priority": 1}
            ],
            "protected_bullets": ["Protected Hero Achievement"],
        }
        role_minimums = {"Treering Yearbooks": 1}
        resume_data = {
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "achievements": [
                        "Regular bullet",
                        "Protected Hero Achievement",
                    ],
                }
            ]
        }
        new_data, trimmed = orchestrator.trim_surplus_bullet_deterministically(
            resume_data, profile_data, role_minimums
        )
        self.assertTrue(trimmed)
        self.assertEqual(
            new_data["EXPERIENCE"][0]["achievements"], ["Protected Hero Achievement"]
        )

    def test_trim_surplus_bullet_returns_false_when_all_at_floor(self):
        profile_data = {
            "roles": [
                {"name": "Treering Yearbooks", "min_bullets": 6, "flex_priority": 1},
                {"name": "Mercor", "min_bullets": 2, "flex_priority": 2},
            ],
            "protected_bullets": [],
        }
        role_minimums = {"Treering Yearbooks": 6, "Mercor": 2}
        resume_data = {
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "achievements": ["T1", "T2", "T3", "T4", "T5", "T6"],
                },
                {"company": "Mercor", "achievements": ["M1", "M2"]},
            ]
        }
        new_data, trimmed = orchestrator.trim_surplus_bullet_deterministically(
            resume_data, profile_data, role_minimums
        )
        self.assertFalse(trimmed)
        self.assertEqual(len(new_data["EXPERIENCE"][0]["achievements"]), 6)
        self.assertEqual(len(new_data["EXPERIENCE"][1]["achievements"]), 2)

    def test_trim_surplus_bullet_handles_company_name_normalization(self):
        profile_data = {
            "roles": [
                {
                    "name": "Element 8 / Strategy LLC",
                    "min_bullets": 2,
                    "flex_priority": 2,
                },
            ],
            "protected_bullets": [],
        }
        role_minimums = {"Element 8 / Strategy LLC": 2}
        resume_data = {
            "EXPERIENCE": [
                {
                    "company": "Element 8 / Strategy LLC (Now Alleyoop)",
                    "achievements": ["E1", "E2", "E3"],
                },
            ]
        }
        new_data, trimmed = orchestrator.trim_surplus_bullet_deterministically(
            resume_data, profile_data, role_minimums
        )
        self.assertTrue(trimmed)
        self.assertEqual(len(new_data["EXPERIENCE"][0]["achievements"]), 2)


if __name__ == "__main__":
    unittest.main()
