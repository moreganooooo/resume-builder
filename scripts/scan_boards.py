"""
scan_boards.py -- board-scanner source for scan.py, ported from career-ops's
providers/*.mjs plugin layer (vendored into board-scanners/providers/,
2026-07-26; see docs/superpowers/plans/2026-07-16-three-repo-merge-punchlist.md
item 5). Covers the zero-config aggregator/search-driven providers
(RemoteOK, Remotive, Himalayas, Jobicy, WeWorkRemotely, WorkingNomads,
FourDayWeek, NoDesk, AuthenticJobs, CrunchBoard, Jobspresso,
RealWorkFromAnywhere, PowerToFly, TheMuse, HackerNews, plus Adzuna/USAJobs
which use the exact same mechanism but need an API key in the active
profile's .env before they return anything). The direct-to-ATS providers
(Greenhouse/Ashby/Lever/etc., which need a curated company list) are a
separate module -- see scan_ats.py, which reuses several helpers here
(_run_node_provider, _passes_title_filter, _passes_location_filter,
_html_to_text, _fetch_posting_text).

Each provider is a plain ESM module with no shared runtime beyond
board-scanners/providers/_http.mjs -- resume-builder shells out to
board-scanners/run_provider.mjs per provider via subprocess and parses its
JSON stdout, rather than rewriting any provider's fetch logic in Python
(same "port, don't rewrite" approach the punchlist decided for all ~26).

career-ops's providers/*.mjs only ever return
title/company/url/location/posted_at -- its own scan.mjs never fetches a
description either, since its downstream pipeline is a human/Claude
reading the URL directly, not a Gemini batch call. resume-builder's
tailor stage needs real JD text up front, though, so this vendored copy
diverges from career-ops here (2026-07-26): most of these providers'
underlying APIs already return a full description in the same response
that gave us title/url/company -- career-ops's providers just discarded
it. Each vendored provider.mjs now maps that field through instead
(RSS-based providers already extracted <description> for search-term
matching and were dropping it before return; JSON-API providers needed a
one-line addition per provider). fetch_board_jobs() uses that directly
when present -- faster and more reliable than a second per-posting-page
fetch, and the only way to get a body at all for a provider like
Himalayas, whose own posting pages sit behind a Cloudflare managed
challenge no plain HTTP request can pass. _fetch_posting_text() (a
best-effort GET + whole-page text extraction, not a per-ATS content
selector) is now only a fallback for the one provider with no native
description (FourDayWeek).
"""

import html
import json
import logging
import os
import re
import subprocess

import cli_art
import profile_paths
import requests
import yaml
from bs4 import BeautifulSoup

# board-scanners/ (repo root) holds only the shared engine code (the Node
# provider modules + the run_provider.mjs shim) -- generic across every
# profile, same as any other script in this repo. The actual scan
# *config* (which companies, which search terms, which title/location
# keywords) is 100% profile-specific and lives under
# profiles/<name>/board_scanner/ instead (profile_paths.board_scanner_dir()).
BOARD_SCANNERS_DIR = os.path.join(profile_paths.PROJECT_ROOT, "board-scanners")
RUN_PROVIDER_SCRIPT = os.path.join(BOARD_SCANNERS_DIR, "run_provider.mjs")

BOARD_PROVIDERS = [
    "remoteok",
    "remotive",
    "himalayas",
    "jobicy",
    "weworkremotely",
    "workingnomads",
    "fourdayweek",
    "nodesk",
    "authenticjobs",
    "crunchboard",
    "jobspresso",
    "realworkfromanywhere",
    "powertofly",
    "themuse",
    "hackernews",
    # Same mechanism as everything above -- just needs an API key in the
    # active profile's .env (ADZUNA_APP_ID/ADZUNA_APP_KEY;
    # USAJOBS_API_KEY/USAJOBS_EMAIL) or they return nothing (the
    # provider's own .mjs throws, _run_node_provider logs it and moves on).
    "adzuna",
    "usajobs",
]

NODE_TIMEOUT_SECONDS = 30
POSTING_FETCH_TIMEOUT_SECONDS = 15
MAX_DESCRIPTION_CHARS = 15_000
MIN_DESCRIPTION_CHARS = 200

# Vars no board/ATS provider has any legitimate need for (unlike
# ADZUNA_APP_ID/ADZUNA_APP_KEY, USAJOBS_API_KEY/etc. above, which specific
# providers genuinely do read from the environment) -- a denylist, not an
# allowlist, since providers' real credential needs vary per-provider and
# an allowlist would risk silently breaking one of them. liveness.py keeps
# its own copy of this same list for check-liveness.mjs's Chromium child
# (B41).
_SUBPROCESS_ENV_STRIP = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "JOBRIGHT_COOKIE_STRING")


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _SUBPROCESS_ENV_STRIP}


