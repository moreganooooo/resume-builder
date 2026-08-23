import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import profile_paths  # noqa: E402


class TestActiveProfile(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_defaults_to_the_only_profile_when_unset(self):
        """With one profile on disk, that is unambiguously the answer --
        whatever it is named. This used to assert a hardcoded "morgan",
        which was only correct on one person's machine and silently handed
        everyone else a path to a profile that does not exist."""
        os.environ.pop("RESUME_PROFILE", None)
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "dominick"))
            with patch.object(profile_paths, "PROFILES_DIR", tmp):
                self.assertEqual(profile_paths.active_profile(), "dominick")

    def test_defaults_to_legacy_name_when_no_profiles_exist(self):
        os.environ.pop("RESUME_PROFILE", None)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(profile_paths, "PROFILES_DIR", tmp):
                self.assertEqual(
                    profile_paths.active_profile(),
                    profile_paths._LEGACY_DEFAULT_PROFILE,
                )

    def test_several_profiles_resolve_deterministically(self):
        os.environ.pop("RESUME_PROFILE", None)
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("zoe", "alice", "bob"):
                os.makedirs(os.path.join(tmp, n))
            with patch.object(profile_paths, "PROFILES_DIR", tmp):
                # No legacy default present -> first alphabetically, so the
                # answer never depends on directory iteration order.
                self.assertEqual(profile_paths.active_profile(), "alice")

    def test_returns_explicit_profile_when_directory_exists(self):
        # Isolated against a temp PROFILES_DIR rather than the checkout's
        # own profiles/: active_profile() now returns the DIRECTORY's
        # spelling, and the real directory's casing differs by machine
        # (macOS resolves profiles/Morgan and profiles/morgan to the
        # same file, git tracks one spelling, a Linux CI box gets the other).
        # Asserting against the live checkout made this test's result
        # depend on which machine ran it.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "morgan"))
            with patch.object(profile_paths, "PROFILES_DIR", tmp):
                os.environ["RESUME_PROFILE"] = "morgan"
                self.assertEqual(profile_paths.active_profile(), "morgan")

    def test_falls_back_to_case_insensitive_match_when_name_does_not_resolve(self):
        """A name that does not resolve as spelled is matched against the
        real on-disk listing before failing. macOS resolves profiles/Morgan
        and profiles/morgan to the same directory, so a profile created on
        a Mac can carry a casing that fails outright on a Linux Syncthing
        peer whose checkout has the other spelling.

        os.path.isdir is forced False here because on a case-insensitive
        filesystem the direct check would succeed and this fallback would
        never be exercised -- the test would then silently pass on macOS
        while testing nothing.
        """
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "morgan"))
            # available_profiles() also calls isdir -- on PROFILES_DIR
            # itself and on each entry -- so the stub must keep those
            # truthful while making the mis-cased lookup miss.
            with (
                patch.object(profile_paths, "PROFILES_DIR", tmp),
                patch(
                    "os.path.isdir",
                    side_effect=lambda p: p == tmp or p.endswith("morgan"),
                ),
            ):
                os.environ["RESUME_PROFILE"] = "MORGAN"
                self.assertEqual(profile_paths.active_profile(), "morgan")

    def test_raises_on_unknown_profile(self):
        os.environ["RESUME_PROFILE"] = "nonexistent_profile_xyz"
        with self.assertRaises(ValueError):
            profile_paths.active_profile()


