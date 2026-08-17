import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402


class BootstrapEndToEndTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(
            self.bootstrap_dir, "source_documents"
        )
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(
            self.bootstrap_dir, "timeline.json"
        )
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(
            self.bootstrap_dir, "checkpoint.json"
        )
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(
            self.bootstrap_dir, "bullet-bank-draft.csv"
        )
        bootstrap_bullet_bank.REVIEW_CSV_PATH = os.path.join(
            self.bootstrap_dir, "review-needed.csv"
        )
        bootstrap_bullet_bank.CERTIFICATIONS_PATH = os.path.join(
            self.bootstrap_dir, "certifications.json"
        )
        bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH = os.path.join(
            self.tmp_dir, "bullet-bank-clean.csv"
        )
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)
        bootstrap_profile.CV_DRAFT_CHECKPOINT_PATH = os.path.join(
            self.bootstrap_dir, "cv_draft_checkpoint.json"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


class TestDryRunSmokeTestOnRealFiles(BootstrapEndToEndTestCase):
    """Uses real fixture files and real local-extraction code (Task 2) --
    only the Gemini-calling functions are short-circuited, via dry_run,
    to prove the whole chain doesn't crash on genuine input."""

    def test_mixed_real_files_dry_run_completes_without_crashing(self):
        with open(
            os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "My_Resume.txt"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("Acme Corp, Marketing Manager, 2019-2022\n- Grew email list by 40%")
        with open(
            os.path.join(
                bootstrap_bullet_bank.SOURCE_DOCS_DIR, "achievement_notes.txt"
            ),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("I once led a cross-functional project that shipped early.")

        import docx

        doc = docx.Document()
        doc.add_paragraph("Some freeform career notes with no clear company.")
        doc.save(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "notes.docx"))

        summary = bootstrap_bullet_bank.run_ingestion(dry_run=True)

        self.assertEqual(
            summary,
            {
                "extracted": 0,
                "attributed": 0,
                "flagged": 0,
                "certificates": 0,
                "failed": 0,
            },
        )
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH))
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.CERTIFICATIONS_PATH))
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.TIMELINE_PATH))
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH))


class TestMultiDocumentConsolidation(BootstrapEndToEndTestCase):
    """Combines a resume, a recommendation letter, and a certificate in one
    run_ingestion() call -- Task 5's tests only ever exercised one document
    type at a time; this proves they consolidate correctly together."""

    def _touch(self, filename: str) -> None:
        with open(
            os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("placeholder")

    @patch("bootstrap_bullet_bank.bootstrap_timeline.match_to_timeline")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_certificate")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_achievements")
    @patch(
        "bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements"
    )
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type")
    @patch(
        "bootstrap_bullet_bank.bootstrap_extractors.extract_local_text",
        return_value="fixture text",
    )
    @patch(
        "bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind",
        return_value="text",
    )
    def test_resume_letter_and_certificate_combine_correctly(
        self,
        mock_detect,
        mock_extract_text,
        mock_classify,
        mock_extract_resume,
        mock_extract_achievements,
        mock_extract_cert,
        mock_match,
    ):
        self._touch("resume.txt")
        self._touch("recommendation_letter.txt")
        self._touch("cert.txt")

        def classify_side_effect(filename, text, dry_run=False):
            return {
                "resume.txt": "resume",
                "recommendation_letter.txt": "recommendation_letter",
                "cert.txt": "certificate",
            }[filename]

        mock_classify.side_effect = classify_side_effect
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp",
                    title="Manager",
                    start_date="2019",
                    end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )
        mock_extract_achievements.return_value = [
            bootstrap_extractors.RawAchievement(
                raw_text="Delivered the migration ahead of schedule",
                company_hint="Acme Corp",
                date_hint=None,
                title_hint=None,
                confidence="medium",
            )
        ]
        mock_match.return_value = ("Acme Corp", "medium")
        mock_extract_cert.return_value = bootstrap_extractors.Certificate(
            name="PMP Certification",
            issuer="PMI",
            date="2020",
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["extracted"], 2)
        self.assertEqual(summary["certificates"], 1)

        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            clean_content = f.read()
        self.assertIn("Grew email list by 40%", clean_content)
        self.assertIn("Delivered the migration ahead of schedule", clean_content)
        self.assertEqual(clean_content.count("Acme Corp"), 2)

        with open(bootstrap_bullet_bank.CERTIFICATIONS_PATH, encoding="utf-8") as f:
            certs = json.load(f)
        self.assertEqual(certs[0]["name"], "PMP Certification")


