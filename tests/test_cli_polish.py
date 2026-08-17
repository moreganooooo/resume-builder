import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
from click.testing import CliRunner  # noqa: E402


class TestPolishCommand(unittest.TestCase):

    def test_no_file_launches_picker_path(self):
        with patch("cli.polish_module.run") as mock_run:
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["polish"])
        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once_with(None)

    def test_file_argument_is_forwarded(self):
        with patch("cli.polish_module.run") as mock_run:
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["polish", "README.md"])
        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once_with("README.md")

    def test_nonexistent_file_argument_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["polish", "definitely/does/not/exist.json"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