class TestPathHelpers(unittest.TestCase):

    def test_kb_dir_resolves_under_profile_root(self):
        expected = os.path.join(profile_paths.PROFILES_DIR, "morgan", "knowledge_base")
        self.assertEqual(profile_paths.kb_dir("morgan"), expected)

    def test_jds_dir_resolves_under_top_level_jds(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "jds", "morgan")
        self.assertEqual(profile_paths.jds_dir("morgan"), expected)

    def test_output_dir_resolves_under_top_level_output(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "output", "morgan")
        self.assertEqual(profile_paths.output_dir("morgan"), expected)

    def test_checkpoints_dir_nests_under_output_dir(self):
        expected = os.path.join(
            profile_paths.PROJECT_ROOT, "output", "morgan", "checkpoints"
        )
        self.assertEqual(profile_paths.checkpoints_dir("morgan"), expected)

    def test_applications_md_path_resolves_under_top_level_data(self):
        expected = os.path.join(
            profile_paths.PROJECT_ROOT, "data", "morgan", "applications.md"
        )
        self.assertEqual(profile_paths.applications_md_path("morgan"), expected)

    def test_tracker_csv_path_lives_inside_jds_dir(self):
        expected = os.path.join(
            profile_paths.PROJECT_ROOT, "jds", "morgan", "jd_tracker_log.csv"
        )
        self.assertEqual(profile_paths.tracker_csv_path("morgan"), expected)

    def test_situational_roles_path_resolves_under_profile_root(self):
        expected = os.path.join(
            profile_paths.PROFILES_DIR, "morgan", "situational_roles.yaml"
        )
        self.assertEqual(profile_paths.situational_roles_path("morgan"), expected)

    def test_data_dir_resolves_under_top_level_data(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "data", "morgan")
        self.assertEqual(profile_paths.data_dir("morgan"), expected)

    def test_applications_md_path_nests_under_data_dir(self):
        expected = os.path.join(profile_paths.data_dir("morgan"), "applications.md")
        self.assertEqual(profile_paths.applications_md_path("morgan"), expected)

    def test_board_scanner_dir_resolves_under_profile_root(self):
        expected = os.path.join(profile_paths.PROFILES_DIR, "morgan", "board_scanner")
        self.assertEqual(profile_paths.board_scanner_dir("morgan"), expected)

    def test_kb_snapshot_dir_nests_under_data_dir(self):
        expected = os.path.join(profile_paths.data_dir("morgan"), "kb_snapshots")
        self.assertEqual(profile_paths.kb_snapshot_dir("morgan"), expected)

    def test_company_locations_cache_path_resolves_under_profile_root(self):
        expected = os.path.join(
            profile_paths.PROFILES_DIR, "morgan", "company_locations.json"
        )
        self.assertEqual(profile_paths.company_locations_cache_path("morgan"), expected)


class TestSyncRoots(unittest.TestCase):

    def setUp(self):
        # write_sync_ignore_files() makedirs all four sync roots, so this
        # class used to create profiles/, jds/, output/ and data/ entries
        # in the real checkout and rely on tearDown to remove them -- which
        # leaves them behind whenever a test errors before tearDown runs.
        # isolate_for_tests() redirects all four at once instead.
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.profile = "test_sync_roots_xyz"
        self.dirs = [
            profile_paths.profile_root(self.profile),
            profile_paths.jds_dir(self.profile),
            profile_paths.output_dir(self.profile),
            profile_paths.data_dir(self.profile),
        ]

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_sync_roots_names_the_four_operational_directories(self):
        roots = dict(profile_paths.sync_roots(self.profile))
        self.assertEqual(roots["profile"], profile_paths.profile_root(self.profile))
        self.assertEqual(roots["jds"], profile_paths.jds_dir(self.profile))
        self.assertEqual(roots["output"], profile_paths.output_dir(self.profile))
        self.assertEqual(roots["data"], profile_paths.data_dir(self.profile))

    def test_write_sync_ignore_files_creates_every_directory_and_stignore(self):
        profile_paths.write_sync_ignore_files(self.profile)
        for d in self.dirs:
            self.assertTrue(os.path.isdir(d))
            stignore = os.path.join(d, ".stignore")
            self.assertTrue(os.path.isfile(stignore))
            with open(stignore) as f:
                self.assertIn("__pycache__", f.read())

    def test_write_sync_ignore_files_does_not_clobber_a_hand_edited_stignore(self):
        os.makedirs(profile_paths.profile_root(self.profile), exist_ok=True)
        custom_path = os.path.join(
            profile_paths.profile_root(self.profile), ".stignore"
        )
        with open(custom_path, "w") as f:
            f.write("my-custom-rule\n")

        profile_paths.write_sync_ignore_files(self.profile)

        with open(custom_path) as f:
            self.assertEqual(f.read(), "my-custom-rule\n")


