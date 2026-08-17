import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bullet_bank_menu  # noqa: E402
import menu  # noqa: E402


class TestUpdateKnowledgeChoiceRegistered(unittest.TestCase):

    def test_choice_is_registered(self):
        # Moved into the Bullet Bank submenu (bullet_bank_menu.py) as part
        # of the 2026-08 menu collapse -- no longer a flat main-menu entry.
        values = [c.value for c in bullet_bank_menu._build_choices()]
        self.assertIn("update_knowledge", values)

    def test_handler_registered(self):
        self.assertIn("update_knowledge", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["update_knowledge"], menu._handle_update_knowledge)


class TestHandleUpdateKnowledgeNotYetSetUp(unittest.TestCase):

    @patch("menu.cli_art.console.print")
    @patch("menu.os.path.isdir", return_value=False)
    def test_returns_false_without_prompting_when_profile_has_no_kb(self, mock_isdir, mock_print):
        with patch("menu.questionary.checkbox") as mock_checkbox:
            result = menu._handle_update_knowledge()
        self.assertFalse(result)
        mock_checkbox.assert_not_called()
        printed = mock_print.call_args[0][0]
        self.assertIn("New User? Start Here!", printed)

    @patch("menu._print_source_docs_instructions")
    @patch("menu.os.listdir", return_value=[])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=False)
    @patch("menu.os.path.isdir", return_value=True)
    def test_configured_profile_without_a_bootstrap_checkpoint_is_not_locked_out(
        self, mock_isdir, mock_exists, mock_makedirs, mock_listdir, mock_instructions,
    ):
        """B7: this gated on bootstrap/checkpoint.json -- evidence of *how* a
        profile was created -- so Morgan's own 628-bullet, 1,144-JD profile was
        told it hadn't been set up. os.path.exists is forced False here to stand
        in for the absent checkpoint; the handler must get past the gate anyway
        and reach the source-documents step."""
        with patch("menu.questionary.checkbox") as mock_checkbox:
            result = menu._handle_update_knowledge()
        self.assertFalse(result)          # no new files to ingest
        mock_instructions.assert_called_once()  # but it got past the setup gate
        mock_checkbox.assert_not_called()


class TestProfileIsSetUp(unittest.TestCase):

    @patch("menu.os.path.isdir", return_value=True)
    def test_true_when_profile_dir_and_kb_both_exist(self, mock_isdir):
        self.assertTrue(menu._profile_is_set_up("morgan"))

    @patch("menu.os.path.isdir", return_value=False)
    def test_false_when_neither_exists(self, mock_isdir):
        self.assertFalse(menu._profile_is_set_up("nobody"))

    def test_false_on_an_invalid_profile_name(self):
        with patch("menu.os.path.isdir", side_effect=ValueError("bad profile")):
            self.assertFalse(menu._profile_is_set_up("../escape"))


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
    @patch("menu.charm_prompt.confirm")
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
        mock_confirm.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = menu._handle_update_knowledge()

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertIn("--scope", args)
        self.assertEqual(args[args.index("--scope") + 1], "both")

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.charm_prompt.confirm")
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
        mock_confirm.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        menu._handle_update_knowledge()

        args = mock_run.call_args[0][0]
        self.assertEqual(args[args.index("--scope") + 1], "bullets")

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.charm_prompt.confirm")
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
        mock_confirm.return_value = True
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
    @patch("menu.charm_prompt.confirm")
    @patch("menu.questionary.checkbox")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["new_cert.pdf"])
    @patch("menu.os.makedirs")
    @patch("menu.os.path.exists", return_value=True)
    def test_declining_final_confirm_returns_false_without_running(
        self, mock_exists, mock_makedirs, mock_listdir, mock_isfile, mock_checkbox, mock_confirm, mock_run,
    ):
        mock_checkbox.return_value.ask.return_value = ["bullets", "profile"]
        mock_confirm.return_value = False
        result = menu._handle_update_knowledge()
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
