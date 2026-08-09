import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import scan_boards  # noqa: E402


class TestChildEnv(unittest.TestCase):

    def test_strips_secrets_but_keeps_provider_credentials(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "secret-key", "JOBRIGHT_COOKIE_STRING": "secret-cookie",
            "ADZUNA_APP_KEY": "real-provider-credential", "PATH": os.environ.get("PATH", ""),
        }):
            child_env = scan_boards._child_env()
        self.assertNotIn("GEMINI_API_KEY", child_env)
        self.assertNotIn("JOBRIGHT_COOKIE_STRING", child_env)
        self.assertEqual(child_env["ADZUNA_APP_KEY"], "real-provider-credential")
        self.assertIn("PATH", child_env)


class TestFormatDuration(unittest.TestCase):

    def test_seconds_only(self):
        self.assertEqual(scan_boards._format_duration(45), "45s")

    def test_minutes_and_seconds(self):
        self.assertEqual(scan_boards._format_duration(125), "2m05s")

    def test_hours_and_minutes(self):
        self.assertEqual(scan_boards._format_duration(3725), "1h02m")

    def test_negative_clamps_to_zero(self):
        self.assertEqual(scan_boards._format_duration(-5), "0s")


class TestProgressReporter(unittest.TestCase):

    def test_no_eta_on_first_step(self):
        reporter = scan_boards.ProgressReporter(3, label="Checking")
        with patch("cli_art.console.print") as mock_print:
            reporter.step("Acme")
        mock_print.assert_called_once_with("  [1/3] Checking Acme...", markup=False, soft_wrap=True)

    def test_eta_appears_from_second_step_on(self):
        reporter = scan_boards.ProgressReporter(3, label="Checking")
        with patch("cli_art.console.print"):
            reporter.step("Acme")
        with patch("cli_art.console.print") as mock_print:
            reporter.step("Widgets Inc")
        printed = mock_print.call_args[0][0]
        self.assertIn("[2/3] Checking Widgets Inc...", printed)
        self.assertIn("remaining)", printed)


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
        mock_fetch_text.assert_called_once_with("https://x.com/1", "fourdayweek")

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

    @patch("scan_boards._scan_warning")
    @patch("subprocess.run")
    def test_error_envelope_kind_used_instead_of_guessing_from_stderr(self, mock_run, mock_warn):
        # run_provider.mjs (B27, docs/review/phase-9-backlog.md) writes a
        # JSON error envelope to stdout on every failure path -- a specific
        # kind should now win over the old stderr-last-line heuristic.
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='{"error":{"kind":"auth","message":"websearch: BRAVE_API_KEY is not set."}}',
            stderr="websearch: BRAVE_API_KEY is not set.\nAdd it to your .env file.",
        )
        self.assertEqual(scan_boards._run_node_provider("websearch", {}), [])
        mock_warn.assert_called_once()
        _, kwargs = mock_warn.call_args
        self.assertEqual(kwargs["kind"], "auth")
        self.assertEqual(kwargs["reason"], "websearch: BRAVE_API_KEY is not set.")

    @patch("scan_boards._scan_warning")
    @patch("subprocess.run")
    def test_falls_back_to_stderr_reason_when_stdout_is_not_an_envelope(self, mock_run, mock_warn):
        # A crash before run_provider.mjs's own handlers run (e.g. the node
        # binary itself missing, or something throwing before main()) can
        # still leave stdout empty or non-JSON -- must not raise, and must
        # fall back to the pre-B27 behavior.
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some raw crash\nlast line")
        self.assertEqual(scan_boards._run_node_provider("remoteok", {}), [])
        _, kwargs = mock_warn.call_args
        self.assertEqual(kwargs["kind"], "provider_failed")
        self.assertEqual(kwargs["reason"], "last line")


class TestParseErrorEnvelope(unittest.TestCase):

    def test_valid_envelope(self):
        self.assertEqual(
            scan_boards._parse_error_envelope('{"error":{"kind":"quota","message":"rate limited"}}'),
            {"kind": "quota", "message": "rate limited"},
        )

    def test_not_json_returns_none(self):
        self.assertIsNone(scan_boards._parse_error_envelope("not json at all"))

    def test_json_without_error_key_returns_none(self):
        self.assertIsNone(scan_boards._parse_error_envelope('[{"title": "a job"}]'))

    def test_error_without_kind_returns_none(self):
        self.assertIsNone(scan_boards._parse_error_envelope('{"error":{"message":"oops"}}'))


class TestFlagThinDescription(unittest.TestCase):

    @patch("scan_boards._scan_warning")
    def test_thin_description_gets_scan_metadata_and_a_warning(self, mock_warn):
        job = {"description": "too short"}
        scan_boards._flag_thin_description(job, "workday", "https://x.com/1")
        self.assertEqual(job["_scan"], {"thin_description": True, "description_chars": 9})
        mock_warn.assert_called_once()
        _, kwargs = mock_warn.call_args
        self.assertEqual(kwargs["kind"], "thin_description")
        self.assertEqual(kwargs["provider_id"], "workday")

    @patch("scan_boards._scan_warning")
    def test_empty_description_reason_says_empty_not_zero_chars(self, mock_warn):
        job = {"description": ""}
        scan_boards._flag_thin_description(job, "workday", "https://x.com/1")
        _, kwargs = mock_warn.call_args
        self.assertEqual(kwargs["reason"], "empty")

    @patch("scan_boards._scan_warning")
    def test_missing_description_key_is_treated_as_empty(self, mock_warn):
        job = {}
        scan_boards._flag_thin_description(job, "workday", "https://x.com/1")
        self.assertEqual(job["_scan"]["description_chars"], 0)

    @patch("scan_boards._scan_warning")
    def test_long_enough_description_is_left_alone(self, mock_warn):
        job = {"description": "x" * 300}
        scan_boards._flag_thin_description(job, "greenhouse", "https://x.com/1")
        self.assertNotIn("_scan", job)
        mock_warn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
