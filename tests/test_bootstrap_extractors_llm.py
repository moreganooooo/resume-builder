import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_extractors  # noqa: E402
import pypdf  # noqa: E402


def _make_pdf(num_pages: int) -> str:
    """A real multi-page PDF for exercising _split_pdf_for_extraction()
    against actual pypdf page counts, not a mock."""
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "source.pdf")
    with open(path, "wb") as f:
        writer.write(f)
    return path


class TestClassifyDocumentType(unittest.TestCase):

    def test_linkedin_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type(
            "LinkedIn_Export.pdf", None
        )
        self.assertEqual(result, "linkedin_export")

    def test_resume_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type(
            "My_Resume_2024.docx", "some text"
        )
        self.assertEqual(result, "resume")

    def test_cv_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("cv_final.pdf", None)
        self.assertEqual(result, "resume")

    def test_certificate_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type(
            "AWS_Certificate.pdf", None
        )
        self.assertEqual(result, "certificate")

    def test_recommendation_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type(
            "Recommendation_Letter_Jane.pdf", None
        )
        self.assertEqual(result, "recommendation_letter")

    def test_no_text_and_ambiguous_filename_defaults_to_achievement_notes(self):
        result = bootstrap_extractors.classify_document_type("scan0042.pdf", None)
        self.assertEqual(result, "achievement_notes")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_ambiguous_filename_with_text_calls_llm(self, mock_generate):
        mock_generate.return_value = ('{"doc_type": "recommendation_letter"}', {})
        result = bootstrap_extractors.classify_document_type(
            "document3.txt", "To whom it may concern..."
        )
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
            bootstrap_extractors.classify_document_type(
                "document3.txt", "some ambiguous text"
            )


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
            "achievement_notes",
            text="I led an onboarding redesign at Acme Corp in 2021.",
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
            bootstrap_extractors.extract_achievements(
                "achievement_notes", text="some notes"
            )


