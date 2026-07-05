"""
scan_linkedin.py — LinkedIn job scanner, ported from job_automater's
scrapers/linkedin_scraper.py.

Differences from the original:
- No MongoDB (store_job_data), no JSON backup file, no progress_callback
  bridge -- this returns a list of job dicts in the same shape
  jd_manager.py already expects from a JD file, for scan.py to dedupe and
  write straight into jds/.
- The li_at session cookie is no longer read from a static .env value.
  Morgan's cookie goes stale in a way that made manual copy-paste the only
  workflow that worked for her, so this reads it live from her actual,
  already-logged-in Chrome via browser_cookie3 on every call instead --
  automates the exact manual step she was doing, no cookie ever stored on
  disk.
"""

import logging
import re

import browser_cookie3
import requests
from bs4 import BeautifulSoup

from linkedin_jobs_scraper import LinkedinScraper
from linkedin_jobs_scraper.events import Events, EventData
from linkedin_jobs_scraper.query import Query, QueryOptions, QueryFilters
from linkedin_jobs_scraper.filters import (
    RelevanceFilters, TimeFilters, TypeFilters, ExperienceLevelFilters, OnSiteOrRemoteFilters,
)

DEFAULT_JOB_LIMIT_PER_QUERY = 20


def get_li_at_cookie() -> str:
    """Reads the live li_at session cookie from Chrome. Returns "" if
    Chrome isn't logged into LinkedIn right now (or the cookie can't be
    read) -- the caller logs a clear, actionable message in that case."""
    try:
        cookie_jar = browser_cookie3.chrome(domain_name="linkedin.com")
    except Exception as e:
        logging.error(f"Could not read Chrome's cookie store: {e}")
        return ""

    for cookie in cookie_jar:
        if cookie.name == "li_at":
            return cookie.value
    return ""


def _fetch_personalized_extras(job_url: str, li_at_cookie: str) -> dict:
    """Authenticated pass over the job page to detect "Top Applicant" status
    and recover a backup description from the page's embedded JSON, using
    Morgan's live session cookie."""
    extras = {"is_top_applicant": False, "backup_description": None}
    if not job_url or not li_at_cookie:
        return extras

    try:
        session = requests.Session()
        session.cookies.set("li_at", li_at_cookie, domain=".linkedin.com")
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "accept-language": "en-US,en;q=0.9",
        })
        response = session.get(job_url, timeout=10)
        if response.status_code != 200:
            return extras

        soup = BeautifulSoup(response.text, "html.parser")

        if soup.find("svg", id="premium-chip-v2-medium") or soup.find(
            string=re.compile("You’d be a top applicant", re.IGNORECASE)
        ):
            extras["is_top_applicant"] = True

        for block in soup.find_all("code", style="display: none"):
            if "description" not in block.text.lower():
                continue
            match = re.search(r'"description"\s*:\s*"([^"]+)"', block.text)
            if match:
                extras["backup_description"] = match.group(1).replace("\\n", "\n")
                break
    except Exception as e:
        logging.debug(f"  [Enhancer] Failed to fetch personalized extras for {job_url}: {e}")

    return extras


def _build_queries(job_limit: int) -> list:
    """The 3 saved searches Morgan actually uses (ported as-is from
    job_automater); edit here to change what LinkedIn is searched for."""
    shared_filters = QueryFilters(
        relevance=RelevanceFilters.RELEVANT,
        time=TimeFilters.DAY,
        on_site_or_remote=[OnSiteOrRemoteFilters.REMOTE],
        experience=[
            ExperienceLevelFilters.ENTRY_LEVEL,
            ExperienceLevelFilters.ASSOCIATE,
            ExperienceLevelFilters.MID_SENIOR,
        ],
        type=[
            TypeFilters.FULL_TIME,
            TypeFilters.PART_TIME,
            TypeFilters.CONTRACT,
            TypeFilters.TEMPORARY,
        ],
    )

    def _query(text):
        return Query(
            query=text,
            options=QueryOptions(
                locations=["United States"],
                apply_link=False,
                skip_promoted_jobs=False,
                page_offset=0,
                limit=job_limit,
                filters=shared_filters,
            ),
        )

    return [
        _query("Email OR Campaign"),
        _query("Lifecycle"),
        _query("Sales OR Revenue AND operations OR support OR enablement"),
    ]


