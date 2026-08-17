import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
from click.testing import CliRunner  # noqa: E402


class TestDoctorCommand(unittest.TestCase):

    @patch("cli.maintenance.record_run")
    @patch("cli.cli_art.render_doctor_report")
    @patch("cli.doctor.run_test_suite", return_value=(True, "OK"))
    @patch("cli.doctor.run_checks", return_value=[])
    def test_runs_checks_and_tests_by_default(self, mock_checks, mock_tests, mock_render, mock_record):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["doctor"])
        self.assertEqual(result.exit_code, 0)
        mock_checks.assert_called_once()
        mock_tests.assert_called_once()
        mock_record.assert_called_once_with("doctor")

    @patch("cli.maintenance.record_run")
    @patch("cli.cli_art.render_doctor_report")
    @patch("cli.doctor.run_test_suite")
    @patch("cli.doctor.run_checks", return_value=[])
    def test_skip_tests_flag_skips_the_test_suite(self, mock_checks, mock_tests, mock_render, mock_record):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["doctor", "--skip-tests"])
        self.assertEqual(result.exit_code, 0)
        mock_tests.assert_not_called()
        mock_render.assert_called_once_with([], None)


if __name__ == "__main__":
    unittest.main()
