import os
import re
import sys
import unittest

import yaml

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import profile_paths  # noqa: E402


class TestMorganProfileYmlNewSchema(unittest.TestCase):

    def setUp(self):
        path = os.path.join(profile_paths.kb_dir("morgan"), "profile.yml")
        with open(path, "r") as f:
            self.data = yaml.safe_load(f)

    def test_roles_section_has_all_six_companies_with_required_fields(self):
        roles = {r["name"]: r for r in self.data["roles"]}
        expected_companies = {
            "Mercor",
            "Treering Yearbooks",
            "Inside Sales Team",
            "Element 8 / Strategy LLC",
            "VML",
            "Callahan Creek",
        }
        self.assertEqual(set(roles.keys()), expected_companies)
        for role in roles.values():
            for field in ("min_bullets", "target_bullets", "page", "flex_priority"):
                self.assertIn(field, role)

    def test_mercor_floor_is_2(self):
        roles = {r["name"]: r for r in self.data["roles"]}
        self.assertEqual(roles["Mercor"]["min_bullets"], 2)

    def test_inside_sales_team_must_fit_page_1(self):
        roles = {r["name"]: r for r in self.data["roles"]}
        self.assertTrue(roles["Inside Sales Team"]["must_fit_page_1"])

    def test_protected_bullets_has_four_entries(self):
        # protected_bullets entries are prose bullet descriptions (e.g. "Outreach.io
        # full platform ownership..."), never URLs -- urlparse(b).hostname would be
        # None for all of them. A word-boundary match on the product name is the
        # correct check here, not URL-hostname parsing.
        self.assertEqual(len(self.data["protected_bullets"]), 4)
        self.assertTrue(
            any(
                re.search(r"\boutreach\.io\b", b, re.IGNORECASE)
                for b in self.data["protected_bullets"]
            )
        )

    def test_fixed_credentials_has_certifications_and_education(self):
        creds = self.data["fixed_credentials"]
        self.assertEqual(len(creds["certifications"]), 3)
        self.assertEqual(len(creds["education"]), 3)
        jccc = [
            e
            for e in creds["education"]
            if e["institution"] == "Johnson County Community College"
        ][0]
        self.assertEqual(jccc["bullet_count"], 1)

    def test_voice_calibration_example_present(self):
        self.assertIn("alignment", self.data["voice_calibration_example"])


if __name__ == "__main__":
    unittest.main()
