import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import scan_boards  # noqa: E402


class TestTitleFilter(unittest.TestCase):

    def test_positive_keyword_passes(self):
        self.assertTrue(scan_boards._passes_title_filter("Lifecycle Marketing Manager"))

    def test_missing_positive_keyword_fails(self):
        self.assertFalse(scan_boards._passes_title_filter("Warehouse Associate"))

    def test_negative_keyword_blocks_even_with_positive_match(self):
        # "Marketing" is positive, " Engineer" is negative -- negative wins.
        self.assertFalse(scan_boards._passes_title_filter("Marketing Software Engineer"))


class TestLocationFilter(unittest.TestCase):

    def test_empty_location_passes(self):
        self.assertTrue(scan_boards._passes_location_filter(""))
        self.assertTrue(scan_boards._passes_location_filter(None))

    def test_remote_passes(self):
        self.assertTrue(scan_boards._passes_location_filter("Remote, US"))

    def test_onsite_blocked(self):
        self.assertFalse(scan_boards._passes_location_filter("Onsite - New York, NY"))

    def test_always_allow_beats_block(self):
        # Both a block term ("Hybrid") and an always_allow term ("Remote")
        # appear -- always_allow wins.
        self.assertTrue(scan_boards._passes_location_filter("Remote, Hybrid optional"))


class TestFetchBoardJobs(unittest.TestCase):

    @patch("scan_boards._fetch_posting_text", return_value="full posting text")
    @patch("scan_boards._run_node_provider")
    def test_normalizes_and_filters_raw_listings(self, mock_run, mock_fetch_text):
        mock_run.return_value = [
            {"title": "Lifecycle Marketing Manager", "url": "https://x.com/1",
             "company": "Acme", "location": "Remote", "posted_at": "2026-07-01"},
            {"title": "Warehouse Associate", "url": "https://x.com/2",
             "company": "Acme", "location": "Remote"},  # fails title filter
            {"title": "Marketing Coordinator", "url": "https://x.com/3",
             "company": "Acme", "location": "Onsite - NYC"},  # fails location filter
        ]
        jobs = scan_boards.fetch_board_jobs(sources=["remoteok"])
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["job_title"], "Lifecycle Marketing Manager")
        self.assertEqual(job["company_name"], "Acme")
        self.assertEqual(job["source_platform"], "remoteok")
        self.assertIsNone(job["source_job_id"])
        self.assertEqual(job["source_url"], "https://x.com/1")
        self.assertEqual(job["description"], "full posting text")

    @patch("scan_boards._run_node_provider", return_value=[])
    def test_no_results_returns_empty_list(self, mock_run):
        self.assertEqual(scan_boards.fetch_board_jobs(sources=["remoteok"]), [])

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    def test_missing_company_falls_back_to_provider_id_not_a_placeholder(self, mock_run, mock_fetch_text):
        # Regression: entry.name used to be a hardcoded "resume-builder-scan"
        # placeholder, which some providers (e.g. remoteok.mjs: `j.company
        # || entry.name`) use as their own company fallback -- that leaked
        # a fake company name into real JD data. Must be the provider id.
        mock_run.return_value = [
            {"title": "Marketing Coordinator", "url": "https://x.com/1", "location": "Remote"},
        ]
        jobs = scan_boards.fetch_board_jobs(sources=["remoteok"])
        self.assertEqual(jobs[0]["company_name"], "remoteok")

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider")
    def test_html_entities_decoded_in_title_and_company(self, mock_run, mock_fetch_text):
        mock_run.return_value = [
            {"title": "Growth &amp; Marketing Manager", "url": "https://x.com/1",
             "company": "Rose, Klein &amp; Marias", "location": "Remote"},
        ]
        jobs = scan_boards.fetch_board_jobs(sources=["remoteok"])
        self.assertEqual(jobs[0]["job_title"], "Growth & Marketing Manager")
        self.assertEqual(jobs[0]["company_name"], "Rose, Klein & Marias")

    @patch("scan_boards._run_node_provider", return_value=[
        {"title": "https://phase.community/job_role/physical-fitness", "url": "https://x.com/1", "location": ""},
    ])
    def test_url_shaped_title_is_dropped(self, mock_run):
        self.assertEqual(scan_boards.fetch_board_jobs(sources=["remoteok"]), [])

    @patch("scan_boards._fetch_posting_text")
    @patch("scan_boards._run_node_provider")
    def test_provider_supplied_description_used_instead_of_fetching_page(self, mock_run, mock_fetch_text):
        # himalayas.app's own posting pages sit behind a Cloudflare
        # challenge -- when a provider's API already returns a
        # description, use it and skip the page fetch entirely.
        mock_run.return_value = [
            {"title": "Marketing Coordinator", "url": "https://x.com/1", "location": "Remote",
             "description": "<p>Full <b>HTML</b> description &amp; details</p><p>Second line<br>after a break</p>"},
        ]
        jobs = scan_boards.fetch_board_jobs(sources=["himalayas"])
        self.assertEqual(jobs[0]["description"], "Full HTML description & details Second line\nafter a break")
        mock_fetch_text.assert_not_called()

    @patch("scan_boards._fetch_posting_text", return_value="fallback text")
    @patch("scan_boards._run_node_provider")
    def test_falls_back_to_page_fetch_when_provider_has_no_description(self, mock_run, mock_fetch_text):
        mock_run.return_value = [
            {"title": "Marketing Coordinator", "url": "https://x.com/1", "location": "Remote"},
        ]
        jobs = scan_boards.fetch_board_jobs(sources=["fourdayweek"])
        self.assertEqual(jobs[0]["description"], "fallback text")
        mock_fetch_text.assert_called_once_with("https://x.com/1")

    @patch("scan_boards._fetch_posting_text", return_value="")
    @patch("scan_boards._run_node_provider", return_value=[])
    def test_search_term_passed_per_provider_entry(self, mock_run, mock_fetch_text):
        scan_boards.fetch_board_jobs(sources=["remoteok", "remotive"], search_term="marketing")
        self.assertEqual(mock_run.call_args_list[0].args, ("remoteok", {"name": "remoteok", "search_term": "marketing"}))
        self.assertEqual(mock_run.call_args_list[1].args, ("remotive", {"name": "remotive", "search_term": "marketing"}))


class TestRunNodeProvider(unittest.TestCase):

    @patch("subprocess.run")
    def test_nonzero_exit_returns_empty_list_not_an_exception(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
        self.assertEqual(scan_boards._run_node_provider("remoteok", {}), [])

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="node", timeout=30))
    def test_timeout_returns_empty_list_not_an_exception(self, mock_run):
        self.assertEqual(scan_boards._run_node_provider("remoteok", {}), [])


if __name__ == "__main__":
    unittest.main()