class TestSignaturePath(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_signature_profile")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._patcher = patch("profile_paths.profile_root", return_value=self.tmp_dir)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_returns_none_when_no_signature_file(self):
        self.assertIsNone(profile_paths.signature_path())

    def test_finds_png(self):
        path = os.path.join(self.tmp_dir, "signature.png")
        open(path, "w").close()
        self.assertEqual(profile_paths.signature_path(), path)

    def test_finds_jpg_when_no_png(self):
        path = os.path.join(self.tmp_dir, "signature.jpg")
        open(path, "w").close()
        self.assertEqual(profile_paths.signature_path(), path)

    def test_png_takes_priority_over_jpg(self):
        png_path = os.path.join(self.tmp_dir, "signature.png")
        open(os.path.join(self.tmp_dir, "signature.jpg"), "w").close()
        open(png_path, "w").close()
        self.assertEqual(profile_paths.signature_path(), png_path)


class TestFixedContentModule(unittest.TestCase):

    def test_raises_import_error_for_missing_fixed_content(self):
        with self.assertRaises(ImportError):
            profile_paths.fixed_content_module("nonexistent_profile_xyz")


class TestSetActiveProfileReloadsStaleModules(unittest.TestCase):
    """jd_manager.py (and anything importing it via attribute access, not
    `from jd_manager import X`) computes its path constants once at import
    time -- a real bug found live-testing Task 14: cli.py and menu.py both
    `import jd_manager` at their own top level, before any --profile flag
    or interactive gate runs, so a mid-process profile switch silently
    left jd_manager pointed at the profile that was active at process
    start. set_active_profile() must reload it so switching actually
    works, not just for profile_paths' own functions."""

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")
        # Sandboxed: this created profiles/test_reload_profile_xyz in the
        # real checkout and removed it in tearDown, which leaves it behind
        # on any error before that point.
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.second_profile = "test_reload_profile_xyz"
        # Both profiles must exist inside the sandbox: this class switches
        # AWAY from whatever profile is ambient, so that one has to resolve
        # against the redirected PROFILES_DIR too.
        self._ambient = self._orig or profile_paths._LEGACY_DEFAULT_PROFILE
        for name in {self._ambient, self.second_profile}:
            os.makedirs(os.path.join(profile_paths.PROFILES_DIR, name), exist_ok=True)

        import jd_manager

        self.jd_manager = jd_manager

    def tearDown(self):
        # Restore RESUME_PROFILE *before* leaving the sandbox. The tests in
        # this class call set_active_profile(), so the variable is left
        # pointing at a profile that only exists inside the temp dir --
        # and once the sandbox is gone, every later test in the run
        # resolves against a profile that no longer exists. Dropping this
        # restore cost 129 cascading errors in a second user's run while
        # passing on a machine where RESUME_PROFILE is always exported.
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig
        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()
        import importlib
        import sys

        if "jd_manager" in sys.modules:
            importlib.reload(sys.modules["jd_manager"])

    def test_jd_manager_jds_dir_updates_after_switch(self):
        profile_paths.set_active_profile(self.second_profile)
        self.assertTrue(
            self.jd_manager.JDS_DIR.endswith(os.path.join("jds", self.second_profile))
        )

    def test_jd_manager_tracker_csv_updates_after_switch(self):
        profile_paths.set_active_profile(self.second_profile)
        self.assertTrue(
            self.jd_manager.TRACKER_CSV.endswith(
                os.path.join("jds", self.second_profile, "jd_tracker_log.csv")
            )
        )


if __name__ == "__main__":
    unittest.main()
