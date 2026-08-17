"""Unit tests for scripts/build_sample.py."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_sample  # noqa: E402


class TestBuildSample(unittest.TestCase):
    """Test suite for build_sample module."""

    def test_build_sample_fixture_missing(self):
        """Test build_sample when SAMPLE_JD_PATH does not exist."""
        with patch.object(build_sample, "SAMPLE_JD_PATH", "/nonexistent/sample_jd.txt"):
            res = build_sample.build_sample()
            self.assertEqual(res, {"resume": {}, "coverletter": {}})

    @patch("build_sample.orchestrator.ResumeEngine")
    @patch("build_sample.jd_manager")
    @patch("os.path.exists", return_value=True)
    def test_build_sample_success(self, mock_exists, mock_jd_manager, mock_engine_cls):
        """Test build_sample calls engine methods and returns result dict."""
        mock_jd_manager.compute_job_key.return_value = "sample_key_123"
        mock_engine = MagicMock()
        mock_engine.build_tailored_resume.return_value = {
            "_output_paths": {"pdf": "/tmp/resume.pdf"}
        }
        mock_engine.build_tailored_coverletter.return_value = {
            "_output_paths": {"pdf": "/tmp/cl.pdf"}
        }
        mock_engine_cls.return_value = mock_engine

        res = build_sample.build_sample()
        self.assertIn("resume", res)
        self.assertIn("coverletter", res)
        self.assertEqual(res["resume"]["_output_paths"]["pdf"], "/tmp/resume.pdf")
        self.assertEqual(res["coverletter"]["_output_paths"]["pdf"], "/tmp/cl.pdf")
        mock_jd_manager.delete_checkpoint.assert_called_once_with("sample_key_123")

    @patch("build_sample.build_sample")
    def test_main_success(self, mock_build_sample):
        """Test main when both resume and coverletter builds succeed."""
        mock_build_sample.return_value = {
            "resume": {"_output_paths": {"pdf": "/tmp/resume.pdf"}},
            "coverletter": {"_output_paths": {"pdf": "/tmp/cl.pdf"}},
        }
        build_sample.main()

    @patch("build_sample.build_sample")
    def test_main_failure(self, mock_build_sample):
        """Test main raises SystemExit when a build fails."""
        mock_build_sample.return_value = {
            "resume": {},
            "coverletter": {},
        }
        with self.assertRaises(SystemExit):
            build_sample.main()


if __name__ == "__main__":
    unittest.main()
