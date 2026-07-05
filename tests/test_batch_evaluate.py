import os
import sys
import unittest

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
