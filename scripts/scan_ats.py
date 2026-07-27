"""
scan_ats.py -- direct-to-ATS board-scanner source for scan.py, ported from
career-ops's providers/*.mjs plugin layer (vendored into
board-scanners/providers/, 2026-07-26; see
docs/superpowers/plans/2026-07-16-three-repo-merge-punchlist.md item 5).
Covers the providers scan_boards.py doesn't: Greenhouse, Ashby, Lever,
Recruitee, SmartRecruiters, Workable, Workday -- each needs a specific
company's careers_url/api before it returns anything, unlike
scan_boards.py's aggregator providers which work with zero config.

Two real sources of company targets, both vendored verbatim from
career-ops's portals.yml (Morgan's own real curation, not a template she
has to rebuild from scratch):

- tracked_companies.yml -- 400 companies, most already resolvable to one
  of the ATS providers above from their careers_url/api (334 of 400 as
  of the 2026-07-26 port). A minority are marked scan_method: websearch
  (no working direct API found for them) or explicitly `provider: X` for
  one of scan_boards.py's aggregator providers instead.
- search_queries.yml -- 68 Brave-search sweep queries (mostly
  "site:boards.greenhouse.io ... remote" style ATS-platform sweeps) for
  discovering companies NOT already in tracked_companies.yml. Runs
  through the vendored websearch.mjs provider; needs BRAVE_API_KEY in
  the active profile's .env or produces nothing (same graceful-no-op
  pattern as Adzuna/USAJobs without their keys).

Provider resolution (_resolve_provider_id) mirrors career-ops's own
scan.mjs resolveProvider(): explicit `provider:` field wins; otherwise
pattern-matched from careers_url/api against the 7 ATS providers vendored
here. An entry that resolves to neither (no api URL in a recognizable
shape, no explicit provider, not scan_method: websearch either) is
skipped -- there's nothing to fetch until it gets one of those three.

Performance note: unlike scan_boards.py (one subprocess call per
*source*), this calls one subprocess per *tracked company* -- 400+ Node
invocations for a full run. Each is cheap alone but it adds up; expect a
full scan_ats run to take real wall-clock time, not the few seconds
scan_boards.py takes.
"""

import html
import logging
import os

import yaml

import scan_boards

TRACKED_COMPANIES_PATH = os.path.join(scan_boards.BOARD_SCANNERS_DIR, "tracked_companies.yml")
SEARCH_QUERIES_PATH = os.path.join(scan_boards.BOARD_SCANNERS_DIR, "search_queries.yml")

# Mirrors board-scanners/providers/_recognition.mjs's RECOGNITION_RULES,
# trimmed to only the providers actually vendored here (career-ops's list
# also has bamboohr/jobvite/icims/jazzhr, which have no provider module
# in this repo -- an entry matching one of those just won't resolve).
_ATS_HOST_PATTERNS = [
    ("greenhouse", "greenhouse.io"),
    ("ashby", "ashbyhq.com"),
    ("lever", "lever.co"),
    ("recruitee", "recruitee.com"),
    ("smartrecruiters", "smartrecruiters.com"),
    ("workable", "workable.com"),
    ("workday", "myworkdayjobs.com"),
]


_ATS_PROVIDER_IDS = frozenset(provider_id for provider_id, _ in _ATS_HOST_PATTERNS)


def _resolve_provider_id(entry: dict) -> str:
    """Explicit provider field wins (covers both the 7 ATS providers here
    and any of scan_boards.py's aggregator providers a tracked_companies
    entry names directly); otherwise pattern-match careers_url/api.
    Returns "" when nothing resolves. Does NOT filter out aggregator
    provider ids -- that's fetch_ats_jobs()'s job (see its docstring) --
    this function just answers "what would this entry resolve to."""
    if entry.get("provider"):
        return entry["provider"]
    haystack = f"{entry.get('careers_url', '')} {entry.get('api', '')}".lower()
    for provider_id, host_fragment in _ATS_HOST_PATTERNS:
        if host_fragment in haystack:
            return provider_id
    return ""


