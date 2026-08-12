import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402


class TestCoverLetterSchemaNewFields(unittest.TestCase):

    def test_contact_fields_default_to_empty_string(self):
        model = orchestrator.CoverLetterSchema(
            company_name="Acme", greeting="Dear Acme Corp Hiring Team,",
            body_paragraphs=["p1", "p2"], sign_off="Sincerely,",
        )
        self.assertEqual(model.contact_name, "")
        self.assertEqual(model.contact_title, "")


class TestResolveCompanyLocation(unittest.TestCase):

    def test_prefers_research_hq_location(self):
        result = orchestrator._resolve_company_location(
            {"company_hq_location": "Austin, TX"}, {"location": "Remote"})
        self.assertEqual(result, "Austin, TX")

    def test_falls_back_to_jd_location_when_research_has_none(self):
        result = orchestrator._resolve_company_location({"company_hq_location": ""}, {"location": "Remote"})
        self.assertEqual(result, "Remote")

    def test_falls_back_to_jd_location_when_research_is_none(self):
        result = orchestrator._resolve_company_location(None, {"location": "Buffalo, NY"})
        self.assertEqual(result, "Buffalo, NY")

    def test_returns_empty_string_when_nothing_known(self):
        self.assertEqual(orchestrator._resolve_company_location(None, {}), "")

    def test_returns_jd_location_even_for_a_remote_role(self):
        # No filtering by remote/on-site -- shown whenever known.
        result = orchestrator._resolve_company_location(None, {"location": "Remote"})
        self.assertEqual(result, "Remote")


class TestReadMatchingResumeTagline(unittest.TestCase):

    def setUp(self):
        self.resume_dir = os.path.join(profile_paths.output_dir(), "json")
        os.makedirs(self.resume_dir, exist_ok=True)
        self.resume_path = os.path.join(self.resume_dir, "_tmp_enrichment_stem_Resume.json")

    def tearDown(self):
        if os.path.exists(self.resume_path):
            os.remove(self.resume_path)

    def test_returns_empty_string_when_no_matching_resume_exists(self):
        self.assertEqual(orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"), "")

    def test_returns_tagline_from_matching_resume_json(self):
        with open(self.resume_path, "w", encoding="utf-8") as f:
            json.dump({"TAGLINE": "CONTENT STRATEGIST | SEO"}, f)
        self.assertEqual(
            orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"),
            "CONTENT STRATEGIST | SEO",
        )

    def test_returns_empty_string_on_malformed_json(self):
        with open(self.resume_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        self.assertEqual(orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"), "")


if __name__ == "__main__":
    unittest.main()
