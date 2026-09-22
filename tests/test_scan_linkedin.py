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
    """P7F10: _fetch_personalized_extras() carries the operator's real li_at
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
            '[dim]Found[/dim] "[#9ab63f]Data Engineer[/#9ab63f]" @ [dim]Acme[/dim]',
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

    def test_build_queries_plain_string_defaults_to_remote_us(self):
        """A plain string entry keeps the original remote/US behavior."""
        [query] = scan_linkedin._build_queries(10, ["Marketing Director"])
        self.assertEqual(query.options.locations, ["United States"])
        self.assertEqual(
            query.options.filters.on_site_or_remote,
            [scan_linkedin.OnSiteOrRemoteFilters.REMOTE],
        )

    def test_build_queries_dict_entry_uses_workplace_mode_and_location(self):
        """A dict entry can override workplace_mode and location, e.g. a
        local search that wants hybrid/onsite roles near a specific city
        instead of a nationwide remote search."""
        [query] = scan_linkedin._build_queries(
            10,
            [
                {
                    "query": "Office Manager",
                    "workplace_mode": ["hybrid", "onsite"],
                    "location": "Williamsville, NY",
                }
            ],
        )
        self.assertEqual(query.query, "Office Manager")
        self.assertEqual(query.options.locations, ["Williamsville, NY"])
        self.assertCountEqual(
            query.options.filters.on_site_or_remote,
            [
                scan_linkedin.OnSiteOrRemoteFilters.HYBRID,
                scan_linkedin.OnSiteOrRemoteFilters.ON_SITE,
            ],
        )

    def test_build_queries_dict_entry_without_overrides_uses_defaults(self):
        """A dict entry that omits workplace_mode/location still falls back
        to the same remote/US defaults as a plain string."""
        [query] = scan_linkedin._build_queries(10, [{"query": "Office Manager"}])
        self.assertEqual(query.options.locations, ["United States"])
        self.assertEqual(
            query.options.filters.on_site_or_remote,
            [scan_linkedin.OnSiteOrRemoteFilters.REMOTE],
        )

    def test_build_queries_uses_default_experience_and_type_filters(self):
        """With no per-profile overrides, the resolved filters match the
        original hardcoded defaults."""
        with (
            patch(
                "scan_linkedin.content_settings.read_linkedin_experience_levels",
                return_value=list(
                    scan_linkedin.content_settings.DEFAULT_LINKEDIN_EXPERIENCE_LEVELS
                ),
            ),
            patch("scan_linkedin.content_settings.read_settings", return_value={}),
        ):
            [query] = scan_linkedin._build_queries(10, ["Marketing Director"])
        self.assertCountEqual(
            query.options.filters.experience,
            [
                scan_linkedin.ExperienceLevelFilters.ENTRY_LEVEL,
                scan_linkedin.ExperienceLevelFilters.ASSOCIATE,
                scan_linkedin.ExperienceLevelFilters.MID_SENIOR,
            ],
        )
        self.assertCountEqual(
            query.options.filters.type,
            [
                scan_linkedin.TypeFilters.FULL_TIME,
                scan_linkedin.TypeFilters.PART_TIME,
                scan_linkedin.TypeFilters.CONTRACT,
                scan_linkedin.TypeFilters.TEMPORARY,
            ],
        )

    def test_build_queries_honors_profile_experience_and_employment_overrides(self):
        with (
            patch(
                "scan_linkedin.content_settings.read_linkedin_experience_levels",
                return_value=["director", "executive"],
            ),
            patch(
                "scan_linkedin.content_settings.read_settings",
                return_value={"employment_type": ["contract_to_hire", "internship"]},
            ),
        ):
            [query] = scan_linkedin._build_queries(10, ["Marketing Director"])
        self.assertCountEqual(
            query.options.filters.experience,
            [
                scan_linkedin.ExperienceLevelFilters.DIRECTOR,
                scan_linkedin.ExperienceLevelFilters.EXECUTIVE,
            ],
        )
        self.assertCountEqual(
            query.options.filters.type,
            [scan_linkedin.TypeFilters.CONTRACT, scan_linkedin.TypeFilters.INTERNSHIP],
        )

    def test_muted_scraper_logger_silences_and_restores_level(self):
        """The li:scraper logger is silenced for the duration of the
        context and restored to whatever it was before, even on error."""
        import logging

        scraper_logger = logging.getLogger("li:scraper")
        scraper_logger.setLevel(logging.INFO)
        try:
            with scan_linkedin._muted_scraper_logger():
                self.assertGreater(scraper_logger.level, logging.CRITICAL)
            self.assertEqual(scraper_logger.level, logging.INFO)

            with self.assertRaises(ValueError):
                with scan_linkedin._muted_scraper_logger():
                    raise ValueError("boom")
            self.assertEqual(scraper_logger.level, logging.INFO)
        finally:
            scraper_logger.setLevel(logging.NOTSET)

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
    @patch("subprocess.run")
    @patch("questionary.select")
    def test_get_li_at_cookie_visual_browser_login_success(
        self, mock_select, mock_subproc, mock_root, mock_check_live
    ):
        """Test Playwright visual browser window login helper."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            mock_select.return_value.ask.return_value = "(Recommended) Log in securely via a visual browser window (automatic capture)"
            mock_subproc.return_value = MagicMock(
                returncode=0,
                stdout='{"success": true, "cookie": "playwright-captured-token"}',
            )

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "playwright-captured-token")
            # Verify cached to disk
            cookie_path = os.path.join(tmpdir, ".linkedin_cookie")
            self.assertTrue(os.path.isfile(cookie_path))
            with open(cookie_path, "r") as f:
                self.assertEqual(f.read().strip(), "playwright-captured-token")

    @patch("scan_linkedin.check_li_cookie_live", return_value=True)
    @patch("scan_linkedin.profile_paths.profile_root")
    @patch("questionary.text")
    @patch("questionary.select")
    def test_get_li_at_cookie_manual_paste_with_curl(
        self, mock_select, mock_text, mock_root, mock_check_live
    ):
        """Test manual paste flow extracting li_at from pasted curl command."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_root.return_value = tmpdir
            mock_select.return_value.ask.return_value = "Paste 'li_at' cookie value (or a Chrome DevTools curl command) manually"
            mock_text.return_value.ask.return_value = "curl 'https://www.linkedin.com/feed/' -H 'Cookie: bcookie=1; li_at=manual-token-123; JSESSIONID=456'"

            cookie = scan_linkedin.get_li_at_cookie()
            self.assertEqual(cookie, "manual-token-123")

    def test_browser_cookie3_not_in_runtime(self):
        """Verify browser_cookie3 is completely decoupled and not referenced in scan_linkedin."""
        self.assertFalse(hasattr(scan_linkedin, "_extract_chrome_cookie"))
        self.assertNotIn("browser_cookie3", dir(scan_linkedin))


if __name__ == "__main__":
    unittest.main()


class TestScanLinkedinAbandonedRun(unittest.TestCase):
    """The library offers no way to cancel a run: scraper.run() blocks on
    its own thread pool, so a timeout can only abandon the thread waiting
    on it. Unchecked, that abandoned run kept driving Chrome and kept
    firing Events.DATA into a caller that had already returned -- results
    printing into whatever screen the user had moved on to, long after the
    scan reported itself finished. These tests pin the guards that stop
    it."""

    def _job_data(self, title="Late Role", company="Acme"):
        return MagicMock(
            title=title,
            company=company,
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
    def test_a_result_arriving_after_the_scan_is_dropped_silently(
        self, mock_scraper_cls, mock_profile, mock_cookie, mock_extras
    ):
        mock_scraper = mock_scraper_cls.return_value
        registered = {}
        mock_scraper.on.side_effect = lambda event, handler: registered.update(
            {event: handler}
        )
        mock_scraper.run.side_effect = lambda queries: registered[
            scan_linkedin.Events.DATA
        ](self._job_data(title="In Time"))

        activity = MagicMock()
        jobs = scan_linkedin.fetch_linkedin_jobs(activity=activity)
        self.assertEqual(["In Time"], [j["job_title"] for j in jobs])
        calls_during_scan = activity.step.call_count

        # Exactly what an abandoned worker does: fire DATA after the
        # function has returned.
        registered[scan_linkedin.Events.DATA](self._job_data(title="Too Late"))

        # It must not reach the screen -- that is the reported bug ...
        self.assertEqual(calls_during_scan, activity.step.call_count)
        # ... and it must not reach the list the caller already holds.
        self.assertEqual(["In Time"], [j["job_title"] for j in jobs])

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
    def test_returns_a_copy_the_scraper_cannot_still_grow(
        self, mock_scraper_cls, mock_profile, mock_cookie, mock_extras
    ):
        mock_scraper = mock_scraper_cls.return_value
        registered = {}
        mock_scraper.on.side_effect = lambda event, handler: registered.update(
            {event: handler}
        )
        mock_scraper.run.side_effect = lambda queries: registered[
            scan_linkedin.Events.DATA
        ](self._job_data())

        first = scan_linkedin.fetch_linkedin_jobs()
        second = scan_linkedin.fetch_linkedin_jobs()
        # Two scans must not share a list; a stale reference growing under
        # the caller is how a result set changes size mid-iteration.
        self.assertIsNot(first, second)
        self.assertEqual(1, len(first))

    @patch("scan_linkedin.get_li_at_cookie", return_value="fake-li-at")
    @patch(
        "scan_linkedin.profile_paths.profile_yaml",
        return_value={"target_roles": {"primary": ["Data Engineer"]}},
    )
    @patch("scan_linkedin.LinkedinScraper")
    def test_listeners_are_disconnected_when_the_run_ends(
        self, mock_scraper_cls, mock_profile, mock_cookie
    ):
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.run.side_effect = lambda queries: None
        scan_linkedin.fetch_linkedin_jobs()
        mock_scraper.remove_all_listeners.assert_called_once()

    def test_stop_scraper_cancels_queued_queries_only_on_a_timeout(self):
        # A clean run's queries are all finished; cancelling its pool would
        # be pointless, and shutting down a healthy pool is not free.
        clean = MagicMock()
        scan_linkedin._stop_scraper(clean, timed_out=False)
        clean._pool.shutdown.assert_not_called()

        # An abandoned run's remaining SEARCH TERMS are the part that can
        # still be stopped -- the in-flight page cannot be.
        hung = MagicMock()
        scan_linkedin._stop_scraper(hung, timed_out=True)
        hung._pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)

    def test_stop_scraper_never_raises_over_a_failed_teardown(self):
        # It runs while we are already reporting a timeout; a traceback
        # here would replace that report.
        broken = MagicMock()
        broken.remove_all_listeners.side_effect = RuntimeError("boom")
        broken._pool.shutdown.side_effect = RuntimeError("boom")
        scan_linkedin._stop_scraper(broken, timed_out=True)

        no_pool = MagicMock(spec=["remove_all_listeners"])
        scan_linkedin._stop_scraper(no_pool, timed_out=True)
