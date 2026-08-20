import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import jd_manager
import orchestrator
import profile_paths


class TestApplicationPackage(unittest.TestCase):

    def setUp(self):
        # build_application_package() runs for real here (only liveness and
        # the LLM calls are mocked), and it writes job rows through
        # db.upsert_job -> profile_paths. Without redirecting PROFILES_DIR
        # those writes land in the developer's own profiles/<name>/data.db:
        # this class alone put thousands of "Test"/"Role" @ "Acme Corp" rows
        # into a real 61 MB database, where they then showed up in the
        # dashboard as real jobs. Same isolation pattern as
        # test_profile_gate.py.
        tmp_profiles = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_profiles, ignore_errors=True)
        os.makedirs(os.path.join(tmp_profiles, "testprofile"), exist_ok=True)

        for patcher in (
            patch.object(profile_paths, "PROFILES_DIR", tmp_profiles),
            patch.dict(os.environ, {"RESUME_PROFILE": "testprofile"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.engine = orchestrator.ResumeEngine()
        self.test_dir = tempfile.mkdtemp()
        self.jd_path = os.path.join(self.test_dir, "test_job.json")
        self.jd_data = {
            "title": "Senior Content Strategist",
            "company": "Testco",
            "source_url": "https://boards.greenhouse.io/testco/jobs/123",
            "description": "We are looking for a Senior Content Strategist with 8+ years experience in content design and messaging.",
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_data, f)
        self.job_key = jd_manager.compute_job_key(self.jd_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if hasattr(self, "job_key") and self.job_key:
            cp = jd_manager._checkpoint_path(self.job_key)
            if os.path.exists(cp):
                os.remove(cp)

    @patch("liveness.verify_jd_paths")
    def test_liveness_expired_moves_to_expired_and_aborts(self, mock_liveness):
        mock_liveness.return_value = {
            "active": 0,
            "likely_active": 0,
            "expired": 1,
            "uncertain": 0,
            "moved": 1,
            "expired_source_paths": [self.jd_path],
        }
        res = self.engine.build_application_package(self.jd_path)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "expired")
        mock_liveness.assert_called_once()

    @patch("liveness.verify_jd_paths")
    def test_fit_skip_moves_to_archived_and_aborts(self, mock_liveness):
        mock_liveness.return_value = {
            "active": 1,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "moved": 0,
        }
        with (
            patch.object(self.engine, "evaluate_fit") as mock_eval,
            patch(
                "jd_manager.archive_jd", return_value="jds/archived/test_job.json"
            ) as mock_archive,
        ):
            mock_eval.return_value = {
                "recommendation": "Skip",
                "composite_score": 2.1,
                "fit_score": 2.0,
                "interview_odds_score": 2.2,
                "practical_pursue_score": 2.0,
                "hard_blockers": ["Requires 15+ years in Defense"],
            }
            res = self.engine.build_application_package(self.jd_path)
            self.assertIsNotNone(res)
            self.assertEqual(res.get("status"), "skipped")
            mock_archive.assert_called_once()

    @patch("liveness.verify_jd_paths")
    def test_fit_skip_with_force_proceeds(self, mock_liveness):
        mock_liveness.return_value = {
            "active": 1,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "moved": 0,
        }
        with (
            patch.object(self.engine, "evaluate_fit") as mock_eval,
            patch.object(self.engine, "build_tailored_resume") as mock_resume,
            patch.object(self.engine, "build_tailored_coverletter") as mock_cl,
            patch("jd_manager.archive_jd") as mock_archive,
            patch("shutil.move"),
            patch("db.checkpoint"),
        ):
            mock_eval.return_value = {"recommendation": "Skip", "composite_score": 2.1}
            mock_resume.return_value = {
                "_output_paths": {
                    "pdf": "res.pdf",
                    "docx": "res.docx",
                    "json": "res.json",
                }
            }
            mock_cl.return_value = {
                "_output_paths": {"pdf": "cl.pdf", "docx": "cl.docx", "json": "cl.json"}
            }

            res = self.engine.build_application_package(self.jd_path, force=True)
            self.assertIsNotNone(res)
            self.assertEqual(res.get("status"), "completed")
            mock_archive.assert_not_called()
            mock_resume.assert_called_once()
            mock_cl.assert_called_once()

    @patch("liveness.verify_jd_paths")
    def test_full_package_builds_all_four_artifacts(self, mock_liveness):
        mock_liveness.return_value = {
            "active": 1,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "moved": 0,
        }
        with (
            patch.object(self.engine, "evaluate_fit") as mock_eval,
            patch.object(self.engine, "build_tailored_resume") as mock_resume,
            patch.object(self.engine, "build_tailored_coverletter") as mock_cl,
            patch("shutil.move"),
            patch("db.checkpoint"),
        ):
            mock_eval.return_value = {
                "recommendation": "Strong Pursue",
                "composite_score": 4.5,
            }
            mock_resume.return_value = {
                "_output_paths": {
                    "pdf": "/path/to/resume.pdf",
                    "docx": "/path/to/resume.docx",
                    "json": "/path/to/resume.json",
                    "html": "/path/to/resume.html",
                }
            }
            mock_cl.return_value = {
                "_output_paths": {
                    "pdf": "/path/to/cl.pdf",
                    "docx": "/path/to/cl.docx",
                    "json": "/path/to/cl.json",
                    "html": "/path/to/cl.html",
                }
            }

            res = self.engine.build_application_package(
                self.jd_path, referral="Jane Doe"
            )
            self.assertIsNotNone(res)
            self.assertEqual(res.get("status"), "completed")
            self.assertEqual(res["output_paths"]["resume_pdf"], "/path/to/resume.pdf")
            self.assertEqual(res["output_paths"]["resume_docx"], "/path/to/resume.docx")
            self.assertEqual(res["output_paths"]["coverletter_pdf"], "/path/to/cl.pdf")
            self.assertEqual(
                res["output_paths"]["coverletter_docx"], "/path/to/cl.docx"
            )
            # Verify referral was saved
            ref = jd_manager.read_referral(self.jd_path)
            self.assertEqual(ref.get("text"), "Jane Doe")

    @patch("orchestrator.ResumeEngine.build_application_package")
    @patch("jd_manager.get_pending_jds")
    def test_run_application_package_batch(self, mock_pending, mock_build_pkg):
        mock_pending.return_value = ["jds/one.json", "jds/two.json"]
        mock_build_pkg.side_effect = [
            {"status": "completed", "output_paths": {}},
            {"status": "skipped", "evaluation": {}},
        ]
        completed, failed = orchestrator.run_application_package()
        self.assertEqual(completed, 1)
        self.assertEqual(failed, 0)
        self.assertEqual(mock_build_pkg.call_count, 2)


if __name__ == "__main__":
    unittest.main()