class TestExtractCertificate(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_certificate(self, mock_generate):
        mock_generate.return_value = (
            '{"name": "AWS Certified Solutions Architect", "issuer": "Amazon Web Services", "date": "2023"}',
            {},
        )
        cert = bootstrap_extractors.extract_certificate(
            text="AWS Certified Solutions Architect, issued 2023"
        )
        self.assertEqual(cert.name, "AWS Certified Solutions Architect")
        self.assertEqual(cert.issuer, "Amazon Web Services")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_none_when_no_name_found(self, mock_generate):
        mock_generate.return_value = (
            '{"name": null, "issuer": null, "date": null}',
            {},
        )
        cert = bootstrap_extractors.extract_certificate(
            text="not actually a certificate"
        )
        self.assertIsNone(cert)

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_failed_api_call_raises_instead_of_returning_none(self, mock_generate):
        mock_generate.return_value = (None, {})
        with self.assertRaises(bootstrap_extractors.IngestionAPIError):
            bootstrap_extractors.extract_certificate(
                text="AWS Certified Solutions Architect, issued 2023"
            )


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
        result = bootstrap_extractors.extract_resume_timeline_and_achievements(
            text="fake resume text"
        )
        self.assertEqual(len(result.experience), 1)
        self.assertEqual(result.experience[0].company, "Acme Corp")
        self.assertEqual(
            result.experience[0].achievements,
            ["Grew email list by 40%", "Launched rebrand"],
        )
        self.assertEqual(result.certifications, [])

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_embedded_certifications(self, mock_generate):
        mock_generate.return_value = (
            '{"experience": [], "certifications": '
            '[{"name": "PMP", "issuer": "PMI", "date": "2020"}]}',
            {},
        )
        result = bootstrap_extractors.extract_resume_timeline_and_achievements(
            text="fake resume text"
        )
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
            bootstrap_extractors.extract_resume_timeline_and_achievements(
                text="fake resume text"
            )


class TestGenerateFromUpload(unittest.TestCase):

    @patch("bootstrap_extractors.genai.Client")
    def test_uploads_file_and_returns_response_text(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.files.upload.return_value = "uploaded-file-handle"
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"achievements": []}'
        )

        result = bootstrap_extractors._generate_from_upload(
            "/tmp/fake.pdf", "system prompt", bootstrap_extractors.RawAchievementList
        )

        self.assertEqual(result, '{"achievements": []}')
        mock_client.files.upload.assert_called_once_with(file="/tmp/fake.pdf")
        mock_client.models.generate_content.assert_called_once()

    @patch("bootstrap_extractors.genai.Client")
    def test_pins_thinking_level_to_minimal_for_flash_lite(self, mock_client_cls):
        # Regression test: gemini_client.GeminiClient.generate() (the
        # text-based REST path) already pins thinkingLevel to MINIMAL for
        # every "flash-lite" call (B46/P5#1) because this tier's default
        # thinking level isn't always MINIMAL and has shifted before. This
        # SDK-based upload path never got that same pin, so a large/dense
        # source PDF could burn enough of its output-token budget on
        # unsuppressed thinking to truncate the JSON achievement list
        # mid-object -- silently recovered as a partial result by
        # GeminiClient.parse_json()'s _salvage_fields() fallback, with no
        # error surfaced.
        from google.genai import types

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.files.upload.return_value = "uploaded-file-handle"
        mock_client.models.generate_content.return_value = MagicMock(
            text='{"achievements": []}'
        )

        bootstrap_extractors._generate_from_upload(
            "/tmp/fake.pdf", "system prompt", bootstrap_extractors.RawAchievementList
        )

        _, kwargs = mock_client.models.generate_content.call_args
        thinking_config = kwargs["config"].thinking_config
        self.assertIsNotNone(thinking_config)
        self.assertEqual(thinking_config.thinking_level, types.ThinkingLevel.MINIMAL)

    @patch("bootstrap_extractors.time.sleep")
    @patch("bootstrap_extractors.genai.Client")
    def test_retries_a_transient_503_and_then_succeeds(
        self, mock_client_cls, mock_sleep
    ):
        from google.genai import errors as genai_errors

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.files.upload.return_value = "uploaded-file-handle"
        transient_error = genai_errors.ServerError(
            503, {"error": {"message": "high demand"}}
        )
        mock_client.models.generate_content.side_effect = [
            transient_error,
            MagicMock(text='{"achievements": []}'),
        ]

        result = bootstrap_extractors._generate_from_upload(
            "/tmp/fake.pdf", "system prompt", bootstrap_extractors.RawAchievementList
        )

        self.assertEqual(result, '{"achievements": []}')
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("bootstrap_extractors.time.sleep")
    @patch("bootstrap_extractors.genai.Client")
    def test_permanent_error_raises_without_retrying(self, mock_client_cls, mock_sleep):
        from google.genai import errors as genai_errors

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.files.upload.return_value = "uploaded-file-handle"
        mock_client.models.generate_content.side_effect = genai_errors.ClientError(
            400, {"error": {"message": "bad request"}}
        )

        with self.assertRaises(bootstrap_extractors.IngestionAPIError):
            bootstrap_extractors._generate_from_upload(
                "/tmp/fake.pdf",
                "system prompt",
                bootstrap_extractors.RawAchievementList,
            )

        mock_client.models.generate_content.assert_called_once()
        mock_sleep.assert_not_called()


