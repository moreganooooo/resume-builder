import contextlib
import io
import json
import os
import shutil
import tempfile
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import dashboard_actions  # noqa: E402


class JDFileTestCase(unittest.TestCase):
    """Gives each test a real JD file on disk.

    These tests used to pass the string self.jd_path, which never
    existed. That was harmless while every action took a path blindly,
    but actions now fall back to a database lookup when the path is
    absent (see jd_source.resolved_jd), so a fictional path silently
    exercises the wrong branch. A real file keeps them testing what they
    name.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.jd_path = os.path.join(self._dir, "a.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({"job_title": "Analyst", "company_name": "Acme"}, f)
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)


class TestLiveness(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_success_refreshes_export_and_returns_zero(self, mock_verify, mock_export):
        mock_verify.return_value = {
            "active": 1,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "moved": 0,
        }
        code = dashboard_actions._liveness(self.jd_path, "/tmp/jobs.json")
        mock_verify.assert_called_once_with([self.jd_path])
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_error_result_returns_nonzero_without_refreshing(
        self, mock_verify, mock_export
    ):
        mock_verify.return_value = {"error": True}
        code = dashboard_actions._liveness(self.jd_path, "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestTailor(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_success_refreshes_export_and_returns_zero(self, mock_run, mock_export):
        mock_run.return_value = (1, 0)
        code = dashboard_actions._tailor(self.jd_path, "/tmp/jobs.json")
        mock_run.assert_called_once_with(jd_path=self.jd_path)
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_zero_completed_returns_nonzero_without_refreshing(
        self, mock_run, mock_export
    ):
        mock_run.return_value = (0, 1)
        code = dashboard_actions._tailor(self.jd_path, "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestStatus(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_valid_status_refreshes_export_and_returns_zero(
        self, mock_save, mock_export
    ):
        code = dashboard_actions._status(
            self.jd_path, "Applied", "/tmp/jobs.json"
        )
        mock_save.assert_called_once_with(self.jd_path, "Applied")
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_invalid_status_rejected_without_saving(self, mock_save, mock_export):
        code = dashboard_actions._status(
            self.jd_path, "NotARealStatus", "/tmp/jobs.json"
        )
        self.assertEqual(code, 1)
        mock_save.assert_not_called()
        mock_export.assert_not_called()


class TestArchive(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.archive_jd")
    def test_success_refreshes_export_and_returns_zero(self, mock_archive, mock_export):
        mock_archive.return_value = "archived/a.json"
        code = dashboard_actions._archive(self.jd_path, "/tmp/jobs.json")
        mock_archive.assert_called_once_with(self.jd_path)
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.archive_jd")
    def test_failure_returns_nonzero_without_refreshing(
        self, mock_archive, mock_export
    ):
        mock_archive.side_effect = Exception("OS Error")
        code = dashboard_actions._archive(self.jd_path, "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestExport(unittest.TestCase):
    """The `export` subcommand backs main.go's startup fallback: a
    dashboard launched straight from the binary gets no -jobs-path, and
    without this would show an empty Browse & Manage Jobs screen."""

    def test_export_writes_the_jobs_file_and_succeeds(self):
        rows = [{"title": "Lifecycle Marketing Manager", "skills": []}]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jobs.json")
            with patch("picker.list_all_evaluated_jds", return_value=rows):
                code = dashboard_actions._export(out)

            self.assertEqual(code, 0)
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), rows)

    def test_export_is_routed_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jobs.json")
            argv = ["dashboard_actions.py", "export", "--jobs-path", out]
            with patch.object(sys, "argv", argv):
                with patch("picker.list_all_evaluated_jds", return_value=[]):
                    self.assertEqual(dashboard_actions.main(), 0)
            self.assertTrue(os.path.exists(out))

    def test_export_does_not_require_a_jd_path(self):
        """Unlike every other subcommand, export operates on the whole
        corpus -- requiring a positional jd_path would break main.go."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jobs.json")
            argv = ["dashboard_actions.py", "export", "--jobs-path", out]
            with patch.object(sys, "argv", argv):
                with patch("picker.list_all_evaluated_jds", return_value=[]):
                    dashboard_actions.main()  # must not SystemExit


class TestUserErrorContract(JDFileTestCase):
    """dashboard_actions.py promises jobs.go that on failure its LAST
    non-empty stderr line is "USER_ERROR: <plain sentence>" -- Go's
    parseActionError() checks only that final line and gives up at the
    first non-empty one it sees.

    That makes the contract silently breakable from either side: anything
    that prints to stderr after _user_error(), or a new failing path that
    forgets to call it, degrades the dashboard back to showing raw
    tracebacks with no test failing. These tests pin the position, not
    just the presence, of the marker."""

    @staticmethod
    def _last_nonempty(stderr_text: str) -> str:
        lines = [ln.strip() for ln in stderr_text.splitlines() if ln.strip()]
        return lines[-1] if lines else ""

    def _capture_stderr(self, fn) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            fn()
        return buf.getvalue()

    def test_invalid_status_puts_marker_on_the_last_line(self):
        err = self._capture_stderr(
            lambda: dashboard_actions._status(
                self.jd_path, "NotARealStatus", "/tmp/jobs.json"
            )
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))
        # The raw developer-facing detail is still emitted, just earlier --
        # jobs.go keeps it behind "d for details".
        self.assertIn("NotARealStatus", err)

    @patch("dashboard_actions.jd_manager.archive_jd")
    def test_archive_failure_puts_marker_on_the_last_line(self, mock_archive):
        mock_archive.side_effect = Exception("OS Error")
        err = self._capture_stderr(
            lambda: dashboard_actions._archive(self.jd_path, "/tmp/jobs.json")
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))

    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_liveness_failure_puts_marker_on_the_last_line(self, mock_verify):
        mock_verify.return_value = {"error": "connection refused"}
        err = self._capture_stderr(
            lambda: dashboard_actions._liveness(self.jd_path, "/tmp/jobs.json")
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))
        self.assertIn("connection refused", err)

    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_tailor_failure_puts_marker_on_the_last_line(self, mock_run):
        mock_run.return_value = (0, 1)
        err = self._capture_stderr(
            lambda: dashboard_actions._tailor(self.jd_path, "/tmp/jobs.json")
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))

    @patch("dashboard_actions.main")
    def test_uncaught_exception_is_translated_not_leaked_as_a_traceback(
        self, mock_main
    ):
        mock_main.side_effect = FileNotFoundError("/gone/master.json")
        err = self._capture_stderr(
            lambda: self.assertEqual(dashboard_actions._run(), 1)
        )
        # Traceback still present as detail...
        self.assertIn("Traceback", err)
        # ...but a plain sentence is what jobs.go will actually surface,
        # and it must not be the raw exception repr.
        last = self._last_nonempty(err)
        self.assertTrue(last.startswith("USER_ERROR:"))
        self.assertNotIn("FileNotFoundError", last)

    @patch("dashboard_actions.main")
    def test_systemexit_is_not_decorated(self, mock_main):
        # argparse's --help/usage path exits via SystemExit and has already
        # written its own output; appending a USER_ERROR line there would
        # corrupt otherwise-clean help text.
        mock_main.side_effect = SystemExit(0)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), self.assertRaises(SystemExit):
            dashboard_actions._run()
        self.assertNotIn("USER_ERROR:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
