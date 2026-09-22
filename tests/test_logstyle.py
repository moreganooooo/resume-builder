"""Tests for scripts/logstyle.py -- the Python half of the log format."""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import logstyle  # noqa: E402

WHEN = datetime.datetime(2026, 9, 22, 14, 3, 11)


class TestLogStyle(unittest.TestCase):
    def test_shape_matches_the_go_side(self):
        """Timestamp, four-character level tag, message, then fields."""
        line = logstyle.format_record("error", "express setup failed", when=WHEN)
        self.assertEqual(line, "2026-09-22 14:03:11 ERRO express setup failed")

    def test_level_tags_are_the_librarys_own(self):
        """charmbracelet/log's own labels -- a reader greps for these."""
        self.assertEqual(
            [logstyle.LEVELS[k] for k in ("debug", "info", "warn", "error", "fatal")],
            ["DEBU", "INFO", "WARN", "ERRO", "FATA"],
        )

    def test_a_value_with_spaces_is_quoted(self):
        """A stage name is several words; unquoted it would read as fields."""
        line = logstyle.format_record(
            "warn", "msg", when=WHEN, stage="Stage 1 of 8 (ingesting)"
        )
        self.assertIn('stage="Stage 1 of 8 (ingesting)"', line)

    def test_a_simple_value_is_left_bare(self):
        line = logstyle.format_record("info", "msg", when=WHEN, profile="morgan")
        self.assertTrue(line.endswith(" profile=morgan"))

    def test_an_embedded_quote_is_escaped(self):
        line = logstyle.format_record("info", "msg", when=WHEN, note='he said "hi"')
        self.assertIn(r'note="he said \"hi\""', line)

    def test_an_unknown_level_does_not_raise(self):
        """A logging call must not break the error handler it was added to."""
        self.assertIn("INFO", logstyle.format_record("nonsense", "msg", when=WHEN))

    def test_the_traceback_is_indented_under_one_record(self):
        """One record per line is what keeps the rest of the file greppable."""
        out = logstyle.format_failure(
            "express setup failed",
            detail="Traceback:\n  File x\nValueError: nope",
            when=WHEN,
            stage="Stage 2",
        )
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("2026-09-22 14:03:11 ERRO"))
        for line in lines[1:]:
            self.assertTrue(line.startswith("    "), line)

    def test_detail_is_optional(self):
        out = logstyle.format_failure("boom", when=WHEN)
        self.assertEqual(out, "2026-09-22 14:03:11 ERRO boom\n")

    def test_every_record_ends_with_exactly_one_newline(self):
        """Appended records must not run together or drift apart."""
        out = logstyle.format_failure("boom", detail="a\nb\n\n\n", when=WHEN)
        self.assertTrue(out.endswith("b\n"))
        self.assertFalse(out.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
