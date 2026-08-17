import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
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
        parsed_urls = [urlparse(u) for u in urls]
        self.assertTrue(all(p.scheme == "https" for p in parsed_urls))
        self.assertTrue(all(p.hostname == "acme.com" for p in parsed_urls))

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

    def test_strips_nav_header_footer_boilerplate(self):
        """F10: raw nav/header/footer text was previously flattened into
        the same blob as real page content, diluting the company-research
        prompt with things like 'Home About Careers Contact'."""
        html = (
            "<html><body>"
            "<nav>Home About Careers Contact</nav>"
            "<header>Acme Corp</header>"
            "<main><p>Acme Corp builds widgets for the enterprise.</p></main>"
            "<footer>Privacy Policy | Terms</footer>"
            "</body></html>"
        )
        text = company_research._extract_visible_text(html)
        self.assertIn("widgets for the enterprise", text)
        self.assertNotIn("Home About Careers", text)
        self.assertNotIn("Privacy Policy", text)

    def test_strips_cookie_consent_banner_by_class_or_id(self):
        html = (
            "<html><body>"
            '<div id="cookie-banner">We use cookies. Accept All</div>'
            '<div class="consent-modal">Manage your consent preferences</div>'
            "<main><p>Acme Corp builds widgets for the enterprise.</p></main>"
            "</body></html>"
        )
        text = company_research._extract_visible_text(html)
        self.assertIn("widgets for the enterprise", text)
        self.assertNotIn("Accept All", text)
        self.assertNotIn("consent preferences", text)


