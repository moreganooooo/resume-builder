import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

_RESEARCH_JSON = (
    '{"overall_tone_adjective": "warm", "company_facts": ["Sells things."]}'
)


class TestResearchCompanyWebsiteFallback(unittest.TestCase):
    """Covers the 2026-07-21 fallback: research_company() used to give up
    immediately when jd_data had no company_website (true unconditionally
    for scan_linkedin.py's JDs). It now tries
    company_research.find_company_website() first."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    @patch(
        "orchestrator.company_research.research_company_via_search", return_value=None
    )
    @patch("orchestrator.company_research.find_company_website")
    def test_falls_through_to_lower_tiers_when_no_website_found(
        self, mock_find, mock_search
    ):
        mock_find.return_value = None
        # No jd_text either, so every tier is exhausted -> None.
        result = self.engine.research_company({"company_name": "Acme Corp"})
        self.assertIsNone(result)
        mock_find.assert_called_once_with("Acme Corp")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.fetch_company_pages")
    @patch("orchestrator.company_research.find_company_website")
    def test_uses_found_website_to_proceed_with_research(
        self, mock_find, mock_fetch, mock_generate
    ):
        mock_find.return_value = "https://www.acme.com"
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = (_RESEARCH_JSON, {})

        self.engine.research_company({"company_name": "Acme Corp"})

        mock_fetch.assert_called_once_with("https://www.acme.com")

    @patch(
        "orchestrator.company_research.research_company_via_search", return_value=None
    )
    @patch("orchestrator.company_research.find_company_website")
    def test_does_not_call_fallback_when_website_already_known(
        self, mock_find, mock_search
    ):
        with patch(
            "orchestrator.company_research.fetch_company_pages", return_value=""
        ):
            self.engine.research_company(
                {"company_name": "Acme Corp", "company_website": "acme.com"}
            )
        mock_find.assert_not_called()


class TestResearchCompanyTierFallback(unittest.TestCase):
    """The 2026-08-11 guarantee: research_company() should produce signal
    for effectively every JD -- website scrape, then confidence-gated
    grounded search, then the JD's own text."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_data = {
            "company_name": "Acme Corp",
            "company_website": "https://www.acme.com",
        }
        self.jd_text = "Acme Corp is hiring a CRM Manager to delight our guests."

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_tier1_used_when_scrape_is_usable(
        self, mock_fetch, mock_search, mock_generate
    ):
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)

        self.assertEqual(result["_research_source"], "website")
        mock_search.assert_not_called()

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_tier2_used_when_scrape_is_thin_and_search_is_high_confidence(
        self, mock_fetch, mock_search, mock_generate
    ):
        mock_fetch.return_value = ""
        mock_search.return_value = "Acme calls its customers guests."
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)

        self.assertEqual(result["_research_source"], "search")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_tier3_used_when_search_is_not_high_confidence(
        self, mock_fetch, mock_search, mock_generate
    ):
        mock_fetch.return_value = ""
        mock_search.return_value = None  # medium/low/failed all surface as None
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)

        self.assertEqual(result["_research_source"], "jd_text")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.find_company_website")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_always_returns_something_when_jd_text_exists(
        self, mock_fetch, mock_find, mock_search, mock_generate
    ):
        # The core guarantee: no website, no search result -- still not None.
        mock_find.return_value = None
        mock_fetch.return_value = ""
        mock_search.return_value = None
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(
            {"company_name": "Acme Corp"}, self.jd_text
        )

        self.assertIsNotNone(result)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_passes_jd_context_hint_to_the_search_tier(
        self, mock_fetch, mock_search, mock_generate
    ):
        mock_fetch.return_value = ""
        mock_search.return_value = "Acme is neighborly."
        mock_generate.return_value = (_RESEARCH_JSON, {})

        self.engine.research_company(
            dict(self.jd_data, job_title="Senior CRM Manager"), self.jd_text
        )

        args, _ = mock_search.call_args
        self.assertEqual(args[0], "Acme Corp")
        self.assertIn("Senior CRM Manager", args[1])

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_returns_none_when_extraction_cannot_be_parsed(
        self, mock_fetch, mock_search, mock_generate
    ):
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = ("not json at all", {})

        self.assertIsNone(self.engine.research_company(self.jd_data, self.jd_text))

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_research_source_never_reaches_the_prompt_block(
        self, mock_fetch, mock_search, mock_generate
    ):
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)
        block = orchestrator.format_company_research_block(result)

        self.assertNotIn("_research_source", block)


if __name__ == "__main__":
    unittest.main()
