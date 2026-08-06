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


class TestRunIngestionAppendsToExistingBank(BootstrapIngestionTestCase):
    # Regression coverage: this script was written for a first-time user
    # with nothing to lose (see its own docstring), but nothing stopped an
    # earlier version from being re-run against an established, months-of-
    # work bank and silently wiping it. The fix isn't to refuse -- it's to
    # make the default behavior genuinely safe: only append rows extracted
    # from files processed in *this* call, never touch what's already there.

    def _seed_existing_bank(self, n_rows: int) -> None:
        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, "w", encoding="utf-8") as f:
            f.write("Role / Company,Tags,Bullet Point\n")
            for i in range(n_rows):
                f.write(f"Acme,[content],- Existing bullet {i}\n")

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_new_document_is_appended_without_touching_existing_rows(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._seed_existing_bank(50)  # a large, established bank
        self._touch("New_Resume.docx")
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

        self.assertEqual(summary["extracted"], 1)  # only the new document's row, not all 51
        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            rows = list(__import__("csv").DictReader(f))
        self.assertEqual(len(rows), 51)  # 50 existing + 1 new
        self.assertIn("Existing bullet 0", rows[0]["Bullet Point"])
        self.assertIn("Grew email list by 40%", rows[-1]["Bullet Point"])

    def test_rerunning_with_no_new_documents_leaves_bank_unchanged(self):
        self._seed_existing_bank(50)
        # No source documents queued at all.
        summary = bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(summary["extracted"], 0)
        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            rows = list(__import__("csv").DictReader(f))
        self.assertEqual(len(rows), 50)

    def test_force_true_discards_existing_rows_and_rebuilds_from_checkpoint(self):
        self._seed_existing_bank(50)
        # force=True reconstructs entirely from checkpoint.json, which is
        # empty here (no files ever processed) -- so the 50 seeded rows,
        # which aren't reachable from an empty checkpoint, are discarded.
        summary = bootstrap_bullet_bank.run_ingestion(force=True)
        self.assertEqual(summary["extracted"], 0)
        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            rows = list(__import__("csv").DictReader(f))
        self.assertEqual(len(rows), 0)


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


class TestRunIngestionAPIFailure(BootstrapIngestionTestCase):
    # B16: reproduces the real bug -- a fresh profile, no API key, a 403 on
    # ingestion. Before the fix: exit 0, checkpoint "done", work_experience
    # []. After: checkpoint "failed" (not "done", so not permanently
    # skipped), a nonzero summary["failed"], and a retry that actually
    # re-attempts the call once the key is fixed.

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_api_failure_checkpoints_failed_not_done(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.side_effect = bootstrap_extractors.IngestionAPIError(
            "Gemini API call failed while extracting the resume/LinkedIn timeline -- "
            "see the WARNING above for the status code."
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["extracted"], 0)
        self.assertEqual(summary["failed"], 1)
        checkpoint = bootstrap_bullet_bank._load_checkpoint()
        self.assertEqual(checkpoint["My_Resume.docx"]["status"], "failed")
        self.assertIn("reason", checkpoint["My_Resume.docx"])
        self.assertNotEqual(checkpoint["My_Resume.docx"]["status"], "done")

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_retry_after_failure_actually_reattempts_the_call(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.side_effect = bootstrap_extractors.IngestionAPIError("simulated 403")

        summary_1 = bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(summary_1["failed"], 1)
        self.assertEqual(mock_extract_resume.call_count, 1)

        # Key is "fixed" -- the next call succeeds for real.
        mock_extract_resume.side_effect = None
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp", title="Manager", start_date="2019", end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )

        summary_2 = bootstrap_bullet_bank.run_ingestion()

        # A "done"-marked file is skipped and never re-invokes the mock (see
        # TestRunIngestionCheckpointResume) -- a "failed"-marked one must
        # NOT be skipped the same way, or fixing the key would never help.
        self.assertEqual(mock_extract_resume.call_count, 2, "a 'failed' checkpoint entry must be retried, not skipped")
        self.assertEqual(summary_2["extracted"], 1)
        self.assertEqual(summary_2["failed"], 0)
        checkpoint = bootstrap_bullet_bank._load_checkpoint()
        self.assertEqual(checkpoint["My_Resume.docx"]["status"], "done")

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_summary_print_mentions_failure_count(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.side_effect = bootstrap_extractors.IngestionAPIError("simulated 403")
        summary = bootstrap_bullet_bank.run_ingestion()

        with patch("builtins.print") as mock_print:
            bootstrap_bullet_bank.print_ingestion_summary(summary)
        printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn("1 document(s) failed", printed)


if __name__ == "__main__":
    unittest.main()
