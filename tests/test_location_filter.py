"""Tests for scripts/location_filter.py -- the tiered scan-time location gate."""

import os
import sys
import unittest
import unittest.mock

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import location_filter as lf  # noqa: E402

KC = {"city": "Kansas City", "state": "MO", "zip": "64111", "radius_miles": 25}


def cfg(**overrides) -> dict:
    merged = dict(KC)
    merged.update(overrides)
    return merged


class TestClassifyWorkplace(unittest.TestCase):
    def test_remote_variants(self):
        for value in ("Remote", "Remote (US)", "Work from home", "WFH", "Anywhere"):
            with self.subTest(value=value):
                self.assertEqual(lf.classify_workplace(value), lf.REMOTE)

    def test_onsite_variants(self):
        for value in ("On-site", "Onsite - Olathe, KS", "In-office", "In Person"):
            with self.subTest(value=value):
                self.assertEqual(lf.classify_workplace(value), lf.ONSITE)

    def test_hybrid_beats_remote(self):
        # Both words appear; hybrid is the truthful answer.
        self.assertEqual(lf.classify_workplace("Hybrid remote"), lf.HYBRID)
        self.assertEqual(lf.classify_workplace("Remote/Hybrid"), lf.HYBRID)

    def test_days_in_office_is_hybrid(self):
        self.assertEqual(lf.classify_workplace("3 days per week in office"), lf.HYBRID)

    def test_plain_city_is_unknown(self):
        self.assertEqual(lf.classify_workplace("Austin, TX"), lf.UNKNOWN)

    def test_structured_work_model_wins(self):
        self.assertEqual(
            lf.classify_workplace("Austin, TX", work_model="Hybrid"), lf.HYBRID
        )

    def test_is_remote_flag_used_only_as_fallback(self):
        self.assertEqual(lf.classify_workplace("Austin, TX", is_remote=True), lf.REMOTE)
        # Text that says hybrid outranks a provider's coarse boolean.
        self.assertEqual(
            lf.classify_workplace("Hybrid - Austin, TX", is_remote=True), lf.HYBRID
        )


class TestExcludedStates(unittest.TestCase):
    def test_parses_codes(self):
        self.assertEqual(
            lf.excluded_states("US Remote (Excluding CA, CO, NY)"),
            {"CA", "CO", "NY"},
        )

    def test_parses_full_names(self):
        self.assertEqual(
            lf.excluded_states("Remote, except California and New York"),
            {"CA", "NY"},
        )

    def test_no_exclusion_clause(self):
        self.assertEqual(lf.excluded_states("Austin, TX"), set())


class TestSplitHubs(unittest.TestCase):
    def test_splits_on_or(self):
        self.assertEqual(
            lf.split_hubs("Austin, TX OR Sunnyvale, CA"),
            ["Austin, TX", "Sunnyvale, CA"],
        )

    def test_comma_is_not_a_separator(self):
        # A comma delimits city from state; splitting on it would shred
        # every ordinary location string.
        self.assertEqual(lf.split_hubs("Austin, TX"), ["Austin, TX"])

    def test_parentheticals_dropped(self):
        self.assertNotIn(
            "Excluding CA", " ".join(lf.split_hubs("Remote (Excluding CA)"))
        )


class TestInternational(unittest.TestCase):
    def test_detects_countries(self):
        for value in ("London, UK", "Toronto, Canada", "Berlin, Germany", "EMEA"):
            with self.subTest(value=value):
                self.assertTrue(lf.looks_international(value))

    def test_us_locations_are_not_international(self):
        for value in ("Austin, TX", "Kansas City, MO", "Remote (US)"):
            with self.subTest(value=value):
                self.assertFalse(lf.looks_international(value))

    def test_canadian_province_codes_detected(self):
        # These look exactly like US state codes; without explicit
        # handling "Toronto, ON" passes as merely unresolvable.
        for value in ("Toronto, ON", "Vancouver, BC", "Montreal, QC"):
            with self.subTest(value=value):
                self.assertTrue(lf.looks_international(value))

    def test_us_state_codes_are_not_mistaken_for_provinces(self):
        # Guards the collision check: OR, ME, NE and friends are states.
        for value in ("Portland, OR", "Bangor, ME", "Omaha, NE", "Reno, NV"):
            with self.subTest(value=value):
                self.assertFalse(lf.looks_international(value))


