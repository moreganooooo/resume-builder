import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import fixed_content  # noqa: E402
import orchestrator  # noqa: E402


class TestFixedContent(unittest.TestCase):

    def test_certifications_are_exactly_three_in_fixed_order(self):
        certs = fixed_content.CERTIFICATIONS
        self.assertEqual(len(certs), 3)
        self.assertEqual(certs[0], {"title": "Email Marketing Software Certification", "org": "HubSpot", "year": "2026"})
        self.assertEqual(certs[1], {"title": "Video for Sales Certification", "org": "Vidyard", "year": "2021"})
        self.assertEqual(certs[2], {"title": "Camp Portfolio", "org": "Bernstein Rein, Kansas City", "year": "2008"})

    def test_build_education_returns_three_items_in_fixed_order(self):
        edu = fixed_content.build_education("content_generalist", "writing_content")
        self.assertEqual(len(edu), 3)
        self.assertEqual(edu[0]["institution"], "University of Kansas")
        self.assertEqual(edu[1]["institution"], "Kansas City Kansas Community College")
        self.assertEqual(edu[2]["institution"], "Johnson County Community College")

    def test_build_education_selects_the_requested_ku_achievement(self):
        edu = fixed_content.build_education("email_ops", "generalist")
        self.assertIn("800%", edu[0]["bullets"][1])
        self.assertIn("managed promotional campaigns", edu[0]["bullets"][1])

    def test_build_education_falls_back_to_first_option_on_unknown_key(self):
        edu = fixed_content.build_education("not_a_real_key", "not_a_real_key_either")
        # Check that one of the KU achievement options is the achievement bullet
        self.assertTrue(any(value == edu[0]["bullets"][1] for value in fixed_content.KU_ACHIEVEMENT_OPTIONS.values()))
        # Check that one of the KCKCC achievement options is the achievement bullet
        self.assertTrue(any(value == edu[1]["bullets"][1] for value in fixed_content.KCKCC_ACHIEVEMENT_OPTIONS.values()))

    def test_template_schema_has_no_free_form_certifications_or_education_fields(self):
        fields = orchestrator.TemplateSchema.model_fields
        self.assertNotIn("CERTIFICATIONS", fields)
        self.assertNotIn("SECTION_CERTIFICATIONS", fields)
        self.assertNotIn("EDUCATION", fields)
        self.assertIn("KU_ACHIEVEMENT_KEY", fields)
        self.assertIn("KCKCC_ACHIEVEMENT_KEY", fields)


if __name__ == "__main__":
    unittest.main()
