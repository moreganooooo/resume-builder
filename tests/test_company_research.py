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


class TestResearchSuccessHardening(unittest.TestCase):
    def test_site_rejection_matches_host_suffix_not_substring(self):
        for bad in (
            "https://www.linkedin.com/company/acme",
            "https://job-boards.greenhouse.io/acme",
            "facebook.com/acmeroofing",
            "https://x.com/acme",
        ):
            with self.subTest(bad=bad):
                self.assertFalse(company_research.is_usable_company_site(bad))
        # A substring check let "x.com" reject these real company sites.
        for good in ("https://www.fedex.com", "box.com", "https://acme.com/about"):
            with self.subTest(good=good):
                self.assertTrue(company_research.is_usable_company_site(good))

    def test_deep_link_is_reduced_to_the_origin(self):
        # Appending /about to a deep link 404'd on every candidate.
        urls = company_research._candidate_urls("https://acme.com/careers/123?x=1")
        self.assertIn("https://acme.com/about", urls)
        self.assertIn("https://acme.com", urls)  # the homepage, tried last
        self.assertFalse(any("careers/123" in u for u in urls))

    @patch("company_research.requests.get")
    def test_unreachable_host_stops_after_one_attempt(self, mock_get):
        mock_get.side_effect = company_research.requests.exceptions.ConnectionError()
        self.assertEqual(company_research.fetch_company_pages("acme.com"), "")
        self.assertEqual(mock_get.call_count, 1)

    @patch("company_research.requests.get")
    def test_sends_a_browser_user_agent(self, mock_get):
        # The requests default UA is 403'd by most WAFs.
        mock_get.return_value = _response(status_code=404, text="")
        company_research.fetch_company_pages("acme.com")
        ua = mock_get.call_args.kwargs["headers"]["User-Agent"]
        self.assertIn("Mozilla", ua)
        self.assertNotIn("python-requests", ua)


class TestRenderedFallback(unittest.TestCase):
    @patch(
        "company_research.fetch_rendered_text",
        return_value={"https://acme.com/about": "Acme builds widgets. " * 20},
    )
    @patch("company_research.requests.get")
    def test_thin_but_reachable_site_falls_back_to_rendering(self, mock_get, mock_render):
        # An empty JS shell answers 200 with no visible text.
        mock_get.return_value = _response(status_code=200, text="<div id='root'></div>")
        text = company_research.fetch_company_pages("acme.com")
        self.assertGreaterEqual(len(text), company_research.MIN_USEFUL_CHARS)
        self.assertEqual(
            mock_render.call_args.args[0], ["https://acme.com/about", "https://acme.com"]
        )

    @patch("company_research.fetch_rendered_text")
    @patch(
        "company_research.requests.get",
        side_effect=company_research.requests.exceptions.ConnectionError(),
    )
    def test_unreachable_host_is_not_rendered(self, _get, mock_render):
        company_research.fetch_company_pages("acme.com")
        mock_render.assert_not_called()

    def test_renderer_never_launches_a_browser_under_tests(self):
        with patch.dict(os.environ):
            os.environ.pop("RESUME_ALLOW_TEST_NETWORK", None)
            with patch("company_research.subprocess.run") as mock_run:
                self.assertEqual(
                    company_research.fetch_rendered_text(["https://acme.com"]), {}
                )
        mock_run.assert_not_called()


class TestCompanyResearchCache(unittest.TestCase):
    RESEARCH = {"_research_source": "website", "company_facts": ["Sells things."]}

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache_file = os.path.join(self.tmp, "cache.json")
        for target, value in (
            ("company_research._cache_path", self.cache_file),
            ("company_research._cache_disabled", False),
        ):
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_round_trip_is_keyed_on_normalized_company_name(self):
        company_research.save_cached_research(
            "Acme Corp", self.RESEARCH, "https://www.acme.com/about"
        )
        self.assertEqual(
            company_research.load_cached_research("ACME corp."), self.RESEARCH
        )

    def test_jd_text_tier_is_never_cached(self):
        # Derived from one posting; reusing it for another would leak it.
        company_research.save_cached_research(
            "Acme Corp", {"_research_source": "jd_text", "company_facts": ["x"]}
        )
        self.assertIsNone(company_research.load_cached_research("Acme Corp"))

    def test_a_different_known_website_is_a_miss(self):
        # Two companies can share a name; the site is the better identity.
        company_research.save_cached_research("Acme", self.RESEARCH, "acme.com")
        self.assertIsNone(
            company_research.load_cached_research("Acme", "https://acme-industrial.com")
        )
        self.assertEqual(
            company_research.load_cached_research("Acme", "https://www.acme.com"),
            self.RESEARCH,
        )
        # A LinkedIn "website" is not an identity, so it does not veto a hit.
        self.assertEqual(
            company_research.load_cached_research(
                "Acme", "https://www.linkedin.com/company/acme"
            ),
            self.RESEARCH,
        )

    def test_expired_entry_is_a_miss(self):
        import datetime
        import json

        company_research.save_cached_research("Acme Corp", self.RESEARCH)
        with open(self.cache_file, encoding="utf-8") as f:
            data = json.load(f)
        old = datetime.datetime.now() - datetime.timedelta(
            days=company_research.CACHE_TTL_DAYS + 1
        )
        data["acme corp"]["saved_at"] = old.isoformat(timespec="seconds")
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertIsNone(company_research.load_cached_research("Acme Corp"))


