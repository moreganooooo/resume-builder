"""Tests for cli_art's plain-language error classifier.

The signature table is ordered, first-match-wins, so a broad needle placed
above a narrow one silently steals the narrow one's message. That already
happened once ("quota" swallowing "sustained quota issue", which flipped
the advice from "swap your API key" to "wait for the reset"), so the
collisions are pinned here rather than left to review to catch.

The failure texts below are verbatim from actually triggering each
failure, not paraphrased -- a signature that matches a paraphrase but not
the real message is worse than no signature at all, because it looks
covered.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cli_art  # noqa: E402
from gemini_client import SustainedFailureError  # noqa: E402

# Verbatim captured output, one entry per real failure mode.
PLAYWRIGHT_MISSING_BROWSER = (
    "browserType.launch: Executable doesn't exist at /Users/x/Library/Caches/"
    "ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/"
    "chrome-headless-shell\n"
    "╔════════════════════════════════════════════════════════════╗\n"
    "║ Looks like Playwright was just installed or updated.       ║\n"
    "║ Please run the following command to download new browsers: ║\n"
    "║     npx playwright install                                 ║\n"
    "╚════════════════════════════════════════════════════════════╝"
)
PLAYWRIGHT_MAC12 = "Error: Playwright does not support chromium on mac12"
NODE_MODULE_MISSING = "Error: Cannot find module 'playwright'"
CSV_RAGGED_ROW = "Error tokenizing data. C error: Expected 2 fields in line 3, saw 5"
CSV_UNCLOSED_QUOTE = "Error tokenizing data. C error: EOF inside string starting at row 1"
CSV_EMPTY = "No columns to parse from file"


class TestSignatureOrdering(unittest.TestCase):
    """Regression guards for broad-needle-shadows-narrow-needle."""

    def test_sustained_failure_is_not_shadowed_by_the_generic_quota_entry(self):
        exc = SustainedFailureError(
            "GeminiClient.generate() exhausted retries on 5 consecutive calls "
            "(model=gemini-2.5-flash) -- this looks like a sustained quota issue, "
            "not a transient blip. Swap GEMINI_API_KEY/GOOGLE_API_KEY in .env and re-run."
        )
        explanation, fix = cli_art.describe_error(exc, "tailoring your resume")
        # The specific entry names swapping the key. The generic "quota"
        # entry says to wait for a reset, which is the wrong advice here.
        self.assertIn("refused several requests in a row", explanation)
        self.assertIn("Swap GEMINI_API_KEY", fix)
        self.assertNotIn("Wait for the quota to reset", fix)

    def test_generic_quota_entry_still_matches_an_ordinary_quota_error(self):
        # The narrow entry above must not have disabled the broad one.
        explanation, fix = cli_art.describe_error(
            RuntimeError("Resource has been exhausted: quota exceeded"), "scoring bullets"
        )
        self.assertIn("usage limit", explanation)
        self.assertIn("Wait for the quota to reset", fix)


class TestSubprocessStderrClassification(unittest.TestCase):
    """Node subprocess failures arrive as a non-zero return code plus
    stderr text, never as a Python exception, so they can only be reached
    through describe_stderr()."""

    def test_missing_chromium(self):
        explanation, fix = cli_art.describe_stderr(PLAYWRIGHT_MISSING_BROWSER)
        self.assertIn("headless browser", explanation)
        self.assertIn("playwright install chromium", fix)

    def test_macos12_unsupported_gets_the_downgrade_fix_not_the_reinstall_fix(self):
        # The obvious remedy (reinstall browsers) is the wrong one here --
        # this machine needs Playwright pinned DOWN to 1.61.1. See CLAUDE.md.
        explanation, fix = cli_art.describe_stderr(PLAYWRIGHT_MAC12)
        self.assertIn("too new for this machine's macOS", explanation)
        self.assertIn("1.61.1", fix)

    def test_missing_node_module(self):
        explanation, fix = cli_art.describe_stderr(NODE_MODULE_MISSING)
        self.assertIn("Node package", explanation)
        self.assertIn("npm install", fix)

    def test_unrecognized_stderr_falls_through_to_the_generic_message(self):
        explanation, fix = cli_art.describe_stderr("Segmentation fault: 11")
        self.assertEqual(explanation, cli_art._GENERIC_EXPLANATION)
        self.assertIsNone(fix)

    def test_type_anchored_signatures_never_fire_on_bare_text(self):
        # describe_stderr() has no exception to type-check, so entries
        # anchored to a type (FileNotFoundError and friends) must be
        # skipped rather than matched loosely on their empty needle.
        explanation, _ = cli_art.describe_stderr("some file is missing somewhere")
        self.assertEqual(explanation, cli_art._GENERIC_EXPLANATION)


class TestCsvCorruption(unittest.TestCase):
    """pandas raises ParserError/EmptyDataError -- both subclass
    ValueError, so these match on message text, not type. Verified against
    both the raw text and a genuinely raised exception."""

    def test_ragged_row(self):
        explanation, fix = cli_art.describe_stderr(CSV_RAGGED_ROW)
        self.assertIn("wrong number of columns", explanation)
        self.assertIn("spreadsheet", fix)

    def test_unclosed_quote_is_distinguished_from_a_ragged_row(self):
        explanation, _ = cli_art.describe_stderr(CSV_UNCLOSED_QUOTE)
        self.assertIn("quote that's opened but never closed", explanation)

    def test_empty_file(self):
        explanation, _ = cli_art.describe_stderr(CSV_EMPTY)
        self.assertIn("completely empty", explanation)

    def test_real_pandas_exceptions_classify_the_same_way(self):
        import tempfile

        import pandas as pd

        with tempfile.TemporaryDirectory() as d:
            ragged = os.path.join(d, "ragged.csv")
            with open(ragged, "w", encoding="utf-8") as f:
                f.write('Bullet Point,Tags\n"one",a\n"two",a,b,c,d\n')
            with self.assertRaises(Exception) as ctx:
                pd.read_csv(ragged)
            explanation, _ = cli_art.describe_error(ctx.exception, "reading your bullet bank")
            self.assertIn("wrong number of columns", explanation)

            empty = os.path.join(d, "empty.csv")
            open(empty, "w", encoding="utf-8").close()
            with self.assertRaises(Exception) as ctx:
                pd.read_csv(empty)
            explanation, _ = cli_art.describe_error(ctx.exception, "reading your bullet bank")
            self.assertIn("completely empty", explanation)


if __name__ == "__main__":
    unittest.main()
