"""Tests for scripts/scan_indeed.py -- Indeed via JobSpy.

Network is always mocked. These assert the call SHAPE (location and
radius actually reach JobSpy) and the normalization, including the
pandas NaN trap that would otherwise write the literal string "nan"
into a JD file.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import scan_indeed  # noqa: E402

SETTINGS = {
    "city": "Getzville",
    "state": "NY",
    "zip": "14068",
    "radius_miles": 25,
    "workplace_mode": "any",
}


def frame_of(rows):
    """A minimal stand-in for the DataFrame JobSpy returns."""
    frame = MagicMock()
    frame.__len__.return_value = len(rows)
    frame.iterrows.return_value = [(i, row) for i, row in enumerate(rows)]
    return frame


ROW = {
    "title": "Marketing Manager",
    "company": "Acme",
    "job_url": "https://indeed.com/viewjob?jk=1",
    "location": "Buffalo, NY, US",
    "description": "x" * 4000,
    "date_posted": "2026-08-20",
    "id": "in-1",
    "is_remote": False,
}


class TestOriginResolution(unittest.TestCase):
    def test_prefers_city_state(self):
        self.assertEqual(scan_indeed._origin_from_settings(SETTINGS), "Getzville, NY")

    def test_falls_back_to_zip(self):
        # Unlike Jooble's API, Indeed resolves a bare postal code fine.
        self.assertEqual(scan_indeed._origin_from_settings({"zip": "14068"}), "14068")

    def test_empty_settings(self):
        self.assertEqual(scan_indeed._origin_from_settings({}), "")


class TestFetchIndeedJobs(unittest.TestCase):
    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_location_and_radius_reach_jobspy(self, _):
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            scan_indeed.fetch_indeed_jobs()
        kwargs = fake.call_args.kwargs
        self.assertEqual(kwargs["location"], "Getzville, NY")
        self.assertEqual(kwargs["distance"], 25)
        self.assertEqual(kwargs["site_name"], ["indeed"])

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_normalizes_to_the_shared_job_shape(self, _):
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["job_title"], "Marketing Manager")
        self.assertEqual(job["company_name"], "Acme")
        self.assertEqual(job["source_platform"], "indeed")
        self.assertEqual(job["location"], "Buffalo, NY, US")
        # Indeed returns the real body, so it is NOT marked a teaser the
        # way jooble/adzuna are.
        self.assertNotIn("description_is_teaser", job)
        self.assertNotIn("_scan", job)

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_nan_never_reaches_a_job_field(self, _):
        # pandas yields NaN for missing cells; str(NaN) is the literal
        # "nan", which would land in a JD file as if it were real text.
        # A NaN company is a separate case -- those rows are skipped
        # outright (see TestMissingEmployer) -- so this uses fields where
        # empty is a legitimate value.
        row = dict(ROW, date_posted=float("nan"), location=float("nan"))
        fake = MagicMock(return_value=frame_of([row]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual(jobs[0]["posted_at"], "")
        self.assertEqual(jobs[0]["location"], "")

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_rows_without_a_title_or_url_are_dropped(self, _):
        rows = [dict(ROW, title=""), dict(ROW, job_url=""), ROW]
        fake = MagicMock(return_value=frame_of(rows))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual(len(jobs), 1)

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_thin_description_uses_the_shared_flag(self, _):
        row = dict(ROW, description="too short")
        fake = MagicMock(return_value=frame_of([row]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertTrue(jobs[0]["_scan"]["thin_description"])

    @patch("location_settings.read_settings", return_value={})
    def test_no_configured_location_returns_empty(self, _):
        # Without an origin there is no local search to make; skip
        # rather than silently scraping the whole country.
        self.assertEqual(scan_indeed.fetch_indeed_jobs(), [])

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_scrape_failure_degrades_to_empty(self, _):
        # Scraping is fragile by nature -- a block or a layout change
        # must not abort the whole scan run.
        fake = MagicMock(side_effect=RuntimeError("blocked"))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            self.assertEqual(scan_indeed.fetch_indeed_jobs(), [])

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_empty_result_set_is_not_an_error(self, _):
        fake = MagicMock(return_value=frame_of([]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            self.assertEqual(scan_indeed.fetch_indeed_jobs(), [])

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_remote_flag_preserved_as_tristate(self, _):
        rows = [dict(ROW, is_remote=True), dict(ROW, is_remote=None)]
        fake = MagicMock(return_value=frame_of(rows))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertIs(jobs[0]["is_remote"], True)
        # None, not False -- "not stated" is not "on-site".
        self.assertIsNone(jobs[1]["is_remote"])


class TestSourceRegistration(unittest.TestCase):
    def test_indeed_is_a_scan_source(self):
        import scan

        self.assertIn("indeed", scan.SOURCE_FETCHERS)
        self.assertIs(scan.SOURCE_FETCHERS["indeed"], scan_indeed.fetch_indeed_jobs)


if __name__ == "__main__":
    unittest.main()


class TestMissingEmployer(unittest.TestCase):
    """Indeed returns no company at all for some postings."""

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_rows_without_a_company_are_skipped(self, _):
        # A JD with no employer cannot be researched, addressed, or
        # deduped, and renders as a blank dashboard row.
        rows = [dict(ROW, company=float("nan")), dict(ROW, company=""), ROW]
        fake = MagicMock(return_value=frame_of(rows))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company_name"], "Acme")
