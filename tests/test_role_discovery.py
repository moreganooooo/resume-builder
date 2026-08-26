import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import role_discovery  # noqa: E402


class TestNormalizeJobTitle(unittest.TestCase):

    def test_normalizes_seniority_and_tags(self):
        self.assertEqual(
            role_discovery.normalize_job_title(
                "Senior Lifecycle Marketing Manager (Remote - US)"
            ),
            "Senior Lifecycle Marketing Manager",
        )
        self.assertEqual(
            role_discovery.normalize_job_title(
                "Staff Software Engineer - Backend [Hybrid]"
            ),
            "Staff Software Engineer Backend",
        )
        self.assertEqual(
            role_discovery.normalize_job_title("Product Marketing Manager (Full-Time)"),
            "Product Marketing Manager",
        )

    def test_handles_empty_and_whitespace(self):
        self.assertEqual(role_discovery.normalize_job_title(""), "")
        self.assertEqual(role_discovery.normalize_job_title("   "), "")


class TestTitleAliasesLoading(unittest.TestCase):

    def test_loads_default_taxonomy(self):
        families = role_discovery.load_title_aliases()
        self.assertIn("lifecycle_marketing", families)
        self.assertIn("growth_marketing", families)
        self.assertIn("product_marketing", families)
        self.assertIn("software_engineering_frontend", families)

    def test_handles_missing_file_gracefully(self):
        families = role_discovery.load_title_aliases(
            custom_path="/nonexistent/path/aliases.yml"
        )
        self.assertEqual(families, {})


class TestMatchRoleFamily(unittest.TestCase):

    def test_exact_alias_match(self):
        family_id, family_data, score = role_discovery.match_role_family(
            "Lifecycle Marketing Manager"
        )
        self.assertEqual(family_id, "lifecycle_marketing")
        self.assertIsNotNone(family_data)
        self.assertEqual(score, 1.0)

    def test_variation_match(self):
        family_id, family_data, score = role_discovery.match_role_family(
            "Senior Growth Marketing Lead (Remote)"
        )
        self.assertEqual(family_id, "growth_marketing")
        self.assertIsNotNone(family_data)
        self.assertGreaterEqual(score, 0.5)

    def test_engineering_match(self):
        family_id, family_data, score = role_discovery.match_role_family(
            "Principal React Developer"
        )
        self.assertEqual(family_id, "software_engineering_frontend")
        self.assertIsNotNone(family_data)
        self.assertGreaterEqual(score, 0.5)

    def test_unknown_title_returns_none(self):
        family_id, family_data, score = role_discovery.match_role_family(
            "Underwater Basket Weaver"
        )
        self.assertIsNone(family_id)
        self.assertIsNone(family_data)
        self.assertEqual(score, 0.0)


class TestExpandTitleAliases(unittest.TestCase):

    def test_expands_matched_role(self):
        expanded = role_discovery.expand_title_aliases("CRM Marketing Manager")
        self.assertIn("Lifecycle Marketing Manager", expanded)
        self.assertIn("Retention Marketing", expanded)
        self.assertGreater(len(expanded), 1)

    def test_fallback_on_unmatched(self):
        expanded = role_discovery.expand_title_aliases("Custom Obscure Role Title")
        self.assertEqual(expanded, ["Custom Obscure Role Title"])


class TestOnetClassification(unittest.TestCase):

    def test_returns_onet_code_and_title(self):
        onet = role_discovery.get_onet_classification("Product Marketing Manager")
        self.assertIsNotNone(onet)
        self.assertEqual(onet["onet_code"], "11-2021.00")
        self.assertEqual(onet["onet_title"], "Marketing Managers")

    def test_software_engineer_onet(self):
        onet = role_discovery.get_onet_classification("Senior Backend Engineer")
        self.assertIsNotNone(onet)
        self.assertEqual(onet["onet_code"], "15-1252.00")
        self.assertEqual(onet["onet_title"], "Software Developers")

    def test_unmatched_returns_none(self):
        onet = role_discovery.get_onet_classification("Quantum Astrological Consultant")
        self.assertIsNone(onet)


class TestCoreCompetencies(unittest.TestCase):

    def test_competencies_by_family_id(self):
        skills = role_discovery.get_core_competencies("lifecycle_marketing")
        self.assertGreater(len(skills), 0)
        self.assertTrue(
            any("Email" in s or "CRM" in s or "Retention" in s for s in skills)
        )

    def test_competencies_by_title(self):
        skills = role_discovery.get_core_competencies("Senior Product Designer")
        self.assertGreater(len(skills), 0)
        self.assertTrue(
            any("Figma" in s or "Design" in s or "Research" in s for s in skills)
        )

    def test_competencies_unmatched(self):
        skills = role_discovery.get_core_competencies("Something Unknown")
        self.assertEqual(skills, [])


if __name__ == "__main__":
    unittest.main()
