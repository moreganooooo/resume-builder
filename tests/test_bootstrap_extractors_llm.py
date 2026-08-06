import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_extractors  # noqa: E402


class TestClassifyDocumentType(unittest.TestCase):

    def test_linkedin_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("LinkedIn_Export.pdf", None)
        self.assertEqual(result, "linkedin_export")

    def test_resume_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("My_Resume_2024.docx", "some text")
        self.assertEqual(result, "resume")

    def test_cv_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("cv_final.pdf", None)
        self.assertEqual(result, "resume")

    def test_certificate_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("AWS_Certificate.pdf", None)
        self.assertEqual(result, "certificate")

    def test_recommendation_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("Recommendation_Letter_Jane.pdf", None)
        self.assertEqual(result, "recommendation_letter")

    def test_no_text_and_ambiguous_filename_defaults_to_achievement_notes(self):
        result = bootstrap_extractors.classify_document_type("scan0042.pdf", None)
        self.assertEqual(result, "achievement_notes")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_ambiguous_filename_with_text_calls_llm(self, mock_generate):
        mock_generate.return_value = ('{"doc_type": "recommendation_letter"}', {})
        result = bootstrap_extractors.classify_document_type("document3.txt", "To whom it may concern...")
        self.assertEqual(result, "recommendation_letter")
        mock_generate.assert_called_once()

    def test_dry_run_skips_llm_call(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.classify_document_type(
                "document3.txt", "some ambiguous text", dry_run=True
            )
            mock_generate.assert_not_called()
            self.assertEqual(result, "other")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_failed_api_call_raises_instead_of_defaulting_to_other(self, mock_generate):
        # B16: GeminiClient.generate() returns (None, {}) on a real failure
        # (e.g. a 403 from a missing/bad key) -- this used to silently
        # collapse to doc_type "other" via GeminiClient.parse_json(None) ->
        # {}, indistinguishable from a genuinely ambiguous document.
        mock_generate.return_value = (None, {})
        with self.assertRaises(bootstrap_extractors.IngestionAPIError):
            bootstrap_extractors.classify_document_type("document3.txt", "some ambiguous text")


class TestExtractAchievements(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_text_path_parses_achievements(self, mock_generate):
        mock_generate.return_value = (
            '{"achievements": [{"raw_text": "Led onboarding redesign", '
            '"company_hint": "Acme Corp", "date_hint": "2021", '
            '"title_hint": null, "confidence": "high"}]}',
            {},
        )
        result = bootstrap_extractors.extract_achievements(
            "achievement_notes", text="I led an onboarding redesign at Acme Corp in 2021."
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].raw_text, "Led onboarding redesign")
        self.assertEqual(result[0].company_hint, "Acme Corp")
        self.assertEqual(result[0].confidence, "high")

    def test_requires_exactly_one_of_text_or_upload_path(self):
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_achievements("achievement_notes")
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_achievements(
                "achievement_notes", text="a", upload_path="b"
            )

    @patch("bootstrap_extractors._generate_from_upload")
    def test_upload_path_calls_generate_from_upload(self, mock_upload):
        mock_upload.return_value = '{"achievements": []}'
        result = bootstrap_extractors.extract_achievements(
            "recommendation_letter", upload_path="/tmp/fake.pdf"
        )
        self.assertEqual(result, [])
        mock_upload.assert_called_once()

    def test_dry_run_returns_empty_without_calling_api(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_achievements(
                "achievement_notes", text="some notes", dry_run=True
            )
            mock_generate.assert_not_called()
            self.assertEqual(result, [])

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_failed_api_call_raises_instead_of_returning_empty(self, mock_generate):
        # B16: a real API failure used to collapse to an empty achievements
        # list, indistinguishable from "this document genuinely had none."
        mock_generate.return_value = (None, {})
        with self.assertRaises(bootstrap_extractors.IngestionAPIError):
            bootstrap_extractors.extract_achievements("achievement_notes", text="some notes")


class TestExtractCertificate(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_certificate(self, mock_generate):
        mock_generate.return_value = (
            '{"name": "AWS Certified Solutions Architect", "issuer": "Amazon Web Services", "date": "2023"}',
            {},
        )
        cert = bootstrap_extractors.extract_certificate(text="AWS Certified Solutions Architect, issued 2023")
        self.assertEqual(cert.name, "AWS Certified Solutions Architect")
        self.assertEqual(cert.issuer, "Amazon Web Services")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_none_when_no_name_found(self, mock_generate):
        mock_generate.return_value = ('{"name": null, "issuer": null, "date": null}', {})
        cert = bootstrap_extractors.extract_certificate(text="not actually a certificate")
        self.assertIsNone(cert)

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_failed_api_call_raises_instead_of_returning_none(self, mock_generate):
        mock_generate.return_value = (None, {})
        with self.assertRaises(bootstrap_extractors.IngestionAPIError):
            bootstrap_extractors.extract_certificate(text="AWS Certified Solutions Architect, issued 2023")


class TestExtractResumeTimelineAndAchievements(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_experience_entries(self, mock_generate):
        mock_generate.return_value = (
            '{"experience": [{"company": "Acme Corp", "title": "Marketing Manager", '
            '"start_date": "2019", "end_date": "2022", '
            '"achievements": ["Grew email list by 40%", "Launched rebrand"]}], '
            '"certifications": []}',
            {},
        )
        result = bootstrap_extractors.extract_resume_timeline_and_achievements(text="fake resume text")
        self.assertEqual(len(result.experience), 1)
        self.assertEqual(result.experience[0].company, "Acme Corp")
        self.assertEqual(result.experience[0].achievements, ["Grew email list by 40%", "Launched rebrand"])
        self.assertEqual(result.certifications, [])

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_embedded_certifications(self, mock_generate):
        mock_generate.return_value = (
            '{"experience": [], "certifications": '
            '[{"name": "PMP", "issuer": "PMI", "date": "2020"}]}',
            {},
        )
        result = bootstrap_extractors.extract_resume_timeline_and_achievements(text="fake resume text")
        self.assertEqual(len(result.certifications), 1)
        self.assertEqual(result.certifications[0].name, "PMP")

    def test_dry_run_returns_empty_resume_extraction(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_resume_timeline_and_achievements(
                text="fake resume text", dry_run=True
            )
            mock_generate.assert_not_called()
            self.assertEqual(result.experience, [])
            self.assertEqual(result.certifications, [])

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_failed_api_call_raises_instead_of_returning_empty(self, mock_generate):
        # This is the exact real-world repro from B16: a fresh profile, no
        # API key, a 403 on the first document -- GeminiClient.generate()
        # returns (None, {}), and this used to become an empty-but-"done"
        # ResumeExtraction (work_experience: []) instead of a real failure.
        mock_generate.return_value = (None, {})
        with self.assertRaises(bootstrap_extractors.IngestionAPIError):
            bootstrap_extractors.extract_resume_timeline_and_achievements(text="fake resume text")


class TestGenerateFromUpload(unittest.TestCase):

    @patch("bootstrap_extractors.genai.Client")
    def test_uploads_file_and_returns_response_text(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.files.upload.return_value = "uploaded-file-handle"
        mock_client.models.generate_content.return_value = MagicMock(text='{"achievements": []}')

        result = bootstrap_extractors._generate_from_upload(
            "/tmp/fake.pdf", "system prompt", bootstrap_extractors.RawAchievementList
        )

        self.assertEqual(result, '{"achievements": []}')
        mock_client.files.upload.assert_called_once_with(file="/tmp/fake.pdf")
        mock_client.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
