import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import doctor  # noqa: E402


class TestCheckPythonVersion(unittest.TestCase):

    def test_passes_on_this_interpreter(self):
        # This suite itself only runs on Python 3.10+ (per CLAUDE.md), so
        # the real sys.version_info here is always a real, current pass.
        result = doctor.check_python_version()
        self.assertTrue(result["passed"])
        self.assertEqual(result["fix"], "")

    @patch("doctor.sys")
    def test_fails_below_minimum(self, mock_sys):
        mock_sys.version_info = (3, 9, 0)
        mock_sys.version = "3.9.0"
        result = doctor.check_python_version()
        self.assertFalse(result["passed"])
        self.assertNotEqual(result["fix"], "")


class TestCheckVenv(unittest.TestCase):

    @patch("doctor.os.path.isdir", return_value=True)
    @patch("doctor.sys")
    def test_passes_when_present_and_active(self, mock_sys, mock_isdir):
        mock_sys.prefix = "/some/venv"
        mock_sys.base_prefix = "/usr/local"
        result = doctor.check_venv()
        self.assertTrue(result["passed"])

    @patch("doctor.os.path.isdir", return_value=False)
    @patch("doctor.sys")
    def test_fails_when_missing(self, mock_sys, mock_isdir):
        mock_sys.prefix = "/x"
        mock_sys.base_prefix = "/x"
        result = doctor.check_venv()
        self.assertFalse(result["passed"])

    @patch("doctor.os.path.isfile", return_value=False)
    @patch("doctor.os.path.isdir", return_value=False)
    def test_failing_detail_does_not_claim_ready_to_use(self, mock_isdir, mock_isfile):
        # B32: detail used to hardcode "ready to use" regardless of the
        # actual passed/failed verdict.
        result = doctor.check_venv()
        self.assertFalse(result["passed"])
        self.assertNotIn("ready to use", result["detail"])
        self.assertIn("not usable", result["detail"])


class TestCheckPythonPackages(unittest.TestCase):

    def test_passes_when_everything_importable(self):
        # Real check against this project's actual .venv, which requirements.txt
        # itself guarantees is fully installed per CLAUDE.md Setup.
        result = doctor.check_python_packages()
        self.assertTrue(result["passed"], result["detail"])

    @patch("doctor.importlib.import_module")
    def test_flags_missing_packages_with_a_pip_install_fix(self, mock_import):
        def side_effect(name):
            if name == "yaml":
                raise ImportError("no module named yaml")

        mock_import.side_effect = side_effect
        result = doctor.check_python_packages()
        self.assertFalse(result["passed"])
        self.assertIn("pyyaml", result["detail"])
        self.assertIn("pip install", result["fix"])
        self.assertIn("pyyaml", result["fix"])


class TestCheckNode(unittest.TestCase):

    @patch("doctor.shutil.which", return_value="/usr/local/bin/node")
    def test_passes_when_found(self, mock_which):
        self.assertTrue(doctor.check_node()["passed"])

    @patch("doctor.shutil.which", return_value=None)
    def test_fails_when_not_on_path(self, mock_which):
        result = doctor.check_node()
        self.assertFalse(result["passed"])
        self.assertIn("nodejs.org", result["fix"])


class TestCheckNpm(unittest.TestCase):

    @patch("doctor.shutil.which", side_effect=lambda cmd: f"/usr/local/bin/{cmd}")
    def test_passes_when_both_found(self, mock_which):
        result = doctor.check_npm()
        self.assertTrue(result["passed"])

    @patch("doctor.shutil.which", return_value=None)
    def test_fails_when_neither_found(self, mock_which):
        result = doctor.check_npm()
        self.assertFalse(result["passed"])
        self.assertIn("nodejs.org", result["fix"])


