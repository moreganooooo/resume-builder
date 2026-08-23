import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402


class TestBuildRoleRulesBlock(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    def test_empty_roles_returns_empty_string(self):
        self.assertEqual(self.engine.build_role_rules_block({}), "")
        self.assertEqual(self.engine.build_role_rules_block({"roles": []}), "")

    def test_includes_role_rules_header(self):
        profile_data = {
            "roles": [
                {
                    "name": "Acme Corp",
                    "min_bullets": 2,
                    "target_bullets": 3,
                    "page": 1,
                    "flex_priority": 1,
                },
            ],
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("=== ROLE RULES ===", block)
        self.assertIn("Acme Corp", block)
        self.assertIn("| 2 | 3 | 1 |", block)

    def test_must_fit_page_1_role_is_called_out(self):
        profile_data = {
            "roles": [
                {
                    "name": "Acme Corp",
                    "min_bullets": 2,
                    "target_bullets": 3,
                    "page": 1,
                    "flex_priority": 1,
                    "must_fit_page_1": True,
                },
            ],
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("must fit entirely on page 1: Acme Corp", block)

    def test_protected_bullets_included(self):
        profile_data = {
            "roles": [],
            "protected_bullets": ["Owned the whole thing end to end"],
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("Protected Bullets", block)
        self.assertIn("Owned the whole thing end to end", block)

    def test_fixed_credentials_included(self):
        profile_data = {
            "roles": [],
            "fixed_credentials": {
                "certifications": [
                    {"name": "Widget Cert", "issuer": "Widget Co", "year": 2020}
                ],
                "education": [
                    {"institution": "State U", "credential": "BA", "bullet_count": 2}
                ],
            },
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("Widget Cert | Widget Co | 2020", block)
        self.assertIn("State U -- BA: exactly 2 bullet(s)", block)

    def test_voice_calibration_example_included(self):
        profile_data = {"roles": [], "voice_calibration_example": "A test quote."}
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("A test quote.", block)

    def test_a_real_profile_produces_a_nonempty_block(self):
        """Asserted "Mercor"/"Treering Yearbooks"/"Outreach.io" appeared in
        the block -- three facts about one person's career, so the test only
        meant anything on that person's machine. What actually matters is
        that a populated profile.yml yields a non-empty rules block naming
        the roles it declares."""
        import persona

        with persona.sandbox_profile():
            profile_data = {
                "roles": [
                    {
                        "name": persona.EMPLOYER_WITH_META,
                        "min_bullets": 2,
                        "target_bullets": 3,
                        "page": 1,
                        "flex_priority": 1,
                    },
                    {
                        "name": persona.EMPLOYER_LONG_TENURE,
                        "min_bullets": 3,
                        "target_bullets": 4,
                        "page": 1,
                        "flex_priority": 2,
                    },
                ],
                "fixed_credentials": {
                    "certifications": [
                        {
                            "name": "Lifecycle Marketing Certification",
                            "issuer": "Example Org",
                            "year": 2026,
                        }
                    ]
                },
            }
            block = self.engine.build_role_rules_block(profile_data)

        self.assertTrue(block.strip(), "a populated profile produced an empty block")
        self.assertIn(persona.EMPLOYER_WITH_META, block)
        self.assertIn(persona.EMPLOYER_LONG_TENURE, block)


if __name__ == "__main__":
    unittest.main()
