import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestResearchCompanyWebsiteFallback(unittest.TestCase):
    """Covers the 2026-07-21 fallback: research_company() used to give up
    immediately when jd_data had no company_website (true unconditionally
    for scan_linkedin.py's JDs). It now tries
    company_research.find_company_website() first."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    @patch("orchestrator.company_research.find_company_website")
    def test_skips_entirely_when_no_website_known_and_none_found(self, mock_find):
        mock_find.return_value = None
        result = self.engine.research_company({"company_name": "Acme Corp"})
        self.assertIsNone(result)
        mock_find.assert_called_once_with("Acme Corp")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.fetch_company_pages")
    @patch("orchestrator.company_research.find_company_website")
    def test_uses_found_website_to_proceed_with_research(self, mock_find, mock_fetch, mock_generate):
        mock_find.return_value = "https://www.acme.com"
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = ('{"tone_signals": [], "traceable_facts": []}', {})

        self.engine.research_company({"company_name": "Acme Corp"})

        mock_fetch.assert_called_once_with("https://www.acme.com")

    @patch("orchestrator.company_research.find_company_website")
    def test_does_not_call_fallback_when_website_already_known(self, mock_find):
        with patch("orchestrator.company_research.fetch_company_pages", return_value=""):
            self.engine.research_company({"company_name": "Acme Corp", "company_website": "acme.com"})
        mock_find.assert_not_called()


if __name__ == "__main__":
    unittest.main()
