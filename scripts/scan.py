"""
scan.py — the `scan` stage: pulls job postings from external sources and
writes new ones straight into jds/ as JD files (the same format the
pipeline already reads via jd_manager), deduped against
jd_tracker_log.csv and jds/ itself.

No new storage layer (no Mongo, no separate staging file, per 2026-07-04
scope decision) -- a scanned job either becomes a JD file ready for
`resume run`/`resume tailor`, or is skipped as already-known.
"""

import collections
import datetime
import json
import logging
import os

import cli_art
import jd_manager
import liveness
import scan_ats
import scan_boards
import scan_indeed
import scan_jobright
import scan_linkedin
import theme
from atomic_write import atomic_write


class _ScanWarningCollector(logging.Handler):
    """Captures scan_boards.py/scan_ats.py's structured warnings
    (posting-text fetch failures, provider failures -- anything logged
    via scan_boards._scan_warning()) instead of letting Python's default
    last-resort handler dump them straight to the terminal as raw
    WARNING:root: lines. Installed on the root logger for the duration
    of run_scan() and suppresses that default dump entirely (attaching
    any handler to the root logger takes over from the last-resort
    fallback) -- render_scan_report() presents a grouped, themed summary
    from what this collects instead. Only captures records carrying the
    `scan_warning` marker, so an unrelated stray warning elsewhere in the
    app during a scan isn't silently swallowed."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        if getattr(record, "scan_warning", False):
            self.records.append(record)


def _summarize_warnings(records: list) -> list:
    """Groups captured warning records by (provider_id, kind, reason),
    sorted most-frequent-first -- "workday: posting text fetch failed
    (HTTP 404) x44" reads as one line instead of 44 raw ones."""
    counts = collections.Counter((r.provider_id, r.kind, r.reason) for r in records)
    return [
        {"provider_id": provider_id, "kind": kind, "reason": reason, "count": count}
        for (provider_id, kind, reason), count in sorted(
            counts.items(), key=lambda kv: -kv[1]
        )
    ]


# A JD just found by a scan is, by definition, confirmed to exist right
# now -- seeding _liveness here means it starts inside liveness.py's
# recency window instead of needing a redundant separate check seconds
# later.
_SCAN_LIVENESS_REASON = "confirmed to exist by scan"

# Each verify pass is one real Chromium navigation (~16s, see liveness.py's
# docstring) run sequentially over every newly-written JD, with no cap and
# no confirmation -- a permissive scan_filters.yml scaffold (empty
# positive: list, see seed_scan_filters_from_target_roles() in
# bootstrap_profile.py) plus 17+ aggregator boards means a stranger's
# first scan can write hundreds of JDs and then hang for hours verifying
# all of them (B34). Above this many, ask before running the full verify
# pass in a real terminal; in a non-interactive context (no one there to
# answer), cap automatically rather than hang unbounded.
VERIFY_CONFIRM_THRESHOLD = 25

SOURCE_FETCHERS = {
    "jobright": scan_jobright.fetch_jobright_jobs,
    "linkedin": scan_linkedin.fetch_linkedin_jobs,
    # Indeed via JobSpy -- the largest US board and, so far, the only
    # free source of tailoring-grade text for LOCAL roles. See
    # scan_indeed.py for why it is a Python source and not a Node
    # provider, and why it scrapes only Indeed of JobSpy's five sites.
    "indeed": scan_indeed.fetch_indeed_jobs,
    "boards": scan_boards.fetch_board_jobs,
    "ats": scan_ats.fetch_ats_jobs,
}


