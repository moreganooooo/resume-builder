import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import dashboard_actions  # noqa: E402

# A throwaway jobs-export path for tests. Every call site below mocks
# dashboard._export_jobs_to, so nothing is actually written here -- but a
# literal "/tmp/..." is both a bandit B108 finding and a shared path that
# would collide between concurrent runs if a mock were ever dropped.
FAKE_JOBS_PATH = os.path.join(tempfile.gettempdir(), "dashboard_actions_test_jobs.json")


class JDFileTestCase(unittest.TestCase):
    """Gives each test a real JD file on disk.

    These tests used to pass the string self.jd_path, which never
    existed. That was harmless while every action took a path blindly,
    but actions now fall back to a database lookup when the path is
    absent (see jd_source.resolved_jd), so a fictional path silently
    exercises the wrong branch. A real file keeps them testing what they
    name.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.jd_path = os.path.join(self._dir, "a.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({"job_title": "Analyst", "company_name": "Acme"}, f)
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)


class TestLiveness(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_success_refreshes_export_and_returns_zero(self, mock_verify, mock_export):
        mock_verify.return_value = {
            "active": 1,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "moved": 0,
        }
        code = dashboard_actions._liveness(self.jd_path, FAKE_JOBS_PATH)
        mock_verify.assert_called_once_with([self.jd_path])
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_error_result_returns_nonzero_without_refreshing(
        self, mock_verify, mock_export
    ):
        mock_verify.return_value = {"error": True}
        code = dashboard_actions._liveness(self.jd_path, FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestTailor(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_success_refreshes_export_and_returns_zero(self, mock_run, mock_export):
        mock_run.return_value = (1, 0)
        code = dashboard_actions._tailor(self.jd_path, FAKE_JOBS_PATH)
        mock_run.assert_called_once_with(jd_path=self.jd_path)
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_zero_completed_returns_nonzero_without_refreshing(
        self, mock_run, mock_export
    ):
        mock_run.return_value = (0, 1)
        code = dashboard_actions._tailor(self.jd_path, FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestStatus(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_valid_status_refreshes_export_and_returns_zero(
        self, mock_save, mock_export
    ):
        code = dashboard_actions._status(self.jd_path, "Applied", FAKE_JOBS_PATH)
        mock_save.assert_called_once_with(self.jd_path, "Applied")
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_invalid_status_rejected_without_saving(self, mock_save, mock_export):
        code = dashboard_actions._status(self.jd_path, "NotARealStatus", FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_save.assert_not_called()
        mock_export.assert_not_called()


class TestArchive(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.archive_jd")
    def test_success_refreshes_export_and_returns_zero(self, mock_archive, mock_export):
        mock_archive.return_value = "archived/a.json"
        code = dashboard_actions._archive(self.jd_path, FAKE_JOBS_PATH)
        mock_archive.assert_called_once_with(self.jd_path)
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.archive_jd")
    def test_failure_returns_nonzero_without_refreshing(
        self, mock_archive, mock_export
    ):
        mock_archive.side_effect = Exception("OS Error")
        code = dashboard_actions._archive(self.jd_path, FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestExport(unittest.TestCase):
    """The `export` subcommand backs main.go's startup fallback: a
    dashboard launched straight from the binary gets no -jobs-path, and
    without this would show an empty Browse & Manage Jobs screen."""

    def test_export_writes_the_jobs_file_and_succeeds(self):
        rows = [{"title": "Lifecycle Marketing Manager", "skills": []}]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jobs.json")
            with patch("picker.list_all_evaluated_jds", return_value=rows):
                code = dashboard_actions._export(out)

            self.assertEqual(code, 0)
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), rows)

    def test_export_is_routed_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jobs.json")
            argv = ["dashboard_actions.py", "export", "--jobs-path", out]
            with patch.object(sys, "argv", argv):
                with patch("picker.list_all_evaluated_jds", return_value=[]):
                    self.assertEqual(dashboard_actions.main(), 0)
            self.assertTrue(os.path.exists(out))

    def test_export_does_not_require_a_jd_path(self):
        """Unlike every other subcommand, export operates on the whole
        corpus -- requiring a positional jd_path would break main.go."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "jobs.json")
            argv = ["dashboard_actions.py", "export", "--jobs-path", out]
            with patch.object(sys, "argv", argv):
                with patch("picker.list_all_evaluated_jds", return_value=[]):
                    self.assertEqual(dashboard_actions.main(), 0)
            self.assertTrue(os.path.exists(out))


