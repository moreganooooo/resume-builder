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

import jd_manager
import scan_jobright
import scan_linkedin

SOURCE_FETCHERS = {
    "jobright": scan_jobright.fetch_jobright_jobs,
    "linkedin": scan_linkedin.fetch_linkedin_jobs,
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

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)
    return dest


def run_scan(sources: list = None) -> int:
    """Runs each requested source's fetcher, writes new jobs into jds/ (skipping
    anything already known), and returns the count of new JD files written."""
    sources = sources or list(SOURCE_FETCHERS.keys())
    tracker = jd_manager.JDTracker()
    written = 0

    for source in sources:
        fetch = SOURCE_FETCHERS.get(source)
        if fetch is None:
            print(f"  WARNING: unknown scan source '{source}', skipping. "
                  f"Known sources: {', '.join(SOURCE_FETCHERS)}")
            continue

        print(f"\nScanning {source}...")
        jobs = fetch()
        total = len(jobs)
        print(f"  Fetched {total} jobs from {source}.")

        for i, job in enumerate(jobs, 1):
            company = job.get("company_name", "unknown")
            title = job.get("job_title", "unknown")
            job_id = job.get("source_job_id")
            job_key = str(job_id) if job_id else None
            if job_key and jd_manager.job_key_known(
                job_key, tracker=tracker,
                source_url=job.get("source_url"), company_name=job.get("company_name"),
                job_title=job.get("job_title"),
            ):
                print(f"  [{i}/{total}] Skipping {company} -- {title} (already known)")
                continue

            dest = _write_jd_file(job)
            written += 1
            print(f"  [{i}/{total}] + {company} -- {title} -> {dest}")

    print(f"\nScan summary: {written} new JD file(s) written to jds/.")
    return written
