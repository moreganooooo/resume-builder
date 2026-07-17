import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from click.testing import CliRunner  # noqa: E402

import cli  # noqa: E402
import menu  # noqa: E402
import profile_paths  # noqa: E402


class TestCliProfileFlag(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_profile_flag_sets_env_var_before_subcommand_runs(self):
        runner = CliRunner()
        with patch("cli.tailor.callback"):
            runner.invoke(cli.cli, ["--profile", "morgan", "tailor", "jds/dummy_jd.txt"])
        self.assertEqual(os.environ.get("RESUME_PROFILE"), "morgan")

    def test_no_profile_flag_leaves_env_var_untouched(self):
        os.environ.pop("RESUME_PROFILE", None)
        runner = CliRunner()
        with patch("cli.tailor.callback"):
            runner.invoke(cli.cli, ["tailor", "jds/dummy_jd.txt"])
        self.assertIsNone(os.environ.get("RESUME_PROFILE"))


class TestMenuProfileGate(unittest.TestCase):

    def setUp(self):
        self._orig_profile = os.environ.get("RESUME_PROFILE")
        self._orig_guest = os.environ.get("RESUME_GUEST_MODE")
        os.environ.pop("RESUME_PROFILE", None)
        os.environ.pop("RESUME_GUEST_MODE", None)

    def tearDown(self):
        for var, orig in (("RESUME_PROFILE", self._orig_profile), ("RESUME_GUEST_MODE", self._orig_guest)):
            if orig is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = orig

    def test_gate_always_shown_even_with_a_single_profile(self):
        with patch("questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = "morgan"
            menu._confirm_active_profile()
        mock_select.assert_called_once()

    def test_choosing_existing_profile_sets_it_for_session(self):
        with patch("questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = "morgan"
            menu._confirm_active_profile()
        self.assertEqual(os.environ.get("RESUME_PROFILE"), "morgan")
        self.assertIsNone(os.environ.get("RESUME_GUEST_MODE"))

    def test_im_new_here_then_start_setup_calls_bootstrap(self):
        with patch("questionary.select") as mock_select, \
             patch("menu._handle_bootstrap") as mock_bootstrap:
            mock_select.return_value.ask.side_effect = ["I'm new here", "Start new user setup now"]
            menu._confirm_active_profile()
        mock_bootstrap.assert_called_once()

    def test_im_new_here_then_look_around_sets_guest_mode(self):
        with patch("questionary.select") as mock_select, \
             patch("menu._handle_bootstrap") as mock_bootstrap:
            mock_select.return_value.ask.side_effect = ["I'm new here", "Look around the main menu first"]
            menu._confirm_active_profile()
        mock_bootstrap.assert_not_called()
        self.assertEqual(os.environ.get("RESUME_GUEST_MODE"), "1")
        self.assertIsNone(os.environ.get("RESUME_PROFILE"))


class TestGuestModeBlocksRealActions(unittest.TestCase):

    def setUp(self):
        self._orig_guest = os.environ.get("RESUME_GUEST_MODE")
        os.environ["RESUME_GUEST_MODE"] = "1"

    def tearDown(self):
        if self._orig_guest is None:
            os.environ.pop("RESUME_GUEST_MODE", None)
        else:
            os.environ["RESUME_GUEST_MODE"] = self._orig_guest

    def test_non_bootstrap_choice_is_blocked_in_guest_mode(self):
        with patch("menu.questionary.select") as mock_select, \
             patch("menu._run_with_chain") as mock_run, \
             patch("menu._confirm_active_profile"):
            mock_select.return_value.ask.side_effect = ["evaluate_all", "exit"]
            menu.run_interactive_menu()
        mock_run.assert_not_called()

    def test_bootstrap_choice_is_allowed_in_guest_mode(self):
        with patch("menu.questionary.select") as mock_select, \
             patch("menu._run_with_chain") as mock_run, \
             patch("menu._confirm_active_profile"):
            mock_select.return_value.ask.side_effect = ["bootstrap", "exit"]
            menu.run_interactive_menu()
        mock_run.assert_called_once_with("bootstrap", unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
