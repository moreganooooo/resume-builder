"""city_level_distance(): the fallback that gives a local posting a distance
when location_enricher can only resolve addresses -- without it, routine
onsite/commute lines zeroed roles a few miles from home."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

HOME = {"city": "Getzville", "state": "NY", "radius_miles": 20}


class TestCityLevelDistance(unittest.TestCase):
    def test_bare_city_resolves_to_a_distance(self):
        miles = orchestrator.city_level_distance("Buffalo, NY, US", HOME)
        self.assertIsNotNone(miles)
        self.assertTrue(8 < miles < 15, miles)

    def test_multi_hub_posting_uses_its_nearest_hub(self):
        miles = orchestrator.city_level_distance("San Francisco, CA; Buffalo, NY", HOME)
        self.assertTrue(miles < 15, miles)

    def test_unresolvable_location_is_none_not_zero(self):
        self.assertIsNone(orchestrator.city_level_distance("Remote", HOME))
        self.assertIsNone(orchestrator.city_level_distance("", HOME))

    def test_missing_home_city_is_none(self):
        self.assertIsNone(orchestrator.city_level_distance("Buffalo, NY", {}))

    def test_commute_blocker_clears_once_the_distance_is_known(self):
        ev = {
            "fit_subscores": {}, "interview_odds_subscores": {}, "practical_pursue_subscores": {},
            "hard_blockers": [{"category": "onsite_commute", "text": "Fully Onsite in Buffalo, NY."}],
            "recommendation": "Skip",
        }
        miles = orchestrator.city_level_distance("Buffalo, NY, US", HOME)
        rescored = orchestrator.rescore_evaluation_with_location(
            dict(ev), distance_miles=miles, radius_miles=20, posting_age_days=0
        )
        self.assertEqual(rescored["hard_blockers"], [])


if __name__ == "__main__":
    unittest.main()
