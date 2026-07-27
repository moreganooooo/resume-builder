import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import scan_ats  # noqa: E402


class TestResolveProviderId(unittest.TestCase):

    def test_explicit_provider_wins(self):
        self.assertEqual(scan_ats._resolve_provider_id({"provider": "remoteok", "careers_url": "https://boards.greenhouse.io/x"}), "remoteok")

    def test_greenhouse_pattern_match(self):
        self.assertEqual(scan_ats._resolve_provider_id({"careers_url": "https://boards.greenhouse.io/acme"}), "greenhouse")

    def test_ashby_pattern_match(self):
        self.assertEqual(scan_ats._resolve_provider_id({"careers_url": "https://jobs.ashbyhq.com/acme"}), "ashby")

    def test_lever_pattern_match_from_api_field(self):
        self.assertEqual(scan_ats._resolve_provider_id({"api": "https://api.lever.co/v0/postings/acme"}), "lever")

    def test_workday_pattern_match(self):
        self.assertEqual(scan_ats._resolve_provider_id({"careers_url": "https://acme.wd1.myworkdayjobs.com/External"}), "workday")

    def test_no_match_returns_empty_string(self):
        self.assertEqual(scan_ats._resolve_provider_id({"careers_url": "https://acme.com/careers"}), "")

    def test_scan_method_websearch_with_no_provider_field_does_not_resolve(self):
        # scan_method: websearch entries are handled by the sweep path
        # (search_queries.yml / fetch_ats_jobs' second loop), not routed
        # to an ATS provider directly.
        self.assertEqual(scan_ats._resolve_provider_id({"careers_url": "https://acme.com/careers", "scan_method": "websearch"}), "")


class TestFetchAtsJobs(unittest.TestCase):

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    def test_skips_disabled_and_unresolvable_companies(self, mock_companies, mock_queries, mock_run, mock_fetch_text):
        mock_companies.return_value = [
            {"name": "Acme", "careers_url": "https://boards.greenhouse.io/acme", "enabled": True},
            {"name": "Disabled Co", "careers_url": "https://boards.greenhouse.io/disabled", "enabled": False},
            {"name": "No Provider Co", "careers_url": "https://acme.com/careers", "enabled": True},
        ]
        mock_run.return_value = [
            {"title": "Marketing Coordinator", "url": "https://x.com/1", "location": "Remote", "company": "Acme"},
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
    def test_sweep_query_renamed_to_scan_query_for_websearch_provider(self, mock_queries, mock_companies, mock_run, mock_fetch_text):
        mock_queries.return_value = [
            {"name": "Greenhouse Sweep", "query": "site:boards.greenhouse.io marketing remote", "enabled": True},
            {"name": "Disabled Sweep", "query": "irrelevant", "enabled": False},
        ]
        mock_run.return_value = []
        scan_ats.fetch_ats_jobs()
        mock_run.assert_called_once_with("websearch", {
            "name": "Greenhouse Sweep", "query": "site:boards.greenhouse.io marketing remote",
            "enabled": True, "scan_query": "site:boards.greenhouse.io marketing remote",
        })

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    @patch("scan_ats._load_search_queries", return_value=[])
    @patch("scan_ats._load_tracked_companies")
    def test_title_and_location_filters_still_apply(self, mock_companies, mock_queries, mock_run, mock_fetch_text):
        mock_companies.return_value = [
            {"name": "Acme", "careers_url": "https://boards.greenhouse.io/acme", "enabled": True},
        ]
        mock_run.return_value = [
            {"title": "Warehouse Associate", "url": "https://x.com/1", "location": "Remote", "company": "Acme"},
        ]
        self.assertEqual(scan_ats.fetch_ats_jobs(), [])


if __name__ == "__main__":
    unittest.main()