class TestEvaluateLocation(unittest.TestCase):
    def test_remote_passes(self):
        verdict = lf.evaluate_location("Remote (US)", cfg())
        self.assertTrue(verdict.passes)
        self.assertEqual(verdict.workplace, lf.REMOTE)

    def test_exclusion_of_home_state_rejects_even_remote(self):
        verdict = lf.evaluate_location("US Remote (Excluding CA, MO, NY)", cfg())
        self.assertFalse(verdict.passes)
        self.assertIn("MO", verdict.reason)

    def test_exclusion_of_other_state_is_ignored(self):
        self.assertTrue(
            lf.evaluate_location("US Remote (Excluding CA, NY)", cfg()).passes
        )

    def test_nearby_onsite_passes_with_distance(self):
        verdict = lf.evaluate_location("Overland Park, KS", cfg())
        self.assertTrue(verdict.passes)
        self.assertLess(verdict.distance_miles, 25)

    def test_distant_onsite_rejected(self):
        verdict = lf.evaluate_location("Austin, TX", cfg())
        self.assertFalse(verdict.passes)
        self.assertGreater(verdict.distance_miles, 500)

    def test_compound_scored_by_nearest_hub(self):
        verdict = lf.evaluate_location("Austin, TX OR Overland Park, KS", cfg())
        self.assertTrue(verdict.passes)
        self.assertLess(verdict.distance_miles, 25)

    def test_workplace_token_does_not_block_resolution(self):
        verdict = lf.evaluate_location("Hybrid - Kansas City, MO", cfg())
        self.assertTrue(verdict.passes)
        self.assertIsNotNone(verdict.distance_miles)

    def test_international_onsite_rejected(self):
        verdict = lf.evaluate_location("London, UK", cfg())
        self.assertFalse(verdict.passes)
        self.assertEqual(verdict.reason, "international location")

    def test_unresolvable_is_kept_not_dropped(self):
        # Unknown must never be treated as far away.
        verdict = lf.evaluate_location("Greater Austin Area", cfg())
        self.assertTrue(verdict.passes)
        self.assertIsNone(verdict.distance_miles)

    def test_empty_location_passes(self):
        self.assertTrue(lf.evaluate_location("", cfg()).passes)
        self.assertTrue(lf.evaluate_location("   ", cfg()).passes)

    def test_workplace_mode_filters(self):
        remote_only = cfg(workplace_mode="remote")
        self.assertTrue(lf.evaluate_location("Remote (US)", remote_only).passes)
        self.assertFalse(
            lf.evaluate_location("Hybrid - Olathe, KS", remote_only).passes
        )

    def test_unknown_workplace_survives_mode_filter(self):
        # A bare city has no stated mode; rejecting it on mode alone
        # would discard postings whose provider simply omitted the field.
        verdict = lf.evaluate_location(
            "Overland Park, KS", cfg(workplace_mode="onsite")
        )
        self.assertTrue(verdict.passes)

    def test_no_radius_configured_passes_everything_resolvable(self):
        verdict = lf.evaluate_location(
            "Austin, TX", {"city": "Kansas City", "state": "MO"}
        )
        self.assertTrue(verdict.passes)
        self.assertIsNone(verdict.distance_miles)

    def test_distance_is_none_never_a_sentinel(self):
        verdict = lf.evaluate_location("Greater Austin Area", cfg())
        self.assertIsNone(verdict.distance_miles)


class TestOriginFromConfig(unittest.TestCase):
    def test_zip_preferred(self):
        self.assertEqual(lf.origin_from_config(cfg()), "64111")

    def test_city_state_fallback(self):
        self.assertEqual(
            lf.origin_from_config({"city": "Austin", "state": "TX"}), "Austin, TX"
        )

    def test_empty_config(self):
        self.assertEqual(lf.origin_from_config({}), "")
        self.assertEqual(lf.origin_from_config(None), "")


if __name__ == "__main__":
    unittest.main()


class TestScanBoardsDelegation(unittest.TestCase):
    """The gate both scanners share must switch behavior on config alone."""

    def setUp(self):
        import scan_boards

        self.scan_boards = scan_boards

    def _with_filters(self, filters):
        return unittest.mock.patch.object(
            self.scan_boards, "_load_filters", return_value=filters
        )

    def test_falls_back_to_keywords_without_location_block(self):
        legacy = {"location_filter": {"always_allow": ["Remote"], "block": ["Onsite"]}}
        with self._with_filters(legacy):
            self.assertTrue(self.scan_boards._passes_location_filter("Remote (US)"))
            self.assertFalse(
                self.scan_boards._passes_location_filter("Onsite - Olathe, KS")
            )
            self.assertTrue(self.scan_boards._passes_location_filter(""))

    def test_location_block_supersedes_keyword_block(self):
        # The same "Onsite" string the keyword list rejects must now pass
        # on distance -- this is the relaxation, gated on config.
        both = {
            "location_filter": {"always_allow": ["Remote"], "block": ["Onsite"]},
            "location": dict(KC),
        }
        with self._with_filters(both):
            self.assertTrue(
                self.scan_boards._passes_location_filter("Onsite - Olathe, KS")
            )
            self.assertFalse(self.scan_boards._passes_location_filter("Austin, TX"))

    def test_posting_hints_are_forwarded(self):
        with self._with_filters({"location": dict(KC, workplace_mode="remote")}):
            self.assertTrue(
                self.scan_boards._passes_location_filter("Austin, TX", is_remote=True)
            )
            self.assertFalse(
                self.scan_boards._passes_location_filter("Austin, TX", is_remote=False)
            )


