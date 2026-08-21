"""
websearch_ddg.py -- DuckDuckGo backend for the `scan_method: websearch`
sweeps, replacing Brave's now-metered free tier.

Why the search runs in Python while the FILTERING stays in
board-scanners/providers/websearch.mjs: that module already holds a lot
of hard-won logic -- blocked-domain lists, job-URL recognition,
direct-vs-listicle title checks, company extraction from a URL, provider
promotion via _recognition.mjs -- and duplicating any of it in a second
language is how the two drift apart. So Python does the part Node cannot
do reliably, and hands the raw results back for the existing filter to
judge.

Node cannot do it reliably: DuckDuckGo's HTML endpoint answers a plain
fetch with HTTP 202 and an empty challenge page after the first request
or two (measured 2026-08-21 -- one query returned 47 links, every
subsequent one returned 0, with and without pacing). The `ddgs` library
performs the token handshake those endpoints expect, and returned 10
results for each of three consecutive queries in 2.5-7s.

Brave still wins when BRAVE_API_KEY is set: it is a real search API with
structured results, and an existing key should not be thrown away. This
is the no-key path, which is now the default one.
"""

import logging
import os
import sys

# Sweeps run sequentially through scan_ats.py's own loop, so this is a
# per-call cap rather than a global budget.
DEFAULT_MAX_RESULTS = 20


# Opt-in escape hatch for tests that deliberately exercise this function
# with a mocked backend.
_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"


def _blocked_under_tests() -> bool:
    """True when a test run would otherwise make a REAL search request.

    Same failure this repo already hit when database candidates were
    added to liveness: existing tests traversed the new code path and
    started doing live network I/O nobody asked for. Here, every
    scan_ats test that exercises the sweep loop reaches this function,
    so without the guard the suite fires real DuckDuckGo queries and
    fails when they are rate-limited.

    Tests that mean to call this set RESUME_ALLOW_TEST_NETWORK=1 and
    patch the backend.
    """
    return "unittest" in sys.modules and not os.environ.get(_TEST_NETWORK_ENV)


def search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list:
    """Returns [{"url", "title", "description"}, ...] for one query.

    Shaped to match the fields websearch.mjs reads off a Brave result, so
    the JS side needs no per-backend branching beyond "were results
    handed to me".

    Never raises: a search backend that is rate-limited or offline should
    cost this sweep its results, not abort the whole scan.
    """
    if not query or not query.strip():
        return []
    if _blocked_under_tests():
        return []
    try:
        from ddgs import DDGS
    except ImportError:
        logging.error(
            "websearch_ddg: ddgs is not installed "
            "(pip install -r requirements.txt); skipping sweep."
        )
        return []

    try:
        rows = list(DDGS().text(query, max_results=max_results))
    except Exception as e:
        logging.error(f"websearch_ddg: search failed for {query!r} -- {e}")
        return []

    results = []
    for row in rows:
        url = (row.get("href") or "").strip()
        title = (row.get("title") or "").strip()
        if not url or not title:
            continue
        results.append(
            {
                "url": url,
                "title": title,
                # ddgs calls the snippet "body"; websearch.mjs reads
                # `description`, matching Brave's field name.
                "description": (row.get("body") or "").strip(),
            }
        )
    return results