class TestCheckPlaywrightNpmPackage(unittest.TestCase):

    @patch("doctor.os.path.isdir", return_value=True)
    def test_passes_when_present(self, mock_isdir):
        self.assertTrue(doctor.check_playwright_npm_package()["passed"])

    @patch("doctor.shutil.which", return_value="/usr/local/bin/npm")
    @patch("doctor.os.path.isdir", return_value=False)
    def test_fails_with_npm_install_fix(self, mock_isdir, mock_which):
        result = doctor.check_playwright_npm_package()
        self.assertFalse(result["passed"])
        self.assertIn("npm install", result["fix"])

    @patch("doctor.shutil.which", return_value=None)
    @patch("doctor.os.path.isdir", return_value=False)
    def test_fix_is_conditional_on_npm_being_available(self, mock_isdir, mock_which):
        # B32: telling someone without npm to run `npm install` with no
        # other context is a dead end -- the fix should point at the
        # npm/npx check first.
        result = doctor.check_playwright_npm_package()
        self.assertFalse(result["passed"])
        self.assertIn("npm/npx check", result["fix"])


class TestCheckPlaywrightChromium(unittest.TestCase):

    @patch("doctor.os.listdir", return_value=["chromium-1223", "firefox-1532"])
    @patch("doctor.os.path.isdir", return_value=True)
    def test_passes_when_a_chromium_install_exists(self, mock_isdir, mock_listdir):
        self.assertTrue(doctor.check_playwright_chromium()["passed"])

    @patch("doctor.shutil.which", return_value="/usr/local/bin/npx")
    @patch("doctor.os.path.isdir", return_value=False)
    def test_fails_when_cache_dir_missing(self, mock_isdir, mock_which):
        result = doctor.check_playwright_chromium()
        self.assertFalse(result["passed"])
        self.assertIn("playwright install chromium", result["fix"])

    @patch("doctor.shutil.which", return_value=None)
    @patch("doctor.os.path.isdir", return_value=False)
    def test_fix_is_conditional_on_npx_being_available(self, mock_isdir, mock_which):
        result = doctor.check_playwright_chromium()
        self.assertFalse(result["passed"])
        self.assertIn("npm/npx check", result["fix"])


class TestCheckGo(unittest.TestCase):

    @patch("doctor.shutil.which", return_value="/usr/local/bin/go")
    def test_always_passes_when_found(self, mock_which):
        result = doctor.check_go()
        self.assertTrue(result["passed"])
        self.assertIn("found", result["detail"])

    @patch("doctor.shutil.which", return_value=None)
    def test_still_passes_when_not_on_path(self, mock_which):
        # Optional dependency -- missing Go is never a hard failure, just
        # a note that `resume dashboard` specifically won't work.
        result = doctor.check_go()
        self.assertTrue(result["passed"])
        self.assertIn("resume dashboard", result["detail"])


class TestCheckGeminiApiKey(unittest.TestCase):

    @patch("doctor._env_values", return_value={"GEMINI_API_KEY": "abc123"})
    def test_passes_when_set_in_env_file(self, mock_values):
        result = doctor.check_gemini_api_key()
        self.assertTrue(result["passed"])
        self.assertIn(".env", result["detail"])

    @patch.dict(os.environ, {}, clear=True)
    @patch("doctor._env_values", return_value={})
    def test_fails_when_nowhere_to_be_found(self, mock_values):
        result = doctor.check_gemini_api_key()
        self.assertFalse(result["passed"])
        self.assertNotEqual(result["fix"], "")


class TestCheckJobrightCookie(unittest.TestCase):

    @patch("doctor._env_values", return_value={})
    def test_always_passes_since_optional(self, mock_values):
        # Never a hard failure -- only needed for scan --source jobright.
        result = doctor.check_jobright_cookie()
        self.assertTrue(result["passed"])
        self.assertEqual(result["fix"], "")


class TestCheckFonts(unittest.TestCase):

    def test_passes_on_the_real_repo_fonts_dir(self):
        # These files are tracked in git -- a real, present-by-default check.
        result = doctor.check_fonts()
        self.assertTrue(result["passed"], result["detail"])

    @patch("doctor.os.path.exists", return_value=False)
    def test_fails_and_lists_missing_files(self, mock_exists):
        result = doctor.check_fonts()
        self.assertFalse(result["passed"])
        self.assertIn("DMSans-Regular-static.ttf", result["detail"])


