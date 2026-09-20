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
        self.assertIn("| 2 | 3 | - | 1 |", block)

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

    def test_education_entry_missing_bullet_count_defaults_instead_of_raising(self):
        # A hand-written profile.yml education entry that only sets
        # institution/credential (no bullet_count) used to raise
        # KeyError('bullet_count') here and abort every resume build for
        # the whole profile -- observed live on a real profile. Missing,
        # not just falsy: test_profile_yml_schema.py's own schema test is
        # what should catch this before a real build ever does; this is
        # the defense-in-depth fallback.
        profile_data = {
            "roles": [],
            "fixed_credentials": {
                "education": [{"institution": "State U", "credential": "BA"}],
            },
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("State U -- BA: exactly 1 bullet(s)", block)

    def test_education_entry_missing_institution_or_credential_does_not_crash(self):
        profile_data = {
            "roles": [],
            "fixed_credentials": {
                "education": [{"credential": "BA"}, {"institution": "State U"}, {}],
            },
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("1. BA: exactly 1 bullet(s)", block)
        self.assertIn("2. State U: exactly 1 bullet(s)", block)
        self.assertIn("3. Unnamed education entry: exactly 1 bullet(s)", block)

    def test_achievement_slots_tolerate_missing_institution(self):
        from unittest.mock import patch

        import profile_paths

        yml = {
            "fixed_credentials": {
                "education": [
                    {"credential": "BA", "achievement_options": {"k": "framing"}}
                ]
            }
        }
        with patch.object(profile_paths, "profile_yaml", return_value=yml):
            self.assertEqual(
                profile_paths.education_achievement_slots(), [("BA", {"k": "framing"})]
            )

    def test_design_only_entry_without_a_name_does_not_crash(self):
        profile_data = {
            "roles": [],
            "fixed_credentials": {"education": [{"design_only": True}]},
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("Unnamed credential", block)

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
