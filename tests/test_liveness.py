import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import liveness  # noqa: E402


def _mock_popen(returncode=0, stdout="", stderr_lines=None, timeout=False):
    """Builds a subprocess.Popen side_effect matching liveness.py's real
    usage: stdout is written into the real file handle passed as the
    stdout= kwarg (not captured on the returned object, see
    LIVENESS_OUTPUT_PATH's docstring for why), stderr is an iterable of
    lines (the code iterates proc.stderr live), and poll()/wait() model
    a process that's already finished by the time wait() is called --
    unless timeout=True, in which case wait() raises TimeoutExpired and
    poll() reports still-running (None) so the kill() path is exercised."""

    def _side_effect(*args, **kwargs):
        stdout_file = kwargs.get("stdout")
        if stdout_file is not None:
            stdout_file.write(stdout)
            stdout_file.flush()
        proc = MagicMock()
        proc.stderr = iter(stderr_lines or [])
        proc.returncode = returncode
        if timeout:
            proc.poll.return_value = None
            # First wait() (timeout=timeout_s, inside the try) raises;
            # the second, bare wait() in the finally block (after kill())
            # must return normally, matching real subprocess.wait()'s
            # behavior once the killed process has actually exited.
            proc.wait.side_effect = [
                subprocess.TimeoutExpired(cmd="node", timeout=1),
                returncode,
            ]
        else:
            proc.poll.return_value = returncode
            proc.wait.return_value = returncode
        return proc

    return _side_effect


