import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402

fixed_content = profile_paths.fixed_content_module("morgan")


class TestFixedContent(unittest.TestCase):

    def test_certifications_are_exactly_three_in_fixed_order(self):
        certs = fixed_content.CERTIFICATIONS
        self.assertEqual(len(certs), 3)
        self.assertEqual(
            certs[0],
            {
                "title": "Email Marketing Software Certification",
                "org": "HubSpot",
                "year": "2026",
            },
        )
        self.assertEqual(
            certs[1],
            {
                "title": "Video for Sales Certification",
                "org": "Vidyard",
                "year": "2021",
            },
        )
        self.assertEqual(
            certs[2],
            {
                "title": "Camp Portfolio",
                "org": "Bernstein Rein, Kansas City",
                "year": "2008",
            },
        )

    def test_build_education_returns_three_items_in_fixed_order(self):
        edu = fixed_content.build_education(
            {
                "University of Kansas": "content_generalist",
                "Kansas City Kansas Community College": "writing_content",
            }
        )
        self.assertEqual(len(edu), 3)
        self.assertEqual(edu[0]["institution"], "University of Kansas")
        self.assertEqual(edu[1]["institution"], "Kansas City Kansas Community College")
        self.assertEqual(edu[2]["institution"], "Johnson County Community College")

    def test_build_education_selects_the_requested_ku_achievement(self):
        edu = fixed_content.build_education(
            {
                "University of Kansas": "email_ops",
                "Kansas City Kansas Community College": "generalist",
            }
        )
        self.assertIn("800%", edu[0]["bullets"][1])
        self.assertIn("managed promotional campaigns", edu[0]["bullets"][1])

    def test_build_education_falls_back_to_first_option_on_unknown_key(self):
        edu = fixed_content.build_education(
            {
                "University of Kansas": "not_a_real_key",
                "Kansas City Kansas Community College": "not_a_real_key_either",
            }
        )
        # Check that one of the KU achievement options is the achievement bullet
        self.assertTrue(
            any(
                value == edu[0]["bullets"][1]
                for value in fixed_content.KU_ACHIEVEMENT_OPTIONS.values()
            )
        )
        # Check that one of the KCKCC achievement options is the achievement bullet
        self.assertTrue(
            any(
                value == edu[1]["bullets"][1]
                for value in fixed_content.KCKCC_ACHIEVEMENT_OPTIONS.values()
            )
        )

    def test_build_education_defaults_to_empty_dict_when_no_keys_given(self):
        edu = fixed_content.build_education()
        self.assertEqual(len(edu), 3)

    def test_build_education_omits_graduation_years(self):
        # Graduation years let a recruiter infer age -- deliberately dropped
        # from every education entry. render_html.py's build_education_html()
        # already skips a missing "year" key gracefully (see its meta_parts
        # truthy filter), so no template change was needed for this.
        edu = fixed_content.build_education()
        for entry in edu:
            self.assertNotIn("year", entry)

    def test_template_schema_has_no_free_form_certifications_or_education_fields(self):
        fields = orchestrator.TemplateSchema.model_fields
        self.assertNotIn("CERTIFICATIONS", fields)
        self.assertNotIn("SECTION_CERTIFICATIONS", fields)
        self.assertNotIn("EDUCATION", fields)
        # Achievement-key fields are no longer static fields on this class at
        # all -- they're per-profile (EDU_ACHIEVEMENT_KEY_<n>), built by
        # ResumeEngine.build_education_achievement_schema_fields() and
        # merged in at call time. See test_orchestrator_schema_cleanup.py's
        # test_education_achievement_schema_fields_survive_sanitize_schema_as_enums.
        self.assertNotIn("KU_ACHIEVEMENT_KEY", fields)
        self.assertNotIn("KCKCC_ACHIEVEMENT_KEY", fields)

    def test_all_ku_achievement_options_are_valid(self):
        """Test that all KU achievement options produce valid education entries."""
        for ku_key in fixed_content.KU_ACHIEVEMENT_OPTIONS.keys():
            edu = fixed_content.build_education({"University of Kansas": ku_key})
            self.assertEqual(len(edu), 3)
            # The selected achievement is the second bullet for this school
            expected_bullet = fixed_content.KU_ACHIEVEMENT_OPTIONS[ku_key]
            self.assertEqual(edu[0]["bullets"][1], expected_bullet)

    def test_all_kckcc_achievement_options_are_valid(self):
        """Test that all KCKCC achievement options produce valid education entries."""
        for kckcc_key in fixed_content.KCKCC_ACHIEVEMENT_OPTIONS.keys():
            edu = fixed_content.build_education(
                {"Kansas City Kansas Community College": kckcc_key}
            )
            self.assertEqual(len(edu), 3)
            # The selected achievement is the second bullet for this school
            expected_bullet = fixed_content.KCKCC_ACHIEVEMENT_OPTIONS[kckcc_key]
            self.assertEqual(edu[1]["bullets"][1], expected_bullet)


