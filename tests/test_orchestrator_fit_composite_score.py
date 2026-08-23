import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

PERFECT_FIT = {dim: 5 for dim in orchestrator.FIT_SUBSCORE_WEIGHTS}
PERFECT_INTERVIEW_ODDS = {dim: 5 for dim in orchestrator.INTERVIEW_ODDS_WEIGHTS}
PERFECT_PRACTICAL = {dim: 5 for dim in orchestrator.PRACTICAL_PURSUE_WEIGHTS}


class TestLayerScores(unittest.TestCase):

    def test_perfect_fit_subscores_score_5(self):
        self.assertEqual(orchestrator.compute_fit_score(PERFECT_FIT), 5.0)

    def test_perfect_interview_odds_subscores_score_5(self):
        self.assertEqual(
            orchestrator.compute_interview_odds_score(PERFECT_INTERVIEW_ODDS), 5.0
        )

    def test_perfect_practical_pursue_subscores_score_5(self):
        self.assertEqual(
            orchestrator.compute_practical_pursue_score(PERFECT_PRACTICAL), 5.0
        )

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
        self.assertEqual(
            orchestrator.fit_composite_score(5.0, 5.0, 5.0, over), expected
        )

    def test_penalty_grows_linearly_past_the_threshold(self):
        over = orchestrator.STALE_POSTING_THRESHOLD_DAYS + 7
        expected = round(5.0 - 7 * orchestrator.STALE_POSTING_PENALTY_PER_DAY, 2)
        self.assertEqual(
            orchestrator.fit_composite_score(5.0, 5.0, 5.0, over), expected
        )

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
            stale_strong,
            fresh_mediocre,
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


