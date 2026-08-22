import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import batch_evaluate  # noqa: E402
import db  # noqa: E402
import jd_source  # noqa: E402
import profile_paths  # noqa: E402


class TestSortKey(unittest.TestCase):

    def test_higher_score_sorts_first(self):
        results = [
            {"composite_score": 3.0, "error": False},
            {"composite_score": 4.8, "error": False},
            {"composite_score": 1.2, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        scores = [r["composite_score"] for r in results]
        self.assertEqual(scores, [4.8, 3.0, 1.2])

    def test_errored_entries_always_sort_last_regardless_of_score(self):
        results = [
            {"composite_score": 1.0, "error": False},
            {"composite_score": None, "error": True},
            {"composite_score": 4.9, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        self.assertFalse(results[0]["error"])
        self.assertFalse(results[1]["error"])
        self.assertTrue(results[2]["error"])
        self.assertEqual(results[0]["composite_score"], 4.9)

    def test_errored_entry_with_missing_score_key_does_not_raise(self):
        results = [
            {"error": True},
            {"composite_score": 2.0, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        self.assertFalse(results[0]["error"])
        self.assertTrue(results[1]["error"])

    def test_errored_entry_with_none_score_does_not_raise(self):
        results = [
            {"composite_score": None, "error": True},
            {"composite_score": 3.5, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        self.assertFalse(results[0]["error"])
        self.assertTrue(results[1]["error"])


class TestEvaluateAllPendingPersistsEvaluations(unittest.TestCase):

    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_successful_evaluation_gets_persisted(
        self, mock_engine_cls, mock_key, mock_meta, mock_save
    ):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.0,
            "recommendation": "Strong pursue",
            "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_save.assert_called_once_with(
            "jds/a.json",
            {
                "composite_score": 4.0,
                "recommendation": "Strong pursue",
                "hard_blockers": [],
            },
        )

    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_errored_evaluation_is_not_persisted(
        self, mock_engine_cls, mock_key, mock_meta, mock_save
    ):
        mock_engine_cls.return_value.evaluate_fit.return_value = {}
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_save.assert_not_called()


class TestEvaluateAllPendingAutoArchivesSkip(unittest.TestCase):

    @patch("batch_evaluate.jd_manager.archive_jd", return_value="jds/archived/a.json")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_skip_recommendation_gets_archived(
        self, mock_engine_cls, mock_key, mock_meta, mock_save, mock_archive
    ):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 1.5,
            "recommendation": "Skip",
            "hard_blockers": [],
        }
        results = batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_archive.assert_called_once_with("jds/a.json")
        self.assertEqual(results[0]["source_file"], "jds/archived/a.json")

    @patch("batch_evaluate.jd_manager.archive_jd")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_non_skip_recommendation_is_not_archived(
        self, mock_engine_cls, mock_key, mock_meta, mock_save, mock_archive
    ):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.5,
            "recommendation": "Strong pursue",
            "hard_blockers": [],
        }
        results = batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_archive.assert_not_called()
        self.assertEqual(results[0]["source_file"], "jds/a.json")

    @patch("batch_evaluate.jd_manager.archive_jd", return_value="jds/archived/a.json")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_job_key_computed_before_the_file_is_moved(
        self, mock_engine_cls, mock_key, mock_meta, mock_save, mock_archive
    ):
        # compute_job_key(path) reads the file at `path` -- must be
        # called before archive_jd() moves it out from under it.
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 1.5,
            "recommendation": "Skip",
            "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_key.assert_called_once_with("jds/a.json")


class TestEvaluateAllPendingPacesCalls(unittest.TestCase):

    @patch("batch_evaluate.time.sleep")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_sleeps_between_calls_but_not_before_the_first(
        self,
        mock_engine_cls,
        mock_key,
        mock_meta,
        mock_save,
        mock_sleep,
    ):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.0,
            "recommendation": "Strong pursue",
            "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/a.json", "jds/b.json", "jds/c.json"])
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("batch_evaluate.time.sleep")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_never_sleeps_for_a_single_jd(
        self,
        mock_engine_cls,
        mock_key,
        mock_meta,
        mock_save,
        mock_sleep,
    ):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.0,
            "recommendation": "Strong pursue",
            "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_sleep.assert_not_called()


class TestEvaluateAllPendingSkipsAlreadyEvaluated(unittest.TestCase):

    @patch("batch_evaluate.time.sleep")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.jd_manager.read_evaluation")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_skips_already_evaluated_jds_by_default(
        self,
        mock_engine_cls,
        mock_read_eval,
        mock_key,
        mock_meta,
        mock_save,
        mock_sleep,
    ):
        mock_read_eval.side_effect = lambda path: {
            "jds/scored.json": {
                "composite_score": 4.0,
                "recommendation": "Strong pursue",
            },
            "jds/unscored.json": None,
        }[path]
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 3.0,
            "recommendation": "Selective pursue",
            "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/scored.json", "jds/unscored.json"])
        mock_engine_cls.return_value.evaluate_fit.assert_called_once_with(
            "jds/unscored.json"
        )

    @patch("batch_evaluate.time.sleep")
    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.jd_manager.read_evaluation")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_skip_evaluated_false_reevaluates_everything(
        self,
        mock_engine_cls,
        mock_read_eval,
        mock_key,
        mock_meta,
        mock_save,
        mock_sleep,
    ):
        mock_read_eval.side_effect = lambda path: {
            "jds/scored.json": {
                "composite_score": 4.0,
                "recommendation": "Strong pursue",
            },
            "jds/unscored.json": None,
        }[path]
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 3.0,
            "recommendation": "Selective pursue",
            "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(
            ["jds/scored.json", "jds/unscored.json"],
            skip_evaluated=False,
        )
        self.assertEqual(mock_engine_cls.return_value.evaluate_fit.call_count, 2)


