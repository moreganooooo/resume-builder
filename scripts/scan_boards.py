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
import time

import requests
import yaml
from bs4 import BeautifulSoup

import profile_paths

# board-scanners/ (repo root) holds only the shared engine code (the Node
# provider modules + the run_provider.mjs shim) -- generic across every
# profile, same as any other script in this repo. The actual scan
# *config* (which companies, which search terms, which title/location
# keywords) is 100% profile-specific and lives under
# profiles/<name>/board_scanner/ instead (profile_paths.board_scanner_dir()).
BOARD_SCANNERS_DIR = os.path.join(profile_paths.PROJECT_ROOT, "board-scanners")
RUN_PROVIDER_SCRIPT = os.path.join(BOARD_SCANNERS_DIR, "run_provider.mjs")

BOARD_PROVIDERS = [
    "remoteok", "remotive", "himalayas", "jobicy", "weworkremotely",
    "workingnomads", "fourdayweek", "nodesk", "authenticjobs", "crunchboard",
    "jobspresso", "realworkfromanywhere", "powertofly", "themuse", "hackernews",
    # Same mechanism as everything above -- just needs an API key in the
    # active profile's .env (ADZUNA_APP_ID/ADZUNA_APP_KEY;
    # USAJOBS_API_KEY/USAJOBS_EMAIL) or they return nothing (the
    # provider's own .mjs throws, _run_node_provider logs it and moves on).
    "adzuna", "usajobs",
]

NODE_TIMEOUT_SECONDS = 30
POSTING_FETCH_TIMEOUT_SECONDS = 15
MAX_DESCRIPTION_CHARS = 15_000
MIN_DESCRIPTION_CHARS = 200

def _format_duration(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


class ProgressReporter:
    """Prints "[i/N] <label> <name>... (~Xm Ys remaining)" per item and
    tracks a running average time-per-item for the ETA. A scan against
    scan_ats.py's tracked_companies.yml is ~400 sequential subprocess
    calls with no feedback otherwise -- reads as "did it hang?" on a
    real run. ETA only appears from the 2nd item on (nothing to average
    yet on the 1st)."""

    def __init__(self, total: int, label: str = "Checking"):
        self.total = total
        self.label = label
        self.start = time.time()
        self.done = 0

    def step(self, name: str) -> None:
        self.done += 1
        eta = ""
        if self.done > 1:
            avg = (time.time() - self.start) / self.done
            remaining = avg * (self.total - self.done)
            eta = f" (~{_format_duration(remaining)} remaining)"
        print(f"  [{self.done}/{self.total}] {self.label} {name}...{eta}")


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
        path = os.path.join(profile_paths.board_scanner_dir(profile), "scan_filters.yml")
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


def _scan_warning(msg: str, *, kind: str, provider_id: str, reason: str, url: str = "") -> None:
    """logging.warning() with structured `extra` fields scan.py's
    _ScanWarningCollector reads to render a grouped, themed summary
    instead of a raw wall of WARNING:root: lines -- the plain message is
    still there for anyone watching logs directly (e.g. `resume test -vv`
    or a bare terminal without the themed report)."""
    logging.warning(msg, extra={"scan_warning": True, "kind": kind, "provider_id": provider_id, "reason": reason, "url": url})


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
        kind="thin_description", provider_id=provider_id,
        reason=f"{chars} chars" if chars else "empty", url=source_url,
    )


def _run_node_provider(provider_id: str, entry: dict) -> list:
    try:
        result = subprocess.run(
            ["node", RUN_PROVIDER_SCRIPT, provider_id, json.dumps(entry)],
            capture_output=True, text=True, timeout=NODE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _scan_warning(f"scan_boards: {provider_id} failed to run -- {e}",
                      kind="network" if isinstance(e, subprocess.TimeoutExpired) else "config",
                      provider_id=provider_id, reason=type(e).__name__)
        return []

    if result.returncode != 0:
        envelope = _parse_error_envelope(result.stdout)
        if envelope:
            kind, reason = envelope["kind"], envelope.get("message", "unknown error")
        else:
            kind = "provider_failed"
            reason = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"
        _scan_warning(f"scan_boards: {provider_id} -- {result.stderr.strip()}",
                      kind=kind, provider_id=provider_id, reason=reason)
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        _scan_warning(f"scan_boards: {provider_id} returned invalid JSON -- {e}",
                      kind="provider_failed", provider_id=provider_id, reason="invalid JSON output")
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
            url, timeout=POSTING_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; resume-builder/1.0)"},
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        reason = f"HTTP {status_code}" if status_code else type(e).__name__
        _scan_warning(f"scan_boards: couldn't fetch posting text from {url} -- {e}",
                      kind="posting_text_failed", provider_id=provider_id, reason=reason, url=url)
        return ""

    return _html_to_text(response.text)


def fetch_board_jobs(sources: list = None, search_term: str = None) -> list:
    """Runs each requested board provider (default: all of BOARD_PROVIDERS),
    applies the title/location prefilter, fetches each surviving posting's
    full text, and returns a list of job dicts in the same shape
    scan_jobright.py/scan_linkedin.py already produce."""
    sources = sources or BOARD_PROVIDERS

    jobs = []
    progress = ProgressReporter(len(sources), label="Fetching")
    for provider_id in sources:
        progress.step(provider_id)
        # `entry.name` is what a provider falls back to for `company` when
        # its own raw listing has none (e.g. remoteok.mjs: `j.company ||
        # entry.name`) -- use the provider id, not a placeholder, so a
        # missing company reads as "we don't know, here's the source" (e.g.
        # "workingnomads") instead of leaking a made-up name into real data.
        entry = {"name": provider_id}
        if search_term:
            entry["search_term"] = search_term

        raw_jobs = _run_node_provider(provider_id, entry)
        logging.info(f"scan_boards: {provider_id} returned {len(raw_jobs)} raw listing(s).")

        for raw in raw_jobs:
            title = html.unescape((raw.get("title") or "").strip())
            url = raw.get("url") or ""
            if not title or not url:
                continue
            if title.startswith(("http://", "https://")):
                continue  # a handful of feed entries have a URL as their title -- not a real job title
            if not _passes_title_filter(title):
                continue
            if not _passes_location_filter(raw.get("location")):
                continue

            # Most providers' own APIs already return a full description
            # (career-ops's providers just discarded it since its pipeline
            # never needed one) -- prefer that over a per-posting-page
            # fetch, which is slower and can be blocked/rate-limited/stale.
            # Only fetch the live page when a provider genuinely has none.
            raw_description = raw.get("description") or ""
            description = _html_to_text(raw_description) if raw_description else _fetch_posting_text(url, provider_id)

            job = {
                "job_title": title,
                "company_name": html.unescape((raw.get("company") or provider_id).strip()),
                "source_platform": provider_id,
                "source_job_id": None,
                "source_url": url,
                "location": raw.get("location") or "",
                "posted_at": raw.get("posted_at") or "",
                "description": description,
            }
            _flag_thin_description(job, provider_id, url)
            jobs.append(job)

    return jobs
