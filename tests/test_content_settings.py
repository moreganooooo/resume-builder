"""Tests for the Settings editor behind the language, travel and employment filters.

The property under test is not "does it write YAML" -- it is that a
round trip through the editor cannot change anything the user did not
touch. scan_filters.yml is hand-maintained and carries explanatory
comments plus a 400-entry title filter; an editor that rewrote the whole
document would silently discard both.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import content_settings as cs  # noqa: E402
import yaml  # noqa: E402

BASE = """\
enabled_boards:
- remoteok
location:
  city: Getzville
  radius_miles: 5
# Body-text gates. Both are exclusion-only.
languages:
- en
max_travel_percent: 10
employment_type:
- full_time
- part_time
location_filter:
  block:
  - Hybrid
"""

NO_FILTERS = """\
enabled_boards:
- remoteok
location_filter:
  block:
  - Hybrid
"""


class _TempYaml(unittest.TestCase):
    def _write(self, text):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".yml", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def _read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()


class TestReadSettings(_TempYaml):
    def test_reads_both_keys(self):
        settings = cs.read_settings(self._write(BASE))
        self.assertEqual(settings["languages"], ["en"])
        self.assertEqual(settings["max_travel_percent"], 10)

    def test_absent_keys_are_absent_not_defaulted(self):
        """An unset filter is inert. A default would silently turn it on."""
        self.assertEqual(cs.read_settings(self._write(NO_FILTERS)), {})

    def test_unreadable_file_is_empty_not_an_error(self):
        self.assertEqual(cs.read_settings("/nonexistent/scan_filters.yml"), {})


class TestDescribe(unittest.TestCase):
    def test_unset_filters_read_as_any(self):
        self.assertEqual(cs.describe({}), "languages: any; travel: any; types: any")

    def test_names_the_language_rather_than_the_code(self):
        text = cs.describe({"languages": ["en", "es"], "max_travel_percent": 25})
        self.assertIn("English", text)
        self.assertIn("Spanish", text)
        self.assertIn("25%", text)

    def test_an_unknown_code_still_renders(self):
        self.assertIn("ja", cs.describe({"languages": ["ja"]}))


class TestWriteSettings(_TempYaml):
    def test_round_trip(self):
        path = self._write(BASE)
        cs.write_settings({"languages": ["en", "fr"], "max_travel_percent": 50}, path)
        self.assertEqual(
            cs.read_settings(path),
            {"languages": ["en", "fr"], "max_travel_percent": 50},
        )

    def test_comments_and_unrelated_keys_survive(self):
        """The whole reason this rewrites in place instead of dumping."""
        path = self._write(BASE)
        cs.write_settings({"languages": ["de"], "max_travel_percent": 0}, path)
        text = self._read(path)
        self.assertIn("# Body-text gates", text)
        data = yaml.safe_load(text)
        self.assertEqual(data["enabled_boards"], ["remoteok"])
        self.assertEqual(data["location"]["radius_miles"], 5)
        self.assertEqual(data["location_filter"]["block"], ["Hybrid"])

    def test_zero_is_written_not_treated_as_unset(self):
        """0% travel is a real, strict setting -- not "no ceiling"."""
        path = self._write(BASE)
        cs.write_settings({"languages": ["en"], "max_travel_percent": 0}, path)
        self.assertEqual(cs.read_settings(path)["max_travel_percent"], 0)

    def test_dropping_a_key_returns_that_filter_to_inert(self):
        path = self._write(BASE)
        cs.write_settings({"languages": ["en"]}, path)
        settings = cs.read_settings(path)
        self.assertNotIn("max_travel_percent", settings)
        self.assertEqual(settings["languages"], ["en"])

    def test_clearing_both_leaves_the_rest_of_the_file(self):
        path = self._write(BASE)
        cs.write_settings({}, path)
        self.assertEqual(cs.read_settings(path), {})
        data = yaml.safe_load(self._read(path))
        self.assertEqual(data["enabled_boards"], ["remoteok"])

    def test_adds_keys_to_a_file_that_had_none(self):
        path = self._write(NO_FILTERS)
        cs.write_settings({"languages": ["en"], "max_travel_percent": 10}, path)
        self.assertEqual(
            cs.read_settings(path),
            {"languages": ["en"], "max_travel_percent": 10},
        )


class TestFiltersActuallyConsumeThis(_TempYaml):
    """The editor writes the shape content_filters reads.

    Asserted directly rather than assumed, because the two modules agree
    only by convention: a key renamed on one side would leave the editor
    happily writing a setting nothing acts on.
    """

    def test_written_settings_drive_the_gate(self):
        import content_filters

        path = self._write(BASE)
        cs.write_settings({"languages": ["en"], "max_travel_percent": 10}, path)
        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        passes, _ = content_filters.evaluate_content(
            "Travel up to 60% of the time", config
        )
        self.assertFalse(passes)
        passes, _ = content_filters.evaluate_content(
            "Travel up to 5% of the time", config
        )
        self.assertTrue(passes)


class TestEmploymentTypeSettings(_TempYaml):
    """The structured gate shares this editor with the two body-text ones.

    Same round-trip property: touching one key must not disturb another,
    and clearing one must return only that gate to inert.
    """

    def test_reads_the_list(self):
        path = self._write(BASE)
        self.assertEqual(
            cs.read_settings(path)["employment_type"], ["full_time", "part_time"]
        )

    def test_round_trip(self):
        path = self._write(BASE)
        cs.write_settings({"employment_type": ["contract", "temporary"]}, path)
        self.assertEqual(
            cs.read_settings(path)["employment_type"], ["contract", "temporary"]
        )

    def test_clearing_it_leaves_the_other_two_gates_alone(self):
        path = self._write(BASE)
        cs.write_settings({"languages": ["en"], "max_travel_percent": 10}, path)
        settings = cs.read_settings(path)
        self.assertNotIn("employment_type", settings)
        self.assertEqual(settings["languages"], ["en"])
        self.assertEqual(settings["max_travel_percent"], 10)

    def test_adding_it_to_a_file_that_had_none(self):
        path = self._write(NO_FILTERS)
        cs.write_settings({"employment_type": ["full_time"]}, path)
        self.assertEqual(cs.read_settings(path)["employment_type"], ["full_time"])
        self.assertEqual(
            yaml.safe_load(self._read(path))["enabled_boards"], ["remoteok"]
        )

    def test_written_settings_drive_the_scan_gate(self):
        """The point of the editor: what it writes is what the gate reads.

        Asserted end to end rather than against the dict, because the
        gate consumes the PARSED yaml -- a key written in a shape
        read_settings happens to tolerate but yaml nests differently
        would pass a dict-level test and still filter nothing.
        """
        import employment_type

        path = self._write(BASE)
        cs.write_settings({"employment_type": ["contract"]}, path)
        accepted = yaml.safe_load(self._read(path))["employment_type"]
        self.assertFalse(
            employment_type.passes_employment_filter("Full-time", accepted)[0]
        )
        self.assertTrue(
            employment_type.passes_employment_filter("Contract", accepted)[0]
        )
        self.assertTrue(employment_type.passes_employment_filter(None, accepted)[0])

    def test_describe_names_the_types(self):
        self.assertIn(
            "Part-time", cs.describe({"employment_type": ["full_time", "part_time"]})
        )
        self.assertIn("types: any", cs.describe({}))


class TestMenuWiring(unittest.TestCase):
    def test_settings_menu_offers_the_editor(self):
        import menu

        values = [
            choice.value
            for choice in menu._build_settings_upkeep_choices()
            if hasattr(choice, "value")
        ]
        self.assertIn("manage_content_filters", values)

    def test_label_degrades_rather_than_breaking_the_menu(self):
        """A malformed scan_filters.yml must not make Settings unopenable."""
        import menu

        self.assertIsInstance(menu._content_filter_label(), str)


if __name__ == "__main__":
    unittest.main()
