"""The Click CLI's help and errors use the design system's CLI palette."""

import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
import cli_help  # noqa: E402
from click.testing import CliRunner  # noqa: E402


def _sgr(rgb):
    return "38;2;%d;%d;%d" % rgb


class TestStyledHelp(unittest.TestCase):
    def _help(self, *args, env=None):
        runner = CliRunner(env=env or {"NO_COLOR": None})
        return runner.invoke(cli.cli, [*args, "--help"], color=True)

    def test_palette_matches_the_go_cli(self):
        out = self._help().output
        for rgb in (cli_help.PROGRAM, cli_help.HEADING, cli_help.FLAG):
            self.assertIn(_sgr(rgb), out)

    def test_subcommands_and_subgroups_are_styled(self):
        self.assertIn(_sgr(cli_help.HEADING), self._help("doctor").output)
        self.assertIn(_sgr(cli_help.HEADING), self._help("location").output)

    def test_columns_align_once_color_is_stripped(self):
        plain = CliRunner().invoke(cli.cli, ["--help"]).output
        self.assertIn("  --profile TEXT  Override RESUME_PROFILE", plain)

    def test_no_color_disables_styling(self):
        out = self._help(env={"NO_COLOR": "1"}).output
        self.assertNotIn("\x1b[", out)


class TestStyledErrors(unittest.TestCase):
    def test_usage_error_keeps_exit_code_and_names_a_fix(self):
        result = CliRunner().invoke(cli.cli, ["--bogus"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("✗ Error No such option '--bogus'", result.output)
        self.assertIn("--help' for the available options.", result.output)

    def test_subcommand_error_is_styled_too(self):
        result = CliRunner().invoke(cli.cli, ["doctor", "--bogus"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("✗ Error", result.output)

    def test_a_failing_command_still_exits_nonzero(self):
        with patch("cli.cli_art.display_help", side_effect=SystemExit(3)):
            result = CliRunner().invoke(cli.cli, ["help"])
        self.assertEqual(result.exit_code, 3)


if __name__ == "__main__":
    unittest.main()
