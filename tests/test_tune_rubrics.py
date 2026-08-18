"""Unit tests for tune_rubrics.py."""

import sqlite3
import unittest
from unittest.mock import patch

from tune_rubrics import compute_optimal_weights, fetch_evaluation_outcomes


class TestTuneRubrics(unittest.TestCase):

    def test_compute_optimal_weights_default(self):
        weights = compute_optimal_weights([])
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=2)
        self.assertIn("skills_match", weights)

    def test_compute_optimal_weights_with_data(self):
        outcomes = [
            {"score": 90, "status": "interview"},
            {"score": 85, "status": "interview"},
            {"score": 75, "status": "rejected"},
            {"score": 80, "status": "applied"},
            {"score": 92, "status": "offer"},
            {"score": 70, "status": "rejected"},
        ]
        weights = compute_optimal_weights(outcomes)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=2)
        self.assertGreaterEqual(weights["skills_match"], 0.35)

    def test_fetch_evaluation_outcomes_no_db(self):
        outcomes = fetch_evaluation_outcomes("/nonexistent/data.db")
        self.assertEqual(outcomes, [])


if __name__ == "__main__":
    unittest.main()
