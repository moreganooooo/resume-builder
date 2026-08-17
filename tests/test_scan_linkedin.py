import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import scan_linkedin  # noqa: E402


class TestFetchPersonalizedExtrasPacing(unittest.TestCase):
    """P7F10: _fetch_personalized_extras() carries Morgan's real li_at
    session cookie on every call and used to fire back-to-back with no
    pacing -- the one place in this subsystem with real account-ban risk.
    These tests prove the fix (a time.sleep() matching the scraper's own
    slow_mo) actually fires, without ever making a real network call."""

    def _mock_response(self, status_code=200, text="<html></html>"):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        return response

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_sleeps_after_a_successful_request(self, mock_session_cls, mock_sleep):
        mock_session_cls.return_value.get.return_value = self._mock_response()

        scan_linkedin._fetch_personalized_extras(
            "https://linkedin.com/jobs/view/1", "cookie-value"
        )

        mock_sleep.assert_called_once_with(
            scan_linkedin._PERSONALIZED_EXTRAS_DELAY_SECONDS
        )

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_sleeps_even_when_the_request_raises(self, mock_session_cls, mock_sleep):
        mock_session_cls.return_value.get.side_effect = Exception("timeout")

        scan_linkedin._fetch_personalized_extras(
            "https://linkedin.com/jobs/view/1", "cookie-value"
        )

        mock_sleep.assert_called_once_with(
            scan_linkedin._PERSONALIZED_EXTRAS_DELAY_SECONDS
        )

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_does_not_sleep_or_hit_the_network_without_a_job_url(
        self, mock_session_cls, mock_sleep
    ):
        scan_linkedin._fetch_personalized_extras("", "cookie-value")

        mock_session_cls.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_does_not_sleep_or_hit_the_network_without_a_cookie(
        self, mock_session_cls, mock_sleep
    ):
        scan_linkedin._fetch_personalized_extras("https://linkedin.com/jobs/view/1", "")

        mock_session_cls.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_still_sleeps_on_a_non_200_response(self, mock_session_cls, mock_sleep):
        mock_session_cls.return_value.get.return_value = self._mock_response(
            status_code=999
        )

        scan_linkedin._fetch_personalized_extras(
            "https://linkedin.com/jobs/view/1", "cookie-value"
        )

        mock_sleep.assert_called_once_with(
            scan_linkedin._PERSONALIZED_EXTRAS_DELAY_SECONDS
        )


class TestFetchLinkedinJobsActivity(unittest.TestCase):

    @patch(
        "scan_linkedin._fetch_personalized_extras",
        return_value={"is_top_applicant": False, "backup_description": None},
    )
    @patch("scan_linkedin.get_li_at_cookie", return_value="fake-li-at")
    @patch(
        "scan_linkedin.profile_paths.profile_yaml",
        return_value={"target_roles": {"primary": ["Data Engineer"]}},
    )
    @patch("scan_linkedin.LinkedinScraper")
    def test_steps_through_activity_on_each_result(
        self, mock_scraper_cls, mock_profile, mock_cookie, mock_extras
    ):
        mock_scraper = mock_scraper_cls.return_value
        registered = {}

        def fake_on(event, handler):
            registered[event] = handler

        mock_scraper.on.side_effect = fake_on

        def fake_run(queries):
            data = MagicMock(
                title="Data Engineer",
                company="Acme",
                link="https://linkedin.com/jobs/view/1",
                apply_link=None,
                place="Remote",
                date=None,
                date_text=None,
                employment_type=None,
                seniority_level=None,
                description="desc",
                description_html=None,
                skills=None,
                job_id="1",
                company_link=None,
            )
            registered[scan_linkedin.Events.DATA](data)

        mock_scraper.run.side_effect = fake_run

        activity = MagicMock()
        jobs = scan_linkedin.fetch_linkedin_jobs(activity=activity)

        self.assertEqual(len(jobs), 1)
        activity.step.assert_called_with(
            "success",
            "LinkedIn",
            '[dim]Found[/dim] "[#12C78F]Data Engineer[/#12C78F]" @ [dim]Acme[/dim]',
            preserve_markup=True,
        )


