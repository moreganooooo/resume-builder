import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

PERFECT_FIT = {dim: 5 for dim in orchestrator.FIT_SUBSCORE_WEIGHTS}
PERFECT_INTERVIEW_ODDS = {dim: 5 for dim in orchestrator.INTERVIEW_ODDS_WEIGHTS}
PERFECT_PRACTICAL = {dim: 5 for dim in orchestrator.PRACTICAL_PURSUE_WEIGHTS}


class TestLayerScores(unittest.TestCase):

    def test_perfect_fit_subscores_score_5(self):
        self.assertEqual(orchestrator.compute_fit_score(PERFECT_FIT), 5.0)

    def test_perfect_interview_odds_subscores_score_5(self):
        self.assertEqual(orchestrator.compute_interview_odds_score(PERFECT_INTERVIEW_ODDS), 5.0)

    def test_perfect_practical_pursue_subscores_score_5(self):
        self.assertEqual(orchestrator.compute_practical_pursue_score(PERFECT_PRACTICAL), 5.0)

    def test_missing_dimension_defaults_to_zero(self):
        self.assertEqual(orchestrator.compute_fit_score({}), 0.0)


class TestFitCompositeScoreStalePostingPenalty(unittest.TestCase):

    def test_no_posting_age_means_no_penalty(self):
        self.assertEqual(orchestrator.fit_composite_score(5.0, 5.0, 5.0, None), 5.0)

    # Derived from the constants rather than hardcoded. These previously
    # asserted literal 4.97/4.79 against a 7-day/0.03-per-day curve, so
    # retuning the curve broke them for no reason -- they are meant to pin
    # the SHAPE of the penalty (none at the threshold, linear past it),
    # not one particular tuning of it.
    def test_exactly_at_threshold_no_penalty(self):
        at = orchestrator.STALE_POSTING_THRESHOLD_DAYS
        self.assertEqual(orchestrator.fit_composite_score(5.0, 5.0, 5.0, at), 5.0)

    def test_one_day_over_threshold(self):
        over = orchestrator.STALE_POSTING_THRESHOLD_DAYS + 1
        expected = round(5.0 - orchestrator.STALE_POSTING_PENALTY_PER_DAY, 2)
        self.assertEqual(orchestrator.fit_composite_score(5.0, 5.0, 5.0, over), expected)

    def test_penalty_grows_linearly_past_the_threshold(self):
        over = orchestrator.STALE_POSTING_THRESHOLD_DAYS + 7
        expected = round(5.0 - 7 * orchestrator.STALE_POSTING_PENALTY_PER_DAY, 2)
        self.assertEqual(orchestrator.fit_composite_score(5.0, 5.0, 5.0, over), expected)

    def test_age_can_overturn_quality_within_three_weeks(self):
        """The property the curve exists for, and the one the previous
        tuning silently failed.

        Applying early is the biggest lever a candidate has, so a stale
        strong posting must eventually rank BELOW a fresh mediocre one.
        Under the old 7/0.03/0.75 curve it never did at any age -- the cap
        was small enough that a strong role bottomed out still ahead of a
        fresh weaker one, so nothing could age off the queue. This asserts
        the crossover happens at all, and within a job-hunt-relevant
        window, without pinning the exact day."""
        fresh_mediocre = orchestrator.fit_composite_score(3.4, 3.4, 3.4, 0)
        stale_strong = orchestrator.fit_composite_score(4.5, 4.0, 4.0, 21)
        self.assertLess(
            stale_strong, fresh_mediocre,
            "a 3-week-old strong posting still outranks a fresh mediocre one -- "
            "the staleness penalty is too weak or its cap is too low to matter",
        )

    def test_penalty_is_capped_at_the_max(self):
        very_old = orchestrator.fit_composite_score(5.0, 5.0, 5.0, 200)
        expected = round(5.0 - orchestrator.STALE_POSTING_MAX_PENALTY, 2)
        self.assertEqual(very_old, expected)
        # Confirms it's actually capped, not still growing linearly.
        even_older = orchestrator.fit_composite_score(5.0, 5.0, 5.0, 500)
        self.assertEqual(very_old, even_older)

    def test_score_never_goes_negative(self):
        self.assertEqual(orchestrator.fit_composite_score(0.0, 0.0, 0.0, 500), 0.0)

    def test_backward_compatible_call_with_no_age_argument(self):
        # Existing callers that never pass posting_age_days shouldn't break.
        self.assertEqual(orchestrator.fit_composite_score(5.0, 5.0, 5.0), 5.0)

    def test_blends_layer_scores_per_composite_score_weights(self):
        # fit=5, interview_odds=0, practical=0 -> only the fit weight (0.40) counts.
        self.assertEqual(
            orchestrator.fit_composite_score(5.0, 0.0, 0.0),
            round(5.0 * orchestrator.COMPOSITE_SCORE_WEIGHTS["fit_score"], 2),
        )


if __name__ == "__main__":
    unittest.main()
