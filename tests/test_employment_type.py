"""Tests for the employment-type vocabulary and its scan-time gate.

The vocabulary is the risky part. Providers publish free text in at least
seven mutually incompatible spellings of "full time", and lever's field is
literally whatever the employer typed, so the mapping is asserted against
the real observed values rather than against tidy ones.
"""

import logging
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import employment_type as et  # noqa: E402


class TestObservedProviderSpellings(unittest.TestCase):
    """Every value here was seen in a real provider response."""

    def test_seven_spellings_of_full_time_agree(self):
        for raw in (
            "FullTime",  # ashby
            "Full-time",  # lever, workable
            "Full Time",  # himalayas
            "full_time",  # remotive
            ["Full-Time"],  # jobicy list-wraps
            "Full time",  # workday
            {"label": "Full-time"},  # smartrecruiters nests under a label
        ):
            with self.subTest(raw=raw):
                self.assertEqual(et.normalize_employment_type(raw), ["full_time"])

    def test_comma_joined_value_yields_both_types(self):
        """jobright emits "Full-time, Contract" for a posting offering both.

        Collapsing it to one would misrepresent the posting to a filter
        accepting only the other.
        """
        self.assertEqual(
            et.normalize_employment_type("Full-time, Contract"),
            ["full_time", "contract"],
        )

    def test_employer_authored_qualifiers_do_not_defeat_the_match(self):
        """lever's `commitment` is a free-text box, not an enum."""
        for raw in ("Full Time - Union", "Full Time - Non-Union"):
            with self.subTest(raw=raw):
                self.assertEqual(et.normalize_employment_type(raw), ["full_time"])

    def test_workplace_mode_hidden_in_the_employment_field_is_routed_away(self):
        """ "Full Time / On Site" is two facts in one field.

        Parsing the whole string as an employment type would either fail
        or, worse, silently discard the workplace half. The employment
        half must survive and the workplace half must not be mistaken for
        a type.
        """
        self.assertEqual(
            et.normalize_employment_type("Full Time / On Site"), ["full_time"]
        )
        self.assertEqual(et.normalize_employment_type("Remote"), [])

    def test_fixed_term_is_temporary_not_full_time(self):
        self.assertEqual(et.normalize_employment_type("Fixed Term"), ["temporary"])

    def test_contract_to_hire_beats_the_shorter_contract_pattern(self):
        """Ordering trap: "contract" is a substring of "contract to hire"."""
        for raw in ("Contract to Hire", "Temp-to-Perm"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    et.normalize_employment_type(raw), ["contract_to_hire"]
                )

    def test_absent_field_is_empty_not_a_guess(self):
        for raw in (None, "", [], {}):
            with self.subTest(raw=raw):
                self.assertEqual(et.normalize_employment_type(raw), [])


class TestUnmappedValuesAnnounceThemselves(unittest.TestCase):
    def setUp(self):
        et._seen_unmapped.clear()

    def test_an_unknown_value_is_logged_with_its_provider(self):
        """A silent miss becomes an "unknown" that passes the gate.

        That is the failure mode worth catching: the filter would quietly
        stop filtering as a provider's vocabulary drifts, and nothing
        would look broken.
        """
        with self.assertLogs(level=logging.WARNING) as captured:
            self.assertEqual(
                et.normalize_employment_type("Volunteer", "somebooard"), []
            )
        joined = "\n".join(captured.output)
        self.assertIn("Volunteer", joined)
        self.assertIn("somebooard", joined)

    def test_a_repeated_value_is_logged_once_per_process(self):
        """A 600-posting scan must not print the same line 600 times."""
        with self.assertLogs(level=logging.WARNING) as captured:
            for _ in range(5):
                et.normalize_employment_type("Volunteer", "b")
        self.assertEqual(len(captured.output), 1)

    def test_a_recognized_workplace_token_is_not_logged_as_unknown(self):
        """A log that cries wolf on "On Site" every scan is unread."""
        logging.getLogger().warning("anchor")  # assertLogs needs >=1 record
        with self.assertLogs(level=logging.WARNING) as captured:
            logging.getLogger().warning("anchor")
            et.normalize_employment_type("On Site", "b")
        self.assertEqual(len(captured.output), 1)


