"""Tests for the body-text scan gates: language and travel.

Both are exclusion filters on data a human never re-reviews, so the
property that matters most is the one asserted hardest here: an
undetermined answer is a PASS. A posting the filter cannot classify is
surfaced, not dropped -- the candidate can dismiss a bad row in a second,
but never sees a good one that was silently removed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import content_filters as cf  # noqa: E402

ENGLISH = (
    "We are looking for a marketing manager to join our team. You will own "
    "the content calendar and work with the design team on campaigns that "
    "reach our customers. This is a remote role and you will report to the "
    "director of marketing. We offer a competitive salary and benefits."
)
SPANISH = (
    "Estamos buscando un especialista en el manejo y la gestión de "
    "pastizales para unirse a nuestro equipo. El candidato trabajará con "
    "los ganaderos de la región y con las organizaciones locales para "
    "desarrollar los planes de conservación de las tierras."
)


class TestLanguageDetection(unittest.TestCase):
    def test_detects_english_and_spanish(self):
        self.assertEqual(cf.detect_language(ENGLISH), "en")
        self.assertEqual(cf.detect_language(SPANISH), "es")

    def test_short_text_is_undetermined(self):
        """Below the token floor the ratio is noise, not evidence."""
        self.assertIsNone(cf.detect_language("Marketing Manager. Apply now."))


class TestLanguageFilter(unittest.TestCase):
    def test_inert_without_config(self):
        for config in (None, [], {}):
            with self.subTest(config=config):
                self.assertTrue(cf.passes_language_filter(SPANISH, config)[0])

    def test_rejects_a_language_the_candidate_does_not_read(self):
        passes, reason = cf.passes_language_filter(SPANISH, ["en"])
        self.assertFalse(passes)
        self.assertIn("es", reason)

    def test_keeps_a_language_the_candidate_reads(self):
        self.assertTrue(cf.passes_language_filter(SPANISH, ["en", "es"])[0])
        self.assertTrue(cf.passes_language_filter(ENGLISH, ["en"])[0])

    def test_undetermined_is_kept(self):
        """The whole safety property, stated once."""
        passes, reason = cf.passes_language_filter("Apply today.", ["en"])
        self.assertTrue(passes)
        self.assertIn("undetermined", reason)


class TestStatedTravelPercent(unittest.TestCase):
    def test_both_orderings(self):
        self.assertEqual(cf.stated_travel_percent("Travel up to 10% annually"), 10)
        self.assertEqual(cf.stated_travel_percent("25% travel required"), 25)

    def test_largest_figure_wins(self):
        """The requirement is the total burden, not the first number named."""
        self.assertEqual(
            cf.stated_travel_percent("Travel 10% domestic and 25% international"), 25
        )

    def test_range_takes_the_top(self):
        self.assertEqual(cf.stated_travel_percent("Ability to travel 10 - 25%"), 25)
        self.assertEqual(
            cf.stated_travel_percent("Travel within region (up to ~50-60%)"), 60
        )

    def test_benefits_percentage_is_not_a_travel_figure(self):
        """Found by reading all 67 real matches in the corpus.

        "Budget intra-office travel ... 100% medical" would otherwise
        reject the posting at every possible ceiling.
        """
        self.assertIsNone(
            cf.stated_travel_percent(
                "Budget for intra-office travel. United States 100% medical, "
                "dental & vision insurance"
            )
        )

    def test_qualitative_phrases_map_to_the_conservative_end(self):
        self.assertEqual(cf.stated_travel_percent("Occasional travel to HQ"), 10)
        self.assertEqual(cf.stated_travel_percent("Frequent travel expected"), 50)
        self.assertEqual(cf.stated_travel_percent("No travel required"), 0)

    def test_a_percentage_wins_over_a_qualitative_phrase(self):
        self.assertEqual(
            cf.stated_travel_percent("Occasional travel, up to 40% at peak"), 40
        )

    def test_of_the_time_is_a_travel_figure(self):
        """The benefits veto used to swallow the commonest phrasing there is."""
        self.assertEqual(cf.stated_travel_percent("Travel up to 60% of the time"), 60)

    def test_the_benefits_veto_still_holds_for_of_our(self):
        self.assertIsNone(
            cf.stated_travel_percent(
                "Some travel. We cover 100% of our medical premium"
            )
        )

    def test_silence_is_none_not_zero(self):
        """None means unstated; 0 means the posting said "no travel"."""
        self.assertIsNone(cf.stated_travel_percent("Great team, remote first."))


class TestTravelFilter(unittest.TestCase):
    def test_inert_without_a_ceiling(self):
        self.assertTrue(cf.passes_travel_filter("50% travel", {})[0])

    def test_rejects_above_the_ceiling(self):
        passes, reason = cf.passes_travel_filter(
            "Travel up to 50%", {"max_travel_percent": 10}
        )
        self.assertFalse(passes)
        self.assertIn("50", reason)

    def test_keeps_at_or_below_the_ceiling(self):
        self.assertTrue(
            cf.passes_travel_filter("Travel up to 10%", {"max_travel_percent": 10})[0]
        )

    def test_unstated_travel_is_kept(self):
        passes, reason = cf.passes_travel_filter(ENGLISH, {"max_travel_percent": 0})
        self.assertTrue(passes)
        self.assertIn("kept for review", reason)


class TestEvaluateContent(unittest.TestCase):
    def test_language_is_reported_before_travel(self):
        """A posting she cannot read is that, not a travel mismatch."""
        passes, reason = cf.evaluate_content(
            SPANISH + " Viajar 80% del tiempo.",
            {"languages": ["en"], "max_travel_percent": 10},
        )
        self.assertFalse(passes)
        self.assertIn("es", reason)

    def test_fully_inert_with_no_config(self):
        self.assertTrue(cf.evaluate_content(SPANISH, {})[0])
        self.assertTrue(cf.evaluate_content("Travel 90%", {})[0])


class TestScannerWiring(unittest.TestCase):
    """The gate has to be REACHED, not merely correct.

    prefilter.evaluate_preflight_gate() was the obvious home for these
    filters and would have been silent: it is called only by
    batch_sweeper.py, which nothing but its own test calls. These
    assertions are what keeps that from happening again.
    """

    def test_both_scanners_share_one_gate(self):
        import scan_ats
        import scan_boards

        self.assertTrue(hasattr(scan_boards, "_passes_content_filters"))
        # scan_ats deliberately calls scan_boards' gate rather than
        # keeping its own copy, exactly as it does for location.
        with open(scan_ats.__file__) as fh:
            source = fh.read()
        self.assertIn("scan_boards._passes_content_filters", source)

    def test_gate_is_called_after_the_description_exists(self):
        """Before the description resolves there is no body to read."""
        import scan_boards

        with open(scan_boards.__file__) as fh:
            source = fh.read()
        body = source[source.index("def process_provider") :]
        self.assertLess(
            body.index("_fetch_posting_text(url, provider_id)"),
            body.index("_passes_content_filters(description)"),
        )


if __name__ == "__main__":
    unittest.main()
