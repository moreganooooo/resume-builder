import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402


class TestUpdateKnowledgeChoiceRegistered(unittest.TestCase):

    def test_choice_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("update_knowledge", values)

    def test_handler_registered(self):
        self.assertIn("update_knowledge", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["update_knowledge"], menu._handle_update_knowledge)


class TestHandleUpdateKnowledgeNotYetSetUp(unittest.TestCase):

    @patch("menu.cli_art.console.print")
    @patch("menu.os.path.exists", return_value=False)
    def test_returns_false_without_prompting_when_no_checkpoint(self, mock_exists, mock_print):
        with patch("menu.questionary.checkbox") as mock_checkbox:
            result = menu._handle_update_knowledge()
        self.assertFalse(result)
        mock_checkbox.assert_not_called()
        printed = mock_print.call_args[0][0]
        self.assertIn("New User? Start Here!", printed)


class TestHandleUpdateKnowledgeEmptyFolder(unittest.TestCase):

    @patch("menu._print_source_docs_instructions")
    @patch("menu.os.listdir", return_value=[])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_returns_false_and_shows_instructions_when_no_new_files(
        self, mock_exists, mock_makedirs, mock_listdir, mock_instructions,
    ):
        with patch("menu.questionary.checkbox") as mock_checkbox:
            result = menu._handle_update_knowledge()
        self.assertFalse(result)
        mock_instructions.assert_called_once()
        mock_checkbox.assert_not_called()


class TestHandleUpdateKnowledgeWithFiles(unittest.TestCase):

    def _patches(self, checked_values):
        mock_checkbox_q = MagicMock()
        mock_checkbox_q.ask.return_value = checked_values
        mock_confirm_q = MagicMock()
        mock_confirm_q.ask.return_value = True
        return mock_checkbox_q, mock_confirm_q

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.questionary.confirm")
    @patch("menu.questionary.checkbox")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["new_cert.pdf"])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_both_selected_runs_scope_both(
        self, mock_exists, mock_makedirs, mock_listdir, mock_isfile,
        mock_checkbox, mock_confirm, mock_intro, mock_run,
    ):
        mock_checkbox.return_value.ask.return_value = ["bullets", "profile"]
        mock_confirm.return_value.ask.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = menu._handle_update_knowledge()

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertIn("--scope", args)
        self.assertEqual(args[args.index("--scope") + 1], "both")

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.questionary.confirm")
    @patch("menu.questionary.checkbox")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["new_cert.pdf"])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_only_bullets_selected_runs_scope_bullets(
        self, mock_exists, mock_makedirs, mock_listdir, mock_isfile,
        mock_checkbox, mock_confirm, mock_intro, mock_run,
    ):
        mock_checkbox.return_value.ask.return_value = ["bullets"]
        mock_confirm.return_value.ask.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        menu._handle_update_knowledge()

        args = mock_run.call_args[0][0]
        self.assertEqual(args[args.index("--scope") + 1], "bullets")

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.questionary.confirm")
    @patch("menu.questionary.checkbox")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["new_cert.pdf"])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_only_profile_selected_runs_scope_profile(
        self, mock_exists, mock_makedirs, mock_listdir, mock_isfile,
        mock_checkbox, mock_confirm, mock_intro, mock_run,
    ):
        mock_checkbox.return_value.ask.return_value = ["profile"]
        mock_confirm.return_value.ask.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        menu._handle_update_knowledge()

        args = mock_run.call_args[0][0]
        self.assertEqual(args[args.index("--scope") + 1], "profile")

    @patch("menu.subprocess.run")
    @patch("menu.questionary.checkbox")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["new_cert.pdf"])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_nothing_checked_returns_false_without_running(
        self, mock_exists, mock_makedirs, mock_listdir, mock_isfile, mock_checkbox, mock_run,
    ):
        mock_checkbox.return_value.ask.return_value = []
        result = menu._handle_update_knowledge()
        self.assertFalse(result)
        mock_run.assert_not_called()

    @patch("menu.subprocess.run")
    @patch("menu.questionary.confirm")
    @patch("menu.questionary.checkbox")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["new_cert.pdf"])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_declining_final_confirm_returns_false_without_running(
        self, mock_exists, mock_makedirs, mock_listdir, mock_isfile, mock_checkbox, mock_confirm, mock_run,
    ):
        mock_checkbox.return_value.ask.return_value = ["bullets", "profile"]
        mock_confirm.return_value.ask.return_value = False
        result = menu._handle_update_knowledge()
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
