import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import verify_syncthing


class TestVerifySyncthing(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_check_directory_structure_creates_missing(self):
        import profile_paths

        with profile_paths.isolate_for_tests(self.tmp_dir):
            with patch.object(profile_paths, "PROJECT_ROOT", self.tmp_dir):
                results = verify_syncthing.check_directory_structure("test_user")
                self.assertEqual(len(results), 4)
                for r in results:
                    self.assertEqual(r["status"], "PASS")
                # Verify directories were created
                self.assertTrue(
                    os.path.isdir(os.path.join(self.tmp_dir, "profiles", "test_user"))
                )
                self.assertTrue(
                    os.path.isdir(os.path.join(self.tmp_dir, "jds", "test_user"))
                )
                self.assertTrue(
                    os.path.isdir(os.path.join(self.tmp_dir, "output", "test_user"))
                )
                self.assertTrue(
                    os.path.isdir(os.path.join(self.tmp_dir, "data", "test_user"))
                )

    def test_check_stignore_creates_default(self):
        with patch("profile_paths.PROJECT_ROOT", self.tmp_dir):
            result = verify_syncthing.check_stignore_rules()
            self.assertEqual(result["status"], "PASS")
            stignore_path = os.path.join(self.tmp_dir, ".stignore")
            self.assertTrue(os.path.isfile(stignore_path))
            with open(stignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("*.db-wal", content)
            self.assertIn("__pycache__", content)

    def test_check_stignore_detects_existing_valid(self):
        stignore_path = os.path.join(self.tmp_dir, ".stignore")
        with open(stignore_path, "w", encoding="utf-8") as f:
            f.write("*.db-wal\n*.db-shm\n__pycache__\n")
        with patch("profile_paths.PROJECT_ROOT", self.tmp_dir):
            result = verify_syncthing.check_stignore_rules()
            self.assertEqual(result["status"], "PASS")

    def test_check_stignore_warns_on_missing_rules(self):
        stignore_path = os.path.join(self.tmp_dir, ".stignore")
        with open(stignore_path, "w", encoding="utf-8") as f:
            f.write("some_other_rule\n")
        with patch("profile_paths.PROJECT_ROOT", self.tmp_dir):
            result = verify_syncthing.check_stignore_rules()
            self.assertEqual(result["status"], "WARN")
            self.assertIn("missing recommended rules", result["detail"])

    @patch("db.checkpoint")
    @patch("db.get_db_path")
    def test_check_database_wal_success(self, mock_get_path, mock_checkpoint):
        fake_db = os.path.join(self.tmp_dir, "data.db")
        with open(fake_db, "w") as f:
            f.write("dummy")
        mock_get_path.return_value = fake_db
        result = verify_syncthing.check_database_wal("test_user")
        self.assertEqual(result["status"], "PASS")
        mock_checkpoint.assert_called_once_with("test_user")

    @patch("db.checkpoint", side_effect=Exception("DB locked"))
    def test_check_database_wal_failure(self, mock_checkpoint):
        result = verify_syncthing.check_database_wal("test_user")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("DB locked", result["detail"])

    @patch("socket.socket")
    def test_check_syncthing_service_online(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value = mock_sock

        result = verify_syncthing.check_syncthing_service()
        self.assertEqual(result["status"], "PASS")

    @patch("socket.socket")
    def test_check_syncthing_service_offline(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # Connection refused
        mock_socket_cls.return_value = mock_sock

        result = verify_syncthing.check_syncthing_service()
        self.assertEqual(result["status"], "INFO")

    def test_check_termux_mobile_environment_on_desktop(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("os.path.isdir", return_value=False),
        ):
            result = verify_syncthing.check_termux_mobile_environment()
            self.assertEqual(result["status"], "PASS")
            self.assertIn("Desktop host", result["detail"])

    def test_run_all_syncthing_checks(self):
        import profile_paths

        with profile_paths.isolate_for_tests(self.tmp_dir):
            with patch.object(profile_paths, "PROJECT_ROOT", self.tmp_dir):
                checks = verify_syncthing.run_all_syncthing_checks("test_user")
                self.assertGreaterEqual(len(checks), 7)


if __name__ == "__main__":
    unittest.main()
