import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from click.testing import CliRunner  # noqa: E402
import cli  # noqa: E402


class TestHelpCommand(unittest.TestCase):

    def test_delegates_to_cli_art_display_help(self):
        runner = CliRunner()
        with patch("cli.cli_art.display_help") as mock_display:
            result = runner.invoke(cli.cli, ["help"])
        self.assertEqual(result.exit_code, 0)
        mock_display.assert_called_once()


class TestVersionAndVerboseFlags(unittest.TestCase):

    def test_version_flag_appears_in_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["--help"])
        self.assertIn("--version", result.output)

    def test_verbose_flag_appears_in_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["--help"])
        self.assertIn("--verbose", result.output)

    def test_version_flag_prints_a_version_and_exits_cleanly(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("resume-builder", result.output)

    def test_verbose_flag_enables_debug_logging(self):
        import logging
        with patch("logging.basicConfig") as mock_basic_config, \
             patch("cli.menu.run_interactive_menu"):
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["--verbose"])
        self.assertEqual(result.exit_code, 0)
        mock_basic_config.assert_called_once_with(level=logging.DEBUG)


if __name__ == "__main__":
    unittest.main()
