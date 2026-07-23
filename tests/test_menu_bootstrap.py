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


class TestHandleBootstrapDelegatesToSubmenu(unittest.TestCase):
    """_handle_bootstrap() no longer runs the whole onboarding flow as one
    opaque subprocess -- for an already-existing, non-guest profile, its
    entire remaining job is the resumable submenu (bootstrap_menu.py)."""

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=True)
    def test_delegates_to_bootstrap_menu_and_returns_its_result(self, mock_run_menu):
        result = menu._handle_bootstrap()
        mock_run_menu.assert_called_once()
        self.assertTrue(result)

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    def test_returns_false_when_submenu_reports_nothing_happened(self, mock_run_menu):
        result = menu._handle_bootstrap()
        self.assertFalse(result)


class TestHandleBootstrapNewProfileTrigger(unittest.TestCase):
    """A real, shipped bug: RESUME_PROFILE unset resolves to "morgan" (whose
    profile always exists), so without an explicit signal, a genuine new
    user reaching _handle_bootstrap() via "Start new user setup now" would
    skip the name prompt entirely and have their documents routed into
    Morgan's own knowledge_base/ instead of creating their own profile."""

    def setUp(self):
        self._orig_profile = os.environ.get("RESUME_PROFILE")
        self._orig_guest = os.environ.get("RESUME_GUEST_MODE")
        os.environ.pop("RESUME_PROFILE", None)
        self.test_profile_name = "test_guest_trigger_profile_xyz"

    def tearDown(self):
        import shutil
        import profile_paths
        shutil.rmtree(os.path.join(profile_paths.PROFILES_DIR, self.test_profile_name), ignore_errors=True)
        for var, orig in (("RESUME_PROFILE", self._orig_profile), ("RESUME_GUEST_MODE", self._orig_guest)):
            if orig is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = orig
        # set_active_profile() reloads jd_manager against whatever
        # RESUME_PROFILE ends up restored to, so jd_manager isn't left
        # pointed at the now-deleted test profile for later tests.
        import profile_paths as pp
        pp.set_active_profile(self._orig_profile or "morgan")

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu.questionary.text")
    def test_guest_mode_triggers_name_prompt_even_though_morgan_profile_exists(self, mock_text, mock_run_menu):
        # Deliberately does NOT mock os.makedirs -- patching it via
        # "menu.os.makedirs" mutates the single shared os module object,
        # which would also silently disable create_new_profile()'s own
        # directory creation in bootstrap_bullet_bank.py. Letting this run
        # for real is also a more honest test of the actual bug (does a
        # real profile directory get created, not just a mocked call).
        # run_bootstrap_menu() itself is mocked -- its own behavior once a
        # profile is active is covered by test_bootstrap_menu.py.
        os.environ["RESUME_GUEST_MODE"] = "1"
        mock_text.return_value.ask.return_value = self.test_profile_name

        menu._handle_bootstrap()

        mock_text.assert_called_once()
        self.assertEqual(os.environ.get("RESUME_PROFILE"), self.test_profile_name)
        import profile_paths
        self.assertTrue(os.path.isdir(profile_paths.kb_dir(self.test_profile_name)))

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu.bootstrap_bullet_bank.create_new_profile")
    @patch("menu.questionary.text")
    def test_no_guest_mode_and_existing_profile_skips_name_prompt(
        self, mock_text, mock_create_profile, mock_run_menu,
    ):
        # RESUME_GUEST_MODE unset, RESUME_PROFILE unset -> resolves to
        # morgan's real, already-set-up profile -> should NOT prompt for
        # a name (this is the normal, unchanged Morgan-daily-use path).
        menu._handle_bootstrap()

        mock_text.assert_not_called()
        mock_create_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
