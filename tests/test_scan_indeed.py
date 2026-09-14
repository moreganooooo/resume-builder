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

# _admit_indeed_job() reads the ACTIVE profile's real scan_filters.yml
# through scan_boards' cache, so every test here that isn't about admission
# runs with it switched off -- otherwise a fixture row's "Buffalo, NY"
# passes or fails depending on whose profile is active.
_real_admit = scan_indeed._admit_indeed_job
_admit_patcher = patch("scan_indeed._admit_indeed_job", return_value=True)


def setUpModule():
    _admit_patcher.start()


def tearDownModule():
    _admit_patcher.stop()


class TestIndeedAdmission(unittest.TestCase):
    """Indeed results now pass the excluded-title and location gates the
    other sources apply."""

    JOB = {"job_title": "Marketing Manager", "location": "Buffalo, NY", "is_remote": False}

    def _admit(self, job, excluded=False, location_ok=True):
        with (
            patch("scan_boards._hits_excluded_title", return_value=excluded),
            patch("scan_boards._passes_location_filter", return_value=location_ok),
        ):
            return _real_admit(job)

    def test_clean_local_listing_is_kept(self):
        self.assertTrue(self._admit(self.JOB))

    def test_excluded_title_is_dropped(self):
        self.assertFalse(self._admit(dict(self.JOB, job_title="Marketing Manager - Clinical"), excluded=True))

    def test_listing_outside_the_radius_is_dropped(self):
        self.assertFalse(self._admit(self.JOB, location_ok=False))

    def test_unreadable_filters_keep_the_listing(self):
        with patch("scan_boards._hits_excluded_title", side_effect=FileNotFoundError):
            self.assertTrue(_real_admit(self.JOB))


SETTINGS = {
    "city": "Springfield",
    "state": "IL",
    "zip": "62701",
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
        self.assertEqual(scan_indeed._origin_from_settings(SETTINGS), "Springfield, IL")

    def test_falls_back_to_zip(self):
        # Unlike Jooble's API, Indeed resolves a bare postal code fine.
        self.assertEqual(scan_indeed._origin_from_settings({"zip": "62701"}), "62701")

    def test_empty_settings(self):
        self.assertEqual(scan_indeed._origin_from_settings({}), "")


class TestDefaultSearchTerm(unittest.TestCase):
    """Regression coverage: scan.run_scan() never threads a search_term
    through to any fetcher (every real call site invokes
    fetch(activity=activity) only), so DEFAULT_SEARCH_TERM ("marketing")
    was silently what every real Indeed scan searched for, on every
    profile, regardless of that profile's actual target roles."""

    def setUp(self):
        import tempfile

        self._tmp_dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self._tmp_dir, ignore_errors=True)
        self._scan_filters_path = os.path.join(self._tmp_dir, "scan_filters.yml")
        patcher = patch(
            "scan_indeed.profile_paths.board_scanner_dir",
            return_value=self._tmp_dir,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_filters(self, positive):
        import yaml

        with open(self._scan_filters_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"title_filter": {"positive": positive}}, f)

    def test_uses_all_positive_titles_up_to_the_cap(self):
        self._write_filters(["Data Scientist", "Machine Learning Engineer"])
        self.assertEqual(
            scan_indeed._default_search_terms(),
            ["Data Scientist", "Machine Learning Engineer"],
        )

    def test_caps_at_max_search_terms(self):
        self._write_filters(["A", "B", "C", "D", "E"])
        terms = scan_indeed._default_search_terms()
        self.assertEqual(len(terms), scan_indeed.MAX_SEARCH_TERMS)
        self.assertEqual(terms, ["A", "B", "C"])

    def test_blank_yaml_items_never_become_the_word_none(self):
        self._write_filters([None, "  ", "Marketing"])
        self.assertEqual(scan_indeed._default_search_terms(), ["Marketing"])

    def test_falls_back_when_no_positive_titles_configured(self):
        self._write_filters([])
        self.assertEqual(
            scan_indeed._default_search_terms(), [scan_indeed.DEFAULT_SEARCH_TERM]
        )

    def test_explicit_indeed_search_terms_win_and_are_capped(self):
        import yaml

        with open(self._scan_filters_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "indeed_search_terms": ["communications", None, "content", "copywriter", "x"],
                    "title_filter": {"positive": ["Data Scientist"]},
                },
                f,
            )
        self.assertEqual(
            scan_indeed._default_search_terms(), ["communications", "content", "copywriter"]
        )

    def test_falls_back_when_scan_filters_missing(self):
        self.assertEqual(
            scan_indeed._default_search_terms(), [scan_indeed.DEFAULT_SEARCH_TERM]
        )

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_fetch_indeed_jobs_covers_every_configured_target_role(self, _):
        self._write_filters(["Data Scientist", "Machine Learning Engineer"])
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            scan_indeed.fetch_indeed_jobs()
        terms_called = [c.kwargs["search_term"] for c in fake.call_args_list]
        self.assertEqual(terms_called, ["Data Scientist", "Machine Learning Engineer"])

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_explicit_search_term_still_wins(self, _):
        self._write_filters(["Data Scientist"])
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            scan_indeed.fetch_indeed_jobs(search_term="Tesla")
        self.assertEqual(fake.call_args.kwargs["search_term"], "Tesla")