def _load_tracked_companies() -> list:
    with open(TRACKED_COMPANIES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("tracked_companies", [])


def _load_search_queries() -> list:
    with open(SEARCH_QUERIES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("search_queries", [])


def _normalize_raw_job(raw: dict, provider_id: str, entry_name: str) -> dict:
    """Same normalization scan_boards.py's fetch_board_jobs() does
    (title/company cleanup, HTML-entity decoding, title/location
    prefilter, prefer a provider-supplied description over a page
    fetch) -- pulled out here so both the tracked_companies and
    search_queries loops in fetch_ats_jobs() share exactly one copy of
    it."""
    title = html.unescape((raw.get("title") or "").strip())
    url = raw.get("url") or ""
    if not title or not url or title.startswith(("http://", "https://")):
        return None
    if not scan_boards._passes_title_filter(title):
        return None
    if not scan_boards._passes_location_filter(raw.get("location")):
        return None

    raw_description = raw.get("description") or ""
    description = scan_boards._html_to_text(raw_description) if raw_description else scan_boards._fetch_posting_text(url, provider_id)

    return {
        "job_title": title,
        "company_name": html.unescape((raw.get("company") or entry_name or provider_id).strip()),
        "source_platform": provider_id,
        "source_job_id": None,
        "source_url": url,
        "location": raw.get("location") or "",
        "posted_at": raw.get("posted_at") or "",
        "description": description,
    }


def fetch_ats_jobs(sources: list = None) -> list:
    """Runs every enabled tracked_companies.yml entry through its
    resolved provider, plus every enabled search_queries.yml sweep query
    through websearch.mjs. `sources` is accepted for SOURCE_FETCHERS
    signature-compatibility with scan.py but unused -- there's no
    meaningful per-call subset the way scan_boards.py has per-provider
    sources; the whole point here is per-company targeting, already
    expressed in tracked_companies.yml itself (its own `enabled` field).

    Skips any entry resolving to an aggregator provider (not one of the
    7 real ATS providers) -- found live, 2026-07-27: 34 tracked_companies
    entries explicitly pin `provider: remoteok`/`jobspresso`/etc. (career-
    ops's own design, each run twice with search_term "marketing"/
    "enablement"), but scan_boards.py's "boards" source already fetches
    those exact same feeds in full and unfiltered. Since "marketing"/
    "enablement" results are necessarily a subset of the full feed, every
    posting these entries could return is already covered by "boards" --
    running them here only re-fetches the same postings under a
    different company label (the pinned entry's own display name, e.g.
    "Jobspresso — Marketing" vs. "boards"'s "jobspresso"), which defeats
    job_key_known()'s source_url+company_name dedup match and produces
    real duplicate JD files (confirmed live: 31 duplicate-URL groups,
    62 files, before this fix)."""
    jobs = []

    for company in _load_tracked_companies():
        if company.get("enabled") is False:
            continue
        provider_id = _resolve_provider_id(company)
        if not provider_id or provider_id not in _ATS_PROVIDER_IDS:
            continue

        raw_jobs = scan_boards._run_node_provider(provider_id, company)
        logging.info(f"scan_ats: {company.get('name')} ({provider_id}) returned {len(raw_jobs)} raw listing(s).")
        for raw in raw_jobs:
            job = _normalize_raw_job(raw, provider_id, company.get("name"))
            if job:
                jobs.append(job)

    for query in _load_search_queries():
        if query.get("enabled") is False:
            continue
        # _isSweep tells websearch.mjs to prefer the company it extracts
        # from the result URL over `entry.name` (the sweep query's own
        # descriptive name, e.g. "Greenhouse — Marketing & Enablement
        # remote") -- omitting it (found live 2026-07-27) meant every
        # sweep-discovered posting got stamped with the query's name as
        # its "company", so the same real posting found via two
        # different sweep queries produced two JD files with different
        # fake company names, defeating dedup's source_url+company_name
        # match. career-ops's own scan.mjs always sets this for
        # search_queries entries; ported that here.
        entry = {**query, "name": query.get("name", "websearch"), "scan_query": query.get("query", ""), "_isSweep": True}
        raw_jobs = scan_boards._run_node_provider("websearch", entry)
        logging.info(f"scan_ats: sweep '{query.get('name')}' returned {len(raw_jobs)} raw listing(s).")
        for raw in raw_jobs:
            job = _normalize_raw_job(raw, "websearch", raw.get("company"))
            if job:
                jobs.append(job)

    return jobs