class TestCheckSignatureImage(unittest.TestCase):

    def test_always_passes_missing_or_not(self):
        # Informational only, per README's documented graceful degradation.
        self.assertTrue(doctor.check_signature_image()["passed"])
        self.assertEqual(doctor.check_signature_image()["fix"], "")


class TestCheckIconSet(unittest.TestCase):

    def test_always_passes(self):
        self.assertTrue(doctor.check_icon_set()["passed"])

    @patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "unicode"})
    def test_reports_env_override(self):
        result = doctor.check_icon_set()
        self.assertIn("RESUME_BUILDER_ICONS override", result["detail"])

    @patch.dict(os.environ, {}, clear=False)
    @patch("ui_config.get_icon_set", return_value="nerd")
    def test_reports_persisted_choice(self, mock_get):
        os.environ.pop("RESUME_BUILDER_ICONS", None)
        result = doctor.check_icon_set()
        self.assertIn("nerd", result["detail"])
        self.assertIn("first launch", result["detail"])

    @patch.dict(os.environ, {}, clear=False)
    @patch("ui_config.get_icon_set", return_value=None)
    def test_reports_not_yet_chosen(self, mock_get):
        os.environ.pop("RESUME_BUILDER_ICONS", None)
        result = doctor.check_icon_set()
        self.assertIn("not yet chosen", result["detail"])


class TestCheckDashboardThemeSync(unittest.TestCase):

    def test_passes_on_the_real_checked_in_file(self):
        # The committed Go file must already match what the generator
        # produces from the current theme.py -- this is the actual
        # regression guard (B23/P2F9): if someone hand-edits the Go file's
        # hex values, or changes theme.py without re-running the sync
        # script, this fails.
        result = doctor.check_dashboard_theme_sync()
        self.assertTrue(result["passed"], result["detail"])

    def test_fails_when_file_is_out_of_sync(self):
        import sync_dashboard_theme

        tmp_path = os.path.join(os.path.dirname(__file__), "_tmp_out_of_sync.go")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("package theme\n// stale content\n")
        try:
            with patch("sync_dashboard_theme.DASHBOARD_THEME_PATH", tmp_path):
                result = doctor.check_dashboard_theme_sync()
            self.assertFalse(result["passed"])
            self.assertIn("sync_dashboard_theme.py", result["fix"])
        finally:
            os.remove(tmp_path)

    def test_fails_when_file_is_missing(self):
        import sync_dashboard_theme

        missing_path = os.path.join(os.path.dirname(__file__), "_tmp_does_not_exist.go")
        with patch("sync_dashboard_theme.DASHBOARD_THEME_PATH", missing_path):
            result = doctor.check_dashboard_theme_sync()
        self.assertFalse(result["passed"])
        self.assertIn("not found", result["detail"])


