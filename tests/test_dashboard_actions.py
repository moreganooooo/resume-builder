import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import dashboard_actions  # noqa: E402


class TestLiveness(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_success_refreshes_export_and_returns_zero(self, mock_verify, mock_export):
        mock_verify.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0}
        code = dashboard_actions._liveness("jds/morgan/a.json", "/tmp/jobs.json")
        mock_verify.assert_called_once_with(["jds/morgan/a.json"])
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_error_result_returns_nonzero_without_refreshing(self, mock_verify, mock_export):
        mock_verify.return_value = {"error": True}
        code = dashboard_actions._liveness("jds/morgan/a.json", "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestTailor(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_success_refreshes_export_and_returns_zero(self, mock_run, mock_export):
        mock_run.return_value = (1, 0)
        code = dashboard_actions._tailor("jds/morgan/a.json", "/tmp/jobs.json")
        mock_run.assert_called_once_with(jd_path="jds/morgan/a.json")
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_zero_completed_returns_nonzero_without_refreshing(self, mock_run, mock_export):
        mock_run.return_value = (0, 1)
        code = dashboard_actions._tailor("jds/morgan/a.json", "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestStatus(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_valid_status_refreshes_export_and_returns_zero(self, mock_save, mock_export):
        code = dashboard_actions._status("jds/morgan/a.json", "Applied", "/tmp/jobs.json")
        mock_save.assert_called_once_with("jds/morgan/a.json", "Applied")
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_invalid_status_rejected_without_saving(self, mock_save, mock_export):
        code = dashboard_actions._status("jds/morgan/a.json", "NotARealStatus", "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_save.assert_not_called()
        mock_export.assert_not_called()


class TestUserErrorContract(unittest.TestCase):
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
            lambda: dashboard_actions._status("jds/morgan/a.json", "NotARealStatus", "/tmp/jobs.json")
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))
        # The raw developer-facing detail is still emitted, just earlier --
        # jobs.go keeps it behind "d for details".
        self.assertIn("NotARealStatus", err)

    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_liveness_failure_puts_marker_on_the_last_line(self, mock_verify):
        mock_verify.return_value = {"error": "connection refused"}
        err = self._capture_stderr(
            lambda: dashboard_actions._liveness("jds/morgan/a.json", "/tmp/jobs.json")
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))
        self.assertIn("connection refused", err)

    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_tailor_failure_puts_marker_on_the_last_line(self, mock_run):
        mock_run.return_value = (0, 1)
        err = self._capture_stderr(
            lambda: dashboard_actions._tailor("jds/morgan/a.json", "/tmp/jobs.json")
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))

    @patch("dashboard_actions.main")
    def test_uncaught_exception_is_translated_not_leaked_as_a_traceback(self, mock_main):
        mock_main.side_effect = FileNotFoundError("/gone/master.json")
        err = self._capture_stderr(lambda: self.assertEqual(dashboard_actions._run(), 1))
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