class TestChildEnv(unittest.TestCase):

    def test_strips_secrets_but_keeps_everything_else(self):
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "secret-key",
                "GOOGLE_API_KEY": "secret-key-2",
                "JOBRIGHT_COOKIE_STRING": "secret-cookie",
                "PATH": os.environ.get("PATH", ""),
            },
        ):
            child_env = liveness._child_env()
        self.assertNotIn("GEMINI_API_KEY", child_env)
        self.assertNotIn("GOOGLE_API_KEY", child_env)
        self.assertNotIn("JOBRIGHT_COOKIE_STRING", child_env)
        self.assertIn("PATH", child_env)


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
            json.dump(
                {"source_url": "https://example.com/job/1", "job_title": "Test"}, f
            )
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
    @patch("liveness.subprocess.Popen")
    def test_expired_jd_gets_moved_to_expired_dir(self, mock_popen, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.with_url_path,
                        "url": "https://example.com/job/1",
                        "result": "expired",
                        "code": "http_gone",
                        "reason": "HTTP 404",
                    },
                ]
            ),
        )

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["expired"], 1)
        self.assertEqual(summary["moved"], 1)
        self.assertFalse(os.path.exists(self.with_url_path))
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "with_url.json")))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_active_jd_stays_in_place(self, mock_popen, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.with_url_path,
                        "url": "https://example.com/job/1",
                        "result": "active",
                        "code": "apply_control_visible",
                        "reason": "visible apply control detected",
                    },
                ]
            ),
        )

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_uncertain_jd_stays_in_place_and_is_flagged(
        self, mock_popen, mock_get_pending
    ):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.with_url_path,
                        "url": "https://example.com/job/1",
                        "result": "uncertain",
                        "code": "no_apply_control",
                        "reason": "content present but no strong liveness signals found",
                    },
                ]
            ),
        )

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
    @patch("liveness.subprocess.Popen")
    def test_subprocess_failure_moves_nothing(self, mock_popen, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(
            returncode=1, stderr_lines=["Fatal: browser launch failed"]
        )

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_malformed_json_output_moves_nothing(self, mock_popen, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(returncode=0, stdout="not valid json{{{")

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_temp_input_file_cleaned_up_after_success(
        self, mock_popen, mock_get_pending
    ):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.with_url_path,
                        "url": "https://example.com/job/1",
                        "result": "active",
                        "code": "apply_control_visible",
                        "reason": "ok",
                    },
                ]
            ),
        )

        liveness.run_liveness_check()

        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))
        self.assertFalse(os.path.exists(liveness.LIVENESS_OUTPUT_PATH))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_temp_input_file_cleaned_up_after_subprocess_failure(
        self, mock_popen, mock_get_pending
    ):
        mock_get_pending.return_value = [self.with_url_path]
        mock_popen.side_effect = _mock_popen(returncode=1, stderr_lines=["boom"])

        liveness.run_liveness_check()

        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))
        self.assertFalse(os.path.exists(liveness.LIVENESS_OUTPUT_PATH))

    @patch("liveness.os.killpg")
    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_timeout_returns_error_and_kills_the_process(
        self, mock_popen, mock_get_pending, mock_killpg
    ):
        mock_get_pending.return_value = [self.with_url_path]
        created_procs = []
        base_side_effect = _mock_popen(timeout=True)

        def _capturing_side_effect(*args, **kwargs):
            proc = base_side_effect(*args, **kwargs)
            created_procs.append(proc)
            return proc

        mock_popen.side_effect = _capturing_side_effect

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(len(created_procs), 1)
        created_procs[0].kill.assert_called_once()
        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))
        self.assertFalse(os.path.exists(liveness.LIVENESS_OUTPUT_PATH))


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
            json.dump(
                {"source_url": "https://example.com/job/1", "job_title": "Test"}, f
            )

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
        with patch("liveness.subprocess.Popen") as mock_popen:
            result = liveness.verify_jd_paths([])
        mock_popen.assert_not_called()
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["expired_source_paths"], [])

    @patch("liveness.subprocess.Popen")
    def test_expired_path_is_moved_and_reported_in_expired_source_paths(
        self, mock_popen
    ):
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.with_url_path,
                        "url": "https://example.com/job/1",
                        "result": "expired",
                        "code": "http_gone",
                        "reason": "HTTP 404",
                    },
                ]
            ),
        )

        result = liveness.verify_jd_paths([self.with_url_path])

        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["expired_source_paths"], [self.with_url_path])
        self.assertFalse(os.path.exists(self.with_url_path))
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "with_url.json")))

    @patch("liveness.subprocess.Popen")
    def test_active_path_is_not_moved(self, mock_popen):
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.with_url_path,
                        "url": "https://example.com/job/1",
                        "result": "active",
                        "code": "apply_control_visible",
                        "reason": "ok",
                    },
                ]
            ),
        )

        result = liveness.verify_jd_paths([self.with_url_path])

        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["expired_source_paths"], [])
        self.assertTrue(os.path.exists(self.with_url_path))

    def test_does_not_call_get_pending_jds(self):
        # verify_jd_paths operates only on the paths it's given -- it
        # must never fall back to scanning the whole pending queue.
        with (
            patch("liveness.jd_manager.get_pending_jds") as mock_pending,
            patch("liveness.subprocess.Popen") as mock_popen,
        ):
            mock_popen.side_effect = _mock_popen(returncode=0, stdout="[]")
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
        fresh_checked_at = (
            datetime.datetime.now() - datetime.timedelta(hours=1)
        ).isoformat(timespec="seconds")
        stale_checked_at = (
            datetime.datetime.now() - datetime.timedelta(hours=48)
        ).isoformat(timespec="seconds")
        fresh = self._write(
            "fresh.json",
            {
                "source_url": "https://x/1",
                "_liveness": {"result": "active", "checked_at": fresh_checked_at},
            },
        )
        stale = self._write(
            "stale.json",
            {
                "source_url": "https://x/2",
                "_liveness": {"result": "active", "checked_at": stale_checked_at},
            },
        )
        never = self._write("never.json", {"source_url": "https://x/3"})

        recently_checked, to_check = liveness.split_recently_checked(
            [fresh, stale, never]
        )

        self.assertEqual(recently_checked, [fresh])
        self.assertEqual(set(to_check), {stale, never})

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_recently_checked_jd_is_skipped_by_default(
        self, mock_popen, mock_get_pending
    ):
        fresh_checked_at = (
            datetime.datetime.now() - datetime.timedelta(hours=1)
        ).isoformat(timespec="seconds")
        fresh = self._write(
            "fresh.json",
            {
                "source_url": "https://x/1",
                "_liveness": {"result": "active", "checked_at": fresh_checked_at},
            },
        )
        mock_get_pending.return_value = [fresh]

        summary = liveness.run_liveness_check()

        mock_popen.assert_not_called()
        self.assertEqual(summary["recently_checked"], 1)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_refresh_flag_re_checks_recently_checked_jds(
        self, mock_popen, mock_get_pending
    ):
        fresh_checked_at = (
            datetime.datetime.now() - datetime.timedelta(hours=1)
        ).isoformat(timespec="seconds")
        fresh = self._write(
            "fresh.json",
            {
                "source_url": "https://x/1",
                "_liveness": {"result": "active", "checked_at": fresh_checked_at},
            },
        )
        mock_get_pending.return_value = [fresh]
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": fresh,
                        "url": "https://x/1",
                        "result": "active",
                        "reason": "ok",
                    },
                ]
            ),
        )

        summary = liveness.run_liveness_check(refresh=True)

        mock_popen.assert_called_once()
        self.assertEqual(summary["active"], 1)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.Popen")
    def test_checked_result_is_persisted_onto_the_jd(
        self, mock_popen, mock_get_pending
    ):
        path = self._write("a.json", {"source_url": "https://x/1"})
        mock_get_pending.return_value = [path]
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": path,
                        "url": "https://x/1",
                        "result": "active",
                        "reason": "apply button found",
                    },
                ]
            ),
        )

        liveness.run_liveness_check()

        persisted = jd_manager.read_liveness(path)
        self.assertEqual(persisted["result"], "active")
        self.assertEqual(persisted["reason"], "apply button found")