class TestFetchCompanyPages(unittest.TestCase):

    @patch("company_research.requests.get")
    def test_returns_empty_string_when_all_candidates_fail(self, mock_get):
        mock_get.return_value = _response(status_code=404, text="")
        result = company_research.fetch_company_pages("acme.com")
        self.assertEqual(result, "")
        self.assertEqual(mock_get.call_count, len(company_research.CANDIDATE_PATHS))

    @patch("company_research.requests.get")
    def test_stops_early_once_enough_content_collected(self, mock_get):
        big_text = (
            "<p>" + ("word " * 400) + "</p>"
        )  # ~2000 chars visible, over EARLY_STOP_CHARS
        mock_get.return_value = _response(status_code=200, text=big_text)
        result = company_research.fetch_company_pages("acme.com")
        self.assertGreater(len(result), 0)
        self.assertEqual(mock_get.call_count, 1)

    @patch("company_research.requests.get")
    def test_combines_text_across_multiple_successful_pages(self, mock_get):
        mock_get.side_effect = [
            _response(status_code=200, text="<p>About us content.</p>"),
            _response(status_code=404, text=""),
            _response(status_code=200, text="<p>Careers page content.</p>"),
        ] + [_response(status_code=404, text="")] * (
            len(company_research.CANDIDATE_PATHS) - 3
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
        mock_generate.return_value = (
            "Sure! The URL is https://www.acme.com/ -- hope that helps.",
            {},
        )
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


class TestApplyVocabularySubstitutions(unittest.TestCase):

    SUBS = [{"generic_term": "customers", "company_term": "guests"}]

    def test_replaces_lowercase_occurrence(self):
        result = company_research.apply_vocabulary_substitutions(
            "Grew customers by 30%", self.SUBS
        )
        self.assertEqual(result, "Grew guests by 30%")

    def test_preserves_leading_capital(self):
        result = company_research.apply_vocabulary_substitutions(
            "Customers drove the renewal", self.SUBS
        )
        self.assertEqual(result, "Guests drove the renewal")

    def test_preserves_all_caps(self):
        result = company_research.apply_vocabulary_substitutions(
            "CUSTOMERS FIRST", self.SUBS
        )
        self.assertEqual(result, "GUESTS FIRST")

    def test_respects_word_boundaries(self):
        # "customers" must not match inside "customersuccess"
        result = company_research.apply_vocabulary_substitutions(
            "Owned customersuccess tooling", self.SUBS
        )
        self.assertEqual(result, "Owned customersuccess tooling")

    def test_singular_is_not_matched_by_plural_pair(self):
        # \b means "customers" cannot match the shorter "customer".
        result = company_research.apply_vocabulary_substitutions(
            "Each customer mattered", self.SUBS
        )
        self.assertEqual(result, "Each customer mattered")

    def test_applies_multiple_pairs_in_one_string(self):
        subs = [
            {"generic_term": "customers", "company_term": "guests"},
            {"generic_term": "employees", "company_term": "team members"},
        ]
        result = company_research.apply_vocabulary_substitutions(
            "Trained employees to serve customers", subs
        )
        self.assertEqual(result, "Trained team members to serve guests")

    def test_empty_substitutions_is_a_no_op(self):
        self.assertEqual(
            company_research.apply_vocabulary_substitutions("Grew customers", []),
            "Grew customers",
        )

    def test_skips_malformed_pair_without_raising(self):
        subs = [
            {"generic_term": "", "company_term": "guests"},
            {"company_term": "guests"},
            {"generic_term": "customers", "company_term": ""},
            {"generic_term": "customers", "company_term": "guests"},
        ]
        result = company_research.apply_vocabulary_substitutions("Grew customers", subs)
        self.assertEqual(result, "Grew guests")

    def test_regex_metacharacters_in_term_are_treated_literally(self):
        subs = [{"generic_term": "C++", "company_term": "Cpp"}]
        result = company_research.apply_vocabulary_substitutions(
            "Shipped C++ tooling", subs
        )
        self.assertEqual(result, "Shipped Cpp tooling")


class TestApplyVocabularySubstitutionsToResume(unittest.TestCase):

    SUBS = [{"generic_term": "customers", "company_term": "guests"}]

    def _resume(self):
        return {
            "SUMMARY": "Strategist who grows customers",
            "EXPERIENCE": [
                {
                    "company": "Acme",
                    "achievements": [
                        "Grew customers by 30%",
                        "Launched a loyalty program",
                    ],
                },
                {"company": "Globex", "achievements": ["Retained customers at 94%"]},
            ],
        }

    def test_substitutes_in_every_role_s_achievements(self):
        result = company_research.apply_vocabulary_substitutions_to_resume(
            self._resume(), self.SUBS
        )
        self.assertEqual(
            result["EXPERIENCE"][0]["achievements"][0], "Grew guests by 30%"
        )
        self.assertEqual(
            result["EXPERIENCE"][1]["achievements"][0], "Retained guests at 94%"
        )

    def test_leaves_untargeted_bullets_byte_identical(self):
        result = company_research.apply_vocabulary_substitutions_to_resume(
            self._resume(), self.SUBS
        )
        self.assertEqual(
            result["EXPERIENCE"][0]["achievements"][1], "Launched a loyalty program"
        )

    def test_does_not_touch_the_summary(self):
        # The Summary is model-written with the vocabulary already in context;
        # this deterministic pass is bullets-only by design.
        result = company_research.apply_vocabulary_substitutions_to_resume(
            self._resume(), self.SUBS
        )
        self.assertEqual(result["SUMMARY"], "Strategist who grows customers")

    def test_empty_substitutions_returns_resume_unchanged(self):
        original = self._resume()
        result = company_research.apply_vocabulary_substitutions_to_resume(original, [])
        self.assertEqual(result, self._resume())

    def test_tolerates_missing_or_malformed_experience(self):
        for resume in (
            {},
            {"EXPERIENCE": None},
            {"EXPERIENCE": ["not a dict"]},
            {"EXPERIENCE": [{"company": "Acme"}]},
            {"EXPERIENCE": [{"achievements": "not a list"}]},
            {"EXPERIENCE": [{"achievements": [None, 42]}]},
        ):
            with self.subTest(resume=resume):
                company_research.apply_vocabulary_substitutions_to_resume(
                    resume, self.SUBS
                )


class TestResearchCompanyViaSearch(unittest.TestCase):

    HIGH = "CONFIDENCE: high\nAcme calls its customers guests and leads with neighborly warmth."

    def test_returns_none_when_company_name_missing(self):
        self.assertIsNone(company_research.research_company_via_search(""))
        self.assertIsNone(company_research.research_company_via_search(None))

    @patch("company_research.GeminiClient.generate")
    def test_returns_text_on_high_confidence(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        result = company_research.research_company_via_search("Acme Corp")
        self.assertIn("neighborly warmth", result)

    @patch("company_research.GeminiClient.generate")
    def test_strips_the_confidence_line_from_the_returned_text(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        result = company_research.research_company_via_search("Acme Corp")
        self.assertNotIn("CONFIDENCE:", result)

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_medium_confidence(self, mock_generate):
        mock_generate.return_value = ("CONFIDENCE: medium\nProbably a retailer.", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_low_confidence(self, mock_generate):
        mock_generate.return_value = (
            "CONFIDENCE: low\nNot sure which Acme this is.",
            {},
        )
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_when_confidence_line_missing(self, mock_generate):
        # Fail closed: unlabeled output is never trusted.
        mock_generate.return_value = ("Acme is a warm, neighborly retailer.", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_when_high_confidence_has_no_body_text(self, mock_generate):
        mock_generate.return_value = ("CONFIDENCE: high", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_passes_google_search_tool_not_response_schema(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        company_research.research_company_via_search("Acme Corp")
        _, kwargs = mock_generate.call_args
        self.assertEqual(kwargs.get("tools"), [{"google_search": {}}])
        self.assertNotIn("response_schema", kwargs)

    @patch("company_research.GeminiClient.generate")
    def test_includes_context_hint_in_the_prompt(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        company_research.research_company_via_search(
            "Acme Corp", "Senior CRM Manager, retail"
        )
        _, kwargs = mock_generate.call_args
        self.assertIn("Senior CRM Manager, retail", kwargs.get("contents", ""))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_api_exception_instead_of_raising(self, mock_generate):
        mock_generate.side_effect = RuntimeError("network error")
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))
