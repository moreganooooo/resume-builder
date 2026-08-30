"""Tests for scan_boards' zero-yield alarm.

The alarm exists because a provider that exits 0 and returns [] emits no
warning at all, so a dead board is indistinguishable from a quiet one.
crunchboard (feed 301-redirected to a marketing homepage) and
ycombinator (Algolia app decommissioned) both sat enabled and silent
until every provider was probed by hand.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import scan_boards  # noqa: E402


class TestZeroYieldLedger(unittest.TestCase):
    def setUp(self):
        scan_boards.reset_provider_yield()

    def test_provider_returning_nothing_every_run_is_flagged(self):
        scan_boards._record_provider_yield("crunchboard", 0)
        scan_boards._record_provider_yield("crunchboard", 0)
        self.assertEqual(scan_boards.zero_yield_providers(), ["crunchboard"])

    def test_one_empty_run_among_productive_ones_is_not_flagged(self):
        """A search_term matching nothing this week is ordinary.

        Warning per-entry would bury a genuinely dead board in noise,
        which is the failure mode this alarm exists to avoid -- not to
        reproduce.
        """
        scan_boards._record_provider_yield("greenhouse", 0)
        scan_boards._record_provider_yield("greenhouse", 12)
        self.assertEqual(scan_boards.zero_yield_providers(), [])

    def test_provider_that_never_ran_is_not_flagged(self):
        """Silence from a provider nobody asked for is not evidence."""
        self.assertEqual(scan_boards.zero_yield_providers(), [])

    def test_reset_clears_between_scans(self):
        scan_boards._record_provider_yield("dead", 0)
        scan_boards.reset_provider_yield()
        self.assertEqual(scan_boards.zero_yield_providers(), [])

    def test_multiple_dead_providers_are_reported_sorted(self):
        for pid in ("ycombinator", "crunchboard"):
            scan_boards._record_provider_yield(pid, 0)
        self.assertEqual(
            scan_boards.zero_yield_providers(), ["crunchboard", "ycombinator"]
        )


class TestZeroYieldWarning(unittest.TestCase):
    def setUp(self):
        scan_boards.reset_provider_yield()

    def test_warning_names_the_provider_and_how_to_verify(self):
        scan_boards._record_provider_yield("crunchboard", 0)
        with self.assertLogs(level="WARNING") as captured:
            scan_boards.warn_on_zero_yield()
        joined = "\n".join(captured.output)
        self.assertIn("crunchboard", joined)
        # An alarm that does not say what to do next gets ignored.
        self.assertIn("probe_provider_fields.py", joined)

    def test_no_warning_when_every_provider_produced_something(self):
        scan_boards._record_provider_yield("greenhouse", 3)
        with self.assertNoLogs(level="WARNING"):
            scan_boards.warn_on_zero_yield()


if __name__ == "__main__":
    unittest.main()
