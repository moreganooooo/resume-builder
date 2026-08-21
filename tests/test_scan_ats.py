import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import scan_ats  # noqa: E402


class TestResolveProviderId(unittest.TestCase):

    def test_explicit_provider_wins(self):
        self.assertEqual(
            scan_ats._resolve_provider_id(
                {
                    "provider": "remoteok",
                    "careers_url": "https://boards.greenhouse.io/x",
                }
            ),
            "remoteok",
        )

    def test_greenhouse_pattern_match(self):
        self.assertEqual(
            scan_ats._resolve_provider_id(
                {"careers_url": "https://boards.greenhouse.io/acme"}
            ),
            "greenhouse",
        )

    def test_ashby_pattern_match(self):
        self.assertEqual(
            scan_ats._resolve_provider_id(
                {"careers_url": "https://jobs.ashbyhq.com/acme"}
            ),
            "ashby",
        )

    def test_lever_pattern_match_from_api_field(self):
        self.assertEqual(
            scan_ats._resolve_provider_id(
                {"api": "https://api.lever.co/v0/postings/acme"}
            ),
            "lever",
        )

    def test_workday_pattern_match(self):
        self.assertEqual(
            scan_ats._resolve_provider_id(
                {"careers_url": "https://acme.wd1.myworkdayjobs.com/External"}
            ),
            "workday",
        )

    def test_no_match_returns_empty_string(self):
        self.assertEqual(
            scan_ats._resolve_provider_id({"careers_url": "https://acme.com/careers"}),
            "",
        )

    def test_scan_method_websearch_with_no_provider_field_does_not_resolve(self):
        # scan_method: websearch entries are handled by the sweep path
        # (search_queries.yml / fetch_ats_jobs' second loop), not routed
        # to an ATS provider directly.
        self.assertEqual(
            scan_ats._resolve_provider_id(
                {"careers_url": "https://acme.com/careers", "scan_method": "websearch"}
            ),
            "",
        )


class TestClassifyAts(unittest.TestCase):

    def test_workday_classifies_enterprise_high(self):
        result = scan_ats.classify_ats(
            "https://acme.wd1.myworkdayjobs.com/External/job/123"
        )
        self.assertEqual(
            result, {"provider_id": "workday", "weight_tier": "enterprise_high"}
        )

    def test_taleo_classifies_enterprise_high(self):
        result = scan_ats.classify_ats(
            "https://acme.taleo.net/careersection/2/jobdetail.ftl"
        )
        self.assertEqual(
            result, {"provider_id": "taleo", "weight_tier": "enterprise_high"}
        )

    def test_rippling_classifies_ai_prescreened(self):
        result = scan_ats.classify_ats("https://ats.rippling.com/acme/jobs/abc123")
        self.assertEqual(
            result, {"provider_id": "rippling", "weight_tier": "ai_prescreened"}
        )

    def test_greenhouse_classifies_startup_zero(self):
        result = scan_ats.classify_ats("https://boards.greenhouse.io/acme/jobs/123")
        self.assertEqual(
            result, {"provider_id": "greenhouse", "weight_tier": "startup_zero"}
        )

    def test_lever_classifies_startup_zero(self):
        result = scan_ats.classify_ats("https://jobs.lever.co/acme/abc")
        self.assertEqual(
            result, {"provider_id": "lever", "weight_tier": "startup_zero"}
        )

    def test_ashby_classifies_evidence_based(self):
        result = scan_ats.classify_ats("https://jobs.ashbyhq.com/acme/abc")
        self.assertEqual(
            result, {"provider_id": "ashby", "weight_tier": "evidence_based"}
        )

    def test_recruitee_classifies_unknown_tier(self):
        result = scan_ats.classify_ats("https://acme.recruitee.com/o/role")
        self.assertEqual(result, {"provider_id": "recruitee", "weight_tier": "unknown"})

    def test_no_match_returns_none(self):
        self.assertIsNone(scan_ats.classify_ats("https://acme.com/careers/role"))

    def test_empty_source_url_returns_none(self):
        self.assertIsNone(scan_ats.classify_ats(""))


