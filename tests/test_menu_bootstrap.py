import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402


class TestBootstrapChoiceRegistered(unittest.TestCase):

    def test_bootstrap_is_first_choice(self):
        first = menu._CHOICES[0]
        self.assertEqual(first.value, "bootstrap")

    def test_bootstrap_handler_registered(self):
        self.assertIn("bootstrap", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["bootstrap"], menu._handle_bootstrap)


class TestHandleBootstrapEmptyFolder(unittest.TestCase):

    @patch("menu.questionary.confirm")
    @patch("menu.os.listdir", return_value=[])
    @patch("menu.os.makedirs")
    def test_returns_false_and_does_not_prompt_when_empty(self, mock_makedirs, mock_listdir, mock_confirm):
        result = menu._handle_bootstrap()
        self.assertFalse(result)
        mock_confirm.assert_not_called()


class TestHandleBootstrapWithFiles(unittest.TestCase):

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.questionary.confirm")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["resume.pdf", "linkedin.pdf"])
    @patch("menu.os.makedirs")
    def test_confirms_and_runs_subprocess_when_files_present(
        self, mock_makedirs, mock_listdir, mock_isfile, mock_confirm, mock_intro, mock_run,
    ):
        mock_confirm.return_value.ask.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = menu._handle_bootstrap()

        self.assertTrue(result)
        mock_intro.assert_called_once_with(2)
        mock_run.assert_called_once()

    @patch("menu.subprocess.run")
    @patch("menu.questionary.confirm")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["resume.pdf"])
    @patch("menu.os.makedirs")
    def test_declining_confirm_does_not_run_subprocess(
        self, mock_makedirs, mock_listdir, mock_isfile, mock_confirm, mock_run,
    ):
        mock_confirm.return_value.ask.return_value = False
        result = menu._handle_bootstrap()
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
