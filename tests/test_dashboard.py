import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
# tests/ itself, so `import persona` works when run standalone.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dashboard  # noqa: E402


class TestGoAvailable(unittest.TestCase):

    @patch("dashboard.shutil.which", return_value="/usr/local/bin/go")
    def test_true_when_go_on_path(self, mock_which):
        self.assertTrue(dashboard.go_available())

    @patch("dashboard.shutil.which", return_value=None)
    def test_false_when_go_missing(self, mock_which):
        self.assertFalse(dashboard.go_available())


class TestRun(unittest.TestCase):

    def setUp(self):
        # dashboard.run(<profile>) resolves that profile's real paths, so the
        # profile has to exist. A persona sandbox gives it one without
        # depending on whoever is operating this checkout.
        import persona

        self._sandbox = persona.sandbox_profile("testprofile")
        self._sandbox.__enter__()

    def tearDown(self):
        self._sandbox.__exit__(None, None, None)

    @patch("dashboard.go_available", return_value=False)
    def test_returns_false_with_install_hint_when_go_missing(self, mock_go):
        success, message = dashboard.run("testprofile")
        self.assertFalse(success)
        self.assertIn("Go isn't installed", message)

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.os.path.exists", return_value=False)
    @patch("dashboard.go_available", return_value=True)
    def test_returns_false_when_nothing_to_show(self, mock_go, mock_exists, mock_list):
        success, message = dashboard.run("testprofile")
        self.assertFalse(success)
        self.assertIn("Nothing to show yet", message)

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[{"path": "a.json"}])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=False)
    @patch("dashboard.go_available", return_value=True)
    def test_proceeds_without_applications_md_when_jobs_are_evaluated(
        self, mock_go, mock_exists, mock_subproc, mock_list
    ):
        # applications.md only feeds Pipeline -- a profile with evaluated
        # jobs but no logged application statuses still has something for
        # the Jobs screen to show, so it shouldn't be locked out entirely.
        mock_subproc.return_value = MagicMock(returncode=0)
        success, message = dashboard.run("testprofile")
        self.assertTrue(success)

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_launches_go_run_with_the_profile_data_dir(
        self, mock_go, mock_exists, mock_subproc, mock_list
    ):
        mock_subproc.return_value = MagicMock(returncode=0)
        success, message = dashboard.run("testprofile")
        self.assertTrue(success)
        expected_data_dir = dashboard.profile_paths.data_dir("testprofile")
        args = mock_subproc.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], ".")
        self.assertEqual(args[3], "-path")
        self.assertEqual(args[4], expected_data_dir)
        self.assertEqual(args[5], "-jobs-path")
        self.assertTrue(
            args[6]
        )  # a real temp path was generated; cleanup itself is TestRunCleansUpJobsExport's job
        self.assertEqual(args[7], "-python-path")
        self.assertEqual(args[8], dashboard.sys.executable)
        self.assertEqual(args[9], "-project-root")
        self.assertEqual(args[10], dashboard.profile_paths.PROJECT_ROOT)
        self.assertEqual(mock_subproc.call_args[1]["cwd"], dashboard.DASHBOARD_DIR)
        self.assertIn("env", mock_subproc.call_args[1])

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_returns_false_when_dashboard_process_exits_nonzero(
        self, mock_go, mock_exists, mock_subproc, mock_list
    ):
        mock_subproc.return_value = MagicMock(returncode=1)
        success, message = dashboard.run("testprofile")
        self.assertFalse(success)
        self.assertIn("exited with an error", message)


class TestExportJobsTo(unittest.TestCase):

    @patch("dashboard.picker.list_all_evaluated_jds")
    def test_writes_rows_to_the_given_path(self, mock_list):
        rows = [{"path": "a.json", "status": "Pending"}]
        mock_list.return_value = rows
        path = os.path.join(tempfile.gettempdir(), "test_export_jobs_to.json")
        try:
            dashboard._export_jobs_to(path)
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), rows)
        finally:
            os.remove(path)


