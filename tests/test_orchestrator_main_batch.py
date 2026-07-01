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


if __name__ == "__main__":
    unittest.main()