class TestSplitPdfForExtraction(unittest.TestCase):
    """Regression coverage for the large-PDF under-extraction bug: a single
    call over a long, multi-topic PDF summarizes/selects rather than
    exhaustively enumerating achievements -- confirmed live on a 49-page
    document that dropped an entire personal project. Splitting into
    page-range chunks gives each topic its own extraction pass."""

    def setUp(self):
        self._cleanup_dirs = []
        self.addCleanup(self._remove_dirs)

    def _remove_dirs(self):
        for d in self._cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _track(self, path: str) -> str:
        self._cleanup_dirs.append(os.path.dirname(path))
        return path

    def test_short_pdf_is_not_split(self):
        path = self._track(_make_pdf(5))
        self.assertEqual(bootstrap_extractors._split_pdf_for_extraction(path), [path])

    def test_pdf_at_threshold_is_not_split(self):
        path = self._track(_make_pdf(bootstrap_extractors.PDF_CHUNK_PAGE_THRESHOLD))
        self.assertEqual(bootstrap_extractors._split_pdf_for_extraction(path), [path])

    def test_non_pdf_is_never_split(self):
        path = "/tmp/some_notes.txt"
        self.assertEqual(bootstrap_extractors._split_pdf_for_extraction(path), [path])

    def test_unopenable_pdf_falls_back_to_original_path(self):
        self.assertEqual(
            bootstrap_extractors._split_pdf_for_extraction("/nonexistent/fake.pdf"),
            ["/nonexistent/fake.pdf"],
        )

    def test_large_pdf_is_split_with_one_page_overlap(self):
        path = self._track(_make_pdf(25))
        chunks = bootstrap_extractors._split_pdf_for_extraction(path)
        try:
            self.assertGreater(len(chunks), 1)
            page_counts = [len(pypdf.PdfReader(c).pages) for c in chunks]
            # 25 pages, chunk size 10, 1-page overlap: 0-9, 9-18, 18-24.
            self.assertEqual(page_counts, [10, 10, 7])
            for c in chunks:
                self.assertTrue(os.path.exists(c))
        finally:
            bootstrap_extractors._cleanup_pdf_chunks(chunks, path)
        for c in chunks:
            self.assertFalse(os.path.exists(c))

    def test_cleanup_leaves_single_unchunked_path_untouched(self):
        path = self._track(_make_pdf(3))
        bootstrap_extractors._cleanup_pdf_chunks([path], path)
        self.assertTrue(os.path.exists(path))


class TestExtractAchievementsFromLargePdf(unittest.TestCase):
    """extract_achievements() end-to-end over a real multi-chunk PDF:
    verifies every chunk actually gets its own extraction call, results
    from every chunk are merged, and exact cross-chunk repeats (expected
    from the 1-page overlap) are deduped rather than double-counted."""

    def setUp(self):
        self.path = _make_pdf(25)
        self.addCleanup(shutil.rmtree, os.path.dirname(self.path), ignore_errors=True)

    @patch("bootstrap_extractors._generate_from_upload")
    def test_merges_and_dedupes_across_chunks(self, mock_upload):
        mock_upload.side_effect = [
            '{"achievements": [{"raw_text": "Built pipeline A", "confidence": "high"}, '
            '{"raw_text": "Shared boundary achievement", "confidence": "medium"}]}',
            '{"achievements": [{"raw_text": "Shared boundary achievement", "confidence": "medium"}, '
            '{"raw_text": "Built dashboard B", "confidence": "high"}]}',
            '{"achievements": [{"raw_text": "Built dashboard B", "confidence": "high"}, '
            '{"raw_text": "Led project C", "confidence": "low"}]}',
        ]

        result = bootstrap_extractors.extract_achievements(
            "other", upload_path=self.path
        )

        self.assertEqual(mock_upload.call_count, 3)
        raw_texts = sorted(a.raw_text for a in result)
        self.assertEqual(
            raw_texts,
            [
                "Built dashboard B",
                "Built pipeline A",
                "Led project C",
                "Shared boundary achievement",
            ],
        )

    @patch("bootstrap_extractors._generate_from_upload")
    def test_temp_chunks_cleaned_up_after_extraction(self, mock_upload):
        mock_upload.return_value = '{"achievements": []}'
        real_split = bootstrap_extractors._split_pdf_for_extraction
        captured = {}

        def spy_split(path):
            chunks = real_split(path)
            captured["chunks"] = chunks
            return chunks

        with patch(
            "bootstrap_extractors._split_pdf_for_extraction", side_effect=spy_split
        ):
            bootstrap_extractors.extract_achievements("other", upload_path=self.path)

        self.assertGreater(len(captured["chunks"]), 1)
        for c in captured["chunks"]:
            self.assertFalse(os.path.exists(c))
        # The original file survives (it's the caller's, not a temp chunk).
        self.assertTrue(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
