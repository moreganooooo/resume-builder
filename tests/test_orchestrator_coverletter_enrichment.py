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


class TestCoverLetterEnrichmentWiring(unittest.TestCase):
    """Confirms build_tailored_coverletter() merges tagline, resolved
    company_location, and contact fallback into the saved letter_data."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_enrichment.json")
        self.jd_json = {
            "job_title": "Content Strategist",
            "company_name": "Acme Corp",
            "location": "Remote",
            "description": "We are hiring a Content Strategist.",
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_json, f)

        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.resume_json_path = os.path.join(self.engine.output_json_dir, f"{self.stem}_Resume.json")
        os.makedirs(self.engine.output_json_dir, exist_ok=True)
        with open(self.resume_json_path, "w", encoding="utf-8") as f:
            json.dump({"TAGLINE": "CONTENT STRATEGIST | SEO | LIFECYCLE MARKETING"}, f)

        self.json_out = os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json")
        self.html_out = os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html")

    def tearDown(self):
        for path in (self.jd_path, self.resume_json_path, self.json_out, self.html_out):
            if os.path.exists(path):
                os.remove(path)

    def _clean_letter_json(self):
        return json.dumps({
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "contact_name": "",
            "contact_title": "",
            "body_paragraphs": [
                "I'm excited to apply for this role at Acme Corp.",
                "My background lines up well with what you need.",
            ],
            "sign_off": "Sincerely,",
        })

    def _run_build(self):
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            return self.engine.build_tailored_coverletter(self.jd_path)

    @patch.object(orchestrator.ResumeEngine, "research_company",
                   return_value={"company_hq_location": "Austin, TX", "company_facts": [], "notable_highlights": []})
    @patch("orchestrator.GeminiClient.generate")
    def test_tagline_and_research_location_land_in_saved_letter(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["tagline"], "CONTENT STRATEGIST | SEO | LIFECYCLE MARKETING")
        self.assertEqual(result["company_location"], "Austin, TX")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_falls_back_to_jd_location_when_research_has_none(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["company_location"], "Remote")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_contact_fallback_fills_from_scraped_jd_contacts(self, mock_generate, mock_research):
        self.jd_json["social_connections"] = [
            {"fullName": "Maggie Smith", "jobTitle": "HR Manager", "companyName": "Acme Corp"},
        ]
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_json, f)
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["contact_name"], "Maggie Smith")
        self.assertEqual(result["contact_title"], "HR Manager")


if __name__ == "__main__":
    unittest.main()
