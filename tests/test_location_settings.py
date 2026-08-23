"""Tests for scripts/location_settings.py -- the radius/workplace editor."""

import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import location_settings as ls  # noqa: E402
import yaml  # noqa: E402

SAMPLE = """# Vendored from career-ops/portals.yml -- this comment is load-bearing
# history that a yaml round-trip would silently delete.

location_filter:
  always_allow:
      - "Remote"
  block:
      - "Onsite"

title_filter:
  positive:
      - "Marketing"
"""


class _TempFilters(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "scan_filters.yml")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(SAMPLE)

    def read(self) -> str:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.read()


class TestReadWrite(_TempFilters):
    def test_unconfigured_reads_empty(self):
        self.assertEqual(ls.read_settings(self.path), {})

    def test_write_then_read_roundtrip(self):
        settings = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 15,
            "workplace_mode": "any",
        }
        ls.write_settings(settings, self.path)
        self.assertEqual(ls.read_settings(self.path), settings)

    def test_comments_are_preserved(self):
        # The whole reason this module edits text instead of round-tripping
        # yaml: safe_dump() would drop every comment in the file.
        ls.write_settings({"zip": "62701", "radius_miles": 25}, self.path)
        body = self.read()
        self.assertIn("Vendored from career-ops", body)
        self.assertIn("load-bearing", body)

    def test_other_blocks_are_untouched(self):
        ls.write_settings({"zip": "62701", "radius_miles": 25}, self.path)
        data = yaml.safe_load(self.read())
        self.assertEqual(data["title_filter"]["positive"], ["Marketing"])
        self.assertEqual(data["location_filter"]["block"], ["Onsite"])

    def test_rewrite_replaces_rather_than_appends(self):
        ls.write_settings({"zip": "62701", "radius_miles": 25}, self.path)
        ls.write_settings({"zip": "62701", "radius_miles": 5}, self.path)
        self.assertEqual(self.read().count("location:\n"), 1)
        self.assertEqual(ls.read_settings(self.path)["radius_miles"], 5)

    def test_leading_zero_zip_survives(self):
        # Unquoted, 01002 would load as the integer 1002.
        ls.write_settings({"zip": "01002", "radius_miles": 25}, self.path)
        self.assertEqual(ls.read_settings(self.path)["zip"], "01002")

    def test_clear_removes_block_and_keeps_the_rest(self):
        ls.write_settings({"zip": "62701", "radius_miles": 25}, self.path)
        ls.clear_settings(self.path)
        self.assertEqual(ls.read_settings(self.path), {})
        self.assertIn("Vendored from career-ops", self.read())
        self.assertIn("title_filter", self.read())

    def test_write_when_no_location_filter_anchor_exists(self):
        path = os.path.join(self.dir.name, "bare.yml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('title_filter:\n  positive:\n      - "Marketing"\n')
        ls.write_settings({"zip": "62701", "radius_miles": 10}, path)
        with open(path, "r", encoding="utf-8") as handle:
            self.assertEqual(yaml.safe_load(handle)["location"]["radius_miles"], 10)


class TestValidateOrigin(unittest.TestCase):
    def test_valid_zip(self):
        self.assertTrue(ls.validate_origin("", "", "62701")[0])

    def test_valid_city_state(self):
        self.assertTrue(ls.validate_origin("Springfield", "IL", "")[0])

    def test_unknown_zip_rejected(self):
        ok, message = ls.validate_origin("", "", "00000")
        self.assertFalse(ok)
        self.assertIn("00000", message)

    def test_nothing_entered_rejected(self):
        ok, message = ls.validate_origin("", "", "")
        self.assertFalse(ok)
        self.assertIn("ZIP", message)

    def test_unresolvable_city_rejected(self):
        # Rejected at entry rather than silently disabling distance
        # checks later, which would look like the filter not working.
        self.assertFalse(ls.validate_origin("Nowheresville", "NY", "")[0])


class TestDescribe(unittest.TestCase):
    def test_unconfigured(self):
        self.assertIn("not configured", ls.describe({}))

    def test_radius_summary(self):
        text = ls.describe(
            {"zip": "62701", "radius_miles": 15, "workplace_mode": "any"}
        )
        self.assertIn("62701", text)
        self.assertIn("15 mi", text)

    def test_remote_only_omits_radius(self):
        text = ls.describe(
            {"zip": "62701", "radius_miles": 15, "workplace_mode": "remote"}
        )
        self.assertIn("remote only", text)
        self.assertNotIn("15 mi", text)


class TestRadiusChoices(unittest.TestCase):
    def test_range_is_five_to_twenty_five(self):
        self.assertEqual(ls.RADIUS_CHOICES, (5, 10, 15, 20, 25))


if __name__ == "__main__":
    unittest.main()


class TestMultiSelectRendering(_TempFilters):
    """A list of modes must survive the YAML round-trip."""

    def test_list_renders_and_reads_back(self):
        ls.write_settings(
            {
                "zip": "62701",
                "radius_miles": 25,
                "workplace_mode": ["remote", "onsite"],
            },
            self.path,
        )
        self.assertEqual(
            sorted(ls.read_settings(self.path)["workplace_mode"]), ["onsite", "remote"]
        )

    def test_single_item_list_renders_as_a_plain_string(self):
        ls.write_settings(
            {"zip": "62701", "radius_miles": 25, "workplace_mode": ["remote"]},
            self.path,
        )
        self.assertEqual(ls.read_settings(self.path)["workplace_mode"], "remote")

    def test_empty_list_falls_back_to_any(self):
        ls.write_settings(
            {"zip": "62701", "radius_miles": 25, "workplace_mode": []}, self.path
        )
        self.assertEqual(ls.read_settings(self.path)["workplace_mode"], "any")

    def test_describe_joins_a_combination(self):
        text = ls.describe(
            {"zip": "62701", "radius_miles": 25, "workplace_mode": ["remote", "onsite"]}
        )
        self.assertIn("onsite+remote", text)

    def test_selectable_workplaces_excludes_any(self):
        # "any" is what selecting all three means, not a fourth checkbox
        # that could be ticked alongside them and contradict them.
        values = [v for v, _ in ls.SELECTABLE_WORKPLACES]
        self.assertEqual(values, ["remote", "hybrid", "onsite"])