# Keyed by profile name (not a single cached value) -- this gets called
# once per raw listing inside fetch_board_jobs()'s loop, so it's worth
# caching for real, but a stale single-value cache would silently keep
# serving the previously-active profile's filters after a runtime
# profile switch (profile_paths.set_active_profile(), e.g. the
# interactive menu's --profile gate) instead of picking up the new
# profile's own scan_filters.yml.
_filters_cache = {}


def _load_filters() -> dict:
    profile = profile_paths.active_profile()
    if profile not in _filters_cache:
        path = os.path.join(
            profile_paths.board_scanner_dir(profile), "scan_filters.yml"
        )
        with open(path, "r", encoding="utf-8") as f:
            _filters_cache[profile] = yaml.safe_load(f)
    return _filters_cache[profile]


def _passes_title_filter(title: str) -> bool:
    """Python port of career-ops's scan.mjs buildTitleFilter(): title must
    contain at least one positive keyword and no negative keyword
    (case-insensitive substring match)."""
    tf = _load_filters().get("title_filter", {})
    lower = (title or "").lower()
    positive = [k.lower() for k in tf.get("positive", [])]
    negative = [k.lower() for k in tf.get("negative", [])]
    if positive and not any(k in lower for k in positive):
        return False
    if any(k in lower for k in negative):
        return False
    return True


def _passes_location_filter(location: str) -> bool:
    """Python port of scan.mjs's buildLocationFilter(): empty/missing
    location always passes; always_allow beats block; block rejects."""
    if not location or not location.strip():
        return True
    lf = _load_filters().get("location_filter", {})
    lower = location.lower()
    always_allow = [k.lower() for k in lf.get("always_allow", [])]
    block = [k.lower() for k in lf.get("block", [])]
    if any(k in lower for k in always_allow):
        return True
    if any(k in lower for k in block):
        return False
    return True


def _scan_warning(
    msg: str, *, kind: str, provider_id: str, reason: str, url: str = ""
) -> None:
    """logging.warning() with structured `extra` fields scan.py's
    _ScanWarningCollector reads to render a grouped, themed summary
    instead of a raw wall of WARNING:root: lines -- the plain message is
    still there for anyone watching logs directly (e.g. `resume test -vv`
    or a bare terminal without the themed report)."""
    logging.warning(
        msg,
        extra={
            "scan_warning": True,
            "kind": kind,
            "provider_id": provider_id,
            "reason": reason,
            "url": url,
        },
    )


def _parse_error_envelope(stdout: str) -> dict | None:
    """run_provider.mjs writes `{"error": {"kind", "message"}}` to stdout on
    every failure path (see B27, docs/review/phase-9-backlog.md) instead of
    leaving it empty -- gives a specific reason (auth/quota/network/config)
    instead of scan_boards.py having to guess one from the last line of
    stderr, which used to be the only signal and couldn't tell "LinkedIn
    cookie expired" apart from "host is down" apart from "bad YAML entry".
    Returns None when stdout isn't that shape (e.g. the node binary itself
    is missing, or a crash before run_provider.mjs's own handlers run) --
    callers fall back to the old stderr-based reason in that case."""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if not isinstance(error, dict) or "kind" not in error:
        return None
    return error


def _flag_thin_description(job: dict, provider_id: str, source_url: str) -> None:
    """Sets `job["_scan"]` (per CLAUDE.md's underscore-prefixed persisted-
    metadata convention -- same shape family as `_liveness`/`_evaluation`/
    `_application`) and raises a `_scan_warning` when a job's description is
    missing or too thin to tailor against, instead of the posting silently
    shipping with `"description": null`/near-empty and no trace of why.
    Six of 24 board-scanner providers never emitted a description at all
    before B36 (docs/review/phase-9-backlog.md) gave each a real source --
    this is the safety net for whatever's still thin after that (a
    provider's detail-fetch failing for one posting, a source that
    genuinely has nothing, etc.), so it stays visible in the scan report
    instead of silently degrading. Shared by fetch_board_jobs() below and
    scan_ats.py's _normalize_raw_job() (scan_ats.py already imports and
    reuses this module's other helpers the same way -- see its own
    docstring)."""
    chars = len((job.get("description") or "").strip())
    if chars >= MIN_DESCRIPTION_CHARS:
        return
    job["_scan"] = {"thin_description": True, "description_chars": chars}
    _scan_warning(
        f"scan_boards: {provider_id} posting has a thin/empty description ({chars} chars) -- {source_url}",
        kind="thin_description",
        provider_id=provider_id,
        reason=f"{chars} chars" if chars else "empty",
        url=source_url,
    )


