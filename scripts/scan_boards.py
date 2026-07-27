"""
scan_boards.py -- board-scanner source for scan.py, ported from career-ops's
providers/*.mjs plugin layer (vendored into board-scanners/providers/,
2026-07-26; see docs/superpowers/plans/2026-07-16-three-repo-merge-punchlist.md
item 5). Only the zero-config aggregator/search-driven providers are wired
up here (RemoteOK, Remotive, Himalayas, Jobicy, WeWorkRemotely,
WorkingNomads, FourDayWeek, NoDesk, AuthenticJobs, CrunchBoard, Jobspresso,
RealWorkFromAnywhere, PowerToFly, TheMuse, HackerNews) -- none need an API
key or a curated company list, so they produce results immediately. The
API-key providers (Adzuna, USAJobs) and the direct-to-ATS providers
(Greenhouse/Ashby/Lever/etc., which need a curated tracked_companies list)
are a separate follow-up, not ported yet.

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

import requests
import yaml
from bs4 import BeautifulSoup

import profile_paths

BOARD_SCANNERS_DIR = os.path.join(profile_paths.PROJECT_ROOT, "board-scanners")
RUN_PROVIDER_SCRIPT = os.path.join(BOARD_SCANNERS_DIR, "run_provider.mjs")
FILTERS_PATH = os.path.join(BOARD_SCANNERS_DIR, "scan_filters.yml")

BOARD_PROVIDERS = [
    "remoteok", "remotive", "himalayas", "jobicy", "weworkremotely",
    "workingnomads", "fourdayweek", "nodesk", "authenticjobs", "crunchboard",
    "jobspresso", "realworkfromanywhere", "powertofly", "themuse", "hackernews",
]

NODE_TIMEOUT_SECONDS = 30
POSTING_FETCH_TIMEOUT_SECONDS = 15
MAX_DESCRIPTION_CHARS = 15_000

_filters_cache = None


def _load_filters() -> dict:
    global _filters_cache
    if _filters_cache is None:
        with open(FILTERS_PATH, "r", encoding="utf-8") as f:
            _filters_cache = yaml.safe_load(f)
    return _filters_cache


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


def _run_node_provider(provider_id: str, entry: dict) -> list:
    try:
        result = subprocess.run(
            ["node", RUN_PROVIDER_SCRIPT, provider_id, json.dumps(entry)],
            capture_output=True, text=True, timeout=NODE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logging.warning(f"scan_boards: {provider_id} failed to run -- {e}")
        return []

    if result.returncode != 0:
        logging.warning(f"scan_boards: {provider_id} -- {result.stderr.strip()}")
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logging.warning(f"scan_boards: {provider_id} returned invalid JSON -- {e}")
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


def _fetch_posting_text(url: str) -> str:
    """Best-effort plain-text extraction of a posting page. Whole-page
    text, not a per-ATS content selector -- good enough to tailor
    against, not guaranteed clean. Returns "" on any failure; a thin JD
    (title/company only) is still written rather than dropping the
    posting entirely. Only used as a fallback for providers whose raw
    listing carries no description of its own (see fetch_board_jobs) --
    most providers' own APIs already return one, which is both more
    reliable (no per-posting-page fetch to fail/block/rate-limit) and
    avoids sites like himalayas.app that put their posting pages behind
    a Cloudflare challenge no plain HTTP request can pass."""
    try:
        response = requests.get(
            url, timeout=POSTING_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; resume-builder/1.0)"},
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.warning(f"scan_boards: couldn't fetch posting text from {url} -- {e}")
        return ""

    return _html_to_text(response.text)


def fetch_board_jobs(sources: list = None, search_term: str = None) -> list:
    """Runs each requested board provider (default: all of BOARD_PROVIDERS),
    applies the title/location prefilter, fetches each surviving posting's
    full text, and returns a list of job dicts in the same shape
    scan_jobright.py/scan_linkedin.py already produce."""
    sources = sources or BOARD_PROVIDERS

    jobs = []
    for provider_id in sources:
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
            description = _html_to_text(raw_description) if raw_description else _fetch_posting_text(url)

            jobs.append({
                "job_title": title,
                "company_name": html.unescape((raw.get("company") or provider_id).strip()),
                "source_platform": provider_id,
                "source_job_id": None,
                "source_url": url,
                "location": raw.get("location") or "",
                "posted_at": raw.get("posted_at") or "",
                "description": description,
            })

    return jobs
