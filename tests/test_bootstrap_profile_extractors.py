import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_extractors  # noqa: E402


class TestExtractContactInfo(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_contact_fields(self, mock_generate):
        mock_generate.return_value = (
            '{"full_name": "Jamie Rivera", "email": "jamie@example.com", '
            '"phone": "555-0100", "location": "Austin, TX", '
            '"linkedin_url": "linkedin.com/in/jamierivera", "portfolio_url": null}',
            {},
        )
        info = bootstrap_extractors.extract_contact_info(text="fake resume header text")
        self.assertEqual(info.full_name, "Jamie Rivera")
        self.assertEqual(info.email, "jamie@example.com")
        self.assertIsNone(info.portfolio_url)

    def test_requires_exactly_one_of_text_or_upload_path(self):
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_contact_info()
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_contact_info(text="a", upload_path="b")

    def test_dry_run_returns_blank_contact_info(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            info = bootstrap_extractors.extract_contact_info(text="some text", dry_run=True)
            mock_generate.assert_not_called()
            self.assertIsNone(info.full_name)


class TestExtractRecommendationQuote(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_quote_and_attribution(self, mock_generate):
        mock_generate.return_value = (
            '{"name": "Alex Chen", "title": "VP Marketing", '
            '"quote": "One of the strongest writers I have worked with."}',
            {},
        )
        quote = bootstrap_extractors.extract_recommendation_quote(text="fake letter text")
        self.assertEqual(quote.name, "Alex Chen")
        self.assertEqual(quote.title, "VP Marketing")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_none_when_no_quote_found(self, mock_generate):
        mock_generate.return_value = ('{"name": null, "title": null, "quote": null}', {})
        quote = bootstrap_extractors.extract_recommendation_quote(text="not actually a letter")
        self.assertIsNone(quote)

    def test_dry_run_returns_none(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            quote = bootstrap_extractors.extract_recommendation_quote(text="some text", dry_run=True)
            mock_generate.assert_not_called()
            self.assertIsNone(quote)


class TestSuggestSecondaryRoles(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_suggested_roles(self, mock_generate):
        mock_generate.return_value = (
            '{"secondary_roles": ["Customer Education Specialist", "Customer Adoption Specialist"]}',
            {},
        )
        roles = bootstrap_extractors.suggest_secondary_roles(
            ["Marketing Manager"], "Led onboarding programs and campaign automation."
        )
        self.assertEqual(roles, ["Customer Education Specialist", "Customer Adoption Specialist"])

    def test_dry_run_returns_empty_list(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            roles = bootstrap_extractors.suggest_secondary_roles(["Marketing Manager"], "text", dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(roles, [])


class TestDraftBackgroundGuide(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_generated_prose(self, mock_generate):
        mock_generate.return_value = ("A marketer who blends writing and systems thinking.", {})
        draft = bootstrap_extractors.draft_background_guide(["resume summary text", "rec letter text"])
        self.assertEqual(draft, "A marketer who blends writing and systems thinking.")

    def test_dry_run_returns_empty_string(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            draft = bootstrap_extractors.draft_background_guide(["text"], dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(draft, "")


class TestExtractLedgerEntries(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_metrics_tools_projects(self, mock_generate):
        mock_generate.return_value = (
            '{"metrics": [{"label": "Reply rate", "value": "22%", "employer": "Acme Corp"}], '
            '"tools": [{"name": "Salesforce", "employer": "Acme Corp"}, {"name": "Outreach.io", "employer": "Acme Corp"}], '
            '"projects": [{"name": "Content Committee", "employer": "Acme Corp"}]}',
            {},
        )
        result = bootstrap_extractors.extract_ledger_entries("[Acme Corp] Grew reply rate to 22% using Outreach.io.")
        self.assertEqual(len(result.metrics), 1)
        self.assertEqual(result.metrics[0].value, "22%")
        self.assertEqual(result.metrics[0].employer, "Acme Corp")
        self.assertIn("Salesforce", [t.name for t in result.tools])
        self.assertIn("Content Committee", [p.name for p in result.projects])

    def test_dry_run_returns_empty_extraction(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_ledger_entries("some achievements", dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(result.metrics, [])
            self.assertEqual(result.tools, [])
            self.assertEqual(result.projects, [])


class TestChunkLines(unittest.TestCase):

    def test_short_text_is_a_single_chunk(self):
        chunks = bootstrap_extractors._chunk_lines("line one\nline two", max_chars=1000)
        self.assertEqual(chunks, ["line one\nline two"])

    def test_splits_before_exceeding_max_chars(self):
        lines = [f"[Acme Corp] Achievement number {i}" for i in range(10)]
        text = "\n".join(lines)
        chunks = bootstrap_extractors._chunk_lines(text, max_chars=100)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)

    def test_never_splits_a_single_line_across_chunks(self):
        # Every real line here is short; a max_chars smaller than any one
        # line would force an impossible split -- confirm no line is ever
        # truncated or dropped, only grouped differently.
        lines = [f"[Acme Corp] Achievement number {i}" for i in range(10)]
        text = "\n".join(lines)
        chunks = bootstrap_extractors._chunk_lines(text, max_chars=30)
        rejoined = "\n".join(chunks).split("\n")
        self.assertEqual(rejoined, lines)

    def test_no_lines_lost_or_duplicated_across_chunks(self):
        lines = [f"[Beta Inc] Bullet {i}" for i in range(25)]
        text = "\n".join(lines)
        chunks = bootstrap_extractors._chunk_lines(text, max_chars=200)
        all_lines = []
        for chunk in chunks:
            all_lines.extend(chunk.split("\n"))
        self.assertEqual(all_lines, lines)


class TestExtractLedgerEntriesChunked(unittest.TestCase):
    # Regression coverage for the truncation bug: extract_ledger_entries()
    # used to hard-truncate achievements_text to 6000 chars, silently
    # dropping later companies' bullets from a large profile's ledger
    # extraction. extract_ledger_entries_chunked() must see every bullet.

    def test_dry_run_returns_empty_extraction_without_calling_generate(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_ledger_entries_chunked("some achievements", dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(result.metrics, [])

    @patch("bootstrap_extractors.extract_ledger_entries")
    def test_merges_results_across_chunks(self, mock_extract):
        mock_extract.side_effect = [
            bootstrap_extractors.LedgerExtraction(
                tools=[bootstrap_extractors.NamedLedgerItem(name="Salesforce", employer="Acme Corp")],
            ),
            bootstrap_extractors.LedgerExtraction(
                tools=[bootstrap_extractors.NamedLedgerItem(name="Outreach.io", employer="Beta Inc")],
            ),
        ]
        # Force two chunks by patching the chunk size down to something a
        # two-line achievements_text will actually split across.
        with patch("bootstrap_extractors.LEDGER_CHUNK_CHARS", 10):
            result = bootstrap_extractors.extract_ledger_entries_chunked(
                "[Acme Corp] Grew reply rate\n[Beta Inc] Shipped a redesign"
            )
        self.assertEqual(mock_extract.call_count, 2)
        names = {t.name for t in result.tools}
        self.assertEqual(names, {"Salesforce", "Outreach.io"})

    @patch("bootstrap_extractors.extract_ledger_entries")
    def test_exact_duplicate_within_same_employer_is_collapsed(self, mock_extract):
        mock_extract.side_effect = [
            bootstrap_extractors.LedgerExtraction(
                tools=[bootstrap_extractors.NamedLedgerItem(name="Salesforce", employer="Acme Corp")],
            ),
            bootstrap_extractors.LedgerExtraction(
                tools=[bootstrap_extractors.NamedLedgerItem(name="Salesforce", employer="Acme Corp")],
            ),
        ]
        with patch("bootstrap_extractors.LEDGER_CHUNK_CHARS", 10):
            result = bootstrap_extractors.extract_ledger_entries_chunked(
                "[Acme Corp] Used Salesforce for pipeline\n[Acme Corp] Used Salesforce for forecasting"
            )
        self.assertEqual(len(result.tools), 1)

    @patch("bootstrap_extractors.extract_ledger_entries")
    def test_same_tool_name_under_different_employers_stays_separate(self, mock_extract):
        mock_extract.side_effect = [
            bootstrap_extractors.LedgerExtraction(
                tools=[bootstrap_extractors.NamedLedgerItem(name="Salesforce", employer="Acme Corp")],
            ),
            bootstrap_extractors.LedgerExtraction(
                tools=[bootstrap_extractors.NamedLedgerItem(name="Salesforce", employer="Beta Inc")],
            ),
        ]
        with patch("bootstrap_extractors.LEDGER_CHUNK_CHARS", 10):
            result = bootstrap_extractors.extract_ledger_entries_chunked(
                "[Acme Corp] Used Salesforce for pipeline\n[Beta Inc] Used Salesforce for forecasting"
            )
        self.assertEqual(len(result.tools), 2)


if __name__ == "__main__":
    unittest.main()