class TestScanLinkedinCookieAndQueries(unittest.TestCase):
    """Unit tests for cookie validation, cookie retrieval, and query building."""

    @patch("scan_linkedin.requests.Session")
    def test_check_li_cookie_live(self, mock_session_cls):
        """Test cookie liveness check on valid, invalid, and error responses."""
        self.assertFalse(scan_linkedin.check_li_cookie_live(""))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_session_cls.return_value.get.return_value = mock_resp
        self.assertTrue(scan_linkedin.check_li_cookie_live("valid-cookie"))

        mock_resp.status_code = 302
        self.assertFalse(scan_linkedin.check_li_cookie_live("expired-cookie"))

        mock_session_cls.return_value.get.side_effect = Exception("Network down")
        self.assertFalse(scan_linkedin.check_li_cookie_live("error-cookie"))

    def test_build_queries(self):
        """Test _build_queries constructs Query objects."""
        queries = scan_linkedin._build_queries(
            10, ["Marketing Director", "Content Strategist"]
        )
        self.assertEqual(len(queries), 2)
        self.assertEqual(queries[0].query, "Marketing Director")
        self.assertEqual(queries[1].query, "Content Strategist")

    @patch("scan_linkedin.check_li_cookie_live", return_value=True)
    @patch("scan_linkedin.profile_paths.profile_root")
    def test_get_li_at_cookie_cached(self, mock_root, mock_check_live):
        """Test get_li_at_cookie returns cached cookie when live."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            cookie_file = os.path.join(tmpdir, ".linkedin_cookie")
            with open(cookie_file, "w") as f:
                f.write("cached-secret-cookie")

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "cached-secret-cookie")

    @patch("scan_linkedin.check_li_cookie_live", return_value=True)
    @patch("scan_linkedin.profile_paths.profile_root")
    @patch("questionary.select")
    @patch("questionary.text")
    def test_get_li_at_cookie_paste_curl(
        self, mock_text, mock_select, mock_root, mock_check_live
    ):
        """Test pasting curl command containing li_at extracts token and caches it."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            mock_select.return_value.ask.return_value = "Paste 'li_at' cookie value (or a Chrome DevTools curl command) manually"
            mock_text.return_value.ask.return_value = "curl 'https://linkedin.com' -H 'Cookie: li_at=extracted-token-abc; other=123'"

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "extracted-token-abc")
            # Verify cached to file
            cookie_file = os.path.join(tmpdir, ".linkedin_cookie")
            self.assertTrue(os.path.exists(cookie_file))
            with open(cookie_file) as f:
                self.assertEqual(f.read(), "extracted-token-abc")

    @patch("scan_linkedin.check_li_cookie_live", return_value=True)
    @patch("scan_linkedin.profile_paths.profile_root")
    @patch("subprocess.run")
    @patch("questionary.select")
    def test_get_li_at_cookie_visual_browser(
        self, mock_select, mock_subproc, mock_root, mock_check_live
    ):
        """Test automated login capture via node script."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            mock_select.return_value.ask.return_value = "(Recommended) Log in securely via a visual browser window (automatic capture)"
            mock_subproc.return_value = MagicMock(
                returncode=0,
                stdout='{"success": true, "cookie": "node-captured-cookie"}\n',
            )

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "node-captured-cookie")

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_fetch_personalized_extras_top_applicant_and_backup_desc(
        self, mock_session_cls, mock_sleep
    ):
        """Test parsing top applicant chip and backup description from code block."""
        html = """
        <html>
            <svg id="premium-chip-v2-medium"></svg>
            <code style="display: none">{"description": "This is a backup job description."}</code>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_session_cls.return_value.get.return_value = mock_resp

        extras = scan_linkedin._fetch_personalized_extras(
            "https://linkedin.com/jobs/view/999", "cookie"
        )
        self.assertTrue(extras["is_top_applicant"])
        self.assertEqual(
            extras["backup_description"], "This is a backup job description."
        )

    @patch("scan_linkedin.profile_paths.profile_yaml", return_value={})
    def test_fetch_linkedin_jobs_empty_search_terms(self, mock_profile):
        """Test fetch_linkedin_jobs returns empty list if no queries are set."""
        jobs = scan_linkedin.fetch_linkedin_jobs()
        self.assertEqual(jobs, [])

    @patch(
        "scan_linkedin.profile_paths.profile_yaml",
        return_value={"linkedin_search_queries": ["Engineer"]},
    )
    @patch("scan_linkedin.get_li_at_cookie", return_value="")
    def test_fetch_linkedin_jobs_no_cookie(self, mock_cookie, mock_profile):
        """Test fetch_linkedin_jobs returns empty list if cookie is not provided."""
        jobs = scan_linkedin.fetch_linkedin_jobs()
        self.assertEqual(jobs, [])

    @patch("scan_linkedin.time.sleep")
    @patch(
        "scan_linkedin._fetch_personalized_extras",
        return_value={"is_top_applicant": False, "backup_description": None},
    )
    @patch("scan_linkedin.LinkedinScraper")
    @patch("scan_linkedin.get_li_at_cookie", return_value="fake-cookie")
    @patch(
        "scan_linkedin.profile_paths.profile_yaml",
        return_value={"target_roles": {"primary": ["Frontend Dev"]}},
    )
    def test_fetch_linkedin_jobs_callbacks_and_error(
        self, mock_profile, mock_cookie, mock_scraper_cls, mock_extras, mock_sleep
    ):
        """Test on_data, on_error, on_end, and scraper exception handling."""
        mock_scraper = mock_scraper_cls.return_value
        registered = {}

        def fake_on(event, handler):
            registered[event] = handler

        mock_scraper.on.side_effect = fake_on

        def fake_run(queries):
            # Job with external link
            data_ext = MagicMock(
                title="Frontend Dev",
                company="TechCorp",
                link="https://other.com",
                apply_link="https://apply.techcorp.com",
                place="New York, NY (Hybrid)",
                date="2026-08-01",
                date_text="1 day ago",
                employment_type="Full-time",
                seniority_level="Mid-Senior",
                description="great role",
                description_html="<p>great role</p>",
                skills=["React"],
                job_id="2",
                company_link="https://linkedin.com/company/techcorp",
            )
            # Job with unknown link
            data_unk = MagicMock(
                title="Designer",
                company="Studio",
                link="https://unknown.com",
                apply_link=None,
                place="Austin, TX",
                date=None,
                date_text=None,
                employment_type=None,
                seniority_level=None,
                description=None,
                description_html=None,
                skills=None,
                job_id="3",
                company_link=None,
            )
            registered[scan_linkedin.Events.DATA](data_ext)
            registered[scan_linkedin.Events.DATA](data_unk)
            registered[scan_linkedin.Events.ERROR]("Rate limit reached")
            registered[scan_linkedin.Events.END]()

        mock_scraper.run.side_effect = fake_run

        jobs = scan_linkedin.fetch_linkedin_jobs(activity=None)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["application_type"], "external")
        self.assertEqual(jobs[0]["work_model"], "Hybrid")
        self.assertEqual(jobs[1]["application_type"], "unknown")
        self.assertEqual(jobs[1]["work_model"], "Onsite")

        # Scraper run raising exception
        mock_scraper.run.side_effect = Exception("Browser crashed")
        jobs_err = scan_linkedin.fetch_linkedin_jobs(activity=None)
        self.assertEqual(jobs_err, [])

    @patch("scan_linkedin.check_li_cookie_live")
    @patch("scan_linkedin.profile_paths.profile_root")
    @patch("questionary.select")
    def test_get_li_at_cookie_expired_and_cancelled(
        self, mock_select, mock_root, mock_check_live
    ):
        """Test expired cached cookie falls through to prompt, and user cancellation."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            cookie_file = os.path.join(tmpdir, ".linkedin_cookie")
            with open(cookie_file, "w") as f:
                f.write("expired-cookie")
            mock_check_live.return_value = False
            mock_select.return_value.ask.return_value = None

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "")

    @patch("scan_linkedin.check_li_cookie_live", return_value=True)
    @patch("scan_linkedin.profile_paths.profile_root")
    @patch("scan_linkedin.browser_cookie3.chrome")
    @patch("questionary.select")
    def test_get_li_at_cookie_chrome_extraction(
        self, mock_select, mock_chrome, mock_root, mock_check_live
    ):
        """Test Chrome cookie jar extraction."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            mock_select.return_value.ask.return_value = "Extract automatically from Google Chrome (triggers macOS Keychain prompt)"
            cookie_obj = MagicMock()
            cookie_obj.name = "li_at"
            cookie_obj.value = "chrome-extracted-cookie"
            mock_chrome.return_value = [cookie_obj]

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "chrome-extracted-cookie")


if __name__ == "__main__":
    unittest.main()
