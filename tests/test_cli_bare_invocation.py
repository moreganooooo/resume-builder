import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
from click.testing import CliRunner  # noqa: E402


class TestBareInvocation(unittest.TestCase):

    def test_no_subcommand_launches_the_menu(self):
        with patch("cli.menu.run_interactive_menu") as mock_menu:
            runner = CliRunner()
            result = runner.invoke(cli.cli, [])
        self.assertEqual(result.exit_code, 0)
        mock_menu.assert_called_once()

    def test_a_real_subcommand_does_not_launch_the_menu(self):
        with (
            patch("cli.menu.run_interactive_menu") as mock_menu,
            patch("cli.scan_module.run_scan") as mock_scan,
        ):
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["scan"])
        self.assertEqual(result.exit_code, 0)
        mock_menu.assert_not_called()
        mock_scan.assert_called_once()
