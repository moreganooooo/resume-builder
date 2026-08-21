"""
scan_indeed.py -- Indeed as a first-class scan source, via JobSpy.

Why this is a Python source rather than a board-scanners/providers/*.mjs
plugin: Indeed has no free public API, and the only maintained scraper
for it is JobSpy (MIT), which is a Python library. scan_jobright.py and
scan_linkedin.py already establish this shape -- a Python fetcher
registered in scan.py's SOURCE_FETCHERS returning the same job dicts the
Node providers produce -- so this follows them rather than inventing a
mechanism.

Why Indeed specifically, out of the five boards JobSpy supports.
Measured against Buffalo NY on 2026-08-21:

    indeed         15/15 postings with descriptions, median 4,066 chars
    linkedin       descriptions only with linkedin_fetch_description,
                   and the location field comes back EMPTY -- which
                   would defeat the radius filter entirely. Already
                   covered by scan_linkedin.py regardless.
    zip_recruiter  HTTP 403 (Cloudflare)
    glassdoor      HTTP 400, "location not parsed"
    google         0 results, with or without google_search_term

So this module deliberately scrapes ONE site. The others are not
commented-out options waiting to be enabled; they did not work.

The three failures were re-tested against JobSpy's own documented
guidance and then CONTROLLED, because "we called it wrong" and "the site
blocks it" call for very different responses:

  * Glassdoor requires country_indeed (passed) and USA is a supported
    country. It still answered 400 "location not parsed" for every
    format tried, including the README's own example location
    ("San Francisco, CA") and a bare state.
  * Google's README says to paste the exact string from Google's jobs
    search box. Its own verbatim example
    ("software engineer jobs near San Francisco, CA since yesterday")
    also returned 0.
  * ZipRecruiter uses only `location`, per its docs. Still 403, which is
    Cloudflare; JobSpy's FAQ answer for that is rotating residential
    proxies -- a paid dependency to reach a board Indeed already covers.

In the SAME run, Indeed with identical settings returned results. That
control is the point: the harness, the network, and the call pattern are
all fine, so these three are upstream failures, not usage errors. 1.1.82
was the newest release when this was written, so there is no version to
upgrade into either.

Re-check by running those three against the README examples again. If
they start working, adding one is a small change -- the normalization
below is site-agnostic.

Indeed matters because it is the largest US job board and the only free
source found so far that returns tailoring-grade text for LOCAL roles.
The aggregators reachable by API (jooble ~275 chars, adzuna exactly 500)
are structurally teaser-only -- see their provider modules -- and
USAJOBS, while full-text, is federal-only and sparse in any one metro.

No API key. JobSpy scrapes, so this is best-effort by nature: it is
wrapped so a block or a layout change degrades to zero jobs and a
warning, never an exception that takes a whole scan down.
"""

import logging
import os

import cli_art
import location_settings

# JobSpy's own default is 50; ours comes from the profile's configured
# commute radius, and this is only the fallback when none is set.
DEFAULT_DISTANCE_MILES = 25
DEFAULT_SEARCH_TERM = "marketing"
DEFAULT_RESULTS_WANTED = 50

# Indeed's own site key in JobSpy.
SITE_NAME = "indeed"


def _origin_from_settings(settings: dict) -> str:
    """Indeed wants a human place name ("Buffalo, NY"), not a ZIP.

    Prefers city/state for that reason, but a ZIP-only origin is still
    usable here (unlike Jooble's API, which silently returns nothing for
    one) because Indeed resolves postal codes fine.
    """
    city = str(settings.get("city") or "").strip()
    state = str(settings.get("state") or "").strip()
    if city and state:
        return f"{city}, {state}"
    return str(settings.get("zip") or "").strip()


def _clean(value) -> str:
    """pandas gives NaN for missing cells, which str()s to the literal
    'nan' -- that would land in a JD file as if it were real text."""
    if value is None:
        return ""
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _is_remote(row) -> bool | None:
    value = row.get("is_remote")
    if value is None or _clean(value) == "":
        return None
    return bool(value)


def fetch_indeed_jobs(search_term: str = None, activity=None) -> list:
    """Scrapes Indeed for the active profile's configured location.

    Returns the same job-dict shape as the other sources. Returns [] --
    never raises -- when the profile has no configured origin, when
    JobSpy is not installed, or when the scrape is blocked.
    """
    settings = location_settings.read_settings()
    location = _origin_from_settings(settings)
    if not location:
        cli_art.cli_error(
            "Indeed scan needs a location -- set one under Settings & Upkeep "
            "-> Location & Commute Radius. Skipping."
        )
        return []

    try:
        from jobspy import scrape_jobs
    except ImportError:
        cli_art.cli_error(
            "python-jobspy is not installed (pip install -r requirements.txt). "
            "Skipping Indeed scan."
        )
        return []

    distance = settings.get("radius_miles") or DEFAULT_DISTANCE_MILES
    term = search_term or DEFAULT_SEARCH_TERM

    if activity is not None:
        activity.start_source(1, label="Fetching")
        activity.step(
            "discovery",
            "Indeed",
            f"Checking {cli_art.format_board_name('indeed')} "
            f"({location}, {distance} mi)",
            preserve_markup=True,
        )

    try:
        frame = scrape_jobs(
            site_name=[SITE_NAME],
            search_term=term,
            location=location,
            distance=int(distance),
            results_wanted=DEFAULT_RESULTS_WANTED,
            country_indeed="USA",
        )
    except Exception as e:
        # Scraping is inherently fragile -- a block, a layout change, or a
        # transient network fault must not abort the whole scan run.
        logging.error(f"scan_indeed: Indeed scrape failed -- {e}")
        cli_art.cli_error(f"Indeed scan failed ({type(e).__name__}). Skipping.")
        return []

    if frame is None or len(frame) == 0:
        logging.info("scan_indeed: Indeed returned no listings.")
        return []

    jobs = []
    for _, row in frame.iterrows():
        title = _clean(row.get("title"))
        url = _clean(row.get("job_url"))
        if not title or not url:
            continue

        # Indeed genuinely returns no employer for some postings -- every
        # company_* field comes back NaN, typically on confidential or
        # staffing listings. Skipped rather than written, because a JD
        # with no employer cannot be researched, addressed in a cover
        # letter, or deduped by source_url+company_name, and it renders
        # as a blank row in the dashboard. Writing "Unknown Company"
        # instead is the placeholder pollution scripts/purge_stub_jobs.py
        # exists to clean up.
        company = _clean(row.get("company"))
        if not company:
            logging.info(
                f"scan_indeed: skipping {title!r} -- Indeed lists no employer."
            )
            continue

        description = _clean(row.get("description"))
        job = {
            "job_title": title,
            "company_name": company,
            "source_platform": "indeed",
            "source_job_id": _clean(row.get("id")) or None,
            "source_url": url,
            "location": _clean(row.get("location")),
            "is_remote": _is_remote(row),
            "posted_at": _clean(row.get("date_posted")),
            "description": description,
        }

        # Reuses the shared thin-description safety net rather than a
        # private threshold, so Indeed reports the same way every other
        # source does. Not marked as a teaser: unlike jooble/adzuna,
        # Indeed returns the real posting body.
        import scan_boards

        scan_boards._flag_thin_description(job, "indeed", url)
        jobs.append(job)

    logging.info(f"scan_indeed: returning {len(jobs)} listing(s).")
    return jobs
