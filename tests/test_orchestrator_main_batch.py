import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestMainBatchMode(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_main_batch")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.completed_dir = os.path.join(self.tmp_dir, "completed")
        os.makedirs(self.completed_dir, exist_ok=True)

        self.good_path = os.path.join(self.tmp_dir, "good.txt")
        self.bad_path = os.path.join(self.tmp_dir, "bad.txt")
        for path in (self.good_path, self.bad_path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("a JD")

        self._real_completed_dir = orchestrator.jd_manager.COMPLETED_DIR
        orchestrator.jd_manager.COMPLETED_DIR = self.completed_dir

    def tearDown(self):
        orchestrator.jd_manager.COMPLETED_DIR = self._real_completed_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    @patch("orchestrator.jd_manager.JDTracker")
    @patch("orchestrator.jd_manager.get_pending_jds")
    @patch.object(orchestrator.ResumeEngine, "build_tailored_resume")
    def test_batch_mode_marks_completed_and_failed_and_moves_files(
        self, mock_build, mock_get_pending, mock_tracker_cls
    ):
        mock_get_pending.return_value = [self.good_path, self.bad_path]

        def build_side_effect(jd_path, master_resume, output_filename=None, job_key=None):
            if jd_path == self.good_path:
                return {"_output_paths": {"json": "j.json", "html": "h.html", "pdf": "p.pdf"}}
            return {}

        mock_build.side_effect = build_side_effect
        mock_tracker = mock_tracker_cls.return_value

        with patch.object(sys, "argv", ["orchestrator.py"]):
            orchestrator.main()

        mock_tracker.mark_completed.assert_called_once()
        mock_tracker.mark_failed.assert_called_once()
        self.assertTrue(os.path.exists(os.path.join(self.completed_dir, "good.txt")))
        self.assertFalse(os.path.exists(self.good_path))
        # A failed JD stays in place (pending) for the next run to retry.
        self.assertTrue(os.path.exists(self.bad_path))

    @patch("orchestrator.jd_manager.JDTracker")
    @patch("orchestrator.jd_manager.get_pending_jds")
    @patch.object(orchestrator.ResumeEngine, "build_tailored_resume")
    @patch("orchestrator.jd_manager.compute_job_key")
    def test_batch_mode_handles_compute_job_key_oserror(
        self, mock_compute_key, mock_build, mock_get_pending, mock_tracker_cls
    ):
        # good_path's job_key computation raises OSError (e.g. file vanished
        # or became unreadable between listing and processing); bad_path's
        # key computation succeeds normally and its build succeeds.
        def compute_key_side_effect(jd_path):
            if jd_path == self.good_path:
                raise OSError("could not read file")
            return "some-job-key"

        mock_compute_key.side_effect = compute_key_side_effect
        mock_get_pending.return_value = [self.good_path, self.bad_path]

        def build_side_effect(jd_path, master_resume, output_filename=None, job_key=None):
            return {"_output_paths": {"json": "j.json", "html": "h.html", "pdf": "p.pdf"}}

        mock_build.side_effect = build_side_effect
        mock_tracker = mock_tracker_cls.return_value

        stdout = io.StringIO()
        with patch.object(sys, "argv", ["orchestrator.py"]), \
                contextlib.redirect_stdout(stdout):
            orchestrator.main()

        # There's no real job_key for good_path (compute_job_key raised before
        # one could be produced), so main() logs the error, records a
        # sentinel "unreadable:<filename>" row via mark_failed so the tracker
        # CSV has history of it, and moves on. bad_path succeeds, so
        # mark_completed is called exactly once and mark_failed exactly once.
        mock_tracker.mark_completed.assert_called_once()
        mock_tracker.mark_failed.assert_called_once_with(
            job_key="unreadable:good.txt",
            source_file="good.txt",
            error_message="could not read file",
        )

        # good_path is left untouched (never moved, build_tailored_resume
        # never even invoked for it) since the loop continued past it.
        self.assertTrue(os.path.exists(self.good_path))
        self.assertEqual(mock_build.call_count, 1)

        # bad_path succeeded and was moved into the completed dir.
        self.assertTrue(os.path.exists(os.path.join(self.completed_dir, "bad.txt")))
        self.assertFalse(os.path.exists(self.bad_path))

        # The failed_count must have been incremented for the OSError case -
        # this is the regression this test guards against (Finding 1): the
        # summary line must report "1 failed", not "0 failed".
        self.assertIn("1 completed, 1 failed", stdout.getvalue())

    @patch("orchestrator.jd_manager.JDTracker")
    @patch("orchestrator.jd_manager.get_pending_jds")
    @patch.object(orchestrator.ResumeEngine, "build_tailored_resume")
    def test_batch_mode_handles_build_exception(
        self, mock_build, mock_get_pending, mock_tracker_cls
    ):
        # bad_path's build_tailored_resume call raises an unhandled exception
        # (not just a falsy return value); good_path still succeeds.
        mock_get_pending.return_value = [self.good_path, self.bad_path]

        def build_side_effect(jd_path, master_resume, output_filename=None, job_key=None):
            if jd_path == self.good_path:
                return {"_output_paths": {"json": "j.json", "html": "h.html", "pdf": "p.pdf"}}
            raise Exception("boom")

        mock_build.side_effect = build_side_effect
        mock_tracker = mock_tracker_cls.return_value

        with patch.object(sys, "argv", ["orchestrator.py"]):
            orchestrator.main()

        # The batch continues past the raised exception: good.txt succeeds,
        # bad.txt is marked failed via tracker.mark_failed (job_key was
        # computed fine before build_tailored_resume raised).
        mock_tracker.mark_completed.assert_called_once()
        mock_tracker.mark_failed.assert_called_once()
        self.assertTrue(os.path.exists(os.path.join(self.completed_dir, "good.txt")))
        self.assertFalse(os.path.exists(self.good_path))
        self.assertTrue(os.path.exists(self.bad_path))

    @patch("orchestrator.jd_manager.JDTracker")
    @patch.object(orchestrator.ResumeEngine, "build_tailored_resume")
    @patch("orchestrator.jd_manager.compute_job_key")
    def test_single_file_mode_exits_nonzero_on_unreadable_jd(
        self, mock_compute_key, mock_build, mock_tracker_cls
    ):
        # Regression test for Finding 1: in single-file mode
        # (`python orchestrator.py jds/missing.txt`), if compute_job_key
        # raises OSError, main() must still exit non-zero instead of
        # silently succeeding (exit 0) because failed_count never got
        # incremented.
        missing_path = os.path.join(self.tmp_dir, "missing.txt")
        mock_compute_key.side_effect = OSError("No such file or directory")

        with patch.object(sys, "argv", ["orchestrator.py", missing_path]):
            with self.assertRaises(SystemExit) as ctx:
                orchestrator.main()

        self.assertEqual(ctx.exception.code, 1)
        mock_build.assert_not_called()
        mock_tracker_cls.return_value.mark_failed.assert_called_once_with(
            job_key="unreadable:missing.txt",
            source_file="missing.txt",
            error_message="No such file or directory",
        )
        mock_tracker_cls.return_value.mark_completed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
