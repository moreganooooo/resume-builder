import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cli


class TestCliPackage(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

    @patch("orchestrator.run_application_package", return_value=(1, 0))
    @patch("menu.offer_next_steps")
    def test_cli_package_single_jd(self, mock_menu, mock_run):
        with self.runner.isolated_filesystem():
            with open("job.json", "w") as f:
                f.write("{}")
            result = self.runner.invoke(cli.cli, ["package", "job.json"])
            self.assertEqual(result.exit_code, 0)
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertEqual(kwargs.get("jd_path"), "job.json")

    @patch("orchestrator.run_application_package", return_value=(1, 0))
    @patch("menu.offer_next_steps")
    def test_cli_build_alias(self, mock_menu, mock_run):
        with self.runner.isolated_filesystem():
            with open("job.json", "w") as f:
                f.write("{}")
            result = self.runner.invoke(cli.cli, ["build", "job.json"])
            self.assertEqual(result.exit_code, 0)
            mock_run.assert_called_once()

    @patch("orchestrator.run_application_package", return_value=(0, 1))
    @patch("menu.offer_next_steps")
    def test_cli_package_failed_exit_code(self, mock_menu, mock_run):
        with self.runner.isolated_filesystem():
            with open("job.json", "w") as f:
                f.write("{}")
            result = self.runner.invoke(cli.cli, ["package", "job.json"])
            self.assertEqual(result.exit_code, 1)

    def test_cli_package_pick_and_jd_file_conflict(self):
        with self.runner.isolated_filesystem():
            with open("job.json", "w") as f:
                f.write("{}")
            result = self.runner.invoke(cli.cli, ["package", "job.json", "--pick"])
            self.assertEqual(result.exit_code, 1)

    def test_cli_package_pick_and_referral_conflict(self):
        result = self.runner.invoke(cli.cli, ["package", "--pick", "--referral", "Jane Doe"])
        self.assertEqual(result.exit_code, 1)


if __name__ == "__main__":
    unittest.main()