class TestCacheIsOffForUnisolatedTests(unittest.TestCase):
    def test_suite_run_in_the_checkout_never_touches_the_real_cache(self):
        self.assertTrue(company_research._cache_disabled())


class TestSearchEngineWebsiteLookup(unittest.TestCase):
    def _find(self, name, results):
        with patch("websearch_ddg.search", return_value=results):
            return company_research._find_website_via_search_engine(name)

    def test_company_name_in_the_host_is_accepted(self):
        self.assertEqual(
            self._find("Acorns", [{"url": "https://www.acorns.com/about", "title": "Invest"}]),
            "https://www.acorns.com",
        )

    def test_homepage_titled_with_the_name_is_accepted(self):
        # adr.org carries no trace of "American Arbitration Association".
        self.assertEqual(
            self._find(
                "American Arbitration Association",
                [{"url": "https://www.adr.org/", "title": "American Arbitration Association | ADR"}],
            ),
            "https://www.adr.org",
        )

    def test_directory_deep_link_titled_with_the_name_is_rejected(self):
        # Researching the wrong company is worse than researching none.
        self.assertIsNone(
            self._find(
                "A Full Renovation LLC",
                [
                    {"url": "https://www.bizapedia.com/fl/a-full-renovation-llc.html",
                     "title": "A Full Renovation LLC in Tampa, FL"},
                    {"url": "https://www.somedirectory.com/company/a-full-renovation",
                     "title": "A Full Renovation LLC - Company Profile"},
                ],
            )
        )

    def test_name_merely_inside_another_companys_domain_is_rejected(self):
        # Live false positives under plain containment.
        for name, url in (
            ("Skill", "https://www.gskill.com/"),
            ("Sona", "https://sonagrouptours.com/"),
            ("KOPA", "https://www.m-kopa.com/"),
        ):
            with self.subTest(name=name):
                self.assertIsNone(self._find(name, [{"url": url, "title": "Home"}]))

    def test_title_evidence_needs_a_multi_word_name_and_a_word_boundary(self):
        # Live false positives: a raw startswith let "Skill" match
        # "Skillsoft", and a lone generic word matched another company.
        for name, url, title in (
            ("Skill", "https://www.skillsoft.com/", "Skillsoft | Transform Your Workforce"),
            ("Sona", "https://sonagrouptours.com/", "Sona Group Tours"),
        ):
            with self.subTest(name=name):
                self.assertIsNone(self._find(name, [{"url": url, "title": title}]))
        # A multi-word name must match whole words, not a prefix of one.
        self.assertIsNone(
            self._find(
                "Acme Roof",
                [{"url": "https://acmeroofingpros.com/", "title": "Acme Roofing Pros"}],
            )
        )

    def test_common_affix_around_the_name_is_accepted(self):
        self.assertEqual(
            self._find("Ladders", [{"url": "https://www.theladders.com/jobs", "title": "Jobs"}]),
            "https://www.theladders.com",
        )

    def test_subdomain_is_trimmed_to_the_main_site(self):
        # ui.elevenlabs.io (a design system) was matched live.
        self.assertEqual(
            self._find("ElevenLabs", [{"url": "https://ui.elevenlabs.io/docs", "title": "UI"}]),
            "https://elevenlabs.io",
        )

    def test_skips_a_bad_result_for_the_first_good_one(self):
        self.assertEqual(
            self._find(
                "Alignerr",
                [
                    {"url": "https://seamless.ai/b/alignerr-123", "title": "Alignerr | Seamless.AI"},
                    {"url": "https://alignerr.com/", "title": "Alignerr"},
                ],
            ),
            "https://alignerr.com",
        )

    @patch("company_research.GeminiClient.generate")
    def test_find_company_website_uses_the_free_lookup_first(self, mock_generate):
        with patch(
            "websearch_ddg.search",
            return_value=[{"url": "https://www.capitexai.com/", "title": "CapitexAI"}],
        ):
            self.assertEqual(
                company_research.find_company_website("CapitexAI"),
                "https://www.capitexai.com",
            )
        mock_generate.assert_not_called()


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
