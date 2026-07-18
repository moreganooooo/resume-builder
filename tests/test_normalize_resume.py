import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import normalize_resume  # noqa: E402
import profile_paths  # noqa: E402

fixed_content = profile_paths.fixed_content_module("morgan")


class TestNormalizeResume(unittest.TestCase):

    def setUp(self):
        self.raw = {
            "NAME": "Morgan Escott",
            "TAGLINE": "lifecycle marketing manager and crm strategist",
            # Numbered per profile_paths.education_achievement_slots()'s
            # order -- EDU_ACHIEVEMENT_KEY_1 is University of Kansas (the
            # first profile.yml education entry with achievement_options),
            # EDU_ACHIEVEMENT_KEY_2 is Kansas City Kansas Community College.
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
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

    def test_appends_fixed_title_descriptor_for_known_companies(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "Sales/Marketing Strategy + QA Expert", "company": "Mercor", "period": "08/2025 – 08/2025", "achievements": []}]
        result = normalize_resume.normalize(data)
        self.assertEqual(result["EXPERIENCE"][0]["title"], "Sales/Marketing Strategy + QA Expert (AI Training)")

    def test_does_not_double_append_descriptor_if_builder_already_included_it(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "Sales/Marketing Strategy + QA Expert (AI Training)", "company": "Mercor", "period": "08/2025 – 08/2025", "achievements": []}]
        result = normalize_resume.normalize(data)
        self.assertEqual(result["EXPERIENCE"][0]["title"], "Sales/Marketing Strategy + QA Expert (AI Training)")

    def test_forces_the_career_note_for_treering_regardless_of_builder_output(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "X", "company": "Treering Yearbooks", "period": "08/2016 – 08/2024", "achievements": [], "career_note": "something the builder made up"}]
        result = normalize_resume.normalize(data)
        self.assertEqual(result["EXPERIENCE"][0]["career_note"], fixed_content.CAREER_NOTE)

    def test_does_not_add_career_note_for_other_companies(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "X", "company": "Mercor", "period": "08/2025 – 08/2025", "achievements": []}]
        result = normalize_resume.normalize(data)
        self.assertNotIn("career_note", result["EXPERIENCE"][0])

    def test_appends_company_rename_note_for_known_companies(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "X", "company": "Inside Sales Team", "period": "10/2015 – 08/2016", "achievements": []}]
        result = normalize_resume.normalize(data)
        self.assertEqual(result["EXPERIENCE"][0]["company"], "Inside Sales Team (Now Alleyoop)")

    def test_forces_fixed_title_for_element_8_regardless_of_builder_output(self):
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "Whatever The Builder Made Up", "company": "Element 8 / Strategy LLC", "period": "01/2011 – 10/2011", "achievements": []}]
        result = normalize_resume.normalize(data)
        # The fixed title still gets the usual industry descriptor appended,
        # same as every other company's title.
        expected = f'{fixed_content.COMPANY_FIXED_TITLE["Element 8 / Strategy LLC"]} (Design/Agency/Startup)'
        self.assertEqual(result["EXPERIENCE"][0]["title"], expected)

    def test_renormalizing_an_already_renamed_company_stays_idempotent(self):
        # normalize() runs multiple times over the same resume across
        # validator-fix and trim retry loops -- a naive rename-append that
        # used the already-mutated "company" field as its own lookup key
        # would silently stop matching COMPANY_META/CLIENTS/etc. on the 2nd+
        # pass, since "Callahan Creek (Now BarkleyOKRP)" isn't a dict key.
        data = dict(self.raw)
        data["EXPERIENCE"] = [{"title": "X", "company": "Callahan Creek", "period": "05/2009 – 05/2010", "achievements": []}]
        once = normalize_resume.normalize(data)
        twice = normalize_resume.normalize(once)
        self.assertEqual(twice["EXPERIENCE"][0]["company"], "Callahan Creek (Now BarkleyOKRP)")
        self.assertEqual(twice["EXPERIENCE"][0]["clients"], fixed_content.CLIENTS["Callahan Creek"]["list"])
        self.assertEqual(twice["EXPERIENCE"][0]["size_revenue"], fixed_content.COMPANY_META["Callahan Creek"]["size_revenue"])

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

    def test_education_uses_abbreviated_degree_names_to_avoid_wrapping(self):
        # "Bachelor of Science, Journalism + Strategic Communication" was
        # long enough to wrap the KU education line to a 2nd line; BS/AA are
        # equally valid, HR-acceptable degree abbreviations.
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["EDUCATION"][0]["degree"], "BS, Journalism + Strategic Communication")
        self.assertEqual(result["EDUCATION"][1]["degree"], "AA, Journalism")

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


class TestNormalizeUsesActiveProfilesFixedContent(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = "morgan"

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_normalize_applies_morgans_contact_info(self):
        result = normalize_resume.normalize({})
        self.assertEqual(result["NAME"], "Morgan Escott")
        self.assertEqual(result["EMAIL"], "escott.morgan@gmail.com")


if __name__ == "__main__":
    unittest.main()
