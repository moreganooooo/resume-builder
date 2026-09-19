"""
scan_linkedin.py — LinkedIn job scanner, ported from job_automater's
scrapers/linkedin_scraper.py.

Differences from the original:
- No MongoDB (store_job_data), no JSON backup file, no progress_callback
  bridge -- this returns a list of job dicts in the same shape
  jd_manager.py already expects from a JD file, for scan.py to dedupe and
  write straight into jds/.
- The li_at session cookie is authenticated securely via Playwright visual login
  or manually entered, and validated live before use.
"""

import contextlib
import logging
import os
import re
import signal
import threading
import traceback
import time

import cli_art
import content_settings
import profile_paths
import requests
from bs4 import BeautifulSoup
from linkedin_jobs_scraper import LinkedinScraper
from linkedin_jobs_scraper.events import EventData, Events
from linkedin_jobs_scraper.filters import (
    ExperienceLevelFilters,
    OnSiteOrRemoteFilters,
    RelevanceFilters,
    TimeFilters,
    TypeFilters,
)
from linkedin_jobs_scraper.query import Query, QueryFilters, QueryOptions

DEFAULT_JOB_LIMIT_PER_QUERY = 20

# Matches LinkedinScraper's own slow_mo=5 below. Without this,
# _fetch_personalized_extras() fires one authenticated GET per job (up to
# ~60 on a full scan) back-to-back on Morgan's real li_at session cookie --
# the one place in this subsystem with genuine account-ban risk, since it's
# the account she job-searches from. Costs up to 5 extra minutes on a scan
# that already takes longer; worth it.
_PERSONALIZED_EXTRAS_DELAY_SECONDS = (
    0
    if (
        os.environ.get("CI") == "true"
        or os.environ.get("RESUME_BUILDER_TESTING") == "1"
    )
    else 5
)


