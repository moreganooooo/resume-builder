"""
scan.py — the `scan` stage: pulls job postings from external sources and
writes new ones straight into jds/ as JD files (the same format the
pipeline already reads via jd_manager), deduped against
jd_tracker_log.csv and jds/ itself.

No new storage layer (no Mongo, no separate staging file, per 2026-07-04
scope decision) -- a scanned job either becomes a JD file ready for
`resume run`/`resume tailor`, or is skipped as already-known.
"""

import datetime
import json
import os

import cli_art
import jd_manager
import scan_ats
import scan_boards
import scan_jobright
import scan_linkedin
import theme

# A JD just found by a scan is, by definition, confirmed to exist right
# now -- seeding _liveness here means it starts inside liveness.py's
# recency window instead of needing a redundant separate check seconds
# later.
_SCAN_LIVENESS_REASON = "confirmed to exist by scan"

SOURCE_FETCHERS = {
    "jobright": scan_jobright.fetch_jobright_jobs,
    "linkedin": scan_linkedin.fetch_linkedin_jobs,
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
        dest = os.path.join(jd_manager.JDS_DIR, filename.replace(".json", f"_{counter}.json"))
        counter += 1

    # Matches jd_manager.save_liveness()'s exact _liveness shape so
    # liveness.py's recency check reads it back identically either way.
    job["_liveness"] = {
        "result": "active",
        "reason": _SCAN_LIVENESS_REASON,
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)
    return dest


def run_scan(sources: list = None) -> int:
    """Runs each requested source's fetcher, writes new jobs into jds/
    (skipping anything already known), renders a themed report of what
    happened, and returns the count of new JD files written."""
    sources = sources or list(SOURCE_FETCHERS.keys())
    tracker = jd_manager.JDTracker()
    written = 0
    source_results = []

    for source in sources:
        fetch = SOURCE_FETCHERS.get(source)
        if fetch is None:
            source_results.append({"source": source, "error": f"unknown source (known: {', '.join(SOURCE_FETCHERS)})"})
            continue

        jobs = fetch()
        result = {"source": source, "fetched": len(jobs), "written": 0, "skipped": 0, "new_jobs": []}

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
                job_key, tracker=tracker,
                source_url=source_url, company_name=job.get("company_name"),
                job_title=job.get("job_title"),
            ):
                result["skipped"] += 1
                continue

            _write_jd_file(job)
            written += 1
            result["written"] += 1
            result["new_jobs"].append({"company": company, "title": title})

        source_results.append(result)

    cli_art.render_scan_report(source_results, written)
    return written
