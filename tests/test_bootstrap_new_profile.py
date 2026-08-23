import os
import shutil
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import orchestrator  # noqa: E402
import profile_paths  # noqa: E402


class TestCreateNewProfile(unittest.TestCase):

    def setUp(self):
        # Sandboxed rather than created in the real checkout and swept up
        # afterwards: a tearDown-based cleanup leaves all four directories
        # behind whenever the test errors before reaching it.
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.test_profile = "test_profile_xyz"
        self.profile_path = os.path.join(profile_paths.PROFILES_DIR, self.test_profile)

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_creates_profile_directory_structure(self):
        result = bootstrap_bullet_bank.create_new_profile(self.test_profile)
        self.assertEqual(result, self.profile_path)
        self.assertTrue(
            os.path.isdir(os.path.join(self.profile_path, "knowledge_base"))
        )
        self.assertTrue(
            os.path.isdir(
                os.path.join(
                    self.profile_path, "knowledge_base", "bootstrap", "source_documents"
                )
            )
        )

    def test_scaffolds_empty_fixed_content_py(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        fixed_content_path = os.path.join(self.profile_path, "fixed_content.py")
        self.assertTrue(os.path.exists(fixed_content_path))
        with open(fixed_content_path) as f:
            content = f.read()
        self.assertIn("CONTACT_INFO", content)

    def test_scaffolds_empty_situational_roles_yaml(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        path = os.path.join(self.profile_path, "situational_roles.yaml")
        self.assertTrue(os.path.exists(path))

    def test_scaffolds_valid_board_scanner_config(self):
        # scan_boards.py/scan_ats.py would otherwise raise FileNotFoundError
        # the first time this profile runs a scan.
        import yaml

        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        board_scanner_dir = os.path.join(self.profile_path, "board_scanner")

        with open(os.path.join(board_scanner_dir, "tracked_companies.yml")) as f:
            self.assertEqual(yaml.safe_load(f), {"tracked_companies": []})

        with open(os.path.join(board_scanner_dir, "search_queries.yml")) as f:
            self.assertEqual(yaml.safe_load(f), {"search_queries": []})

        with open(os.path.join(board_scanner_dir, "scan_filters.yml")) as f:
            filters = yaml.safe_load(f)
        self.assertEqual(filters["title_filter"], {"positive": [], "negative": []})
        self.assertIn("Remote", filters["location_filter"]["always_allow"])

    def test_seeds_stignore_files_in_every_sync_root(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        for _label, path in profile_paths.sync_roots(self.test_profile):
            self.assertTrue(os.path.isdir(path))
            self.assertTrue(os.path.isfile(os.path.join(path, ".stignore")))

    def test_raises_if_profile_already_exists(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        with self.assertRaises(FileExistsError):
            bootstrap_bullet_bank.create_new_profile(self.test_profile)

    def test_rejects_path_traversal_in_profile_name(self):
        """Both UI entry points (the Go wizard, the questionary fallback)
        only check for non-empty -- create_new_profile is the one place
        they both funnel through, so it must reject a name that would
        escape profiles/ via os.path.join (e.g. "../../tmp/pwned") rather
        than silently creating directories outside the intended tree."""
        for bad_name in ("../escape", "a/b", "..", "trailing/slash/", "with space"):
            with self.assertRaises(ValueError):
                bootstrap_bullet_bank.create_new_profile(bad_name)

    def test_scaffold_has_every_attribute_orchestrator_actually_accesses(self):
        """
        Regression test: BACKGROUND_IDENTITY/BACKGROUND_TAGS were added to
        fixed_content.py (moved out of orchestrator.py's own module
        constants) without also adding empty defaults here -- so a fresh
        profile's very first real build would have hit a hard
        AttributeError in build_background_summary() the moment any bullet
        got audited, not a graceful degradation. This exercises the actual
        consuming functions (not just checking attribute names exist) so
        this class of bug gets caught here instead of on a real user's
        first build.
        """
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        fixed_content = profile_paths.fixed_content_module(self.test_profile)

        orig_profile = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = self.test_profile
        try:
            # build_background_summary() does direct (not getattr)
            # attribute access on both of these -- must not raise.
            summary = orchestrator.build_background_summary("[email]")
            self.assertEqual(summary, fixed_content.BACKGROUND_IDENTITY)

            # extract_cv_section() does direct attribute access on this too.
            self.assertEqual(
                orchestrator.extract_cv_section("some cv text", "Some Company"),
                "some cv text",
            )
        finally:
            if orig_profile is None:
                os.environ.pop("RESUME_PROFILE", None)
            else:
                os.environ["RESUME_PROFILE"] = orig_profile


if __name__ == "__main__":
    unittest.main()
