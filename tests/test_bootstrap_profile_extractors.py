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
            '{"metrics": [{"label": "Reply rate", "value": "22%"}], '
            '"tools": ["Salesforce", "Outreach.io"], "projects": ["Content Committee"]}',
            {},
        )
        result = bootstrap_extractors.extract_ledger_entries("Grew reply rate to 22% using Outreach.io.")
        self.assertEqual(len(result.metrics), 1)
        self.assertEqual(result.metrics[0].value, "22%")
        self.assertIn("Salesforce", result.tools)
        self.assertIn("Content Committee", result.projects)

    def test_dry_run_returns_empty_extraction(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_ledger_entries("some achievements", dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(result.metrics, [])
            self.assertEqual(result.tools, [])
            self.assertEqual(result.projects, [])


if __name__ == "__main__":
    unittest.main()
