"""Tests for the years_experience `direction` field (docs/hard_blockers.md's
overqualification-conflation fix): an entry tagged direction="over_qualified"
is a real recruiting signal but not a real blocker, and must never land in
experience_blockers -- the list the opt-in dashboard filter and
eval_hard_blocker.py's precision measurement both key on.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

MINIMAL_EVAL = {
    "fit_score": 3.0,
    "interview_odds_score": 3.0,
    "fit_subscores": {},
    "interview_odds_subscores": {},
    "practical_pursue_subscores": {"remote_quality": 5},
    "recommendation": "Selective pursue",
    "why": "",
    "posting_age_days": 0,
}


def _rescore(hard_blockers):
    eval_data = dict(MINIMAL_EVAL, hard_blockers=hard_blockers)
    return orchestrator.rescore_evaluation_with_location(
        eval_data,
        distance_miles=None,
        radius_miles=5.0,
        workplace_mode="any",
        remote_required=False,
        posting_age_days=0,
    )


class TestOverQualifiedIsNeverAnExperienceBlocker(unittest.TestCase):
    def test_under_qualified_years_experience_is_kept(self):
        rescored = _rescore(
            [
                {
                    "text": "8+ years of enterprise sales experience",
                    "category": "years_experience",
                    "direction": "under_qualified",
                }
            ]
        )
        self.assertEqual(len(rescored["experience_blockers"]), 1)

    def test_over_qualified_years_experience_is_dropped(self):
        rescored = _rescore(
            [
                {
                    "text": "1-3 years of experience in SDR/BDR roles",
                    "category": "years_experience",
                    "direction": "over_qualified",
                }
            ]
        )
        self.assertEqual(rescored["experience_blockers"], [])

    def test_over_qualified_entry_never_forces_a_skip_either(self):
        # years_experience is already carved out of the unconditional
        # zero-out path regardless of direction -- this just confirms the
        # over_qualified filter doesn't accidentally reroute it there.
        rescored = _rescore(
            [
                {
                    "text": "1-3 years of experience in SDR/BDR roles",
                    "category": "years_experience",
                    "direction": "over_qualified",
                }
            ]
        )
        self.assertNotEqual(rescored["recommendation"], "Skip")

    def test_degree_category_is_unaffected_by_direction_field(self):
        # degree carries no direction concept -- a stray/absent value must
        # not accidentally filter it out.
        rescored = _rescore(
            [
                {
                    "text": "Bachelor's degree required",
                    "category": "degree",
                    "direction": "n/a",
                }
            ]
        )
        self.assertEqual(len(rescored["experience_blockers"]), 1)

    def test_missing_direction_field_defaults_to_kept(self):
        # Legacy/pre-schema-change persisted evaluations have no
        # `direction` key at all -- must not be silently dropped.
        rescored = _rescore(
            [
                {
                    "text": "8+ years of enterprise sales experience",
                    "category": "years_experience",
                }
            ]
        )
        self.assertEqual(len(rescored["experience_blockers"]), 1)


if __name__ == "__main__":
    unittest.main()