class TestVerifyCandidatesActivity(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness_activity")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_expired_dir = jd_manager.EXPIRED_DIR
        jd_manager.EXPIRED_DIR = os.path.join(self.tmp_dir, "expired")
        self.jd_path = os.path.join(self.tmp_dir, "acme.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({"source_url": "https://acme.com/job/1", "job_title": "Test"}, f)

    def tearDown(self):
        jd_manager.EXPIRED_DIR = self._real_expired_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    @patch("liveness.subprocess.Popen")
    def test_structured_progress_line_routes_through_activity_step(self, mock_popen):
        progress_line = (
            json.dumps(
                {
                    "type": "progress",
                    "index": 1,
                    "total": 1,
                    "result": "active",
                    "code": "apply_control_visible",
                    "reason": None,
                    "source_file": self.jd_path,
                }
            )
            + "\n"
        )
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.jd_path,
                        "url": "https://acme.com/job/1",
                        "result": "active",
                        "code": "apply_control_visible",
                        "reason": None,
                    },
                ]
            ),
            stderr_lines=[progress_line],
        )

        activity = MagicMock()
        liveness.verify_jd_paths([self.jd_path], activity=activity)

        activity.step.assert_called_once()
        args = activity.step.call_args.args
        self.assertEqual(args[0], "success")
        self.assertEqual(args[1], "Verify")

    @patch("liveness.subprocess.Popen")
    @patch("liveness.cli_art.print_subprocess_output")
    def test_non_json_stderr_line_falls_back_to_raw_passthrough(
        self, mock_print_raw, mock_popen
    ):
        mock_popen.side_effect = _mock_popen(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "job_key": "abc",
                        "source_file": self.jd_path,
                        "url": "https://acme.com/job/1",
                        "result": "active",
                        "code": "apply_control_visible",
                        "reason": None,
                    },
                ]
            ),
            stderr_lines=["Fatal: something unexpected\n"],
        )

        activity = MagicMock()
        liveness.verify_jd_paths([self.jd_path], activity=activity)

        activity.step.assert_not_called()
        mock_print_raw.assert_called_once()


class TestDatabaseCandidatesAreGuardedInTests(unittest.TestCase):
    """A liveness sweep is real Playwright network I/O. When database
    candidates were first added, the existing tests mocked the filesystem
    JD list but knew nothing about a database source, so the suite
    silently launched Chromium and started checking 643 live URLs."""

    def test_no_database_candidates_against_the_real_profile(self):
        self.assertEqual(liveness._gather_db_candidates(), [])

    def test_liveness_recency_helper_skips_a_recent_check(self):
        import datetime

        recent = {"checked_at": datetime.datetime.now().isoformat()}
        self.assertTrue(liveness._liveness_is_recent(recent))

    def test_liveness_recency_helper_allows_a_stale_check(self):
        import datetime

        stale = {
            "checked_at": (
                datetime.datetime.now() - datetime.timedelta(days=5)
            ).isoformat()
        }
        self.assertFalse(liveness._liveness_is_recent(stale))

    def test_liveness_recency_helper_tolerates_junk(self):
        for value in (None, {}, {"checked_at": "not-a-date"}, {"checked_at": None}):
            self.assertFalse(liveness._liveness_is_recent(value))


