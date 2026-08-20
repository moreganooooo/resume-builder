import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
import menu  # noqa: E402
import profile_paths  # noqa: E402
from click.testing import CliRunner  # noqa: E402


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
            runner.invoke(
                cli.cli, ["--profile", "morgan", "tailor", "jds/dummy_jd.txt"]
            )
        self.assertEqual(os.environ.get("RESUME_PROFILE"), "morgan")

    def test_no_profile_flag_leaves_env_var_untouched(self):
        os.environ.pop("RESUME_PROFILE", None)
        runner = CliRunner()
        with patch("cli.tailor.callback"):
            runner.invoke(cli.cli, ["tailor", "jds/dummy_jd.txt"])
        self.assertIsNone(os.environ.get("RESUME_PROFILE"))


class TestMenuProfileGate(unittest.TestCase):
    # Isolated from the real profiles/ directory via a temp dir patched
    # onto profile_paths.PROFILES_DIR -- these tests used to list()
    # whatever profiles actually exist on the machine running them and
    # assert against a hardcoded "morgan", which broke the moment the
    # real profile folder was renamed to different casing ("Morgan").
    # A fixture directory means these tests can never again depend on
    # what any real profile is named, on this machine or any other.

    def setUp(self):
        self._orig_profile = os.environ.get("RESUME_PROFILE")
        self._orig_guest = os.environ.get("RESUME_GUEST_MODE")
        os.environ.pop("RESUME_PROFILE", None)
        os.environ.pop("RESUME_GUEST_MODE", None)

        self._tmp_profiles_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self._tmp_profiles_dir, "testuser"))
        os.makedirs(os.path.join(self._tmp_profiles_dir, "test_profile"))
        self._profiles_dir_patcher = patch.object(
            profile_paths, "PROFILES_DIR", self._tmp_profiles_dir
        )
        self._profiles_dir_patcher.start()

    def tearDown(self):
        self._profiles_dir_patcher.stop()
        shutil.rmtree(self._tmp_profiles_dir, ignore_errors=True)
        for var, orig in (
            ("RESUME_PROFILE", self._orig_profile),
            ("RESUME_GUEST_MODE", self._orig_guest),
        ):
            if orig is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = orig

    def test_ctrl_c_on_profile_prompt_returns_false_without_new_user_flow(self):
        # Regression: .ask() returns None on Ctrl-C/Esc; this used to fall
        # through uncaught into the "I'm new here" branch below.
        with (
            patch("questionary.select") as mock_select,
            patch("menu._handle_bootstrap") as mock_bootstrap,
        ):
            mock_select.return_value.ask.return_value = None
            result = menu._confirm_active_profile()
        self.assertFalse(result)
        mock_bootstrap.assert_not_called()
        self.assertIsNone(os.environ.get("RESUME_GUEST_MODE"))
        self.assertIsNone(os.environ.get("RESUME_PROFILE"))

    def test_ctrl_c_on_new_user_prompt_returns_false_without_guest_mode(self):
        # Regression: cancelling the second prompt used to fall through
        # uncaught into "Look around the main menu first" (guest mode).
        with (
            patch("questionary.select") as mock_select,
            patch("menu._handle_bootstrap") as mock_bootstrap,
        ):
            mock_select.return_value.ask.side_effect = ["I'm new here", None]
            result = menu._confirm_active_profile()
        self.assertFalse(result)
        mock_bootstrap.assert_not_called()
        self.assertIsNone(os.environ.get("RESUME_GUEST_MODE"))

    def test_gate_always_shown_even_with_a_single_profile(self):
        with patch("questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = "testuser"
            menu._confirm_active_profile()
        mock_select.assert_called_once()

    def test_choosing_existing_profile_sets_it_for_session(self):
        with patch("questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = "testuser"
            menu._confirm_active_profile()
        self.assertEqual(os.environ.get("RESUME_PROFILE"), "testuser")
        self.assertIsNone(os.environ.get("RESUME_GUEST_MODE"))

    def test_default_selection_matches_active_profile_regardless_of_case(self):
        # Regression: profile_paths.active_profile() falls back to a
        # hardcoded "morgan" (lowercase) when RESUME_PROFILE is unset. A
        # real profile folder renamed to different casing used to make
        # `current in names` fail, silently falling back to names[0]
        # (alphabetically-first, not necessarily the active profile) as
        # the picker's highlighted default instead of the real one.
        # active_profile() itself is mocked here (rather than set via
        # RESUME_PROFILE) so this stays deterministic across filesystems
        # -- macOS resolves profiles/TESTUSER against a real testuser/
        # dir case-insensitively, but a case-sensitive filesystem (e.g.
        # CI on Linux) would raise inside active_profile() itself before
        # this fix is even reached.
        with (
            patch("profile_paths.active_profile", return_value="TESTUSER"),
            patch("questionary.select") as mock_select,
        ):
            mock_select.return_value.ask.return_value = "testuser"
            menu._confirm_active_profile()
        self.assertEqual(mock_select.call_args.kwargs["default"], "testuser")
        self.assertIn("currently: testuser", mock_select.call_args.args[0])

    def test_im_new_here_then_start_setup_calls_bootstrap(self):
        with (
            patch("questionary.select") as mock_select,
            patch("menu._handle_bootstrap") as mock_bootstrap,
        ):
            mock_select.return_value.ask.side_effect = [
                "I'm new here",
                "Start new user setup now",
            ]
            menu._confirm_active_profile()
        mock_bootstrap.assert_called_once()

    def test_im_new_here_then_start_setup_marks_guest_mode_before_bootstrap_runs(self):
        # RESUME_PROFILE is unset at this point, so without an explicit
        # signal, _handle_bootstrap()'s own active_profile() call resolves
        # to "morgan" -- whose profile always exists -- and would skip the
        # new-profile prompt entirely, routing a real new user's documents
        # into her knowledge_base/ instead of creating their own. This was
        # a real, shipped bug: _confirm_active_profile() called
        # _handle_bootstrap() with neither RESUME_PROFILE nor
        # RESUME_GUEST_MODE set.
        seen_guest_mode = []

        def _record_and_return(*args, **kwargs):
            seen_guest_mode.append(os.environ.get("RESUME_GUEST_MODE"))
            return True

        with (
            patch("questionary.select") as mock_select,
            patch("menu._handle_bootstrap", side_effect=_record_and_return),
        ):
            mock_select.return_value.ask.side_effect = [
                "I'm new here",
                "Start new user setup now",
            ]
            menu._confirm_active_profile()
        self.assertEqual(seen_guest_mode, ["1"])

    def test_im_new_here_then_start_setup_clears_guest_mode_after_real_profile_created(
        self,
    ):
        with (
            patch("questionary.select") as mock_select,
            patch("menu._handle_bootstrap") as mock_bootstrap,
        ):

            def _create_profile(*args, **kwargs):
                os.environ["RESUME_PROFILE"] = "dominick"

            mock_bootstrap.side_effect = _create_profile
            mock_select.return_value.ask.side_effect = [
                "I'm new here",
                "Start new user setup now",
            ]
            menu._confirm_active_profile()
        self.assertEqual(os.environ.get("RESUME_PROFILE"), "dominick")
        self.assertIsNone(os.environ.get("RESUME_GUEST_MODE"))

    def test_im_new_here_then_look_around_sets_guest_mode(self):
        with (
            patch("questionary.select") as mock_select,
            patch("menu._handle_bootstrap") as mock_bootstrap,
        ):
            mock_select.return_value.ask.side_effect = [
                "I'm new here",
                "Look around the main menu first",
            ]
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
        with (
            patch("menu.questionary.select") as mock_select,
            patch("menu._run_with_chain") as mock_run,
            patch("menu._confirm_active_profile"),
        ):
            mock_select.return_value.ask.side_effect = ["evaluate_all", "exit"]
            menu.run_interactive_menu()
        mock_run.assert_not_called()

    def test_bootstrap_choice_is_allowed_in_guest_mode(self):
        with (
            patch("menu.questionary.select") as mock_select,
            patch("menu._run_with_chain") as mock_run,
            patch("menu._confirm_active_profile"),
        ):
            mock_select.return_value.ask.side_effect = ["bootstrap", "exit"]
            menu.run_interactive_menu()
        mock_run.assert_called_once_with("bootstrap", unittest.mock.ANY)


class TestRunInteractiveMenuExitsOnProfileGateCancel(unittest.TestCase):

    def test_ctrl_c_at_profile_gate_exits_before_the_main_menu_loop(self):
        with (
            patch("menu._confirm_active_profile", return_value=False),
            patch("menu._confirm_icon_set") as mock_icon_set,
            patch("menu.questionary.select") as mock_select,
            patch("menu.cli_art.display_exit_footer") as mock_footer,
        ):
            menu.run_interactive_menu()
        mock_footer.assert_called_once()
        mock_icon_set.assert_not_called()
        mock_select.assert_not_called()


if __name__ == "__main__":
    unittest.main()