class TestScan(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("scan.run_scan")
    def test_scan_success(self, mock_scan, mock_export):
        mock_scan.return_value = {}
        code = dashboard_actions._scan(FAKE_JOBS_PATH)
        mock_scan.assert_called_once()
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("scan.run_scan")
    def test_scan_failure(self, mock_scan, mock_export):
        mock_scan.side_effect = Exception("network down")
        code = dashboard_actions._scan(FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestBatchEvaluate(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("batch_evaluate.evaluate_all_pending")
    def test_batch_evaluate_success(self, mock_eval, mock_export):
        mock_eval.return_value = []
        code = dashboard_actions._batch_evaluate(FAKE_JOBS_PATH)
        mock_eval.assert_called_once()
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("batch_evaluate.evaluate_all_pending")
    def test_batch_evaluate_failure(self, mock_eval, mock_export):
        mock_eval.side_effect = Exception("eval failed")
        code = dashboard_actions._batch_evaluate(FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestSweepStale(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("liveness.run_liveness_check")
    def test_sweep_stale_success(self, mock_sweep, mock_export):
        mock_sweep.return_value = {}
        code = dashboard_actions._sweep_stale(FAKE_JOBS_PATH)
        mock_sweep.assert_called_once()
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("liveness.run_liveness_check")
    def test_sweep_stale_failure(self, mock_sweep, mock_export):
        mock_sweep.side_effect = Exception("sweep failed")
        code = dashboard_actions._sweep_stale(FAKE_JOBS_PATH)
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestMatrix(JDFileTestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("embed_bullet_bank.embed_batch")
    @patch("numpy.load")
    @patch("os.path.exists")
    def test_matrix_file_backed_success(
        self, mock_exists, mock_load, mock_embed, mock_export
    ):
        mock_exists.return_value = True
        mock_load.return_value = np.ones((2, 768), dtype=np.float32)
        mock_embed.return_value = [
            np.ones(768, dtype=np.float32).tolist(),
            np.ones(768, dtype=np.float32).tolist(),
        ]

        jd_data = {
            "title": "Staff Engineer",
            "skills": [{"skill": "Python"}, {"skill": "Go"}],
            "_evaluation": {"composite_score": 90},
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(jd_data, f)

        code = dashboard_actions._matrix(self.jd_path, FAKE_JOBS_PATH)
        self.assertEqual(code, 0)
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)

        with open(self.jd_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        eval_data = saved.get("_evaluation", {})
        self.assertIn("skill_matrix", eval_data)
        self.assertEqual(len(eval_data["skill_matrix"]), 2)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("embed_bullet_bank.embed_batch")
    @patch("numpy.load")
    @patch("os.path.exists")
    @patch("jd_source.resolved_jd")
    def test_matrix_database_backed_success(
        self, mock_resolved, mock_exists, mock_load, mock_embed, mock_export
    ):
        mock_exists.return_value = True
        mock_load.return_value = np.ones((2, 768), dtype=np.float32)
        mock_embed.return_value = [np.ones(768, dtype=np.float32).tolist()]

        jd_data = {
            "title": "Staff Engineer",
            "skills": [{"skill": "Python"}],
            "_evaluation": {"composite_score": 85},
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(jd_data, f)

        @contextlib.contextmanager
        def fake_resolved(identifier):
            yield self.jd_path, True

        mock_resolved.side_effect = fake_resolved

        code = dashboard_actions._matrix("db_job_123", FAKE_JOBS_PATH)
        self.assertEqual(code, 0)
        mock_export.assert_called_once_with(FAKE_JOBS_PATH)

    @patch("dashboard_actions.jd_source.resolved_jd")
    def test_matrix_lookup_error_returns_nonzero(self, mock_resolved):
        mock_resolved.side_effect = LookupError("Not in database")
        code = dashboard_actions._matrix("missing_id", FAKE_JOBS_PATH)
        self.assertEqual(code, 1)

    def test_matrix_unevaluated_jd_returns_nonzero(self):
        jd_data = {"title": "Staff Engineer", "skills": [{"skill": "Python"}]}
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(jd_data, f)
        code = dashboard_actions._matrix(self.jd_path, FAKE_JOBS_PATH)
        self.assertEqual(code, 1)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("embed_bullet_bank.embed_batch")
    @patch("numpy.load")
    @patch("os.path.exists")
    def test_matrix_batches_large_skill_lists(
        self, mock_exists, mock_load, mock_embed, mock_export
    ):
        mock_exists.return_value = True
        mock_load.return_value = np.ones((2, 768), dtype=np.float32)
        mock_embed.side_effect = [
            [np.ones(768, dtype=np.float32).tolist()] * 20,
            [np.ones(768, dtype=np.float32).tolist()] * 5,
        ]

        skills = [{"skill": f"Skill_{i}"} for i in range(25)]
        jd_data = {
            "title": "Staff Engineer",
            "skills": skills,
            "_evaluation": {"composite_score": 90},
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(jd_data, f)

        code = dashboard_actions._matrix(self.jd_path, FAKE_JOBS_PATH)
        self.assertEqual(code, 0)
        self.assertEqual(mock_embed.call_count, 2)


class TestUserErrorContract(JDFileTestCase):
    """dashboard_actions.py promises jobs.go that on failure its LAST
    non-empty stderr line is "USER_ERROR: <plain sentence>" -- Go's
    parseActionError() checks only that final line and gives up at the
    first non-empty one it sees.

    That makes the contract silently breakable from either side: anything
    that prints to stderr after _user_error(), or a new failing path that
    forgets to call it, degrades the dashboard back to showing raw
    tracebacks with no test failing. These tests pin the position, not
    just the presence, of the marker."""

    @staticmethod
    def _last_nonempty(stderr_text: str) -> str:
        lines = [ln.strip() for ln in stderr_text.splitlines() if ln.strip()]
        return lines[-1] if lines else ""

    def _capture_stderr(self, fn) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            fn()
        return buf.getvalue()

    def test_invalid_status_puts_marker_on_the_last_line(self):
        err = self._capture_stderr(
            lambda: dashboard_actions._status(
                self.jd_path, "NotARealStatus", FAKE_JOBS_PATH
            )
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))
        # The raw developer-facing detail is still emitted, just earlier --
        # jobs.go keeps it behind "d for details".
        self.assertIn("NotARealStatus", err)

    @patch("dashboard_actions.jd_manager.archive_jd")
    def test_archive_failure_puts_marker_on_the_last_line(self, mock_archive):
        mock_archive.side_effect = Exception("OS Error")
        err = self._capture_stderr(
            lambda: dashboard_actions._archive(self.jd_path, FAKE_JOBS_PATH)
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))

    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_liveness_failure_puts_marker_on_the_last_line(self, mock_verify):
        mock_verify.return_value = {"error": "connection refused"}
        err = self._capture_stderr(
            lambda: dashboard_actions._liveness(self.jd_path, FAKE_JOBS_PATH)
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))
        self.assertIn("connection refused", err)

    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_tailor_failure_puts_marker_on_the_last_line(self, mock_run):
        mock_run.return_value = (0, 1)
        err = self._capture_stderr(
            lambda: dashboard_actions._tailor(self.jd_path, FAKE_JOBS_PATH)
        )
        self.assertTrue(self._last_nonempty(err).startswith("USER_ERROR:"))

    @patch("dashboard_actions.main")
    def test_uncaught_exception_is_translated_not_leaked_as_a_traceback(
        self, mock_main
    ):
        mock_main.side_effect = FileNotFoundError("/gone/master.json")
        err = self._capture_stderr(
            lambda: self.assertEqual(dashboard_actions._run(), 1)
        )
        # Traceback still present as detail...
        self.assertIn("Traceback", err)
        # ...but a plain sentence is what jobs.go will actually surface,
        # and it must not be the raw exception repr.
        last = self._last_nonempty(err)
        self.assertTrue(last.startswith("USER_ERROR:"))
        self.assertNotIn("FileNotFoundError", last)

    @patch("dashboard_actions.main")
    def test_systemexit_is_not_decorated(self, mock_main):
        # argparse's --help/usage path exits via SystemExit and has already
        # written its own output; appending a USER_ERROR line there would
        # corrupt otherwise-clean help text.
        mock_main.side_effect = SystemExit(0)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), self.assertRaises(SystemExit):
            dashboard_actions._run()
        self.assertNotIn("USER_ERROR:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestCoveragePercentile(unittest.TestCase):
    """Coverage is a rank against the bullet bank's own best-match
    distribution, not a rescaled cosine.

    Gemini embeddings sit in a narrow cone -- measured on the real
    844-bullet corpus, two RANDOM bullets had median similarity 0.727 and
    5% of unrelated pairs already cleared 0.85. Since a skill is scored by
    its MAX similarity over the whole bank, the previous affine mapping
    ((x - 0.50) / 0.35) pinned 95% of queries at 100% and never dropped
    below 63.9%, so the bar could not show a gap at all."""

    def _reference(self):
        rng = np.random.default_rng(0)
        embs = rng.normal(size=(64, 32)).astype(np.float32)
        embs /= np.linalg.norm(embs, axis=1, keepdims=True)
        return dashboard_actions._coverage_reference(embs)

    def test_reference_is_sorted_and_one_entry_per_bullet(self):
        ref = self._reference()
        self.assertEqual(len(ref), 64)
        self.assertTrue(np.all(np.diff(ref) >= 0), "reference must be sorted")

    def test_reference_excludes_self_match(self):
        """Without the diagonal masked, every bullet's best match is
        itself at 1.0 and the whole scale collapses to a constant."""
        ref = self._reference()
        self.assertLess(float(np.max(ref)), 0.999)

    def test_score_is_monotonic_in_similarity(self):
        ref = self._reference()
        scores = [
            dashboard_actions._coverage_percentile(s, ref)
            for s in (-1.0, 0.0, 0.25, 0.5, 1.0)
        ]
        self.assertEqual(scores, sorted(scores))

    def test_strong_and_weak_matches_land_at_opposite_ends(self):
        ref = self._reference()
        self.assertEqual(dashboard_actions._coverage_percentile(-1.0, ref), 0.0)
        self.assertEqual(dashboard_actions._coverage_percentile(1.0, ref), 100.0)

    def test_scale_is_not_degenerate(self):
        """The regression that motivated this: a scale where nearly every
        query pins to the ceiling reports no gaps and is useless."""
        ref = self._reference()
        scored = [dashboard_actions._coverage_percentile(float(s), ref) for s in ref]
        pinned = sum(1 for s in scored if s >= 99.99) / len(scored)
        self.assertLess(pinned, 0.10, f"{pinned:.0%} of queries pinned at 100%")
        self.assertLess(abs(float(np.median(scored)) - 50.0), 10.0)

    def test_empty_reference_scores_zero_rather_than_dividing_by_zero(self):
        self.assertEqual(dashboard_actions._coverage_percentile(0.9, np.array([])), 0.0)
