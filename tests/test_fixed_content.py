import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402

# Resolved lazily against the ACTIVE profile rather than at import time
# against one hardcoded person's. These are consistency checks -- "every
# company referenced in COMPANY_TITLE_DESCRIPTOR exists in COMPANY_META",
# "CONTACT_INFO has all its fields" -- and they are worth running against
# whoever's profile is configured. Hardcoding a name meant the module
# failed to import outright for anyone else, and asserted one person's
# exact certifications rather than any invariant.
fixed_content = None


class TestFixedContent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        global fixed_content
        try:
            fixed_content = profile_paths.fixed_content_module()
        except (ImportError, ValueError) as exc:
            raise unittest.SkipTest(
                f"No bootstrapped profile to validate: {exc}"
            ) from exc

    def test_certifications_are_a_list_of_well_formed_entries(self):
        """Structure, not contents. Which certifications a person holds is
        their business; that each entry carries a title and an org is the
        renderer's contract."""
        certs = fixed_content.CERTIFICATIONS
        self.assertIsInstance(certs, list)
        for cert in certs:
            self.assertIsInstance(cert, dict)
            self.assertTrue(cert.get("title"), f"certification missing title: {cert}")
            self.assertIn("org", cert)

    def test_build_education_returns_a_stable_list(self):
        edu = fixed_content.build_education({})
        self.assertIsInstance(edu, list)
        # Same input, same output -- normalize() calls this on every retry
        # pass, so it must not depend on dict ordering or hidden state.
        self.assertEqual(edu, fixed_content.build_education({}))

    def test_build_education_tolerates_an_unknown_achievement_key(self):
        """An unknown key must fall back, not raise -- the key comes from
        model output, so it cannot be trusted to be one of the options."""
        edu = fixed_content.build_education({"not_a_real_slot": "not_a_real_key"})
        self.assertIsInstance(edu, list)

    def test_build_education_accepts_no_arguments(self):
        """Count is a property of the profile, not of build_education() --
        a freshly-bootstrapped profile legitimately has none yet."""
        self.assertIsInstance(fixed_content.build_education(), list)

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

    def test_every_achievement_option_produces_a_stable_education_list(self):
        """Was written against two specific schools by name. What matters is
        that selecting ANY declared achievement option still yields a
        well-formed education list of the same length."""
        options = getattr(fixed_content, "KU_ACHIEVEMENT_OPTIONS", None) or {}
        if not options:
            self.skipTest("Profile declares no education achievement options.")
        baseline = len(fixed_content.build_education())
        for key in options:
            edu = fixed_content.build_education({"slot": key})
            self.assertEqual(len(edu), baseline)

    def test_second_slot_achievement_options_are_also_valid(self):
        """Second education slot -- same contract as the first."""
        options = getattr(fixed_content, "KCKCC_ACHIEVEMENT_OPTIONS", None) or {}
        if not options:
            self.skipTest("Profile declares no second-slot achievement options.")
        baseline = len(fixed_content.build_education())
        for key in options:
            self.assertEqual(
                len(fixed_content.build_education({"slot": key})), baseline
            )


class TestFixedContentConstantConsistency(unittest.TestCase):
    """Ensure constants in fixed_content are internally consistent across
    structures -- e.g. every company named in COMPANY_TITLE_DESCRIPTOR
    actually exists in COMPANY_META. These hold for any profile."""

    @classmethod
    def setUpClass(cls):
        global fixed_content
        try:
            fixed_content = profile_paths.fixed_content_module()
        except (ImportError, ValueError) as exc:
            raise unittest.SkipTest(
                f"No bootstrapped profile to validate: {exc}"
            ) from exc

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

    def test_background_identity_is_a_string(self):
        """Whether it is filled in is a property of how far along the
        profile is; that it is a string is the contract orchestrator
        depends on (build_background_summary does direct attribute access
        and string ops on it)."""
        self.assertIsInstance(fixed_content.BACKGROUND_IDENTITY, str)

    def test_background_tags_all_populated(self):
        """Test that all BACKGROUND_TAGS entries have substantive content."""
        for tag, content in fixed_content.BACKGROUND_TAGS.items():
            self.assertTrue(
                len(content) > 20,
                f"BACKGROUND_TAGS['{tag}'] content too short: {len(content)} chars",
            )


if __name__ == "__main__":
    unittest.main()