import bootstrap_profile  # noqa: E402


class TestPhaseZeroPointFiveDryRunEndToEnd(BootstrapEndToEndTestCase):
    """Runs Phase 0 then Phase 0.5, both under dry_run=True, over real
    fixture files -- proving the whole chain (ingestion -> checkpoint ->
    timeline -> identity guessing -> file writing) doesn't crash and
    produces every expected file, with zero API calls and zero prompts."""

    def setUp(self):
        super().setUp()
        self.profile_yml_path = os.path.join(self.tmp_dir, "profile.yml")
        self.portals_yml_path = os.path.join(self.tmp_dir, "portals.yml")
        self.cv_md_path = os.path.join(self.tmp_dir, "cv.md")
        self.background_guide_path = os.path.join(
            self.tmp_dir, "user-background-guide.md"
        )
        self.voice_anchors_path = os.path.join(self.tmp_dir, "voice-anchors.md")
        bootstrap_profile.PROFILE_YML_PATH = self.profile_yml_path
        bootstrap_profile.PORTALS_YML_PATH = self.portals_yml_path
        bootstrap_profile.CV_MD_PATH = self.cv_md_path
        bootstrap_profile.BACKGROUND_GUIDE_PATH = self.background_guide_path
        bootstrap_profile.VOICE_ANCHORS_PATH = self.voice_anchors_path
        bootstrap_profile.VERIFIED_METRICS_PATH = os.path.join(
            self.tmp_dir, "verified_metrics.json"
        )
        bootstrap_profile.VERIFIED_TOOLS_PATH = os.path.join(
            self.tmp_dir, "verified_tools.json"
        )
        bootstrap_profile.VERIFIED_PROJECTS_PATH = os.path.join(
            self.tmp_dir, "verified_projects.json"
        )
        bootstrap_profile.VERIFIED_FACTS_PATH = os.path.join(
            self.tmp_dir, "verified_facts.json"
        )
        bootstrap_profile.VERIFIED_CLAIMS_PATH = os.path.join(
            self.tmp_dir, "verified-claims.csv"
        )
        bootstrap_profile.EVIDENCE_GRAPH_PATH = os.path.join(
            self.tmp_dir, "evidence_graph.json"
        )
        bootstrap_profile.EVIDENCE_GUIDE_PATH = os.path.join(
            self.tmp_dir, "evidence-guide.csv"
        )
        bootstrap_profile.SCREENSHOT_METRICS_PATH = os.path.join(
            self.tmp_dir, "extracted-screenshot-metrics.csv"
        )
        bootstrap_profile.RECRUITER_PATTERNS_PATH = os.path.join(
            self.tmp_dir, "recruiter_memory_patterns.json"
        )

    def test_full_dry_run_flow_writes_every_phase_0_5_file(self):
        with open(
            os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "My_Resume.txt"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                "Jamie Rivera\njamie@example.com\nAcme Corp, Marketing Manager, 2019-2022\n- Grew email list by 40%"
            )

        bootstrap_bullet_bank.run_ingestion(dry_run=True)
        bootstrap_profile.run_profile_setup(dry_run=True)

        for path in (
            self.profile_yml_path,
            self.portals_yml_path,
            self.cv_md_path,
            self.background_guide_path,
            self.voice_anchors_path,
            bootstrap_profile.VERIFIED_METRICS_PATH,
            bootstrap_profile.VERIFIED_TOOLS_PATH,
            bootstrap_profile.VERIFIED_PROJECTS_PATH,
            bootstrap_profile.VERIFIED_FACTS_PATH,
            bootstrap_profile.VERIFIED_CLAIMS_PATH,
            bootstrap_profile.EVIDENCE_GRAPH_PATH,
            bootstrap_profile.EVIDENCE_GUIDE_PATH,
            bootstrap_profile.SCREENSHOT_METRICS_PATH,
            bootstrap_profile.RECRUITER_PATTERNS_PATH,
        ):
            self.assertTrue(os.path.exists(path), f"expected {path} to exist")


if __name__ == "__main__":
    unittest.main()
