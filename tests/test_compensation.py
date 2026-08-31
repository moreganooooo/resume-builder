"""Tests for the pay and weekly-hours gates.

The interesting cases here are all false positives. Both parsers were
built after a measured run against the real corpus found that the naive
version of each read something that was not pay (a benefit stipend) or
not a schedule ("respond within 24 hours"), so most of what follows
pins those specific failures rather than the happy path.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import compensation  # noqa: E402
import content_settings  # noqa: E402
import work_hours  # noqa: E402


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestParseCompensation(unittest.TestCase):
    def test_reads_an_annual_range(self):
        parsed = compensation.parse_compensation(
            "The salary range for this role is $80,000 - $95,000 per year."
        )
        self.assertEqual(parsed["min"], 80000)
        self.assertEqual(parsed["max"], 95000)
        self.assertEqual(parsed["period"], "annual")
        self.assertEqual(parsed["annualized_max"], 95000)

    def test_range_wins_over_single_figure(self):
        # The single-figure pattern would match "$80,000" alone and report
        # an $80k maximum, throwing away the top of the band the floor
        # comparison depends on.
        parsed = compensation.parse_compensation("Pay range: $80,000 to $95,000")
        self.assertEqual(parsed["max"], 95000)

    def test_shared_k_suffix_applies_to_both_bounds(self):
        # "$80 - $95K" read literally is an $80/hr-to-$95k range, which is
        # nonsense; the employer stated the suffix once for both.
        parsed = compensation.parse_compensation("Base pay range $80 - $95K annually")
        self.assertEqual(parsed["min"], 80000)
        self.assertEqual(parsed["max"], 95000)

    def test_hourly_rate_is_annualized(self):
        parsed = compensation.parse_compensation("Compensation: $22.50 per hour")
        self.assertEqual(parsed["period"], "hourly")
        self.assertEqual(parsed["annualized_max"], 22.50 * compensation.ANNUAL_HOURS)

    def test_nearest_period_word_wins_not_the_first_one(self):
        # Measured bug: the +/-60 char window reaches a neighbouring
        # sentence, so a posting stating both a yearly salary and a weekly
        # hour count had both cues in range. List order read the salary as
        # weekly and annualized $95,000 to $4.9M.
        parsed = compensation.parse_compensation(
            "The salary range is $80,000 - $95,000 per year. "
            "We need 20-25 hours per week."
        )
        self.assertEqual(parsed["period"], "annual")
        self.assertEqual(parsed["annualized_max"], 95000)


class TestBenefitFiguresAreNotPay(unittest.TestCase):
    """Every one of these was a real false positive on the live corpus.

    Taking the first dollar figure in a body rejected 99 postings at a
    $40k floor, and essentially all of them were perks.
    """

    def test_monthly_internet_stipend(self):
        self.assertIsNone(
            compensation.parse_compensation(
                "We offer a $50 monthly stipend to help cover internet."
            )
        )

    def test_professional_development_stipend(self):
        self.assertIsNone(
            compensation.parse_compensation(
                "Professional development stipend of $2,000 USD per year."
            )
        )

    def test_travel_allowance(self):
        self.assertIsNone(
            compensation.parse_compensation(
                "You'll get a $4,000 annual travel stipend to offset costs."
            )
        )

    def test_home_office_budget(self):
        self.assertIsNone(
            compensation.parse_compensation(
                "A $1,500 home office budget is provided on day one."
            )
        )

    def test_money_with_no_pay_language_at_all_is_ignored(self):
        self.assertIsNone(
            compensation.parse_compensation("We raised $40,000,000 in Series B.")
        )

    def test_implausibly_small_annual_figure_is_rejected(self):
        # Guards the case where a benefit sits near real pay language.
        parsed = compensation.parse_compensation("Annual compensation of $1,200.")
        self.assertIsNone(parsed)


class TestStructuredCompensation(unittest.TestCase):
    def test_min_max_interval_object(self):
        parsed = compensation.normalize_structured(
            {"min": 45, "max": 60, "interval": "hour"}
        )
        self.assertEqual(parsed["period"], "hourly")
        self.assertEqual(parsed["annualized_max"], 60 * compensation.ANNUAL_HOURS)

    def test_provider_period_vocabularies_normalize(self):
        for raw in ("YEAR", "yearly", "per_year", "ANNUM", "annual"):
            parsed = compensation.normalize_structured({"min": 90000, "interval": raw})
            self.assertEqual(parsed["period"], "annual", raw)

    def test_free_text_field_needs_no_pay_anchor(self):
        # A provider's salary FIELD is self-evidently pay; ashby's tier
        # summary carries no sentence at all. Requiring an anchor here
        # would reject every structured free-text field.
        parsed = compensation.normalize_structured("$100K - $130K")
        self.assertEqual(parsed["annualized_max"], 130000)

    def test_range_renders_readably_not_as_raw_floats(self):
        parsed = compensation.normalize_structured(
            {"min": 100000, "max": 130000, "interval": "year"}
        )
        self.assertEqual(parsed["text"], "$100,000-$130,000/yr")

    def test_empty_and_vague_values_are_not_pay(self):
        for value in ("", None, "competitive", "DOE"):
            self.assertIsNone(compensation.normalize_structured(value), value)


class TestEvaluateCompensation(unittest.TestCase):
    FLOORS = {"annual_floor": 40000, "hourly_floor": 20}

    def test_inert_without_a_configured_floor(self):
        passes, reason = compensation.evaluate_compensation("$5 per hour", {})
        self.assertTrue(passes)
        self.assertEqual(reason, "")

    def test_unstated_pay_is_kept(self):
        passes, reason = compensation.evaluate_compensation(
            "No pay information here at all.", self.FLOORS
        )
        self.assertTrue(passes)
        self.assertIn("not stated", reason)

    def test_unstated_pay_is_dropped_when_require_stated(self):
        passes, _ = compensation.evaluate_compensation(
            "No pay information here.", {**self.FLOORS, "require_stated": True}
        )
        self.assertFalse(passes)

    def test_below_floor_is_rejected(self):
        passes, reason = compensation.evaluate_compensation(
            "This position pays $15 an hour.", self.FLOORS
        )
        self.assertFalse(passes)
        self.assertIn("below", reason)

    def test_compares_against_the_max_not_the_min(self):
        # A $30-95K band clears a $40K floor and is worth seeing.
        passes, _ = compensation.evaluate_compensation(
            "Salary range: $30,000 - $95,000 per year.", self.FLOORS
        )
        self.assertTrue(passes)

    def test_structured_data_wins_over_prose(self):
        passes, _ = compensation.evaluate_compensation(
            "The salary range is $200,000 per year.",
            self.FLOORS,
            {"min": 10000, "max": 12000, "interval": "year"},
        )
        self.assertFalse(passes)

    def test_lower_of_the_two_floors_applies(self):
        # $20/hr annualizes to $41,600, above the $40,000 floor. A user
        # who wrote both means one bar, so the looser reading wins rather
        # than rejecting on the rounding difference between them.
        self.assertEqual(compensation.floor_to_annual(self.FLOORS), 40000)

    def test_unclear_period_is_kept_for_review(self):
        passes, reason = compensation.evaluate_compensation(
            "Compensation is $750.", self.FLOORS
        )
        self.assertTrue(passes)
        self.assertIn("unclear", reason)


class TestParseHours(unittest.TestCase):
    def test_range(self):
        parsed = work_hours.parse_hours("We ask for 10-20 hours per week.")
        self.assertEqual((parsed["min"], parsed["max"]), (10, 20))

    def test_en_dash_range(self):
        # Live in the corpus with a true en dash. The ASCII-hyphen-only
        # pattern read this as a flat 25.
        parsed = work_hours.parse_hours("20–25 hours per week")
        self.assertEqual((parsed["min"], parsed["max"]), (20, 25))

    def test_single_figure(self):
        parsed = work_hours.parse_hours("This role is 20 hours a week.")
        self.assertEqual((parsed["min"], parsed["max"]), (20, 20))

    def test_abbreviations_and_slash_form(self):
        for text in ("30 hrs per week", "24 hours/week", "35 hours weekly"):
            self.assertIsNotNone(work_hours.parse_hours(text), text)

    def test_open_ended_bounds_stay_open(self):
        # "up to 25 hours" states a ceiling and nothing about the floor.
        # Filling one in would invent a fact the posting did not state.
        low = work_hours.parse_hours("Commitment of at least 20 hours per week")
        self.assertEqual((low["min"], low["max"]), (20, None))
        high = work_hours.parse_hours("up to 25 hours a week")
        self.assertEqual((high["min"], high["max"]), (None, 25))


class TestHoursFalsePositives(unittest.TestCase):
    """ "24 hours" is nearly always a duration, not a schedule."""

    def test_response_time_promise(self):
        self.assertIsNone(
            work_hours.parse_hours("We respond to all applicants within 24 hours.")
        )

    def test_notice_period(self):
        self.assertIsNone(work_hours.parse_hours("48 hours notice is required."))

    def test_pto_accrual(self):
        self.assertIsNone(work_hours.parse_hours("You accrue 40 hours of PTO."))

    def test_hours_of_operation(self):
        self.assertIsNone(work_hours.parse_hours("Our hours of operation are 9-5."))

    def test_implausible_week_is_rejected(self):
        self.assertIsNone(work_hours.parse_hours("99 hours per week"))


class TestEvaluateHours(unittest.TestCase):
    def test_inert_without_configuration(self):
        passes, reason = work_hours.evaluate_hours("5 hours per week", {})
        self.assertTrue(passes)
        self.assertEqual(reason, "")

    def test_unstated_hours_are_kept(self):
        passes, reason = work_hours.evaluate_hours(
            "No schedule mentioned.", {"min_hours_per_week": 20}
        )
        self.assertTrue(passes)
        self.assertIn("not stated", reason)

    def test_too_few_hours_is_rejected(self):
        passes, _ = work_hours.evaluate_hours(
            "We need 5-10 hours per week", {"min_hours_per_week": 20}
        )
        self.assertFalse(passes)

    def test_too_many_hours_is_rejected(self):
        passes, _ = work_hours.evaluate_hours(
            "This role is 40 hours per week", {"max_hours_per_week": 25}
        )
        self.assertFalse(passes)

    def test_overlap_passes_rather_than_containment(self):
        # A posting offering 10-30 hours satisfies someone wanting 20-40,
        # because 20-30 works for both. Requiring containment would reject
        # every flexible role, which is most part-time postings.
        passes, _ = work_hours.evaluate_hours(
            "10-30 hours per week",
            {"min_hours_per_week": 20, "max_hours_per_week": 40},
        )
        self.assertTrue(passes)

    def test_open_bound_cannot_conflict_on_that_side(self):
        passes, _ = work_hours.evaluate_hours(
            "at least 20 hours per week", {"max_hours_per_week": 25}
        )
        self.assertTrue(passes)


class TestScannerWiring(unittest.TestCase):
    """Both scanners must share one gate, as the location one does."""

    def test_both_scanners_route_through_the_same_functions(self):
        here = os.path.join(os.path.dirname(__file__), "..", "scripts")
        boards = _read(os.path.join(here, "scan_boards.py"))
        ats = _read(os.path.join(here, "scan_ats.py"))
        self.assertIn("def _passes_compensation_filter", boards)
        self.assertIn("def _passes_hours_filter", boards)
        self.assertIn("scan_boards._passes_compensation_filter", ats)
        self.assertIn("scan_boards._passes_hours_filter", ats)

    def test_providers_pass_their_pay_field_through(self):
        root = os.path.join(
            os.path.dirname(__file__), "..", "board-scanners", "providers"
        )
        for name in ("ashby", "lever", "jobicy", "himalayas", "remotive", "workable"):
            body = _read(os.path.join(root, f"{name}.mjs"))
            self.assertIn("compensation", body, name)


class TestCompensationSettings(unittest.TestCase):
    def test_round_trip_preserves_comments_and_other_keys(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scan_filters.yml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# a comment worth keeping\nlanguages:\n- en\n")
            content_settings.write_settings(
                {
                    "languages": ["en"],
                    "compensation": {"annual_floor": 40000, "hourly_floor": 20},
                },
                path,
            )
            written = _read(path)
            self.assertIn("# a comment worth keeping", written)

            read_back = content_settings.read_settings(path)
            self.assertEqual(read_back["compensation"]["annual_floor"], 40000)
            self.assertEqual(read_back["compensation"]["hourly_floor"], 20)

            # Clearing removes the block rather than leaving an empty key.
            content_settings.write_settings({"languages": ["en"]}, path)
            self.assertNotIn("compensation:", _read(path))

    def test_booleans_render_as_yaml_not_python(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scan_filters.yml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("languages:\n- en\n")
            content_settings.write_settings(
                {"compensation": {"annual_floor": 40000, "require_stated": True}}, path
            )
            self.assertIn("require_stated: true", _read(path))
            self.assertTrue(
                content_settings.read_settings(path)["compensation"]["require_stated"]
            )

    def test_settings_keys_are_ones_the_gates_actually_read(self):
        # A key the editor can write but no gate reads is a setting that
        # silently does nothing.
        scripts = os.path.join(os.path.dirname(__file__), "..", "scripts")
        readers = _read(os.path.join(scripts, "work_hours.py")) + _read(
            os.path.join(scripts, "compensation.py")
        )
        for key in content_settings._COMPENSATION_KEYS:
            self.assertIn(f'"{key}"', readers, key)

    def test_money_input_accepts_how_people_type_it(self):
        parse = content_settings._parse_money
        self.assertEqual(parse("$40,000"), 40000)
        self.assertEqual(parse("40000"), 40000)
        self.assertEqual(parse("40k"), 40000)
        self.assertEqual(parse("20"), 20)
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("lots"))

    def test_describe_reports_the_floor(self):
        line = content_settings.describe(
            {"compensation": {"annual_floor": 40000, "hourly_floor": 20}}
        )
        self.assertIn("$40,000/yr", line)
        self.assertIn("$20/hr", line)


if __name__ == "__main__":
    unittest.main()


class TestCapabilityGapsArePersisted(unittest.TestCase):
    """The evaluation writer is an allowlist, and it lost this field.

    CapabilityEvaluationSchema has always required `capability_gaps` and
    orchestrator has always assembled it, but jd_manager.save_evaluation
    copies a fixed set of keys -- so the value was produced on every
    evaluation and discarded on every save. Measured 2026-08-31: 0 of
    1,138 evaluated JDs on disk carried it.
    """

    def test_save_evaluation_keeps_capability_gaps(self):
        import json
        import tempfile

        import jd_manager

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "jd.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"job_title": "Copywriter"}, handle)

            jd_manager.save_evaluation(
                path,
                {
                    "composite_score": 7.5,
                    "capability_gaps": ["No agency-side experience shown"],
                },
            )
            saved = jd_manager.read_evaluation(path)
            self.assertEqual(
                saved["capability_gaps"], ["No agency-side experience shown"]
            )

    def test_every_schema_field_has_a_place_to_land(self):
        # The allowlist is the trap: a field added to the schema and to
        # orchestrator still vanishes unless it is named in the writer.
        import schemas

        writer = _read(
            os.path.join(os.path.dirname(__file__), "..", "scripts", "jd_manager.py")
        )
        for field in schemas.CapabilityEvaluationSchema.model_fields:
            self.assertIn(f'"{field}"', writer, field)
