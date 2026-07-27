import datetime
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


class TestVerifyJdPaths(unittest.TestCase):
    """verify_jd_paths() -- scan.py's default-on verify pass, career-ops's
    scan.mjs --verify ported. No recency skip (unlike run_liveness_check):
    every path passed in gets checked, always."""

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness_verify")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.expired_dir = os.path.join(self.tmp_dir, "expired")
        self._real_expired_dir = jd_manager.EXPIRED_DIR
        jd_manager.EXPIRED_DIR = self.expired_dir

        self.with_url_path = os.path.join(self.tmp_dir, "with_url.json")
        with open(self.with_url_path, "w", encoding="utf-8") as f:
            json.dump({"source_url": "https://example.com/job/1", "job_title": "Test"}, f)

    def tearDown(self):
        jd_manager.EXPIRED_DIR = self._real_expired_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_empty_paths_returns_zeros_without_calling_subprocess(self):
        with patch("liveness.subprocess.run") as mock_run:
            result = liveness.verify_jd_paths([])
        mock_run.assert_not_called()
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["expired_paths"], [])

    @patch("liveness.subprocess.run")
    def test_expired_path_is_moved_and_reported_in_expired_paths(self, mock_run):
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "expired", "code": "http_gone", "reason": "HTTP 404"},
        ]))

        result = liveness.verify_jd_paths([self.with_url_path])

        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["expired_paths"], [self.with_url_path])
        self.assertFalse(os.path.exists(self.with_url_path))
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "with_url.json")))

    @patch("liveness.subprocess.run")
    def test_active_path_is_not_moved(self, mock_run):
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "active", "code": "apply_control_visible", "reason": "ok"},
        ]))

        result = liveness.verify_jd_paths([self.with_url_path])

        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["expired_paths"], [])
        self.assertTrue(os.path.exists(self.with_url_path))

    def test_does_not_call_get_pending_jds(self):
        # verify_jd_paths operates only on the paths it's given -- it
        # must never fall back to scanning the whole pending queue.
        with patch("liveness.jd_manager.get_pending_jds") as mock_pending, \
             patch("liveness.subprocess.run") as mock_run:
            mock_run.return_value = _proc(returncode=0, stdout="[]")
            liveness.verify_jd_paths([self.with_url_path])
        mock_pending.assert_not_called()


class TestRecencySkip(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness_recency")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.expired_dir = os.path.join(self.tmp_dir, "expired")
        self._real_expired_dir = jd_manager.EXPIRED_DIR
        jd_manager.EXPIRED_DIR = self.expired_dir

    def tearDown(self):
        jd_manager.EXPIRED_DIR = self._real_expired_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def _write(self, name, data):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_split_recently_checked_separates_fresh_from_stale(self):
        fresh_checked_at = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(timespec="seconds")
        stale_checked_at = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat(timespec="seconds")
        fresh = self._write("fresh.json", {"source_url": "https://x/1", "_liveness": {"result": "active", "checked_at": fresh_checked_at}})
        stale = self._write("stale.json", {"source_url": "https://x/2", "_liveness": {"result": "active", "checked_at": stale_checked_at}})
        never = self._write("never.json", {"source_url": "https://x/3"})

        recently_checked, to_check = liveness.split_recently_checked([fresh, stale, never])

        self.assertEqual(recently_checked, [fresh])
        self.assertEqual(set(to_check), {stale, never})

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_recently_checked_jd_is_skipped_by_default(self, mock_run, mock_get_pending):
        fresh_checked_at = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(timespec="seconds")
        fresh = self._write("fresh.json", {"source_url": "https://x/1", "_liveness": {"result": "active", "checked_at": fresh_checked_at}})
        mock_get_pending.return_value = [fresh]

        summary = liveness.run_liveness_check()

        mock_run.assert_not_called()
        self.assertEqual(summary["recently_checked"], 1)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_refresh_flag_re_checks_recently_checked_jds(self, mock_run, mock_get_pending):
        fresh_checked_at = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(timespec="seconds")
        fresh = self._write("fresh.json", {"source_url": "https://x/1", "_liveness": {"result": "active", "checked_at": fresh_checked_at}})
        mock_get_pending.return_value = [fresh]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": fresh, "url": "https://x/1", "result": "active", "reason": "ok"},
        ]))

        summary = liveness.run_liveness_check(refresh=True)

        mock_run.assert_called_once()
        self.assertEqual(summary["active"], 1)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_checked_result_is_persisted_onto_the_jd(self, mock_run, mock_get_pending):
        path = self._write("a.json", {"source_url": "https://x/1"})
        mock_get_pending.return_value = [path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": path, "url": "https://x/1", "result": "active", "reason": "apply button found"},
        ]))

        liveness.run_liveness_check()

        persisted = jd_manager.read_liveness(path)
        self.assertEqual(persisted["result"], "active")
        self.assertEqual(persisted["reason"], "apply button found")
