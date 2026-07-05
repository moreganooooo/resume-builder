import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402


class TestShouldProceed(unittest.TestCase):

    def test_skip_confirm_returns_true_without_prompting(self):
        with patch("cli.click.confirm") as mock_confirm:
            result = cli._should_proceed(208, skip_confirm=True)
        self.assertTrue(result)
        mock_confirm.assert_not_called()

    @patch("cli.click.confirm")
    def test_confirm_declined_returns_false(self, mock_confirm):
        mock_confirm.return_value = False
        result = cli._should_proceed(208, skip_confirm=False)
        self.assertFalse(result)
        mock_confirm.assert_called_once()

    @patch("cli.click.confirm")
    def test_confirm_accepted_returns_true(self, mock_confirm):
        mock_confirm.return_value = True
        result = cli._should_proceed(5, skip_confirm=False)
        self.assertTrue(result)
