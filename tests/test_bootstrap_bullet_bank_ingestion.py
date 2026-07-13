import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402


class BootstrapIngestionTestCase(unittest.TestCase):
    """Redirects every bootstrap path constant to a fresh temp dir per test,
    mirroring how test_mine_bullet_bank.py redirects ResumeEngine.kb_dir."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(self.bootstrap_dir, "source_documents")
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(self.bootstrap_dir, "timeline.json")
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(self.bootstrap_dir, "checkpoint.json")
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(self.bootstrap_dir, "bullet-bank-draft.csv")
        bootstrap_bullet_bank.REVIEW_CSV_PATH = os.path.join(self.bootstrap_dir, "review-needed.csv")
        bootstrap_bullet_bank.CERTIFICATIONS_PATH = os.path.join(self.bootstrap_dir, "certifications.json")
        bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH = os.path.join(self.tmp_dir, "bullet-bank-clean.csv")
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _touch(self, filename: str) -> None:
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename), "w", encoding="utf-8") as f:
            f.write("placeholder")


class TestRunIngestionResumeOnly(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_resume_achievements_land_directly_in_clean_csv(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp", title="Manager", start_date="2019", end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["extracted"], 1)
        self.assertEqual(summary["attributed"], 1)
        self.assertEqual(summary["flagged"], 0)
        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Acme Corp", content)
        self.assertIn("Grew email list by 40%", content)


class TestRunIngestionAchievementNotes(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_timeline.match_to_timeline")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="achievement_notes")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="some notes")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="text")
    def test_low_confidence_achievement_goes_to_review(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_achievements, mock_match,
    ):
        self._touch("notes.txt")
        mock_extract_achievements.return_value = [
            bootstrap_extractors.RawAchievement(
                raw_text="Did something notable", company_hint=None, date_hint=None,
                title_hint=None, confidence="low",
            )
        ]
        mock_match.return_value = ("Misc. / Unassigned", "low")

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["flagged"], 1)
        with open(bootstrap_bullet_bank.REVIEW_CSV_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Did something notable", content)


class TestRunIngestionCertificate(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_certificate")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="certificate")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="AWS cert text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="text")
    def test_certificate_goes_to_certifications_json_not_bullets(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_cert,
    ):
        self._touch("aws_cert.txt")
        mock_extract_cert.return_value = bootstrap_extractors.Certificate(
            name="AWS Certified Solutions Architect", issuer="AWS", date="2023",
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["certificates"], 1)
        self.assertEqual(summary["extracted"], 0)
        with open(bootstrap_bullet_bank.CERTIFICATIONS_PATH, encoding="utf-8") as f:
            certs = json.load(f)
        self.assertEqual(certs[0]["name"], "AWS Certified Solutions Architect")


class TestRunIngestionCheckpointResume(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_already_done_file_is_not_reprocessed(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp", title="Manager", start_date="2019", end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )

        bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(mock_extract_resume.call_count, 1)

        bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(mock_extract_resume.call_count, 1, "second run should skip the already-done file")


class TestRunIngestionUnsupportedFile(BootstrapIngestionTestCase):

    def test_unsupported_file_is_skipped_not_crashed(self):
        self._touch("archive.zip")
        summary = bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(summary["extracted"], 0)


if __name__ == "__main__":
    unittest.main()
