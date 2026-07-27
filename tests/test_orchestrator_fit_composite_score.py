import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

PERFECT_SCORES = {dim: 5 for dim in orchestrator.FIT_DIMENSION_WEIGHTS}


class TestFitCompositeScoreStalePostingPenalty(unittest.TestCase):

    def test_no_posting_age_means_no_penalty(self):
        self.assertEqual(orchestrator.fit_composite_score(PERFECT_SCORES, None), 5.0)

    def test_exactly_at_threshold_no_penalty(self):
        self.assertEqual(orchestrator.fit_composite_score(PERFECT_SCORES, 7), 5.0)

    def test_one_day_over_threshold(self):
        self.assertEqual(orchestrator.fit_composite_score(PERFECT_SCORES, 8), 4.97)

    def test_a_week_over_threshold(self):
        self.assertEqual(orchestrator.fit_composite_score(PERFECT_SCORES, 14), 4.79)

    def test_penalty_is_capped_at_the_max(self):
        very_old = orchestrator.fit_composite_score(PERFECT_SCORES, 200)
        expected = round(5.0 - orchestrator.STALE_POSTING_MAX_PENALTY, 2)
        self.assertEqual(very_old, expected)
        # Confirms it's actually capped, not still growing linearly.
        even_older = orchestrator.fit_composite_score(PERFECT_SCORES, 500)
        self.assertEqual(very_old, even_older)

    def test_score_never_goes_negative(self):
        zero_scores = {dim: 0 for dim in orchestrator.FIT_DIMENSION_WEIGHTS}
        self.assertEqual(orchestrator.fit_composite_score(zero_scores, 500), 0.0)

    def test_backward_compatible_call_with_no_age_argument(self):
        # Existing callers that never pass posting_age_days shouldn't break.
        self.assertEqual(orchestrator.fit_composite_score(PERFECT_SCORES), 5.0)


if __name__ == "__main__":
    unittest.main()