class TestFetchAtsJobs(unittest.TestCase):

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    def test_skips_disabled_and_unresolvable_companies(
        self, mock_companies, mock_queries, mock_run, mock_fetch_text
    ):
        mock_companies.return_value = [
            {
                "name": "Acme",
                "careers_url": "https://boards.greenhouse.io/acme",
                "enabled": True,
            },
            {
                "name": "Disabled Co",
                "careers_url": "https://boards.greenhouse.io/disabled",
                "enabled": False,
            },
            {
                "name": "No Provider Co",
                "careers_url": "https://acme.com/careers",
                "enabled": True,
            },
        ]
        mock_run.return_value = [
            {
                "title": "Marketing Coordinator",
                "url": "https://x.com/1",
                "location": "Remote",
                "company": "Acme",
            },
        ]
        jobs = scan_ats.fetch_ats_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company_name"], "Acme")
        self.assertEqual(jobs[0]["source_platform"], "greenhouse")
        # Only one company (Acme) should have actually been fetched.
        mock_run.assert_called_once_with("greenhouse", mock_companies.return_value[0])

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_tracked_companies", return_value=[])
    @patch("scan_ats._load_search_queries")
    def test_sweep_query_renamed_to_scan_query_for_websearch_provider(
        self, mock_queries, mock_companies, mock_run, mock_fetch_text
    ):
        mock_queries.return_value = [
            {
                "name": "Greenhouse Sweep",
                "query": "site:boards.greenhouse.io marketing remote",
                "enabled": True,
            },
            {"name": "Disabled Sweep", "query": "irrelevant", "enabled": False},
        ]
        mock_run.return_value = []
        scan_ats.fetch_ats_jobs()
        mock_run.assert_called_once_with(
            "websearch",
            {
                "name": "Greenhouse Sweep",
                "query": "site:boards.greenhouse.io marketing remote",
                "enabled": True,
                "scan_query": "site:boards.greenhouse.io marketing remote",
                "_isSweep": True,
            },
        )

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_tracked_companies", return_value=[])
    @patch("scan_ats._load_search_queries")
    def test_sweep_entries_are_marked_isSweep_so_websearch_prefers_the_real_company(
        self, mock_queries, mock_companies, mock_run, mock_fetch_text
    ):
        # Regression: without _isSweep, websearch.mjs falls back to the
        # sweep query's own descriptive name (e.g. "Greenhouse —
        # Marketing & Enablement remote") as the "company" on every
        # result -- confirmed live 2026-07-27, this produced duplicate
        # JD files whenever the same real posting matched two different
        # sweep queries, each stamping a different fake company name.
        mock_queries.return_value = [
            {
                "name": "Greenhouse Sweep",
                "query": "site:boards.greenhouse.io remote",
                "enabled": True,
            }
        ]
        mock_run.return_value = []
        scan_ats.fetch_ats_jobs()
        called_entry = mock_run.call_args.args[1]
        self.assertTrue(called_entry["_isSweep"])

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    def test_skips_entries_pinned_to_an_aggregator_provider(
        self, mock_companies, mock_queries, mock_run, mock_fetch_text
    ):
        # Regression: tracked_companies.yml has entries like
        # {"provider": "jobspresso", "search_term": "marketing"} --
        # career-ops's own design, but scan_boards.py's "boards" source
        # already fetches jobspresso's full feed unfiltered, so every
        # posting these entries could return is already covered there.
        # Fetching them here just re-discovers the same postings under a
        # different company label (the entry's own display name), which
        # defeats job_key_known()'s source_url+company_name dedup match
        # and produces real duplicate JD files -- confirmed live
        # 2026-07-27 (31 duplicate-URL groups, 62 files).
        mock_companies.return_value = [
            {
                "name": "Jobspresso — Marketing",
                "provider": "jobspresso",
                "search_term": "marketing",
                "enabled": True,
            },
            {
                "name": "Acme",
                "careers_url": "https://boards.greenhouse.io/acme",
                "enabled": True,
            },
        ]
        mock_run.return_value = [
            {
                "title": "Marketing Coordinator",
                "url": "https://x.com/1",
                "location": "Remote",
                "company": "Acme",
            },
        ]
        jobs = scan_ats.fetch_ats_jobs()
        self.assertEqual(len(jobs), 1)
        mock_run.assert_called_once_with("greenhouse", mock_companies.return_value[1])

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    def test_title_and_location_filters_still_apply(
        self, mock_companies, mock_queries, mock_run, mock_fetch_text
    ):
        mock_companies.return_value = [
            {
                "name": "Acme",
                "careers_url": "https://boards.greenhouse.io/acme",
                "enabled": True,
            },
        ]
        mock_run.return_value = [
            {
                "title": "Warehouse Associate",
                "url": "https://x.com/1",
                "location": "Remote",
                "company": "Acme",
            },
        ]
        self.assertEqual(scan_ats.fetch_ats_jobs(), [])


