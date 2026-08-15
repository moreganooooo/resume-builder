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
import time

import browser_cookie3
import requests
from bs4 import BeautifulSoup

import cli_art
import profile_paths
from linkedin_jobs_scraper import LinkedinScraper
from linkedin_jobs_scraper.events import Events, EventData
from linkedin_jobs_scraper.query import Query, QueryOptions, QueryFilters
from linkedin_jobs_scraper.filters import (
    RelevanceFilters, TimeFilters, TypeFilters, ExperienceLevelFilters, OnSiteOrRemoteFilters,
)

DEFAULT_JOB_LIMIT_PER_QUERY = 20

# Matches LinkedinScraper's own slow_mo=5 below. Without this,
# _fetch_personalized_extras() fires one authenticated GET per job (up to
# ~60 on a full scan) back-to-back on Morgan's real li_at session cookie --
# the one place in this subsystem with genuine account-ban risk, since it's
# the account she job-searches from. Costs up to 5 extra minutes on a scan
# that already takes longer; worth it.
_PERSONALIZED_EXTRAS_DELAY_SECONDS = 5


def get_li_at_cookie() -> str:
    """Reads the live li_at session cookie from Chrome. Returns "" if
    Chrome isn't logged into LinkedIn right now (or the cookie can't be
    read) -- the caller logs a clear, actionable message in that case."""
    try:
        cookie_jar = browser_cookie3.chrome(domain_name="linkedin.com")
    except Exception as e:
        cli_art.cli_error(f"Could not read Chrome's cookie store: {e}")
        return ""

    for cookie in cookie_jar:
        if cookie.name == "li_at":
            return cookie.value
    return ""


def _fetch_personalized_extras(job_url: str, li_at_cookie: str) -> dict:
    """Authenticated pass over the job page to detect "Top Applicant" status
    and recover a backup description from the page's embedded JSON, using
    Morgan's live session cookie. Paced by
    _PERSONALIZED_EXTRAS_DELAY_SECONDS -- see that constant's comment."""
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
    finally:
        # In the finally block (not just after a successful request) since
        # a timeout/exception still means a request hit LinkedIn's server
        # and should count toward pacing.
        time.sleep(_PERSONALIZED_EXTRAS_DELAY_SECONDS)

    return extras


def _build_queries(job_limit: int, search_terms: list) -> list:
    """Builds one LinkedIn Query per search string in search_terms -- see
    fetch_linkedin_jobs() for where those strings actually come from
    (profile.yml, not hardcoded here)."""
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

    return [_query(text) for text in search_terms]


def fetch_linkedin_jobs(limit: int = None, activity=None) -> list:
    """Runs this profile's saved LinkedIn searches and returns a list of
    job dicts (same shape as job_automater's/JobRight's).

    Search terms come from profile.yml's linkedin_search_queries: (hand-
    tuned boolean search strings -- Morgan's own profile.yml has her 3
    real saved searches there) if present, else fall back to one query per
    target_roles.primary entry, so a profile that hasn't hand-tuned
    searches yet still gets something reasonable rather than nothing."""
    profile_data = profile_paths.profile_yaml()
    search_terms = (
        profile_data.get("linkedin_search_queries")
        or (profile_data.get("target_roles") or {}).get("primary")
        or []
    )
    if not search_terms:
        cli_art.cli_error(
            "No linkedin_search_queries or target_roles.primary configured "
            "in profile.yml -- nothing to search for."
        )
        return []

    li_at_cookie = get_li_at_cookie()
    if not li_at_cookie:
        cli_art.cli_error(
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
        # scraper.run() is one long blocking Selenium session with no
        # per-query hook in the library's Events enum -- this per-result
        # line (Events.DATA already fires once per job found) is the only
        # real signal available during the run, so a multi-query/slow-page
        # scan doesn't look hung for minutes with only on_error visible.
        title = getattr(data, 'title', '?')
        company = getattr(data, 'company', '?')
        if activity is not None:
            message = cli_art.format_job_found_message(title, company)
            activity.step("success", "LinkedIn", message, preserve_markup=True)
        else:
            cli_art.cli_info(f"Found: {title} at {company}")

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
            # LinkedIn's job page never exposes the company's own external
            # domain -- only its own /company/<slug> page. Passing that
            # through anyway (rather than hardcoding None) at least gives
            # research_company() something to attempt; it already degrades
            # gracefully (MIN_USEFUL_CHARS check) on the pages LinkedIn
            # blocks from anonymous scraping.
            "company_website": getattr(data, "company_link", None),
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
        cli_art.cli_error(f"[LinkedIn ON_ERROR] {error}")

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

    cli_art.cli_info(
        f"Searching LinkedIn for {len(search_terms)} saved "
        f"quer{'y' if len(search_terms) == 1 else 'ies'}: {', '.join(search_terms)}"
    )
    try:
        scraper.run(_build_queries(job_limit, search_terms))
    except Exception as e:
        cli_art.cli_error(f"LinkedIn scraper run failed: {e}")
        on_end()

    return jobs
