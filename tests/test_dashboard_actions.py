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


if __name__ == "__main__":
    unittest.main()