class TestMultiSelectWorkplaceModes(unittest.TestCase):
    """workplace_mode accepts a list, for combinations one value cannot say."""

    def test_single_string_still_works(self):
        self.assertEqual(lf.wanted_workplaces({"workplace_mode": "remote"}), {"remote"})

    def test_any_means_no_restriction(self):
        self.assertEqual(lf.wanted_workplaces({"workplace_mode": "any"}), set())
        self.assertEqual(lf.wanted_workplaces({}), set())

    def test_list_form(self):
        self.assertEqual(
            lf.wanted_workplaces({"workplace_mode": ["remote", "onsite"]}),
            {"remote", "onsite"},
        )

    def test_any_inside_a_list_wins(self):
        # "any" alongside others is a contradiction; the permissive
        # reading is the safe one.
        self.assertEqual(
            lf.wanted_workplaces({"workplace_mode": ["remote", "any"]}), set()
        )

    def test_unknown_values_ignored(self):
        self.assertEqual(
            lf.wanted_workplaces({"workplace_mode": ["remote", "nonsense"]}),
            {"remote"},
        )

    def test_remote_or_onsite_excludes_hybrid(self):
        # The case that motivated this: willing to work remotely OR to
        # commute in, but not to be on a hybrid schedule.
        config = cfg(workplace_mode=["remote", "onsite"])
        self.assertTrue(lf.evaluate_location("Remote (US)", config).passes)
        self.assertTrue(
            lf.evaluate_location("Onsite - Overland Park, KS", config).passes
        )
        self.assertFalse(
            lf.evaluate_location("Hybrid - Overland Park, KS", config).passes
        )

    def test_unknown_workplace_survives_a_multi_select(self):
        # Same rule as the single-mode case: providers omit the field,
        # and "unknown" is not evidence of anything.
        config = cfg(workplace_mode=["remote", "onsite"])
        self.assertTrue(lf.evaluate_location("Overland Park, KS", config).passes)

    def test_rejection_reason_names_every_wanted_mode(self):
        verdict = lf.evaluate_location(
            "Hybrid - Overland Park, KS", cfg(workplace_mode=["remote", "onsite"])
        )
        self.assertIn("onsite", verdict.reason)
        self.assertIn("remote", verdict.reason)

    def test_evaluate_location_uses_enriched_address(self):
        # 62701 origin with 5 mile radius. Buffalo centroid is 11.4 mi, but Amherst point is ~1.8 mi.
        config = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 5,
        }
        enrichment = {
            "status": "resolved",
            "resolved_address": "1200 S Grand Ave E, Springfield, IL 62702",
            "resolved_zip": "62702",
            "lat": 39.772,
            "lon": -89.6843,
            "source": "jd_text_override",
        }
        verdict = lf.evaluate_location(
            "Williamsville, IL", config, _location_enrichment=enrichment
        )
        self.assertTrue(verdict.passes)
        self.assertLess(verdict.distance_miles, 3.0)

    def test_evaluate_location_reason_formatting(self):
        config = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 5,
        }
        enrichment = {
            "status": "resolved",
            "resolved_address": "1200 S Grand Ave E, Springfield, IL 62702",
            "resolved_zip": "62702",
            "lat": 39.772,
            "lon": -89.6843,
            "source": "jd_text_override",
        }
        verdict = lf.evaluate_location(
            "Williamsville, IL", config, _location_enrichment=enrichment
        )
        self.assertIn("via jd_text_override", verdict.reason)

    def test_hybrid_workplace_with_enriched_address(self):
        config = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 5,
            "workplace_mode": "hybrid",
        }
        enrichment = {
            "status": "resolved",
            "resolved_address": "Springfield, IL 62702",
            "lat": 39.74,
            "lon": -89.6333,
            "source": "osm_nominatim",
        }
        verdict = lf.evaluate_location(
            "Hybrid - Williamsville, NY", config, _location_enrichment=enrichment
        )
        self.assertTrue(verdict.passes)
        self.assertEqual(verdict.workplace, lf.HYBRID)