class TestMultiTermDedup(unittest.TestCase):
    """The same posting can legitimately surface under more than one
    title query -- dedup by source_url is what keeps a two-title profile
    from getting duplicate JD files."""

    def setUp(self):
        import tempfile

        self._tmp_dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self._tmp_dir, ignore_errors=True)
        patcher = patch(
            "scan_indeed.profile_paths.board_scanner_dir",
            return_value=self._tmp_dir,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        import yaml

        with open(
            os.path.join(self._tmp_dir, "scan_filters.yml"), "w", encoding="utf-8"
        ) as f:
            yaml.safe_dump(
                {"title_filter": {"positive": ["Data Scientist", "ML Engineer"]}}, f
            )

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_same_url_across_terms_is_deduped(self, _):
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual(fake.call_count, 2)
        self.assertEqual(len(jobs), 1)

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_distinct_urls_across_terms_are_both_kept(self, _):
        other_row = dict(ROW, job_url="https://indeed.com/viewjob?jk=2")
        fake = MagicMock(side_effect=[frame_of([ROW]), frame_of([other_row])])
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual(len(jobs), 2)

    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_url_less_listings_are_not_false_duplicates(self, _):
        batches = [[{"source_url": "", "job_title": "A"}], [{"source_url": "", "job_title": "B"}]]
        with patch.object(scan_indeed, "_scrape_one_term", side_effect=batches):
            jobs = scan_indeed.fetch_indeed_jobs()
        self.assertEqual([j["job_title"] for j in jobs], ["A", "B"])


class TestFetchIndeedJobs(unittest.TestCase):
    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_location_and_radius_reach_jobspy(self, _):
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            scan_indeed.fetch_indeed_jobs()
        kwargs = fake.call_args.kwargs
        self.assertEqual(kwargs["location"], "Springfield, IL")
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

    def test_indeed_tesla_is_a_separate_scan_source(self):
        import scan

        self.assertIn("indeed_tesla", scan.SOURCE_FETCHERS)
        self.assertIs(
            scan.SOURCE_FETCHERS["indeed_tesla"], scan_indeed.fetch_indeed_tesla_jobs
        )
        # A distinct source, not an alias for the profile's default search.
        self.assertIsNot(
            scan.SOURCE_FETCHERS["indeed_tesla"], scan.SOURCE_FETCHERS["indeed"]
        )


class TestFetchIndeedTeslaJobs(unittest.TestCase):
    @patch("location_settings.read_settings", return_value=SETTINGS)
    def test_searches_for_tesla_regardless_of_target_roles(self, _):
        fake = MagicMock(return_value=frame_of([ROW]))
        with patch.dict("sys.modules", {"jobspy": MagicMock(scrape_jobs=fake)}):
            scan_indeed.fetch_indeed_tesla_jobs()
        self.assertEqual(fake.call_args.kwargs["search_term"], "Tesla")


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
