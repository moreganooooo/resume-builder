import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import liveness  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestLiveness(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.expired_dir = os.path.join(self.tmp_dir, "expired")

        self._real_expired_dir = jd_manager.EXPIRED_DIR
        jd_manager.EXPIRED_DIR = self.expired_dir

        self.with_url_path = os.path.join(self.tmp_dir, "with_url.json")
        self.no_url_path = os.path.join(self.tmp_dir, "no_url.json")
        with open(self.with_url_path, "w", encoding="utf-8") as f:
            json.dump({"source_url": "https://example.com/job/1", "job_title": "Test"}, f)
        with open(self.no_url_path, "w", encoding="utf-8") as f:
            json.dump({"job_title": "No URL Here"}, f)

    def tearDown(self):
        jd_manager.EXPIRED_DIR = self._real_expired_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_gather_candidates_skips_jds_without_source_url(self):
        candidates = liveness._gather_candidates([self.with_url_path, self.no_url_path])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], "https://example.com/job/1")
        self.assertEqual(candidates[0]["source_file"], self.with_url_path)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_expired_jd_gets_moved_to_expired_dir(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "expired", "code": "http_gone", "reason": "HTTP 404"},
        ]))

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["expired"], 1)
        self.assertEqual(summary["moved"], 1)
        self.assertFalse(os.path.exists(self.with_url_path))
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "with_url.json")))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_active_jd_stays_in_place(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "active", "code": "apply_control_visible", "reason": "visible apply control detected"},
        ]))

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_uncertain_jd_stays_in_place_and_is_flagged(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "uncertain", "code": "no_apply_control", "reason": "content present but no strong liveness signals found"},
        ]))

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["uncertain"], 1)
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    def test_jds_without_source_url_are_counted_as_skipped(self, mock_get_pending):
        mock_get_pending.return_value = [self.no_url_path]

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["moved"], 0)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_subprocess_failure_moves_nothing(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=1, stderr="Fatal: browser launch failed")

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_malformed_json_output_moves_nothing(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout="not valid json{{{")

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_temp_input_file_cleaned_up_after_success(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "active", "code": "apply_control_visible", "reason": "ok"},
        ]))

        liveness.run_liveness_check()

        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_temp_input_file_cleaned_up_after_subprocess_failure(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=1, stderr="boom")

        liveness.run_liveness_check()

        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))
