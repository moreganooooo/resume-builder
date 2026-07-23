import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import dashboard  # noqa: E402


class TestGoAvailable(unittest.TestCase):

    @patch("dashboard.shutil.which", return_value="/usr/local/bin/go")
    def test_true_when_go_on_path(self, mock_which):
        self.assertTrue(dashboard.go_available())

    @patch("dashboard.shutil.which", return_value=None)
    def test_false_when_go_missing(self, mock_which):
        self.assertFalse(dashboard.go_available())


class TestRun(unittest.TestCase):

    @patch("dashboard.go_available", return_value=False)
    def test_returns_false_with_install_hint_when_go_missing(self, mock_go):
        success, message = dashboard.run("morgan")
        self.assertFalse(success)
        self.assertIn("Go isn't installed", message)

    @patch("dashboard.os.path.exists", return_value=False)
    @patch("dashboard.go_available", return_value=True)
    def test_returns_false_when_no_applications_logged_yet(self, mock_go, mock_exists):
        success, message = dashboard.run("morgan")
        self.assertFalse(success)
        self.assertIn("No applications logged yet", message)

    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_launches_go_run_with_the_profile_data_dir(self, mock_go, mock_exists, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        success, message = dashboard.run("morgan")
        self.assertTrue(success)
        expected_data_dir = dashboard.profile_paths.data_dir("morgan")
        mock_subproc.assert_called_once_with(
            ["go", "run", ".", "-path", expected_data_dir],
            cwd=dashboard.DASHBOARD_DIR,
        )

    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_returns_false_when_dashboard_process_exits_nonzero(self, mock_go, mock_exists, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=1)
        success, message = dashboard.run("morgan")
        self.assertFalse(success)
        self.assertIn("exited with an error", message)


if __name__ == "__main__":
    unittest.main()
