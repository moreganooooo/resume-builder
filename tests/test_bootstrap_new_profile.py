import os
import shutil
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import profile_paths  # noqa: E402


class TestCreateNewProfile(unittest.TestCase):

    def setUp(self):
        self.test_profile = "test_profile_xyz"
        self.profile_path = os.path.join(profile_paths.PROFILES_DIR, self.test_profile)

    def tearDown(self):
        if os.path.isdir(self.profile_path):
            shutil.rmtree(self.profile_path)

    def test_creates_profile_directory_structure(self):
        result = bootstrap_bullet_bank.create_new_profile(self.test_profile)
        self.assertEqual(result, self.profile_path)
        self.assertTrue(os.path.isdir(os.path.join(self.profile_path, "knowledge_base")))
        self.assertTrue(os.path.isdir(os.path.join(self.profile_path, "knowledge_base", "bootstrap", "source_documents")))

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

    def test_raises_if_profile_already_exists(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        with self.assertRaises(FileExistsError):
            bootstrap_bullet_bank.create_new_profile(self.test_profile)


if __name__ == "__main__":
    unittest.main()