class TestCheckKbAllowlist(unittest.TestCase):

    def setUp(self):
        import orchestrator

        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_kb_allowlist")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._kb_patcher = patch(
            "doctor.profile_paths.kb_dir", return_value=self.tmp_dir
        )
        self._kb_patcher.start()
        self._real_allowlist = orchestrator.KB_ALLOWLIST
        orchestrator.KB_ALLOWLIST = ["bullet-bank.md", "profile.yml"]

    def tearDown(self):
        import orchestrator

        orchestrator.KB_ALLOWLIST = self._real_allowlist
        self._kb_patcher.stop()
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content="content"):
        with open(os.path.join(self.tmp_dir, name), "w", encoding="utf-8") as f:
            f.write(content)

    def test_passes_when_all_present_nonempty_and_no_conflicts(self):
        self._write("bullet-bank.md")
        self._write("profile.yml")
        result = doctor.check_kb_allowlist()
        self.assertTrue(result["passed"], result["detail"])
        self.assertEqual(result["fix"], "")

    def test_fails_and_lists_missing_files(self):
        self._write("bullet-bank.md")
        result = doctor.check_kb_allowlist()
        self.assertFalse(result["passed"])
        self.assertIn("missing", result["detail"])
        self.assertIn("profile.yml", result["detail"])

    def test_fails_on_zero_byte_file(self):
        self._write("bullet-bank.md", content="")
        self._write("profile.yml")
        result = doctor.check_kb_allowlist()
        self.assertFalse(result["passed"])
        self.assertIn("corrupted", result["detail"])
        self.assertIn("bullet-bank.md", result["detail"])

    def test_fails_on_future_mtime(self):
        self._write("bullet-bank.md")
        self._write("profile.yml")
        future = time.time() + 3600
        os.utime(os.path.join(self.tmp_dir, "profile.yml"), (future, future))
        result = doctor.check_kb_allowlist()
        self.assertFalse(result["passed"])
        self.assertIn("corrupted", result["detail"])
        self.assertIn("profile.yml", result["detail"])

    def test_fails_on_sync_conflict_file(self):
        self._write("bullet-bank.md")
        self._write("profile.yml")
        self._write("bullet-bank.sync-conflict-20260101-000000.md")
        result = doctor.check_kb_allowlist()
        self.assertFalse(result["passed"])
        self.assertIn("conflict", result["detail"])
        self.assertIn("sync-conflict", result["detail"])

    def test_collapses_to_one_line_when_fully_unbootstrapped(self):
        # B32: nothing present at all (a brand-new profile) is "never
        # bootstrapped," not "partially broken" -- collapse instead of
        # listing every one of KB_ALLOWLIST's filenames.
        result = doctor.check_kb_allowlist()
        self.assertFalse(result["passed"])
        self.assertIn("0 of 2 present", result["detail"])
        self.assertNotIn("bullet-bank.md", result["detail"])
        self.assertIn("resume bootstrap", result["fix"])


class TestRunChecks(unittest.TestCase):

    def test_returns_one_result_per_registered_check(self):
        results = doctor.run_checks()
        self.assertEqual(len(results), len(doctor.CHECKS))
        for r in results:
            self.assertIn("name", r)
            self.assertIn("passed", r)
            self.assertIn("detail", r)
            self.assertIn("fix", r)


class TestCheckDataDb(unittest.TestCase):

    def test_passes_when_db_is_reachable_and_queryable(self):
        import shutil
        import tempfile

        tmpdir = tempfile.mkdtemp()
        try:
            with patch("profile_paths.profile_root", return_value=tmpdir):
                result = doctor.check_data_db()
            self.assertTrue(result["passed"])
            self.assertIn("reachable", result["detail"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fails_with_actionable_fix_when_db_open_raises(self):
        import db

        with patch.object(db, "get_db", side_effect=OSError("disk full")):
            result = doctor.check_data_db()
        self.assertFalse(result["passed"])
        self.assertIn("disk full", result["detail"])
        self.assertTrue(result["fix"])
        self.assertIn("migrate_filesystem_to_db.py", result["fix"])


class TestRunTestSuite(unittest.TestCase):

    @patch("doctor.subprocess.run")
    def test_passed_true_on_zero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stderr="Ran 5 tests in 0.01s\n\nOK\n"
        )
        passed, summary = doctor.run_test_suite()
        self.assertTrue(passed)
        self.assertIn("OK", summary)

    @patch("doctor.subprocess.run")
    def test_passed_false_on_nonzero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr="Ran 5 tests in 0.01s\n\nFAILED (failures=1)\n"
        )
        passed, summary = doctor.run_test_suite()
        self.assertFalse(passed)
        self.assertIn("FAILED", summary)

    @patch("doctor.subprocess.run")
    def test_passed_false_with_actionable_message_on_timeout(self, mock_run):
        import subprocess as subprocess_module

        mock_run.side_effect = subprocess_module.TimeoutExpired(
            cmd="unittest", timeout=doctor.TEST_SUITE_TIMEOUT_SECONDS
        )
        passed, summary = doctor.run_test_suite()
        self.assertFalse(passed)
        self.assertIn("did not finish", summary)
        self.assertIn("-v", summary)


if __name__ == "__main__":
    unittest.main()
