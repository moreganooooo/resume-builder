import os
import shutil
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import profile_paths  # noqa: E402


class TestProfileManagement(unittest.TestCase):

    def setUp(self):
        # This class exercises the real rename/delete flows across all four
        # sync roots, so it used to create and remove directories directly
        # in the developer's checkout -- leaving them behind whenever a test
        # errored before tearDown. isolate_for_tests() gives it a sandbox
        # with the same shape instead.
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.test_profile = "temp_test_profile_99"
        self.target_rename = "temp_test_profile_100"

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_rename_profile_directories(self):
        # Create directories for self.test_profile
        for label, path in profile_paths.sync_roots(self.test_profile):
            os.makedirs(path, exist_ok=True)
            # Create a dummy file inside
            dummy_file = os.path.join(path, f"dummy_{label}.txt")
            with open(dummy_file, "w") as f:
                f.write(f"test {label}")

        # Simulate rename to self.target_rename (same logic as menu.py's rename flow)
        for label, path in profile_paths.sync_roots(self.test_profile):
            if os.path.exists(path):
                parent = os.path.dirname(path)
                new_path = os.path.join(parent, self.target_rename)
                os.rename(path, new_path)

        # Verify old directories are gone, and new directories exist with dummy files
        for label, path in profile_paths.sync_roots(self.test_profile):
            self.assertFalse(os.path.exists(path))

        for label, path in profile_paths.sync_roots(self.target_rename):
            self.assertTrue(os.path.exists(path))
            dummy_file = os.path.join(path, f"dummy_{label}.txt")
            self.assertTrue(os.path.exists(dummy_file))

    def test_delete_profile_directories(self):
        # Create directories for self.test_profile
        for label, path in profile_paths.sync_roots(self.test_profile):
            os.makedirs(path, exist_ok=True)
            # Create a dummy file inside
            dummy_file = os.path.join(path, f"dummy_{label}.txt")
            with open(dummy_file, "w") as f:
                f.write(f"test {label}")

        # Simulate delete (same logic as menu.py's delete flow)
        for _, path in profile_paths.sync_roots(self.test_profile):
            if os.path.exists(path):
                shutil.rmtree(path)

        # Verify all directories are gone
        for _, path in profile_paths.sync_roots(self.test_profile):
            self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