def _run_node_provider(provider_id: str, entry: dict) -> list:
    try:
        result = subprocess.run(
            ["node", RUN_PROVIDER_SCRIPT, provider_id, json.dumps(entry)],
            capture_output=True,
            text=True,
            timeout=NODE_TIMEOUT_SECONDS,
            env=_child_env(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _scan_warning(
            f"scan_boards: {provider_id} failed to run -- {e}",
            kind="network" if isinstance(e, subprocess.TimeoutExpired) else "config",
            provider_id=provider_id,
            reason=type(e).__name__,
        )
        return []

    if result.returncode != 0:
        envelope = _parse_error_envelope(result.stdout)
        if envelope:
            kind, reason = envelope["kind"], envelope.get("message", "unknown error")
        else:
            kind = "provider_failed"
            reason = (
                result.stderr.strip().splitlines()[-1]
                if result.stderr.strip()
                else f"exit {result.returncode}"
            )
        _scan_warning(
            f"scan_boards: {provider_id} -- {result.stderr.strip()}",
            kind=kind,
            provider_id=provider_id,
            reason=reason,
        )
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        _scan_warning(
            f"scan_boards: {provider_id} returned invalid JSON -- {e}",
            kind="provider_failed",
            provider_id=provider_id,
            reason="invalid JSON output",
        )
        return []


def _html_to_text(markup: str) -> str:
    """Strips markup down to plain text (handles plain text passed through
    unchanged too, since BeautifulSoup finds no tags to strip). Joins on
    spaces rather than newlines so inline tags (<b>, <a>, <strong> --
    common inside job-description HTML) don't fragment a sentence across
    multiple lines; explicit <br> tags are converted to real newlines
    first so paragraph-ish breaks are still preserved."""
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # get_text(strip=True) strips each text fragment individually before
    # joining, so a bare "\n" placed via replace_with() strips down to ""
    # and vanishes -- use a non-whitespace sentinel that survives, then
    # convert it back to a real newline after extraction.
    for br in soup.find_all("br"):
        br.replace_with(" [BR] ")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s*\[BR\]\s*", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_DESCRIPTION_CHARS]


def _fetch_posting_text(url: str, provider_id: str = "") -> str:
    """Best-effort plain-text extraction of a posting page. Whole-page
    text, not a per-ATS content selector -- good enough to tailor
    against, not guaranteed clean. Returns "" on any failure; a thin JD
    (title/company only) is still written rather than dropping the
    posting entirely. Only used as a fallback for providers whose raw
    listing carries no description of its own (see fetch_board_jobs) --
    most providers' own APIs already return one, which is both more
    reliable (no per-posting-page fetch to fail/block/rate-limit) and
    avoids sites like himalayas.app that put their posting pages behind
    a Cloudflare challenge no plain HTTP request can pass. `provider_id`
    is optional and only used to tag the structured warning on failure
    (see _scan_warning) -- doesn't affect the fetch itself."""
    try:
        response = requests.get(
            url,
            timeout=POSTING_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; resume-builder/1.0)"},
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        reason = f"HTTP {status_code}" if status_code else type(e).__name__
        _scan_warning(
            f"scan_boards: couldn't fetch posting text from {url} -- {e}",
            kind="posting_text_failed",
            provider_id=provider_id,
            reason=reason,
            url=url,
        )
        return ""

    return _html_to_text(response.text)


def fetch_board_jobs(
    sources: list = None, search_term: str = None, activity=None
) -> list:
    """Runs each requested board provider (default: all of BOARD_PROVIDERS)
    concurrently, applies the title/location prefilter, fetches each surviving posting's
    full text, and returns a list of job dicts. Runs non-blocking asynchronous sweeps
    concurrently instead of blocking sequentially, speeding up runs by up to 10x."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    filters = _load_filters()
    enabled_boards = filters.get("enabled_boards")
    is_default_run = sources is None
    if sources is None:
        if enabled_boards is not None:
            sources = [b for b in BOARD_PROVIDERS if b in enabled_boards]
        else:
            sources = BOARD_PROVIDERS

    jobs = []
    if activity is not None:
        activity.start_source(len(sources), label="Fetching")

    # Local worker task per board provider
    def process_provider(provider_id: str) -> list:
        # `entry.name` is what a provider falls back to for `company` when
        # its own raw listing has none.
        entry = {"name": provider_id}
        if search_term:
            entry["search_term"] = search_term

        try:
            raw_jobs = _run_node_provider(provider_id, entry)
        except Exception as e:
            logging.error(
                f"scan_boards: Exception running node provider {provider_id}: {e}"
            )
            return []

        logging.info(
            f"scan_boards: {provider_id} returned {len(raw_jobs)} raw listing(s)."
        )
        provider_jobs = []

        for raw in raw_jobs:
            title = html.unescape((raw.get("title") or "").strip())
            url = raw.get("url") or ""
            if not title or not url:
                continue
            if title.startswith(("http://", "https://")):
                continue
            if not _passes_title_filter(title):
                continue
            if not _passes_location_filter(raw.get("location")):
                continue

            raw_description = raw.get("description") or ""
            description = (
                _html_to_text(raw_description)
                if raw_description
                else _fetch_posting_text(url, provider_id)
            )

            job = {
                "job_title": title,
                "company_name": html.unescape(
                    (raw.get("company") or provider_id).strip()
                ),
                "source_platform": provider_id,
                "source_job_id": None,
                "source_url": url,
                "location": raw.get("location") or "",
                "posted_at": raw.get("posted_at") or "",
                "description": description,
            }
            _flag_thin_description(job, provider_id, url)
            provider_jobs.append(job)

        return provider_jobs

    # Spin up ThreadPoolExecutor to poll providers concurrently
    # A limit of 8 concurrent workers prevents thread thrashing while maximizing I/O saturation
    max_workers = min(len(sources), 8) if sources else 1
    if sources:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for provider_id in sources:
                if activity is not None:
                    message = f"Checking {cli_art.format_board_name(provider_id)}"
                    activity.step("discovery", "Boards", message, preserve_markup=True)
                futures[executor.submit(process_provider, provider_id)] = provider_id

            for future in as_completed(futures):
                provider_id = futures[future]
                try:
                    result_jobs = future.result()
                    jobs.extend(result_jobs)
                except Exception as e:
                    logging.error(
                        f"scan_boards: Future task failed for provider {provider_id}: {e}"
                    )

    # Fetch custom RSS feeds concurrently!
    custom_feeds = filters.get("custom_feeds") or []
    if custom_feeds and is_default_run:

        def process_feed(feed: dict) -> list:
            feed_name = feed.get("name")
            feed_url = feed.get("url")
            if not feed_name or not feed_url:
                return []

            feed_jobs = []
            try:
                r = requests.get(feed_url, timeout=10)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, "xml")
                    items = soup.find_all("item")
                    for item in items:
                        title_el = item.find("title")
                        link_el = item.find("link")
                        if not title_el or not link_el:
                            continue
                        title = html.unescape(title_el.text.strip())
                        url = link_el.text.strip()
                        if not _passes_title_filter(title):
                            continue

                        desc_el = item.find("description")
                        desc = _html_to_text(desc_el.text.strip()) if desc_el else ""

                        company = ""
                        author_el = item.find("author")
                        if author_el:
                            company = author_el.text.strip()
                        else:
                            dc_creator = item.find("dc:creator")
                            if dc_creator:
                                company = dc_creator.text.strip()

                        job = {
                            "job_title": title,
                            "company_name": company or feed_name,
                            "source_platform": f"custom_{feed_name.lower().replace(' ', '_')}",
                            "source_job_id": None,
                            "source_url": url,
                            "location": "Remote",
                            "posted_at": "",
                            "description": desc,
                        }
                        feed_jobs.append(job)
                    logging.info(
                        f"scan_boards: custom feed {feed_name} returned {len(feed_jobs)} job(s)."
                    )
            except Exception as e:
                logging.warning(
                    f"scan_boards: Failed to fetch custom feed {feed_name}: {e}"
                )
            return feed_jobs

        if activity is not None:
            activity.step(
                "discovery",
                "Boards",
                "Checking custom RSS feeds concurrently",
                preserve_markup=True,
            )

        with ThreadPoolExecutor(max_workers=min(len(custom_feeds), 4)) as executor:
            feed_futures = [
                executor.submit(process_feed, feed) for feed in custom_feeds
            ]
            for future in as_completed(feed_futures):
                try:
                    jobs.extend(future.result())
                except Exception as e:
                    logging.error(f"scan_boards: Failed custom feed future task: {e}")

    return jobs
