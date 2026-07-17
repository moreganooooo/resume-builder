import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
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

    def test_defaults_to_morgan_when_unset(self):
        os.environ.pop("RESUME_PROFILE", None)
        self.assertEqual(profile_paths.active_profile(), "morgan")

    def test_returns_explicit_profile_when_directory_exists(self):
        os.environ["RESUME_PROFILE"] = "morgan"
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
        expected = os.path.join(profile_paths.PROJECT_ROOT, "output", "morgan", "checkpoints")
        self.assertEqual(profile_paths.checkpoints_dir("morgan"), expected)

    def test_applications_md_path_resolves_under_top_level_data(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "data", "morgan", "applications.md")
        self.assertEqual(profile_paths.applications_md_path("morgan"), expected)

    def test_tracker_csv_path_lives_inside_jds_dir(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "jds", "morgan", "jd_tracker_log.csv")
        self.assertEqual(profile_paths.tracker_csv_path("morgan"), expected)

    def test_situational_roles_path_resolves_under_profile_root(self):
        expected = os.path.join(profile_paths.PROFILES_DIR, "morgan", "situational_roles.yaml")
        self.assertEqual(profile_paths.situational_roles_path("morgan"), expected)


class TestFixedContentModule(unittest.TestCase):

    def test_raises_import_error_for_missing_fixed_content(self):
        with self.assertRaises(ImportError):
            profile_paths.fixed_content_module("nonexistent_profile_xyz")


if __name__ == "__main__":
    unittest.main()
