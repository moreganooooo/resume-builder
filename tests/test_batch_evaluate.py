import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import batch_evaluate  # noqa: E402


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
    def test_successful_evaluation_gets_persisted(self, mock_engine_cls, mock_key, mock_meta, mock_save):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.0, "recommendation": "Strong pursue", "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_save.assert_called_once_with("jds/a.json", {
            "composite_score": 4.0, "recommendation": "Strong pursue", "hard_blockers": [],
        })

    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_errored_evaluation_is_not_persisted(self, mock_engine_cls, mock_key, mock_meta, mock_save):
        mock_engine_cls.return_value.evaluate_fit.return_value = {}
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_save.assert_not_called()