class TestWebsearchPacing(unittest.TestCase):
    """websearch.mjs used to pace itself against Brave's free-tier 1
    req/sec limit with a module-level queue -- dead code across the
    subprocess boundary, since run_provider.mjs spawns one fresh Node
    process per query (see B26, docs/review/phase-9-backlog.md). Real
    pacing now lives in fetch_ats_jobs()'s sweep loop instead."""

    @patch("time.sleep")
    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider", return_value=[])
    @patch("scan_ats._load_tracked_companies", return_value=[])
    @patch("scan_ats._load_search_queries")
    def test_no_sleep_before_the_first_websearch_call(
        self, mock_queries, mock_companies, mock_run, mock_fetch_text, mock_sleep
    ):
        mock_queries.return_value = [
            {"name": "Only Query", "query": "q", "enabled": True}
        ]
        scan_ats.fetch_ats_jobs()
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider", return_value=[])
    @patch("scan_ats._load_tracked_companies", return_value=[])
    @patch("scan_ats._load_search_queries")
    def test_sleeps_between_multiple_websearch_calls(
        self, mock_queries, mock_companies, mock_run, mock_fetch_text, mock_sleep
    ):
        mock_queries.return_value = [
            {"name": "Query One", "query": "q1", "enabled": True},
            {"name": "Query Two", "query": "q2", "enabled": True},
            {"name": "Query Three", "query": "q3", "enabled": True},
        ]
        scan_ats.fetch_ats_jobs()
        # One sleep call before each of the 2nd and 3rd calls -- never
        # before the 1st.
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(mock_run.call_count, 3)

    @patch("time.sleep")
    @patch("time.monotonic")
    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider", return_value=[])
    @patch("scan_ats._load_tracked_companies", return_value=[])
    @patch("scan_ats._load_search_queries")
    def test_does_not_sleep_the_full_gap_when_the_call_itself_already_took_a_while(
        self,
        mock_queries,
        mock_companies,
        mock_run,
        mock_fetch_text,
        mock_monotonic,
        mock_sleep,
    ):
        # Measures from the previous call's *start*, not a blind fixed
        # sleep -- if the call itself already consumed the whole gap
        # (network latency), the next iteration shouldn't sleep on top of
        # that.
        mock_queries.return_value = [
            {"name": "Query One", "query": "q1", "enabled": True},
            {"name": "Query Two", "query": "q2", "enabled": True},
        ]
        # time.monotonic() is called 3 times across 2 queries: once to
        # record the 1st call's start, once for the 2nd iteration's
        # elapsed-time check (already >= the 1s gap here), once to record
        # the 2nd call's own start.
        mock_monotonic.side_effect = [0.0, 1.5, 1.5]
        scan_ats.fetch_ats_jobs()
        mock_sleep.assert_not_called()


