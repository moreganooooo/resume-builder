import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import normalize_resume  # noqa: E402
import fixed_content  # noqa: E402


class TestNormalizeResume(unittest.TestCase):

    def setUp(self):
        self.raw = {
            "NAME": "Morgan Escott",
            "TAGLINE": "lifecycle marketing manager and crm strategist",
            "KU_ACHIEVEMENT_KEY": "content_generalist",
            "KCKCC_ACHIEVEMENT_KEY": "writing_content",
        }

    def test_injects_company_meta_for_known_companies(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "X", "company": "Mercor", "period": "08/2025 – 08/2025", "achievements": []}]
        result = normalize_resume.normalize(data)
        self.assertEqual(result["EXPERIENCE"][0]["size_revenue"], "~800 employees; $75M+ revenue")
        self.assertEqual(result["EXPERIENCE"][0]["location"], "Short-Term Contract | Remote")

    def test_leaves_unknown_company_without_meta(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "X", "company": "Some Startup Nobody Hardcoded", "period": "01/2020 – 01/2021", "achievements": []}]
        result = normalize_resume.normalize(data)
        self.assertNotIn("size_revenue", result["EXPERIENCE"][0])

    def test_injects_fixed_contact_info(self):
        result = normalize_resume.normalize(self.raw)
        for key, value in fixed_content.CONTACT_INFO.items():
            self.assertEqual(result[key], value)

    def test_overrides_any_builder_supplied_contact_info(self):
        data = dict(self.raw)
        data["PHONE"] = "555-000-0000"
        data["EMAIL"] = "someone-else@example.com"
        result = normalize_resume.normalize(data)
        self.assertEqual(result["PHONE"], fixed_content.CONTACT_INFO["PHONE"])
        self.assertEqual(result["EMAIL"], fixed_content.CONTACT_INFO["EMAIL"])

    def test_removes_portfolio_fields_entirely(self):
        data = dict(self.raw)
        data["PORTFOLIO_URL"] = "https://example.com/portfolio"
        data["PORTFOLIO_DISPLAY"] = "example.com/portfolio"
        result = normalize_resume.normalize(data)
        self.assertNotIn("PORTFOLIO_URL", result)
        self.assertNotIn("PORTFOLIO_DISPLAY", result)

    def test_injects_fixed_certifications(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["CERTIFICATIONS"], fixed_content.CERTIFICATIONS)

    def test_injects_fixed_education_using_the_selected_achievement_keys(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(len(result["EDUCATION"]), 3)
        self.assertIn("800% social media follower growth", result["EDUCATION"][0]["bullets"][1])

    def test_forces_section_header_labels(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["SECTION_SUMMARY"], "Professional Summary")
        self.assertEqual(result["SECTION_SKILLS"], "Skills")
        self.assertEqual(result["SECTION_EXPERIENCE"], "Work Experience")
        self.assertEqual(result["SECTION_CERTIFICATIONS"], "Training & Certifications")
        self.assertEqual(result["SECTION_EDUCATION"], "Education")

    def test_forces_tagline_uppercase_and_ampersand(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["TAGLINE"], "LIFECYCLE MARKETING MANAGER & CRM STRATEGIST")

    def test_does_not_mutate_the_input_dict(self):
        original = dict(self.raw)
        normalize_resume.normalize(self.raw)
        self.assertEqual(self.raw, original)

    def test_forces_tagline_ampersand_case_insensitively(self):
        data = dict(self.raw)
        data["TAGLINE"] = "Lifecycle Marketing Manager And CRM Strategist"
        result = normalize_resume.normalize(data)
        self.assertEqual(result["TAGLINE"], "LIFECYCLE MARKETING MANAGER & CRM STRATEGIST")


if __name__ == "__main__":
    unittest.main()