class TestProgressStreamRecovery(unittest.TestCase):
    """An unreadable final blob must not discard a completed sweep.

    The child prints one JSON blob after the browser closes. On
    2026-08-21 an 812-candidate sweep ran ~50 minutes, checked every URL,
    then threw all of it away because stdout came back empty while the
    child still exited 0. Every verdict had already been streamed as a
    progress event.
    """

    CANDIDATES = [
        {"job_key": "k1", "source_file": "k1", "url": "https://x.com/1"},
        {"job_key": "k2", "source_file": "k2", "url": "https://x.com/2"},
    ]
    EVENTS = [
        {
            "type": "progress",
            "source_file": "k1",
            "result": "active",
            "code": "apply_control_visible",
            "reason": None,
        },
        {
            "type": "progress",
            "source_file": "k2",
            "result": "expired",
            "code": "gone",
            "reason": "404",
        },
    ]

    def test_rebuilds_every_result(self):
        rebuilt = liveness._results_from_progress(self.EVENTS, self.CANDIDATES)
        self.assertEqual(len(rebuilt), 2)
        self.assertEqual(rebuilt[0]["result"], "active")
        self.assertEqual(rebuilt[1]["result"], "expired")

    def test_carries_job_key_and_url_from_the_candidate(self):
        # The event does not contain either; both are needed to persist
        # the verdict and to move an expired posting.
        rebuilt = liveness._results_from_progress(self.EVENTS, self.CANDIDATES)
        self.assertEqual(rebuilt[0]["job_key"], "k1")
        self.assertEqual(rebuilt[0]["url"], "https://x.com/1")

    def test_events_for_unknown_candidates_are_ignored(self):
        events = self.EVENTS + [
            {"type": "progress", "source_file": "ghost", "result": "active"}
        ]
        self.assertEqual(
            len(liveness._results_from_progress(events, self.CANDIDATES)), 2
        )

    def test_events_without_a_verdict_are_ignored(self):
        events = [{"type": "progress", "source_file": "k1"}]
        self.assertEqual(liveness._results_from_progress(events, self.CANDIDATES), [])

    def test_empty_inputs_are_safe(self):
        self.assertEqual(liveness._results_from_progress([], self.CANDIDATES), [])
        self.assertEqual(liveness._results_from_progress(self.EVENTS, []), [])
        self.assertEqual(liveness._results_from_progress(None, None), [])


class TestDatabaseRowLabels(unittest.TestCase):
    """Database-only roles are keyed by a content hash, not a path."""

    HASH = "b2f8b2f87da79ce73e6db058af8d950cbfecc5507a511abdc7b07226ba3f32ed"

    def test_falls_back_to_the_raw_key_without_metadata(self):
        # The old behavior, and why the sweep printed 64-char hashes.
        self.assertEqual(liveness._styled_jd_label(self.HASH), self.HASH)

    def test_uses_metadata_when_supplied(self):
        meta = {
            self.HASH: {"title": "Lifecycle Marketing Manager", "company": "Acme Corp"}
        }
        label = liveness._styled_jd_label(self.HASH, meta)
        self.assertIn("Acme Corp", label)
        self.assertIn("Lifecycle Marketing Manager", label)
        self.assertNotIn(self.HASH, label)

    def test_missing_entry_does_not_raise(self):
        self.assertEqual(liveness._styled_jd_label(self.HASH, {}), self.HASH)


class TestSweepCheckpoint(unittest.TestCase):
    """A 30-50 minute sweep must survive an interruption.

    Before this, a Ctrl-C or a crash at minute 40 threw away every
    verdict and the next run started from zero.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = patch.object(
            liveness.profile_paths, "checkpoints_dir", return_value=self.dir.name
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_round_trip(self):
        liveness._save_checkpoint({"k1": {"result": "active"}})
        self.assertEqual(liveness._load_checkpoint()["k1"]["result"], "active")

    def test_clear_removes_it(self):
        liveness._save_checkpoint({"k1": {"result": "active"}})
        liveness._clear_checkpoint()
        self.assertEqual(liveness._load_checkpoint(), {})

    def test_missing_checkpoint_is_empty_not_an_error(self):
        self.assertEqual(liveness._load_checkpoint(), {})

    def test_clearing_a_missing_checkpoint_is_safe(self):
        liveness._clear_checkpoint()  # must not raise

    def test_corrupt_checkpoint_degrades_to_empty(self):
        # A half-written file must not block the next sweep.
        with open(liveness._checkpoint_path(), "w", encoding="utf-8") as handle:
            handle.write('{"results": {"k1": ')
        self.assertEqual(liveness._load_checkpoint(), {})

    def test_unexpected_shape_degrades_to_empty(self):
        with open(liveness._checkpoint_path(), "w", encoding="utf-8") as handle:
            handle.write('["not", "a", "dict"]')
        self.assertEqual(liveness._load_checkpoint(), {})

    def test_save_failure_never_raises(self):
        # The sweep's own work matters more than the checkpoint.
        with patch.object(
            liveness.profile_paths, "checkpoints_dir", return_value="/nonexistent/x"
        ):
            liveness._save_checkpoint({"k1": {"result": "active"}})  # must not raise
