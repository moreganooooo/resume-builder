import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import company_research  # noqa: E402


def _response(status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestCandidateUrls(unittest.TestCase):

    def test_adds_https_scheme_when_missing(self):
        urls = company_research._candidate_urls("acme.com")
        self.assertTrue(all(u.startswith("https://acme.com") for u in urls))

    def test_strips_trailing_slash_before_appending_paths(self):
        urls = company_research._candidate_urls("https://acme.com/")
        self.assertIn("https://acme.com/about", urls)
        self.assertNotIn("https://acme.com//about", urls)

    def test_includes_all_candidate_paths(self):
        urls = company_research._candidate_urls("https://acme.com")
        for path in company_research.CANDIDATE_PATHS:
            self.assertIn(f"https://acme.com{path}", urls)


class TestExtractVisibleText(unittest.TestCase):

    def test_strips_script_and_style_tags(self):
        html = "<html><head><style>.x{color:red}</style></head><body><script>evil()</script><p>Real content</p></body></html>"
        text = company_research._extract_visible_text(html)
        self.assertEqual(text, "Real content")

    def test_collapses_whitespace(self):
        html = "<p>Line one</p>\n\n<p>   Line   two   </p>"
        text = company_research._extract_visible_text(html)
        self.assertEqual(text, "Line one Line two")


class TestFetchCompanyPages(unittest.TestCase):

    @patch("company_research.requests.get")
    def test_returns_empty_string_when_all_candidates_fail(self, mock_get):
        mock_get.return_value = _response(status_code=404, text="")
        result = company_research.fetch_company_pages("acme.com")
        self.assertEqual(result, "")
        self.assertEqual(mock_get.call_count, len(company_research.CANDIDATE_PATHS))

    @patch("company_research.requests.get")
    def test_stops_early_once_enough_content_collected(self, mock_get):
        big_text = "<p>" + ("word " * 400) + "</p>"  # ~2000 chars visible, over EARLY_STOP_CHARS
        mock_get.return_value = _response(status_code=200, text=big_text)
        result = company_research.fetch_company_pages("acme.com")
        self.assertGreater(len(result), 0)
        self.assertEqual(mock_get.call_count, 1)

    @patch("company_research.requests.get")
    def test_combines_text_across_multiple_successful_pages(self, mock_get):
        mock_get.side_effect = (
            [
                _response(status_code=200, text="<p>About us content.</p>"),
                _response(status_code=404, text=""),
                _response(status_code=200, text="<p>Careers page content.</p>"),
            ]
            + [_response(status_code=404, text="")] * (len(company_research.CANDIDATE_PATHS) - 3)
        )
        result = company_research.fetch_company_pages("acme.com")
        self.assertIn("About us content.", result)
        self.assertIn("Careers page content.", result)

    @patch("company_research.requests.get")
    def test_caps_combined_text_at_max_total_chars(self, mock_get):
        huge_text = "<p>" + ("x" * 10000) + "</p>"
        mock_get.return_value = _response(status_code=200, text=huge_text)
        result = company_research.fetch_company_pages("acme.com")
        self.assertLessEqual(len(result), company_research.MAX_TOTAL_CHARS)


class TestFindCompanyWebsite(unittest.TestCase):

    def test_returns_none_when_company_name_missing(self):
        self.assertIsNone(company_research.find_company_website(""))
        self.assertIsNone(company_research.find_company_website(None))

    @patch("company_research.GeminiClient.generate")
    def test_extracts_url_from_grounded_response(self, mock_generate):
        mock_generate.return_value = ("https://www.acme.com", {})
        result = company_research.find_company_website("Acme Corp")
        self.assertEqual(result, "https://www.acme.com")

    @patch("company_research.GeminiClient.generate")
    def test_passes_google_search_tool_not_response_schema(self, mock_generate):
        mock_generate.return_value = ("https://www.acme.com", {})
        company_research.find_company_website("Acme Corp")
        _, kwargs = mock_generate.call_args
        self.assertEqual(kwargs.get("tools"), [{"google_search": {}}])
        self.assertNotIn("response_schema", kwargs)

    @patch("company_research.GeminiClient.generate")
    def test_strips_surrounding_prose_around_the_url(self, mock_generate):
        mock_generate.return_value = ("Sure! The URL is https://www.acme.com/ -- hope that helps.", {})
        result = company_research.find_company_website("Acme Corp")
        self.assertEqual(result, "https://www.acme.com/")

    @patch("company_research.GeminiClient.generate")
    def test_rejects_job_board_and_reference_site_domains(self, mock_generate):
        mock_generate.return_value = ("https://www.linkedin.com/company/acme", {})
        self.assertIsNone(company_research.find_company_website("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_when_no_url_in_response(self, mock_generate):
        mock_generate.return_value = ("I couldn't find that company.", {})
        self.assertIsNone(company_research.find_company_website("Nonexistent Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_api_exception_instead_of_raising(self, mock_generate):
        mock_generate.side_effect = RuntimeError("network error")
        self.assertIsNone(company_research.find_company_website("Acme Corp"))
