import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
from click.testing import CliRunner  # noqa: E402


def _check(name, passed, detail="", fix=""):
    return {"name": name, "passed": passed, "detail": detail, "fix": fix}


class TestQuickstartCommand(unittest.TestCase):

    @patch("cli.maintenance.record_run")
    @patch(
        "cli.doctor.run_checks", return_value=[_check("Python version", True, "3.13")]
    )
    def test_all_checks_passing_prints_success_and_skips_api_key_prompt(
        self, mock_checks, mock_record
    ):
        with patch("cli.cli_art.text") as mock_text:
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["quickstart"])
            self.assertEqual(result.exit_code, 0)
            mock_text.assert_not_called()
            mock_record.assert_called_once_with("doctor")

    @patch("cli.maintenance.record_run")
    @patch("cli._write_gemini_api_key")
    def test_missing_api_key_prompts_and_writes_it_then_rechecks(
        self, mock_write, mock_record
    ):
        checks_missing = [_check("GEMINI_API_KEY", False, "not set", "Add it to .env")]
        checks_after = [_check("GEMINI_API_KEY", True, "set")]
        with (
            patch(
                "cli.doctor.run_checks", side_effect=[checks_missing, checks_after]
            ) as mock_checks,
            patch("cli.cli_art.text", return_value="fake-key-123"),
        ):
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["quickstart"])

        self.assertEqual(result.exit_code, 0)
        mock_write.assert_called_once_with("fake-key-123")
        self.assertEqual(
            mock_checks.call_count, 2
        )  # initial check + re-check after writing

    @patch("cli.maintenance.record_run")
    def test_declining_the_api_key_prompt_does_not_write_or_crash(self, mock_record):
        checks_missing = [_check("GEMINI_API_KEY", False, "not set", "Add it to .env")]
        with (
            patch("cli.doctor.run_checks", return_value=checks_missing),
            patch("cli._write_gemini_api_key") as mock_write,
            patch("cli.cli_art.text", return_value=""),
        ):
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["quickstart"])

        self.assertEqual(result.exit_code, 0)
        mock_write.assert_not_called()

    @patch("cli.maintenance.record_run")
    def test_a_step_that_fails_and_stays_failed_is_reported_not_swallowed(
        self, mock_record
    ):
        """A partial failure (e.g. Go toolchain missing) must be visible
        in the output, not silently dropped -- this is the case the
        remediation guide specifically called out."""
        checks = [_check("Go toolchain", False, "not found", "brew install go")]
        with patch("cli.doctor.run_checks", return_value=checks):
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["quickstart"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Go toolchain", result.output)
        self.assertIn("brew install go", result.output)


if __name__ == "__main__":
    unittest.main()