class TestNormalizeRawJobAndLoaders(unittest.TestCase):
    def test_normalize_raw_job_invalid_titles_and_urls(self):
        self.assertIsNone(scan_ats._normalize_raw_job({}, "greenhouse", "Acme"))
        self.assertIsNone(
            scan_ats._normalize_raw_job(
                {"title": "https://example.com", "url": "https://example.com"},
                "greenhouse",
                "Acme",
            )
        )
        self.assertIsNone(
            scan_ats._normalize_raw_job(
                {"title": "http://example.com", "url": "https://example.com"},
                "greenhouse",
                "Acme",
            )
        )
        self.assertIsNone(
            scan_ats._normalize_raw_job(
                {"title": "Valid Title", "url": ""}, "greenhouse", "Acme"
            )
        )

    @patch("scan_boards._html_to_text", return_value="Parsed HTML description")
    @patch("scan_boards._passes_title_filter", return_value=True)
    @patch("scan_boards._passes_location_filter", return_value=True)
    def test_normalize_raw_job_with_inline_description(
        self, mock_loc, mock_title, mock_html
    ):
        raw = {
            "title": "Senior Marketing Manager",
            "url": "https://boards.greenhouse.io/job/1",
            "description": "<p>Parsed HTML description</p>",
            "company": "Acme Corp",
            "location": "Remote",
            "posted_at": "2026-08-01",
        }
        job = scan_ats._normalize_raw_job(raw, "greenhouse", "Acme")
        self.assertIsNotNone(job)
        self.assertEqual(job["description"], "Parsed HTML description")
        self.assertEqual(job["company_name"], "Acme Corp")
        mock_html.assert_called_once_with("<p>Parsed HTML description</p>")

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_search_queries")
    @patch("scan_ats._load_tracked_companies")
    def test_fetch_ats_jobs_with_activity(
        self, mock_companies, mock_queries, mock_run, mock_fetch_text
    ):
        from unittest.mock import MagicMock

        activity = MagicMock()
        mock_companies.return_value = [
            {
                "name": "Acme",
                "careers_url": "https://boards.greenhouse.io/acme",
                "enabled": True,
            }
        ]
        mock_queries.return_value = [
            {
                "name": "Greenhouse Sweep",
                "query": "site:boards.greenhouse.io remote",
                "enabled": True,
            }
        ]
        mock_run.return_value = [
            {
                "title": "Marketing Coordinator",
                "url": "https://boards.greenhouse.io/job/2",
                "location": "Remote",
                "company": "Acme",
            }
        ]
        jobs = scan_ats.fetch_ats_jobs(activity=activity)
        self.assertEqual(len(jobs), 2)
        activity.start_source.assert_called_once()
        self.assertTrue(activity.step.called)

    def test_file_loaders(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tracked_path = os.path.join(tmpdir, "tracked_companies.yml")
            search_path = os.path.join(tmpdir, "search_queries.yml")
            with open(tracked_path, "w", encoding="utf-8") as f:
                f.write("tracked_companies:\n  - name: TestCo\n")
            with open(search_path, "w", encoding="utf-8") as f:
                f.write("search_queries:\n  - name: TestQuery\n")

            with patch("profile_paths.board_scanner_dir", return_value=tmpdir):
                comps = scan_ats._load_tracked_companies()
                queries = scan_ats._load_search_queries()
                self.assertEqual(comps, [{"name": "TestCo"}])
                self.assertEqual(queries, [{"name": "TestQuery"}])

    def test_canonicalize_job_url_strips_tracking_params(self):
        url = "https://boards.greenhouse.io/acme/jobs/12345?gh_src=custom_source&utm_source=linkedin&utm_medium=job_post&utm_campaign=hiring"
        cleaned = scan_ats.canonicalize_job_url(url)
        self.assertEqual(cleaned, "https://boards.greenhouse.io/acme/jobs/12345")

        lever_url = "https://jobs.lever.co/acme/abc-123?lever-origin=applied&lever-source=Indeed&ref=some_ref"
        self.assertEqual(
            scan_ats.canonicalize_job_url(lever_url),
            "https://jobs.lever.co/acme/abc-123",
        )

        preserves_real_query = "https://example.com/job?id=123&utm_source=email"
        self.assertEqual(
            scan_ats.canonicalize_job_url(preserves_real_query),
            "https://example.com/job?id=123",
        )


if __name__ == "__main__":
    unittest.main()


class TestConcurrentCompanyFetching(unittest.TestCase):
    """The company loop runs in a thread pool; the sweep loop must not."""

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    @patch("scan_boards._run_node_provider")
    def test_all_companies_are_fetched(self, mock_run, mock_companies, *_):
        mock_companies.return_value = [
            {"name": f"Co{i}", "provider": "greenhouse", "enabled": True}
            for i in range(12)
        ]
        mock_run.return_value = [
            {
                "title": "Marketing Coordinator",
                "url": "https://x.com/1",
                "location": "Remote",
                "company": "Acme",
            }
        ]
        jobs = scan_ats.fetch_ats_jobs()
        # Every company fetched exactly once, and nothing lost in the
        # concurrent collection.
        self.assertEqual(mock_run.call_count, 12)
        self.assertEqual(len(jobs), 12)

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    @patch("scan_boards._run_node_provider")
    def test_one_failing_company_does_not_abort_scan(
        self, mock_run, mock_companies, *_
    ):
        mock_companies.return_value = [
            {"name": f"Co{i}", "provider": "greenhouse", "enabled": True}
            for i in range(4)
        ]

        def flaky(provider_id, company):
            if company["name"] == "Co2":
                raise RuntimeError("host unreachable")
            return [
                {
                    "title": "Marketing Coordinator",
                    "url": f"https://x.com/{company['name']}",
                    "location": "Remote",
                    "company": company["name"],
                }
            ]

        mock_run.side_effect = flaky
        jobs = scan_ats.fetch_ats_jobs()
        # The three healthy hosts still return; only the bad one is lost.
        self.assertEqual(len(jobs), 3)
        self.assertNotIn("Co2", [j["company_name"] for j in jobs])