class TestSplitEvaluated(unittest.TestCase):

    @patch("batch_evaluate.jd_manager.read_evaluation")
    def test_splits_into_already_evaluated_and_unevaluated(self, mock_read_eval):
        mock_read_eval.side_effect = lambda path: {
            "jds/scored.json": {
                "composite_score": 4.0,
                "recommendation": "Strong pursue",
            },
            "jds/unscored.json": None,
        }[path]
        already, unevaluated = batch_evaluate.split_evaluated(
            ["jds/scored.json", "jds/unscored.json"]
        )
        self.assertEqual(already, ["jds/scored.json"])
        self.assertEqual(unevaluated, ["jds/unscored.json"])

    @patch("batch_evaluate.jd_manager.read_evaluation", return_value=None)
    def test_all_unevaluated(self, mock_read_eval):
        already, unevaluated = batch_evaluate.split_evaluated(
            ["jds/a.json", "jds/b.json"]
        )
        self.assertEqual(already, [])
        self.assertEqual(unevaluated, ["jds/a.json", "jds/b.json"])


class TestEvaluateDatabaseOnlyJobs(unittest.TestCase):
    """A database-only job -- a board-scan row keyed by content hash, with
    no JD file -- must be evaluable. Most pending jobs are these, and the
    file-only loop counted them in the banner and then skipped them.

    The profile is redirected at a temp directory so this owns a real but
    empty data.db: the write has to actually land for the sync-back to be
    worth asserting on.
    """

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "testprofile"), exist_ok=True)
        for patcher in (
            patch.object(profile_paths, "PROFILES_DIR", tmp),
            patch.dict(os.environ, {"RESUME_PROFILE": "testprofile"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        conn = db.get_db()
        try:
            conn.execute(
                "INSERT INTO jobs (id, title, company, status, raw_text,"
                " metadata_json) VALUES (?, ?, ?, 'pending', '', ?)",
                (
                    "hash-only-row",
                    "Content Designer",
                    "Acme",
                    json.dumps({"description": "A real posting body."}),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_metadata(self) -> dict:
        conn = db.get_db()
        try:
            raw = conn.execute(
                "SELECT metadata_json FROM jobs WHERE id = 'hash-only-row'"
            ).fetchone()["metadata_json"]
        finally:
            conn.close()
        return json.loads(raw or "{}")

    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_evaluation_is_synced_back_into_the_row(self, mock_engine_cls):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.2,
            "recommendation": "Strong pursue",
        }

        results = batch_evaluate.evaluate_all_pending(
            ["hash-only-row"], skip_evaluated=False
        )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["error"])
        self.assertEqual(results[0]["composite_score"], 4.2)
        self.assertEqual(results[0]["company_name"], "Acme")
        # The temp file is gone; the score must have survived in the row.
        self.assertEqual(self._row_metadata()["_evaluation"]["composite_score"], 4.2)

    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_a_skip_archives_the_row_rather_than_moving_a_temp_file(
        self, mock_engine_cls
    ):
        """archive_jd() moves a FILE. For a database-only job that file is
        a temp one, so archiving through it would deposit a stray JD in
        jds/archived/ -- exactly the on-disk clutter jd_source exists to
        avoid. set_status() is the right disposal."""
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 1.1,
            "recommendation": "Skip",
        }

        with patch("batch_evaluate.jd_manager.archive_jd") as mock_archive:
            batch_evaluate.evaluate_all_pending(["hash-only-row"], skip_evaluated=False)

        mock_archive.assert_not_called()
        row = jd_source.lookup_job("hash-only-row")
        self.assertEqual(row["status"], "archived")


if __name__ == "__main__":
    unittest.main()
