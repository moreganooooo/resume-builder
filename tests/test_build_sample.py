"""Unit tests for scripts/build_sample.py."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_sample  # noqa: E402
import profile_paths  # noqa: E402


class TestResolveSampleJdPath(unittest.TestCase):
    """A profile-specific fixture (profiles/<name>/sample_jd.txt) should
    win over the shared, field-specific fixtures/sample_jd.txt -- a
    profile in a different field needs its own realistic test JD or the
    smoke test proves nothing (bullet bank content won't match at all)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_profile_specific_fixture_wins_when_present(self):
        profile_specific = os.path.join(self.tmp_dir, "sample_jd.txt")
        with open(profile_specific, "w", encoding="utf-8") as f:
            f.write("a real JD")
        with patch(
            "build_sample.profile_paths.profile_root", return_value=self.tmp_dir
        ):
            self.assertEqual(build_sample._resolve_sample_jd_path(), profile_specific)

    def test_falls_back_to_shared_fixture_when_absent(self):
        with patch(
            "build_sample.profile_paths.profile_root", return_value=self.tmp_dir
        ):
            self.assertEqual(
                build_sample._resolve_sample_jd_path(), build_sample.SAMPLE_JD_PATH
            )

    def test_falls_back_safely_if_profile_root_raises(self):
        with patch(
            "build_sample.profile_paths.profile_root",
            side_effect=RuntimeError("no active profile"),
        ):
            self.assertEqual(
                build_sample._resolve_sample_jd_path(), build_sample.SAMPLE_JD_PATH
            )


class TestBuildSample(unittest.TestCase):
    """Test suite for build_sample module."""

    def test_build_sample_fixture_missing(self):
        """Test build_sample when SAMPLE_JD_PATH does not exist.

        Must also isolate profile_root() -- _resolve_sample_jd_path()
        checks a profile-specific fixture (profiles/<name>/sample_jd.txt)
        FIRST, before falling back to the shared/patched SAMPLE_JD_PATH.
        Any profile that has actually added its own (e.g. dominick) has a
        real, existing file there, so without this the early-return branch
        this test exists to cover never triggers -- build_sample() runs
        the real pipeline instead and fails on the live-network guard,
        depending on which profile happens to be active when the suite
        runs (see tests/test_no_operator_identity.py's own reasoning)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # isolate_for_tests() rather than patching profile_root alone:
            # a profile has FOUR roots, and the log path resolves through
            # OUTPUT_ROOT, not profile_root. Patching just the one left
            # build_sample() writing a real pipeline_run_*.log into the
            # developer's own output/<profile>/ on every suite run -- the
            # same partial-isolation trap that seeded jds/testprofile and
            # friends.
            with (
                patch.object(
                    build_sample, "SAMPLE_JD_PATH", "/nonexistent/sample_jd.txt"
                ),
                profile_paths.isolate_for_tests(tmp_dir),
            ):
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
