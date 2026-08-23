import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402


class TestBootstrapChoiceRegistered(unittest.TestCase):

    def test_bootstrap_is_first_choice(self):
        first = menu._build_choices()[0]
        self.assertEqual(first.value, "bootstrap")

    def test_bootstrap_handler_registered(self):
        self.assertIn("bootstrap", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["bootstrap"], menu._handle_bootstrap)


class TestHandleBootstrapDelegatesToSubmenu(unittest.TestCase):
    """_handle_bootstrap() skips straight to the resumable submenu
    (bootstrap_menu.py) for an already-existing, non-guest profile -- it
    does not re-run the onboarding wizard every time."""

    @patch("menu.subprocess.run")
    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=True)
    @patch("menu._profile_is_set_up", return_value=True)
    def test_delegates_to_bootstrap_menu_and_returns_its_result(
        self, mock_is_set_up, mock_run_menu, mock_subprocess
    ):
        os.environ.pop("RESUME_GUEST_MODE", None)
        result = menu._handle_bootstrap()
        mock_run_menu.assert_called_once()
        mock_subprocess.assert_not_called()
        self.assertTrue(result)

    @patch("menu.subprocess.run")
    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu._profile_is_set_up", return_value=True)
    def test_returns_false_when_submenu_reports_nothing_happened(
        self, mock_is_set_up, mock_run_menu, mock_subprocess
    ):
        os.environ.pop("RESUME_GUEST_MODE", None)
        result = menu._handle_bootstrap()
        self.assertFalse(result)
        mock_subprocess.assert_not_called()


class TestHandleBootstrapNewProfileTrigger(unittest.TestCase):
    """A real, shipped bug: RESUME_PROFILE unset used to resolve to a
    hardcoded default profile (which always exists), so without an explicit
    signal a genuine new user reaching _handle_bootstrap() via "Start new
    user setup now" would skip the name prompt entirely and have their
    documents routed into the EXISTING profile's knowledge_base/ instead of
    creating their own."""

    def setUp(self):
        import tempfile

        import profile_paths

        self._orig_profile = os.environ.get("RESUME_PROFILE")
        self._orig_guest = os.environ.get("RESUME_GUEST_MODE")
        os.environ.pop("RESUME_PROFILE", None)
        self.test_profile_name = "test_guest_trigger_profile_xyz"
        # Sandbox all four roots up front rather than sweeping them out of
        # the real checkout afterwards -- the tearDown cleanup below only
        # runs when the test gets that far.
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()

    def tearDown(self):
        import shutil

        import profile_paths

        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()
        for var, orig in (
            ("RESUME_PROFILE", self._orig_profile),
            ("RESUME_GUEST_MODE", self._orig_guest),
        ):
            if orig is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = orig
        # set_active_profile() reloads jd_manager against whatever
        # RESUME_PROFILE ends up restored to, so jd_manager isn't left
        # pointed at the now-deleted test profile for later tests.
        #
        # Restore ONLY what was actually there. This used to fall back to a
        # hardcoded profile name when nothing was set, which raises inside
        # set_active_profile() on any machine where that profile does not
        # exist -- and because the raise happens in tearDown, RESUME_PROFILE
        # is left pointing at the bogus name and every subsequent test in
        # the run fails too. It passed only where the developer always had
        # the variable exported; a second user saw 231 cascading errors.
        import importlib
        import sys

        import profile_paths as pp

        if self._orig_profile:
            pp.set_active_profile(self._orig_profile)
        else:
            os.environ.pop("RESUME_PROFILE", None)
            if "jd_manager" in sys.modules:
                importlib.reload(sys.modules["jd_manager"])

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu.subprocess.run")
    def test_guest_mode_triggers_wizard_even_though_morgan_profile_exists(
        self, mock_subprocess_run, mock_run_menu
    ):
        # Deliberately does NOT mock bootstrap_bullet_bank.create_new_profile
        # -- letting this run for real is a more honest test of the actual
        # bug (does a real profile directory get created, not just a mocked
        # call). run_bootstrap_menu() itself is mocked -- its own behavior
        # once a profile is active is covered by test_bootstrap_menu.py.
        os.environ["RESUME_GUEST_MODE"] = "1"
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"profile_name": self.test_profile_name}),
            stderr="",
        )

        menu._handle_bootstrap()

        mock_subprocess_run.assert_called_once()
        self.assertEqual(os.environ.get("RESUME_PROFILE"), self.test_profile_name)
        import profile_paths

        self.assertTrue(os.path.isdir(profile_paths.kb_dir(self.test_profile_name)))
        # All four sync roots, not just profiles/. Nothing verified this
        # before, which is the same gap that let the teardown leak three of
        # them: if create_new_profile() ever stopped seeding one, no test
        # would notice and that data would silently fall out of Syncthing.
        for label, path in profile_paths.sync_roots(self.test_profile_name):
            self.assertTrue(
                os.path.isdir(path), f"sync root {label!r} was not created: {path}"
            )

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu.bootstrap_bullet_bank.create_new_profile")
    @patch("menu.subprocess.run")
    @patch("menu._profile_is_set_up", return_value=True)
    def test_no_guest_mode_and_existing_profile_skips_the_wizard(
        self,
        mock_is_set_up,
        mock_subprocess_run,
        mock_create_profile,
        mock_run_menu,
    ):
        # RESUME_GUEST_MODE unset, profile already set up -> should NOT
        # shell out to the Go wizard (this is the normal, unchanged
        # normal daily-use path, and the exact regression this test guards).
        os.environ.pop("RESUME_GUEST_MODE", None)

        menu._handle_bootstrap()

        mock_subprocess_run.assert_not_called()
        mock_create_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
