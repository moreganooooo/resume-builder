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


if __name__ == "__main__":
    unittest.main()