def _write_jd_file(job: dict) -> str:
    os.makedirs(jd_manager.JDS_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    company = jd_manager.sanitize_for_filename(job.get("company_name", ""))
    title = jd_manager.sanitize_for_filename(job.get("job_title", ""))
    filename = f"{today}_{company}_{title}.json"
    dest = os.path.join(jd_manager.JDS_DIR, filename)

    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(
            jd_manager.JDS_DIR, filename.replace(".json", f"_{counter}.json")
        )
        counter += 1

    # Only seed an optimistic _liveness for JDs with no source_url --
    # those never become liveness candidates (_gather_candidates()
    # requires a url), so this is the only liveness signal
    # jd_manager.compute_posting_age_days()'s fallback will ever see for
    # them. A JD with a source_url gets a real _liveness from the verify
    # pass (if one runs) via jd_manager.save_liveness(), which
    # unconditionally overwrites whatever's seeded here -- seeding one
    # here too would just sit stale and misleadingly "confirmed alive"
    # for a full jd_manager.RECENCY_HOURS whenever verify doesn't end up
    # running for this particular posting (--no-verify, or the
    # VERIFY_CONFIRM_THRESHOLD cap above declining to check everything)
    # (B42). Matches jd_manager.save_liveness()'s exact _liveness shape
    # so liveness.py's recency check reads either source back identically.
    if not job.get("source_url"):
        job["_liveness"] = {
            "result": "active",
            "reason": _SCAN_LIVENESS_REASON,
            "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }

    # Stamp first-sighting BEFORE the write, in-dict, rather than calling
    # jd_manager.save_discovered_at() afterward -- that would mean a
    # read-modify-rewrite of a file written microseconds earlier, and would
    # leave the stamp missing entirely if the process died in between.
    # Only when the source published no real posted date: a real one is
    # strictly better information, and _discovered_at is consulted purely
    # as a fallback (see jd_manager.compute_posting_age_days()).
    if not any(job.get(field) for field in jd_manager._POSTED_DATE_FIELDS):
        job["_discovered_at"] = {
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": "scan",
        }

    with atomic_write(dest, encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)
    return dest


def run_scan(sources: list = None, verify: bool = True) -> int:
    """Runs each requested source's fetcher, writes new jobs into jds/
    (skipping anything already known), then -- unless verify=False --
    runs a real Playwright liveness check on exactly the postings just
    written (career-ops's default-on `scan.mjs --verify`, ported) and
    drops any confirmed-expired ones into jds/expired/ before the report
    ever presents them as a hit. An API/RSS feed can list a posting
    that's already gone by the time we look (seen live: TheMuse serving
    a 404 for a listed posting, 2026-07-26) -- _write_jd_file()'s
    optimistic "confirmed to exist by scan" _liveness seed is a
    scan-time assumption, not a verified fact. Renders a themed report
    of what happened and returns the count of new JD files still
    present in jds/ after verification."""
    sources = sources or list(SOURCE_FETCHERS.keys())
    tracker = jd_manager.JDTracker()
    # Built once and updated in memory as jobs are written below, instead
    # of job_key_known() re-walking jds/+completed/+archived/+expired/ and
    # re-parsing every file on every single candidate -- candidates x
    # total_JD_files file opens on a mature profile otherwise (B35).
    known_jobs_index = jd_manager.build_known_jobs_index()
    written = 0
    source_results = []
    # {path: (source_result_dict, new_jobs_entry_dict)}, so the verify
    # pass below can find and remove exactly the entries that got moved
    # to jds/expired/, across every source, without re-deriving anything.
    written_paths = {}

    collector = _ScanWarningCollector()
    root_logger = logging.getLogger()
    root_logger.addHandler(collector)
    try:
        with cli_art.new_scan_activity() as activity:
            for source in sources:
                fetch = SOURCE_FETCHERS.get(source)
                if fetch is None:
                    source_results.append(
                        {
                            "source": source,
                            "error": f"unknown source (known: {', '.join(SOURCE_FETCHERS)})",
                        }
                    )
                    continue

                warnings_before = len(collector.records)
                jobs = fetch(activity=activity)
                source_warnings = collector.records[warnings_before:]
                result = {
                    "source": source,
                    "fetched": len(jobs),
                    "written": 0,
                    "skipped": 0,
                    "dropped_expired": 0,
                    "new_jobs": [],
                    "warnings": _summarize_warnings(source_warnings),
                }

                for job in jobs:
                    company = job.get("company_name", "unknown")
                    title = job.get("job_title", "unknown")
                    job_id = job.get("source_job_id")
                    source_url = job.get("source_url")
                    # Board-provider jobs have no numeric source_job_id, only a
                    # URL -- fall back to it so job_key_known() actually runs for
                    # them instead of silently skipping dedup (job_key used to be
                    # None whenever source_job_id was absent, and the caller only
                    # dedups when job_key is truthy).
                    job_key = str(job_id) if job_id else (source_url or "")
                    if job_key and jd_manager.job_key_known(
                        job_key,
                        tracker=tracker,
                        source_url=source_url,
                        company_name=job.get("company_name"),
                        job_title=job.get("job_title"),
                        index=known_jobs_index,
                    ):
                        result["skipped"] += 1
                        continue

                    dest = _write_jd_file(job)
                    jd_manager.add_to_known_jobs_index(
                        known_jobs_index,
                        job_key,
                        source_url=source_url,
                        company_name=job.get("company_name"),
                        job_title=job.get("job_title"),
                    )
                    written += 1
                    result["written"] += 1
                    new_job_entry = {"company": company, "title": title}
                    result["new_jobs"].append(new_job_entry)
                    written_paths[dest] = (result, new_job_entry)

                source_results.append(result)
                activity.tally(
                    fetched=sum(r.get("fetched", 0) for r in source_results),
                    written=sum(r.get("written", 0) for r in source_results),
                    skipped=sum(r.get("skipped", 0) for r in source_results),
                )
    finally:
        root_logger.removeHandler(collector)

    if verify and written_paths:
        paths_to_verify = list(written_paths.keys())
        if len(paths_to_verify) > VERIFY_CONFIRM_THRESHOLD:
            proceed = True
            if cli_art.console.is_terminal:
                proceed = cli_art.confirm(
                    f"{len(paths_to_verify)} new postings found -- verify all of them with a "
                    f"real browser check (~{len(paths_to_verify) * 5 // 60} min)? "
                    f"(No verifies just the first {VERIFY_CONFIRM_THRESHOLD}.)",
                    default=False,
                )
            if not proceed:
                paths_to_verify = paths_to_verify[:VERIFY_CONFIRM_THRESHOLD]
        with cli_art.new_scan_activity() as verify_activity:
            verify_result = liveness.verify_jd_paths(
                paths_to_verify, activity=verify_activity
            )
        for path in verify_result.get("expired_source_paths", []):
            entry = written_paths.get(path)
            if not entry:
                continue
            result, new_job_entry = entry
            result["written"] -= 1
            result["dropped_expired"] += 1
            # By identity, not list.remove()'s by-value match -- two
            # postings can share the same company+title (a real posting
            # cross-listed, or just coincidence), and .remove() would drop
            # whichever one happens to come first in the list regardless
            # of which path this expired_source_paths entry is actually about
            # (B42).
            for i, candidate in enumerate(result["new_jobs"]):
                if candidate is new_job_entry:
                    del result["new_jobs"][i]
                    break
            written -= 1

    cli_art.render_scan_report(source_results, written)
    return written