class TestFixedContentConstantConsistency(unittest.TestCase):
    """Ensure constants in fixed_content are internally consistent across structures."""

    def test_company_title_descriptor_references_exist(self):
        """Test that all companies in COMPANY_TITLE_DESCRIPTOR exist in COMPANY_META."""
        for company_name in fixed_content.COMPANY_TITLE_DESCRIPTOR.keys():
            self.assertIn(
                company_name,
                fixed_content.COMPANY_META,
                f"'{company_name}' in COMPANY_TITLE_DESCRIPTOR must also be in COMPANY_META",
            )

    def test_company_rename_note_references_exist(self):
        """Test that all companies in COMPANY_RENAME_NOTE exist in COMPANY_META."""
        for company_name in fixed_content.COMPANY_RENAME_NOTE.keys():
            self.assertIn(
                company_name,
                fixed_content.COMPANY_META,
                f"'{company_name}' in COMPANY_RENAME_NOTE must also be in COMPANY_META",
            )

    def test_company_fixed_title_references_exist(self):
        """Test that all companies in COMPANY_FIXED_TITLE exist in COMPANY_META."""
        for company_name in fixed_content.COMPANY_FIXED_TITLE.keys():
            self.assertIn(
                company_name,
                fixed_content.COMPANY_META,
                f"'{company_name}' in COMPANY_FIXED_TITLE must also be in COMPANY_META",
            )

    def test_clients_references_exist(self):
        """Test that all companies in CLIENTS exist in COMPANY_META."""
        for company_name in fixed_content.CLIENTS.keys():
            self.assertIn(
                company_name,
                fixed_content.COMPANY_META,
                f"'{company_name}' in CLIENTS must also be in COMPANY_META",
            )

    def test_cv_section_keywords_references_exist(self):
        """Test that all companies in CV_SECTION_KEYWORDS exist in COMPANY_META."""
        for keywords, company_name in fixed_content.CV_SECTION_KEYWORDS:
            # CV_SECTION_KEYWORDS stores exact company names from COMPANY_META
            self.assertIn(
                company_name,
                fixed_content.COMPANY_META,
                f"'{company_name}' referenced in CV_SECTION_KEYWORDS must exist in COMPANY_META",
            )

    def test_career_note_company_exists(self):
        """Test that CAREER_NOTE_COMPANY (if set) exists in COMPANY_META."""
        if fixed_content.CAREER_NOTE_COMPANY:  # Empty string means no career note
            self.assertIn(
                fixed_content.CAREER_NOTE_COMPANY,
                fixed_content.COMPANY_META,
                f"CAREER_NOTE_COMPANY '{fixed_content.CAREER_NOTE_COMPANY}' "
                f"must exist in COMPANY_META",
            )

    def test_contact_info_has_required_fields(self):
        """Test CONTACT_INFO has all required fields and non-empty values."""
        required_fields = {"NAME", "PHONE", "EMAIL", "LINKEDIN_DISPLAY", "LOCATION"}
        self.assertTrue(
            required_fields.issubset(fixed_content.CONTACT_INFO.keys()),
            f"CONTACT_INFO missing fields: {required_fields - set(fixed_content.CONTACT_INFO.keys())}",
        )

        for field in required_fields:
            self.assertTrue(
                len(fixed_content.CONTACT_INFO[field]) > 0,
                f"CONTACT_INFO['{field}'] is empty",
            )

    def test_certifications_structure_is_valid(self):
        """Test that CERTIFICATIONS entries have correct structure and content."""
        for cert in fixed_content.CERTIFICATIONS:
            required_keys = {"title", "org", "year"}
            self.assertTrue(
                required_keys.issubset(cert.keys()),
                f"Certification missing keys. Got {cert.keys()}",
            )
            self.assertTrue(
                len(cert["title"]) > 0, "Certification title cannot be empty"
            )
            self.assertTrue(len(cert["org"]) > 0, "Certification org cannot be empty")

    def test_background_identity_populated(self):
        """Test that BACKGROUND_IDENTITY has substantive content."""
        self.assertTrue(
            len(fixed_content.BACKGROUND_IDENTITY) > 50,
            "BACKGROUND_IDENTITY should have substantive content",
        )

    def test_background_tags_all_populated(self):
        """Test that all BACKGROUND_TAGS entries have substantive content."""
        for tag, content in fixed_content.BACKGROUND_TAGS.items():
            self.assertTrue(
                len(content) > 20,
                f"BACKGROUND_TAGS['{tag}'] content too short: {len(content)} chars",
            )


if __name__ == "__main__":
    unittest.main()