class TestGate(unittest.TestCase):
    ACCEPTED = ["full_time", "part_time", "contract", "temporary"]

    def test_inert_without_configuration(self):
        passes, _ = et.passes_employment_filter("Internship", [])
        self.assertTrue(passes)

    def test_unstated_type_is_kept(self):
        """Greenhouse publishes the field 0% of the time.

        Rejecting on absence would silently drop the largest ATS source
        in this corpus.
        """
        passes, reason = et.passes_employment_filter(None, self.ACCEPTED)
        self.assertTrue(passes)
        self.assertIn("not stated", reason)

    def test_an_excluded_type_is_rejected_with_a_reason(self):
        passes, reason = et.passes_employment_filter("Internship", self.ACCEPTED)
        self.assertFalse(passes)
        self.assertIn("internship", reason)

    def test_a_multi_type_posting_passes_on_any_accepted_type(self):
        """ "Full-time, Contract" really is available as a contract."""
        passes, _ = et.passes_employment_filter("Full-time, Contract", ["contract"])
        self.assertTrue(passes)

    def test_an_unmappable_value_is_kept_not_rejected(self):
        passes, _ = et.passes_employment_filter("Volunteer", ["full_time"])
        self.assertTrue(passes)


class TestVocabularyIsComplete(unittest.TestCase):
    def test_every_canonical_type_is_producible(self):
        """A canonical value nothing maps to is a value that never fires."""
        produced = set()
        for raw in (
            "Full-time",
            "Part-time",
            "Contract",
            "Contract to Hire",
            "Temporary",
            "Internship",
        ):
            produced.update(et.normalize_employment_type(raw))
        self.assertEqual(produced, set(et.CANONICAL))

    def test_the_settings_editor_offers_every_canonical_type(self):
        """A type the gate can reject but the editor cannot offer is
        unfixable from the UI."""
        import content_settings

        self.assertEqual(set(content_settings.EMPLOYMENT_LABELS), set(et.CANONICAL))


class TestScannerWiring(unittest.TestCase):
    """Wiring, asserted rather than assumed.

    The failure this guards against is a gate that exists, is tested, and
    is never called -- the filter would be configurable, documented, and
    completely inert.
    """

    def test_both_scanners_share_one_gate(self):
        import scan_ats
        import scan_boards

        self.assertTrue(hasattr(scan_boards, "_passes_employment_filter"))
        with open(scan_ats.__file__) as fh:
            self.assertIn("scan_boards._passes_employment_filter", fh.read())

    def test_the_gate_runs_before_the_description_is_fetched(self):
        """The practical payoff of gating on a published field.

        A posting rejected on type must not first pay for a detail fetch
        -- for ashby that is a whole extra structured-posting request.
        Ordering is the only thing that delivers it.
        """
        import scan_boards

        with open(scan_boards.__file__) as fh:
            source = fh.read()
        body = source[source.index("def process_provider") :]
        self.assertLess(
            body.index("_passes_employment_filter("),
            body.index("_fetch_posting_text(url, provider_id)"),
        )

    def test_the_gate_is_inert_without_configuration(self):
        import scan_boards

        with unittest.mock.patch.object(scan_boards, "_load_filters", return_value={}):
            self.assertTrue(
                scan_boards._passes_employment_filter("Internship", "greenhouse")
            )

    def test_the_gate_rejects_a_configured_exclusion(self):
        import scan_boards

        with unittest.mock.patch.object(
            scan_boards,
            "_load_filters",
            return_value={"employment_type": ["full_time", "part_time"]},
        ):
            self.assertFalse(
                scan_boards._passes_employment_filter("Internship", "ashby")
            )
            self.assertTrue(scan_boards._passes_employment_filter("Part-time", "ashby"))
            # Greenhouse never publishes the field. Absence is not a
            # rejection, or configuring this drops a whole provider.
            self.assertTrue(scan_boards._passes_employment_filter(None, "greenhouse"))

    def test_providers_that_publish_the_field_map_it_through(self):
        """A provider that fetches the value and discards it is the bug
        this whole feature started as."""
        import os

        providers_dir = os.path.join(
            os.path.dirname(__file__), "..", "board-scanners", "providers"
        )
        for name in (
            "ashby",
            "lever",
            "jobicy",
            "himalayas",
            "remotive",
            "smartrecruiters",
            "workable",
        ):
            with self.subTest(provider=name):
                with open(os.path.join(providers_dir, f"{name}.mjs")) as fh:
                    self.assertIn("employment_type", fh.read())


if __name__ == "__main__":
    unittest.main()