def fetch_linkedin_jobs(limit: int = None) -> list:
    """Runs the 3 saved LinkedIn searches and returns a list of job dicts
    (same shape as job_automater's/JobRight's)."""
    li_at_cookie = get_li_at_cookie()
    if not li_at_cookie:
        logging.error(
            "No live li_at cookie found. Log into LinkedIn in Chrome and "
            "keep it open, then retry."
        )
        return []

    # Without this, linkedin_jobs_scraper silently falls back to
    # AnonymousStrategy (deprecated, unreliable) instead of actually using
    # our session -- this global must be set before LinkedinScraper() is
    # constructed, matching job_automater's config.py wiring.
    from linkedin_jobs_scraper.config import Config as LinkedInConfig
    LinkedInConfig.LI_AT_COOKIE = li_at_cookie

    jobs = []

    def on_data(data: EventData):
        apply_link = getattr(data, "apply_link", None)
        linkedin_link = getattr(data, "link", None)

        if apply_link:
            application_type = "external"
            application_url = apply_link
        elif linkedin_link and "linkedin.com/jobs/view" in linkedin_link:
            application_type = "easy_apply"
            application_url = None
        else:
            application_type = "unknown"
            application_url = None

        extras = _fetch_personalized_extras(linkedin_link, li_at_cookie)
        primary_desc = getattr(data, "description", None)
        final_desc = primary_desc if primary_desc else extras["backup_description"]

        place = getattr(data, "place", "") or ""
        jobs.append({
            "status": "new",
            "source_platform": "linkedin",
            "source_job_id": getattr(data, "job_id", None),
            "source_url": linkedin_link,
            "application_type": application_type,
            "application_url": application_url,
            "job_title": getattr(data, "title", None),
            "company_name": getattr(data, "company", None),
            "company_linkedin_url": getattr(data, "company_link", None),
            "company_website": None,
            "location": getattr(data, "place", None),
            "is_remote": "remote" in place.lower(),
            "work_model": "Remote" if "remote" in place.lower() else (
                "Hybrid" if "hybrid" in place.lower() else ("Onsite" if place else None)
            ),
            "publish_time": getattr(data, "date", None),
            "publish_time_desc": getattr(data, "date_text", None),
            "employment_type": getattr(data, "employment_type", None),
            "seniority_level": getattr(data, "seniority_level", None),
            "description": final_desc,
            "description_html": getattr(data, "description_html", None),
            "is_top_applicant": extras["is_top_applicant"],
            "job_summary": None,
            "skills": getattr(data, "skills", None),
            "qualifications": None,
            "core_responsibilities": None,
            "social_connections": None,
            "personal_social_connections": None,
        })

    def on_error(error):
        logging.error(f"[LinkedIn ON_ERROR] {error}")

    def on_end():
        logging.info(f"LinkedIn scan finished: {len(jobs)} jobs.")

    job_limit = limit if limit is not None else DEFAULT_JOB_LIMIT_PER_QUERY
    scraper = LinkedinScraper(
        headless=True,
        max_workers=1,
        slow_mo=5,
        page_load_timeout=120,
    )
    scraper.on(Events.DATA, on_data)
    scraper.on(Events.ERROR, on_error)
    scraper.on(Events.END, on_end)

    try:
        scraper.run(_build_queries(job_limit))
    except Exception as e:
        logging.error(f"LinkedIn scraper run failed: {e}")
        on_end()

    return jobs