class TestLocationProximityScoringAndRescoring(unittest.TestCase):

    def test_calibrate_commute_quality(self):
        # 0 miles from origin -> 5.0
        self.assertEqual(orchestrator.calibrate_commute_quality(0.0, 5.0), 5.0)
        # 2.5 miles (halfway) -> 4.0
        self.assertEqual(orchestrator.calibrate_commute_quality(2.5, 5.0), 4.0)
        # 5.0 miles (boundary) -> 3.0
        self.assertEqual(orchestrator.calibrate_commute_quality(5.0, 5.0), 3.0)
        # Missing or invalid radius defaults cleanly to 5.0
        self.assertEqual(orchestrator.calibrate_commute_quality(None, 5.0), 5.0)

    def test_proximity_boost_closer_is_rated_higher(self):
        # Base score 3.5 at age 0
        base_remote = orchestrator.fit_composite_score(3.5, 3.5, 3.5, 0)
        # Ultra-local (0.0 mi) gets +0.50 boost -> 4.0
        ultra_local = orchestrator.fit_composite_score(
            3.5, 3.5, 3.5, 0, distance_miles=0.0, radius_miles=5.0
        )
        # Halfway (2.5 mi) gets +0.25 boost -> 3.75
        halfway_local = orchestrator.fit_composite_score(
            3.5, 3.5, 3.5, 0, distance_miles=2.5, radius_miles=5.0
        )
        # Boundary (5.0 mi) gets +0.00 boost -> 3.50
        boundary_local = orchestrator.fit_composite_score(
            3.5, 3.5, 3.5, 0, distance_miles=5.0, radius_miles=5.0
        )

        self.assertEqual(ultra_local, 4.00)
        self.assertEqual(halfway_local, 3.75)
        self.assertEqual(boundary_local, 3.50)
        self.assertGreater(ultra_local, halfway_local)
        self.assertGreater(halfway_local, boundary_local)
        self.assertEqual(boundary_local, base_remote)

    def test_rescore_clears_spurious_onsite_blocker_and_promotes_local_role(self):
        eval_data = {
            "fit_score": 3.3,
            "interview_odds_score": 3.65,
            "fit_subscores": {
                "functional_alignment": 4,
                "north_star_alignment": 3,
                "level_plausibility": 4,
                "work_style_sustainability": 4,
                "tools_process_overlap": 3,
            },
            "interview_odds_subscores": {
                "title_continuity": 4,
                "evidence_match": 4,
                "domain_credibility": 4,
                "recruiter_legibility": 4,
                "narrative_burden": 3,
                "funnel_friction": 3,
            },
            "practical_pursue_subscores": {
                "remote_quality": 1,
                "compensation_viability": 3,
                "growth_value": 3,
                "time_to_offer": 3,
                "company_reputation": 4,
                "cultural_signals": 4,
                "posting_legitimacy_score": 5,
            },
            "hard_blockers": [
                "Ability to Commute: Buffalo, NY 14228 (Required)",
                "Onsite/hybrid signal detected (Remote Quality scored 1/5)",
            ],
            "recommendation": "Skip",
            "why": "Application skipped due to triggered deal-breakers: Onsite/hybrid signal detected",
            "posting_age_days": 0,
        }

        rescored = orchestrator.rescore_evaluation_with_location(
            eval_data,
            distance_miles=1.8,
            radius_miles=5.0,
            workplace_mode="any",
            remote_required=False,
            posting_age_days=0,
        )

        self.assertEqual(rescored["hard_blockers"], [])
        self.assertNotEqual(rescored["recommendation"], "Skip")
        self.assertGreater(rescored["composite_score"], 3.0)
        self.assertGreaterEqual(
            rescored["practical_pursue_subscores"]["remote_quality"], 4.0
        )

    def test_rescore_preserves_genuine_dealbreaker_for_local_role(self):
        eval_data = {
            "fit_score": 2.0,
            "interview_odds_score": 2.0,
            "fit_subscores": {},
            "interview_odds_subscores": {},
            "practical_pursue_subscores": {"remote_quality": 1},
            "hard_blockers": [
                "Must possess active Optician License",
                "On-site required",
            ],
            "recommendation": "Skip",
            "posting_age_days": 0,
        }

    def test_is_spurious_commute_blocker_classification(self):
        # Spurious blockers that should be cleared for within-radius roles:
        self.assertTrue(
            orchestrator.is_spurious_commute_blocker(
                "Onsite/hybrid signal detected (Remote Quality scored 1/5)"
            )
        )
        self.assertTrue(
            orchestrator.is_spurious_commute_blocker(
                "Ability to Commute: Buffalo, NY 14228 (Required)"
            )
        )
        self.assertTrue(
            orchestrator.is_spurious_commute_blocker(
                "On-site or hybrid required, vehicle limitations, remote-only availability"
            )
        )
        self.assertTrue(
            orchestrator.is_spurious_commute_blocker(
                "Onsite required, no remote option"
            )
        )
        self.assertTrue(
            orchestrator.is_spurious_commute_blocker(
                "Hybrid schedule (in-office 3 days/week)"
            )
        )
        self.assertTrue(
            orchestrator.is_spurious_commute_blocker(
                "In-office attendance 4 days per week"
            )
        )

        # Genuine dealbreakers that must be PRESERVED even for local roles:
        self.assertFalse(
            orchestrator.is_spurious_commute_blocker(
                "Requires personal vehicle for client site visits"
            )
        )
        self.assertFalse(
            orchestrator.is_spurious_commute_blocker(
                "Hybrid — must also travel to the NYC office twice monthly"
            )
        )
        self.assertFalse(
            orchestrator.is_spurious_commute_blocker(
                "Must possess valid driver's license for field work"
            )
        )
        self.assertFalse(
            orchestrator.is_spurious_commute_blocker(
                "Daily travel throughout WNY territory required"
            )
        )
        self.assertFalse(
            orchestrator.is_spurious_commute_blocker(
                "Must possess active Optician License"
            )
        )
        self.assertFalse(
            orchestrator.is_spurious_commute_blocker("Ability to lift 50 lbs")
        )

    def test_rescore_preserves_travel_and_vehicle_dealbreakers(self):
        eval_data = {
            "fit_score": 4.0,
            "interview_odds_score": 4.0,
            "fit_subscores": {},
            "interview_odds_subscores": {},
            "practical_pursue_subscores": {"remote_quality": 1},
            "hard_blockers": [
                "Requires personal vehicle for client site visits",
                "Hybrid — must also travel to the NYC office twice monthly",
                "On-site required",
            ],
            "recommendation": "Skip",
            "posting_age_days": 0,
        }

        rescored = orchestrator.rescore_evaluation_with_location(
            eval_data,
            distance_miles=1.8,
            radius_miles=5.0,
            workplace_mode="any",
            remote_required=False,
            posting_age_days=0,
        )

        # "On-site required" is cleared, but travel/vehicle blockers remain!
        self.assertEqual(
            rescored["hard_blockers"],
            [
                "Requires personal vehicle for client site visits",
                "Hybrid — must also travel to the NYC office twice monthly",
            ],
        )
        self.assertEqual(rescored["recommendation"], "Skip")
        self.assertEqual(rescored["composite_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
