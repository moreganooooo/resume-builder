"""Tests for scripts/stress_signals.py -- deterministic role-stress phrase detection."""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import stress_signals as ss  # noqa: E402


class TestDetect(unittest.TestCase):
    def test_empty_text_has_no_signals(self):
        self.assertEqual(ss.detect(""), [])
        self.assertEqual(ss.detect(None), [])

    def test_detects_high_call_volume(self):
        hits = ss.detect("You will handle a high volume of calls daily.")
        self.assertEqual([h.category for h in hits], ["high_call_volume"])

    def test_detects_aggressive_targets(self):
        hits = ss.detect("Reps are expected to meet or exceed quota every month.")
        self.assertEqual([h.category for h in hits], ["aggressive_targets"])

    def test_detects_on_call_rotation(self):
        hits = ss.detect("Engineers participate in an on-call rotation.")
        self.assertEqual([h.category for h in hits], ["on_call"])

    def test_detects_fire_fighting(self):
        hits = ss.detect("Ideal candidate wears many hats in a scrappy team.")
        self.assertEqual([h.category for h in hits], ["fire_fighting"])

    def test_detects_fast_paced(self):
        hits = ss.detect("We operate in a fast-paced environment.")
        self.assertEqual([h.category for h in hits], ["fast_paced"])

    def test_no_false_positive_on_unrelated_text(self):
        hits = ss.detect(
            "We build marketing campaigns and collaborate with sales on messaging."
        )
        self.assertEqual(hits, [])

    def test_negated_on_call_does_not_count(self):
        hits = ss.detect("This role has no on-call rotation.")
        self.assertEqual(hits, [])

    def test_negated_weekend_coverage_does_not_count(self):
        hits = ss.detect("No weekend coverage is required for this position.")
        self.assertEqual(hits, [])

    def test_negated_high_call_volume_does_not_count(self):
        hits = ss.detect("You will never deal with a high volume of calls here.")
        self.assertEqual(hits, [])

    def test_fast_paced_is_not_negatable(self):
        # "fast_paced" has no natural negated form in real postings, so a
        # stray "not" nearby should not suppress a genuine match.
        hits = ss.detect("This is not a slow job -- it's a fast-paced environment.")
        self.assertEqual([h.category for h in hits], ["fast_paced"])

    def test_duplicate_matches_within_one_posting_collapse(self):
        hits = ss.detect(
            "We enforce quota. Meet or exceed quota is expected. Quota, quota, quota."
        )
        self.assertEqual(len(hits), 1)

    def test_multiple_distinct_categories_all_reported(self):
        hits = ss.detect(
            "Fast-paced environment with an on-call rotation and aggressive quotas."
        )
        found = {h.category for h in hits}
        self.assertEqual(found, {"fast_paced", "on_call", "aggressive_targets"})


class TestCategories(unittest.TestCase):
    def test_returns_display_labels_not_raw_categories(self):
        labels = ss.categories("Engineers participate in an on-call rotation.")
        self.assertEqual(labels, ["On-call / after-hours availability"])

    def test_dedupes_across_multiple_matches_in_one_category(self):
        labels = ss.categories(
            "High call volume all day. This is a high-volume call queue."
        )
        self.assertEqual(labels, ["High call volume"])

    def test_empty_for_clean_text(self):
        self.assertEqual(ss.categories("A normal marketing role."), [])

    def test_order_matches_category_declaration_order(self):
        labels = ss.categories(
            "On-call rotation required. Fast-paced environment. High volume of calls."
        )
        self.assertEqual(
            labels,
            [
                "High call volume",
                "Fast-paced environment",
                "On-call / after-hours availability",
            ],
        )


if __name__ == "__main__":
    unittest.main()
