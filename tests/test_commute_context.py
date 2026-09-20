"""The evaluator is told how far a non-remote posting's office is, so it no
longer judges the candidate's commute deal-breaker blind."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import location_filter  # noqa: E402
import orchestrator  # noqa: E402


class TestCommuteContext(unittest.TestCase):
    def test_within_radius_says_the_office_is_allowed(self):
        block = orchestrator.build_commute_context(
            3.2, 5, location_filter.ONSITE, "Amherst, NY"
        )
        self.assertIn("3.2 miles", block)
        self.assertIn("WITHIN", block)
        self.assertIn("Amherst, NY", block)

    def test_outside_radius_says_so(self):
        block = orchestrator.build_commute_context(7.5, 5, location_filter.HYBRID)
        self.assertIn("OUTSIDE", block)
        self.assertNotIn("WITHIN", block)

    def test_remote_or_unknown_says_nothing(self):
        self.assertEqual(
            orchestrator.build_commute_context(2.0, 5, location_filter.REMOTE), ""
        )
        self.assertEqual(
            orchestrator.build_commute_context(None, 5, location_filter.ONSITE), ""
        )
        self.assertEqual(
            orchestrator.build_commute_context(2.0, None, location_filter.ONSITE), ""
        )

    def test_block_reaches_the_evaluator_context(self):
        engine = orchestrator.ResumeEngine.__new__(orchestrator.ResumeEngine)
        engine.kb_dir = "/nonexistent"
        engine.scoring_dir = "/nonexistent"
        context = engine.build_fit_evaluation_context(
            "A posting.", [], commute_block="=== COMMUTE X ==="
        )
        self.assertIn("=== COMMUTE X ===", context)
        self.assertLess(
            context.index("=== COMMUTE X ==="), context.index("=== JOB DESCRIPTION ===")
        )


if __name__ == "__main__":
    unittest.main()