def check_li_cookie_live(cookie_val: str) -> bool:
    """Verifies if the saved li_at cookie is still valid on LinkedIn."""
    if not cookie_val:
        return False
    try:
        session = requests.Session()
        session.cookies.set("li_at", cookie_val, domain=".linkedin.com")
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "accept-language": "en-US,en;q=0.9",
            }
        )
        response = session.get(
            "https://www.linkedin.com/feed/", allow_redirects=False, timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False


def get_li_at_cookie() -> str:
    """Reads or extracts the live li_at session cookie. Saves and caches it
    profile-specifically to avoid repeated prompts."""
    import json
    import os
    import subprocess

    import profile_paths
    import questionary
    import theme

    cookie_file = os.path.join(profile_paths.profile_root(), ".linkedin_cookie")

    # 1. Try reading from the profile-specific cache first
    if os.path.isfile(cookie_file):
        try:
            with open(cookie_file, "r") as f:
                cached_cookie = f.read().strip()
            if cached_cookie:
                # Validate the cached cookie liveness
                if check_li_cookie_live(cached_cookie):
                    return cached_cookie
                else:
                    cli_art.console.print(
                        f"[{theme.BRAND_ACCENT}]⚠ Saved LinkedIn session has expired. Let's re-authenticate![/{theme.BRAND_ACCENT}]"
                    )
        except Exception:
            pass

    cli_art.console.print()
    cli_art.console.print(
        f"[{theme.BRAND}]✦  LINKEDIN AUTHENTICATION  ✦[/{theme.BRAND}]"
    )
    cli_art.console.print(
        "To fetch deep details (like applicant stats and full descriptions), an active LinkedIn session is required.\n"
        "You can log in securely via a visual browser window (recommended) or paste an active 'li_at' cookie manually."
    )
    cli_art.console.print()

    try:
        choice = questionary.select(
            "How would you like to provide your LinkedIn cookie?",
            choices=[
                "(Recommended) Log in securely via a visual browser window (automatic capture)",
                "Paste 'li_at' cookie value (or a Chrome DevTools curl command) manually",
            ],
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
    except Exception:
        choice = "(Recommended) Log in securely via a visual browser window (automatic capture)"

    if not choice:
        return ""

    cookie_val = ""

    if "Paste" in choice:
        cookie_val = questionary.text(
            "Paste cookie value (or curl command with 'li_at=...'):",
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if not cookie_val:
            return ""
        cookie_val = cookie_val.strip()
        if (
            "curl" in cookie_val
            or "Cookie:" in cookie_val
            or "cookie:" in cookie_val
            or "li_at=" in cookie_val
        ):
            import re

            match = re.search(r"li_at=([^;\"\s]+)", cookie_val)
            if match:
                cookie_val = match.group(1)
                cli_art.cli_info("Extracted 'li_at' cookie from your pasted inputs!")

    elif "visual browser window" in choice:
        cli_art.console.print()
        cli_art.console.print(
            f"[{theme.BRAND}]✦ LAUNCHING SECURE LOGIN WINDOW ✦[/{theme.BRAND}]"
        )
        cli_art.console.print(
            "A Chromium browser window will now open.\n"
            "Please [bold]log in[/bold] to LinkedIn, complete any verification (such as 2FA or CAPTCHAs),\n"
            "and once you are successfully logged in and redirected to your feed,\n"
            "we will capture your session cookie automatically and proceed!"
        )
        cli_art.console.print()

        script_path = os.path.join(
            profile_paths.PROJECT_ROOT, "scripts", "linkedin_login.mjs"
        )
        try:
            result = subprocess.run(
                ["node", script_path], capture_output=True, text=True, timeout=240
            )
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            data = json.loads(line)
                            if data.get("success"):
                                cookie_val = data.get("cookie")
                                cli_art.display_success_celebration(
                                    "LINKEDIN COOKIE SECURED",
                                    "Your session cookie was captured and cached successfully!",
                                )
                                break
                            else:
                                cli_art.cli_error(f"Login failed: {data.get('error')}")
                        except Exception:
                            pass
            else:
                cli_art.cli_error(
                    f"Login script failed: {result.stderr or 'Closed early'}"
                )
        except subprocess.TimeoutExpired:
            cli_art.cli_error("Login session timed out (4 minutes limit exceeded).")
        except Exception as e:
            cli_art.cli_error(f"Failed to execute login helper: {e}")

    if cookie_val:
        if check_li_cookie_live(cookie_val):
            try:
                with open(cookie_file, "w") as f:
                    f.write(cookie_val)
                cli_art.cli_info("LinkedIn session successfully cached!")
            except Exception as e:
                logging.debug(f"Failed to cache cookie: {e}")
            return cookie_val
        else:
            cli_art.cli_error(
                "Captured LinkedIn session is invalid or did not complete login successfully."
            )

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
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "accept-language": "en-US,en;q=0.9",
            }
        )
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
        logging.debug(
            f"  [Enhancer] Failed to fetch personalized extras for {job_url}: {e}"
        )
    finally:
        # In the finally block (not just after a successful request) since
        # a timeout/exception still means a request hit LinkedIn's server
        # and should count toward pacing.
        time.sleep(_PERSONALIZED_EXTRAS_DELAY_SECONDS)

    return extras


_WORKPLACE_MODE_FILTERS = {
    "remote": OnSiteOrRemoteFilters.REMOTE,
    "onsite": OnSiteOrRemoteFilters.ON_SITE,
    "on_site": OnSiteOrRemoteFilters.ON_SITE,
    "hybrid": OnSiteOrRemoteFilters.HYBRID,
}
_DEFAULT_WORKPLACE_MODES = ["remote"]
_DEFAULT_LOCATION = "United States"

_EXPERIENCE_FILTER_MAP = {
    "internship": ExperienceLevelFilters.INTERNSHIP,
    "entry_level": ExperienceLevelFilters.ENTRY_LEVEL,
    "associate": ExperienceLevelFilters.ASSOCIATE,
    "mid_senior": ExperienceLevelFilters.MID_SENIOR,
    "director": ExperienceLevelFilters.DIRECTOR,
    "executive": ExperienceLevelFilters.EXECUTIVE,
}
_DEFAULT_EXPERIENCE_LEVELS = [
    ExperienceLevelFilters.ENTRY_LEVEL,
    ExperienceLevelFilters.ASSOCIATE,
    ExperienceLevelFilters.MID_SENIOR,
]

# content_settings.EMPLOYMENT_LABELS' vocabulary, mapped onto LinkedIn's
# own native TypeFilters -- contract_to_hire has no direct equivalent, so
# it folds into CONTRACT.
_TYPE_FILTER_MAP = {
    "full_time": TypeFilters.FULL_TIME,
    "part_time": TypeFilters.PART_TIME,
    "contract": TypeFilters.CONTRACT,
    "contract_to_hire": TypeFilters.CONTRACT,
    "temporary": TypeFilters.TEMPORARY,
    "internship": TypeFilters.INTERNSHIP,
}
_DEFAULT_TYPE_FILTERS = [
    TypeFilters.FULL_TIME,
    TypeFilters.PART_TIME,
    TypeFilters.CONTRACT,
    TypeFilters.TEMPORARY,
]


def _resolve_experience_filters() -> list:
    levels = content_settings.read_linkedin_experience_levels()
    resolved = [
        _EXPERIENCE_FILTER_MAP[level]
        for level in levels
        if level in _EXPERIENCE_FILTER_MAP
    ]
    return resolved or list(_DEFAULT_EXPERIENCE_LEVELS)


def _resolve_type_filters() -> list:
    employment = content_settings.read_settings().get("employment_type")
    if not employment:
        return list(_DEFAULT_TYPE_FILTERS)
    resolved = {
        _TYPE_FILTER_MAP[value] for value in employment if value in _TYPE_FILTER_MAP
    }
    return list(resolved) or list(_DEFAULT_TYPE_FILTERS)


@contextlib.contextmanager
def _muted_scraper_logger():
    """Silences linkedin_jobs_scraper's own 'li:scraper' logger (INFO
    lines like "Session is valid" and "Metrics: ...", WARNING lines like
    "Pagination failed, retrying") for the duration of scraper.run().
    That logger sets its own level explicitly (see the package's
    utils/logger.py), so it reaches the root logger and prints raw
    LEVELNAME:name:message lines -- clobbering the "Scanning" spinner --
    whenever ANY handler with a low enough level exists on the root
    logger (e.g. `resume --verbose`'s logging.basicConfig(DEBUG)).
    scan.py's own _ScanWarningCollector doesn't help here: it only
    captures records explicitly marked scan_warning, which this
    third-party logger's records never are. Restores the original level
    afterward rather than assuming a default, in case something else
    already changed it."""
    scraper_logger = logging.getLogger("li:scraper")
    original_level = scraper_logger.level
    scraper_logger.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        scraper_logger.setLevel(original_level)


def _build_queries(job_limit: int, search_terms: list) -> list:
    """Builds one LinkedIn Query per entry in search_terms -- see
    fetch_linkedin_jobs() for where those entries actually come from
    (profile.yml, not hardcoded here). An entry is either a plain search
    string (remote/"United States", the original behavior) or a dict with
    `query` plus optional `workplace_mode` (list of remote/onsite/hybrid)
    and `location` overrides -- e.g. a local search wants onsite/hybrid
    roles near a specific city instead of a nationwide remote search."""

    def _query(entry):
        if isinstance(entry, dict):
            text = entry["query"]
            modes = entry.get("workplace_mode") or _DEFAULT_WORKPLACE_MODES
            location = entry.get("location") or _DEFAULT_LOCATION
        else:
            text = entry
            modes = _DEFAULT_WORKPLACE_MODES
            location = _DEFAULT_LOCATION

        on_site_or_remote = [
            _WORKPLACE_MODE_FILTERS[m.lower().replace("-", "_")]
            for m in modes
            if m.lower().replace("-", "_") in _WORKPLACE_MODE_FILTERS
        ] or [OnSiteOrRemoteFilters.REMOTE]

        filters = QueryFilters(
            relevance=RelevanceFilters.RELEVANT,
            time=TimeFilters.DAY,
            on_site_or_remote=on_site_or_remote,
            experience=_resolve_experience_filters(),
            type=_resolve_type_filters(),
        )

        return Query(
            query=text,
            options=QueryOptions(
                locations=[location],
                apply_link=False,
                skip_promoted_jobs=False,
                page_offset=0,
                limit=job_limit,
                filters=filters,
            ),
        )

    return [_query(entry) for entry in search_terms]


def fetch_linkedin_jobs(limit: int = None, activity=None) -> list:
    """Runs this profile's saved LinkedIn searches and returns a list of
    job dicts (same shape as job_automater's/JobRight's).

    Search terms come from profile.yml's linkedin_search_queries: (hand-
    tuned boolean search strings, or a dict per entry for a search that
    needs its own workplace_mode/location -- see _build_queries()) if
    present, else fall back to one query per target_roles.primary entry,
    so a profile that hasn't hand-tuned searches yet still gets something
    reasonable rather than nothing."""
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
        title = getattr(data, "title", "?")
        company = getattr(data, "company", "?")
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
        jobs.append(
            {
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
                # domain -- only its own /company/<slug> page, already stored
                # just above. None, deliberately: research_company() only runs
                # its website search when company_website is EMPTY, so passing
                # the LinkedIn page through here (as this used to) blocked that
                # search for every LinkedIn-sourced role -- 50 of 80 pending
                # "company websites" were LinkedIn pages (measured 2026-09-13).
                "company_website": None,
                "location": getattr(data, "place", None),
                "is_remote": "remote" in place.lower(),
                "work_model": (
                    "Remote"
                    if "remote" in place.lower()
                    else (
                        "Hybrid"
                        if "hybrid" in place.lower()
                        else ("Onsite" if place else None)
                    )
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
            }
        )

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

    display_terms = [
        entry["query"] if isinstance(entry, dict) else entry for entry in search_terms
    ]
    cli_art.cli_info(
        f"Searching LinkedIn for {len(search_terms)} saved "
        f"quer{'y' if len(search_terms) == 1 else 'ies'}: {', '.join(display_terms)}"
    )

    # Run scraper in a thread with a timeout to prevent indefinite hangs
    # (scraper.run() is blocking Selenium with no overall scan timeout)
    SCRAPER_TIMEOUT_SECONDS = 600  # 10 minutes per search term, ~1hr for 6 terms

    scraper_exception = None
    def _run_scraper():
        nonlocal scraper_exception
        try:
            with _muted_scraper_logger():
                scraper.run(_build_queries(job_limit, search_terms))
        except Exception as e:
            scraper_exception = e

    scraper_thread = threading.Thread(target=_run_scraper, daemon=True)
    scraper_thread.start()
    scraper_thread.join(timeout=SCRAPER_TIMEOUT_SECONDS)

    if scraper_thread.is_alive():
        cli_art.cli_error(
            f"LinkedIn scan exceeded {SCRAPER_TIMEOUT_SECONDS}s timeout and was killed. "
            f"Returning {len(jobs)} roles found so far. This typically indicates a hang in "
            f"Selenium pagination or a query getting stuck on a slow page load."
        )
        logging.error(
            f"LinkedIn scraper timeout after {SCRAPER_TIMEOUT_SECONDS}s. "
            f"Search terms: {display_terms}. Jobs found before timeout: {len(jobs)}"
        )
        on_end()
    elif scraper_exception:
        error_type = type(scraper_exception).__name__
        error_msg = str(scraper_exception)
        cli_art.cli_error(
            f"LinkedIn scraper failed with {error_type}: {error_msg}\n"
            f"Search terms being processed: {', '.join(display_terms)}\n"
            f"Jobs found before error: {len(jobs)}"
        )
        logging.error(
            f"LinkedIn scraper exception ({error_type}): {error_msg}\n"
            f"Full traceback:\n{traceback.format_exc()}"
        )
        on_end()

    return jobs
