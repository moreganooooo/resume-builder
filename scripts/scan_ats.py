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
has to rebuild from scratch) and living under
profiles/<name>/board_scanner/ (profile_paths.board_scanner_dir()) --
100% profile-specific data, unlike the shared engine code in
board-scanners/providers/:

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
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import cli_art
import profile_paths
import scan_boards
import yaml

# Brave Search's free tier is 1 req/sec (see providers/websearch.mjs's own
# module docstring) -- the sweep loop below is the only place this repo
# calls websearch.mjs more than once per process, so it's the only place
# that needs real inter-call pacing (see B26, docs/review/phase-9-backlog.md).
_WEBSEARCH_MIN_GAP_SECONDS = 1.0

# Tracking parameters stripped during URL canonicalization
_TRACKING_QUERY_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gh_src",
        "gh_jid",
        "lever-origin",
        "lever-source",
        "source",
        "ref",
        "sessionid",
        "subid",
        "fbclid",
        "gclid",
        "trk",
        "trackingid",
        "refid",
        "spm",
        "source_type",
        "src",
    }
)


def canonicalize_job_url(url: str) -> str:
    """Strips tracking, referral, and session parameters from a job posting URL."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered_params = [
            (k, v) for k, v in query_params if k.lower() not in _TRACKING_QUERY_PARAMS
        ]
        new_query = urllib.parse.urlencode(filtered_params)
        clean = parsed._replace(query=new_query, fragment="")
        res = clean.geturl()
        return res[:-1] if res.endswith("?") else res
    except Exception:
        return url.strip()


# Recognition rules mapping provider IDs to host/domain fragments
_ATS_HOST_PATTERNS = [
    ("greenhouse", "greenhouse.io"),
    ("ashby", "ashbyhq.com"),
    ("lever", "lever.co"),
    ("recruitee", "recruitee.com"),
    ("smartrecruiters", "smartrecruiters.com"),
    ("workable", "workable.com"),
    ("workday", "myworkdayjobs.com"),
    ("taleo", "taleo.net"),
    ("rippling", "ats.rippling.com"),
    ("bamboohr", "bamboohr.com"),
    ("jobvite", "jobvite.com"),
    ("icims", "icims.com"),
    ("linkedin", "linkedin.com/jobs"),
    ("indeed", "indeed.com"),
]


_ATS_PROVIDER_IDS = frozenset(provider_id for provider_id, _ in _ATS_HOST_PATTERNS)

# How heavily each ATS platform weighs literal keyword-matching, for cover
# letter keyword front-loading (docs/superpowers/plans/2026-08-17-cover-
# letter-blueprint-roadmap.md Group B, Feature #12). Workday/Taleo are
# classic enterprise ATS keyword scanners; Rippling's screen is explicitly
# AI-prescreened; Greenhouse/Lever postings are read by a human first;
# Ashby is evidence-based (structured scorecards, not keyword density).
# Providers with no strong signal either way default to "unknown" via
# .get() at the call site rather than being listed here.
_ATS_WEIGHT_TIERS = {
    "workday": "enterprise_high",
    "taleo": "enterprise_high",
    "icims": "enterprise_high",
    "rippling": "ai_prescreened",
    "greenhouse": "startup_zero",
    "lever": "startup_zero",
    "ashby": "evidence_based",
    "smartrecruiters": "standard",
    "workable": "standard",
    "bamboohr": "standard",
    "jobvite": "standard",
}


def classify_ats(source_url: str) -> dict | None:
    """Classifies a JD's source_url against the known ATS host patterns
    (Feature #1). Returns {"provider_id", "weight_tier"}, or None when
    source_url is empty or matches no known ATS host -- callers should
    treat None as "unclassified," not as an error."""
    if not source_url:
        return None
    haystack = source_url.lower()
    for provider_id, host_fragment in _ATS_HOST_PATTERNS:
        if host_fragment in haystack:
            return {
                "provider_id": provider_id,
                "weight_tier": _ATS_WEIGHT_TIERS.get(provider_id, "unknown"),
            }
    return None


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
    path = os.path.join(profile_paths.board_scanner_dir(), "tracked_companies.yml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("tracked_companies", [])


def _load_search_queries() -> list:
    path = os.path.join(profile_paths.board_scanner_dir(), "search_queries.yml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("search_queries", [])


def _normalize_raw_job(raw: dict, provider_id: str, entry_name: str) -> dict:
    """Same normalization scan_boards.py's fetch_board_jobs() does
    (title/company cleanup, HTML-entity decoding, title/location
    prefilter, prefer a provider-supplied description over a page
    fetch) -- pulled out here so both the tracked_companies and
    search_queries loops in fetch_ats_jobs() share exactly one copy of
    it."""
    title = html.unescape((raw.get("title") or "").strip())
    raw_url = raw.get("url") or ""
    url = canonicalize_job_url(raw_url)
    if not title or not url or title.startswith(("http://", "https://")):
        return None
    if not scan_boards._passes_title_filter(title):
        return None
    if not scan_boards._passes_location_filter(raw.get("location")):
        return None

    raw_description = raw.get("description") or ""
    description = (
        scan_boards._html_to_text(raw_description)
        if raw_description
        else scan_boards._fetch_posting_text(url, provider_id)
    )

    job = {
        "job_title": title,
        "company_name": html.unescape(
            (raw.get("company") or entry_name or provider_id).strip()
        ),
        "source_platform": provider_id,
        "source_job_id": None,
        "source_url": url,
        "location": raw.get("location") or "",
        "posted_at": raw.get("posted_at") or "",
        "description": description,
    }
    # Same carry as scan_boards.fetch_board_jobs -- a provider that
    # declares its text a teaser must not lose that across the rebuild.
    if raw.get("description_is_teaser"):
        job["description_is_teaser"] = True
    scan_boards._flag_thin_description(job, provider_id, url)
    return job


def fetch_ats_jobs(sources: list = None, activity=None) -> list:
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
    62 files, before this fix). `activity` (a cli_art.ScanActivity) is
    optional -- when given, announces each company/sweep as it's
    checked through the shared themed step-log; ~400 sequential
    subprocess calls with zero feedback otherwise reads as a hang on a
    real run."""
    jobs = []
    companies = [c for c in _load_tracked_companies() if c.get("enabled") is not False]
    queries = [q for q in _load_search_queries() if q.get("enabled") is not False]
    if activity is not None:
        activity.start_source(len(companies) + len(queries), label="Checking")

    # Companies are fetched concurrently -- each is an independent Node
    # subprocess against a different ATS host, so they were only ever
    # sequential by omission. With ~400 tracked entries that serialization
    # was the single largest cost in a scan, and the reason a real run
    # reads as a hang (see the `activity` note above). Mirrors the same
    # 8-worker pool scan_boards.fetch_board_jobs() already uses.
    #
    # Kept out of the pool: the websearch sweep loop below, which paces
    # itself against Brave's free-tier 1 req/sec limit. Parallelizing that
    # would trade a slow scan for a rate-limited one.
    def process_company(company: dict) -> list:
        provider_id = _resolve_provider_id(company)
        if not provider_id or provider_id not in _ATS_PROVIDER_IDS:
            return []

        raw_jobs = scan_boards._run_node_provider(provider_id, company)
        logging.info(
            f"scan_ats: {company.get('name')} ({provider_id}) returned {len(raw_jobs)} raw listing(s)."
        )
        found = []
        for raw in raw_jobs:
            job = _normalize_raw_job(raw, provider_id, company.get("name"))
            if job:
                found.append(job)
        return found

    if companies:
        max_workers = min(len(companies), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for company in companies:
                # Announced from the main thread at submit time, so the
                # step log stays ordered and ScanActivity is never touched
                # concurrently.
                if activity is not None:
                    company_name = company.get("name") or "?"
                    message = f"Checking {cli_art.format_board_name(company_name)}"
                    activity.step("discovery", "ATS", message, preserve_markup=True)
                futures[executor.submit(process_company, company)] = company

            for future in as_completed(futures):
                company = futures[future]
                try:
                    jobs.extend(future.result())
                except Exception as e:
                    # One unreachable ATS host must not abort the scan.
                    logging.error(
                        f"scan_ats: Future task failed for {company.get('name')}: {e}"
                    )

    last_websearch_call_at = None
    for query in queries:
        # websearch.mjs used to pace itself against Brave's free-tier 1
        # req/sec limit with a module-level queue -- dead code across the
        # subprocess boundary, since run_provider.mjs spawns one fresh Node
        # process per query (see B26, docs/review/phase-9-backlog.md). Real
        # pacing has to live here instead, where the calls are actually
        # sequential in the same process. Measures from the previous call's
        # *start*, not a blind fixed sleep, so a slow call (network latency
        # already eating into the gap) doesn't also pay a full extra second.
        if last_websearch_call_at is not None:
            remaining = _WEBSEARCH_MIN_GAP_SECONDS - (
                time.monotonic() - last_websearch_call_at
            )
            if remaining > 0:
                time.sleep(remaining)
        last_websearch_call_at = time.monotonic()

        if activity is not None:
            query_name = query.get("name") or "websearch sweep"
            message = f"Checking {cli_art.format_board_name(query_name)}"
            activity.step("discovery", "ATS", message, preserve_markup=True)
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
        entry = {
            **query,
            "name": query.get("name", "websearch"),
            "scan_query": query.get("query", ""),
            "_isSweep": True,
        }
        raw_jobs = scan_boards._run_node_provider("websearch", entry)
        logging.info(
            f"scan_ats: sweep '{query.get('name')}' returned {len(raw_jobs)} raw listing(s)."
        )
        for raw in raw_jobs:
            job = _normalize_raw_job(raw, "websearch", raw.get("company"))
            if job:
                jobs.append(job)

    return jobs