class TestWriteJobsExport(unittest.TestCase):

    @patch("dashboard.picker.list_all_evaluated_jds")
    def test_writes_valid_json_matching_picker_rows(self, mock_list):
        rows = [
            {
                "path": "jds/testprofile/a.json",
                "status": "Pending",
                "title": "T",
                "company": "C",
                "evaluation": {"composite_score": 4.5},
                "liveness": None,
                "application": None,
            }
        ]
        mock_list.return_value = rows

        path = dashboard._write_jobs_export()
        try:
            with open(path, "r", encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(written, rows)
        finally:
            os.remove(path)

    @patch("dashboard.profile_paths.set_active_profile")
    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    def test_sets_active_profile_when_explicit_profile_given(
        self, mock_list, mock_set_active
    ):
        path = dashboard._write_jobs_export("dominick")
        try:
            mock_set_active.assert_called_once_with("dominick")
        finally:
            os.remove(path)

    @patch("dashboard.profile_paths.set_active_profile")
    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    def test_does_not_touch_active_profile_when_none_given(
        self, mock_list, mock_set_active
    ):
        path = dashboard._write_jobs_export()
        try:
            mock_set_active.assert_not_called()
        finally:
            os.remove(path)


class TestRunCleansUpJobsExport(unittest.TestCase):

    def setUp(self):
        # dashboard.run(<profile>) resolves that profile's real paths, so the
        # profile has to exist. A persona sandbox gives it one without
        # depending on whoever is operating this checkout.
        import persona

        self._sandbox = persona.sandbox_profile("testprofile")
        self._sandbox.__enter__()

    def tearDown(self):
        self._sandbox.__exit__(None, None, None)

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_temp_file_removed_after_successful_run(
        self, mock_go, mock_exists, mock_subproc, mock_list
    ):
        mock_subproc.return_value = MagicMock(returncode=0)
        dashboard.run("testprofile")
        jobs_path = mock_subproc.call_args[0][0][6]
        # os.path.isfile, not os.path.exists -- dashboard.os IS the real os
        # module object, so the @patch("dashboard.os.path.exists", ...)
        # above also mutates the shared os.path.exists this assertion would
        # otherwise call, always returning True regardless of the real file.
        self.assertFalse(os.path.isfile(jobs_path))

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_temp_file_removed_even_when_process_fails(
        self, mock_go, mock_exists, mock_subproc, mock_list
    ):
        mock_subproc.return_value = MagicMock(returncode=1)
        dashboard.run("testprofile")
        jobs_path = mock_subproc.call_args[0][0][6]
        # os.path.isfile, not os.path.exists -- dashboard.os IS the real os
        # module object, so the @patch("dashboard.os.path.exists", ...)
        # above also mutates the shared os.path.exists this assertion would
        # otherwise call, always returning True regardless of the real file.
        self.assertFalse(os.path.isfile(jobs_path))


class TestDashboardProfileEnvAndRecompile(unittest.TestCase):

    def setUp(self):
        # dashboard.run(<profile>) resolves that profile's real paths, so the
        # profile has to exist. A persona sandbox gives it one without
        # depending on whoever is operating this checkout.
        import persona

        self._sandbox = persona.sandbox_profile("testprofile")
        self._sandbox.__enter__()

    def tearDown(self):
        self._sandbox.__exit__(None, None, None)

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    @patch("dashboard.ui_config.get_full_ui_config")
    def test_run_passes_profile_ui_env_vars(
        self, mock_ui_conf, mock_go, mock_exists, mock_subproc, mock_list
    ):
        mock_ui_conf.return_value = {
            "icon_set": "unicode",
            "motion": "reduced",
            "theme_mode": "catppuccin-latte",
        }
        mock_subproc.return_value = MagicMock(returncode=0)
        success, _ = dashboard.run("testprofile")
        self.assertTrue(success)
        env = mock_subproc.call_args[1].get("env")
        self.assertIsNotNone(env)
        self.assertEqual(env.get("RESUME_BUILDER_PROFILE"), "testprofile")
        self.assertEqual(env.get("RESUME_BUILDER_ICONS"), "unicode")
        self.assertEqual(env.get("RESUME_BUILDER_MOTION"), "reduced")

    @patch("dashboard.go_available", return_value=True)
    @patch("dashboard.subprocess.run")
    def test_compile_dashboard_when_stale(self, mock_subproc, mock_go):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_dir = os.path.join(tmpdir, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            bin_path = os.path.join(bin_dir, "dashboard")
            # Create dummy bin
            with open(bin_path, "w") as f:
                f.write("bin")
            # Create newer .go file
            go_file = os.path.join(tmpdir, "main.go")
            with open(go_file, "w") as f:
                f.write("package main")
            # Set go file mtime newer
            os.utime(go_file, (time.time() + 100, time.time() + 100))

            with patch("dashboard.DASHBOARD_DIR", tmpdir):
                stale = dashboard._is_binary_stale(bin_path)
                self.assertTrue(stale)


if __name__ == "__main__":
    unittest.main()
