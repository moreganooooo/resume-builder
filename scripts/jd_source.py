"""jd_source.py -- resolves a JD identifier to something the pipeline can
work with, whether or not that JD has a file on disk.

Every action in dashboard_actions.py takes a `jd_path`, which made a JD
file the precondition for doing anything. But most job rows never had a
file: the filesystem-to-database migration keyed them by content hash,
and after the terminal-data purge the majority of pending jobs -- and the
majority of high-scoring ones -- live only in data.db. They were visible
and inert.

Rather than write ~1,200 JD files to disk purely so existing code has
something to open, this resolves an identifier on demand:

  * an existing file path resolves to itself, unchanged
  * a database id materializes a TEMPORARY file, and any changes the
    action makes to it are synced back into the database afterwards

The temp file is the point: it costs nothing at rest, which matters on a
space-constrained machine. The one deliberate exception is tailoring --
see materialize_permanently(). Building a resume is the moment a job
stops being a scan result and becomes something being worked, so that is
the moment it earns a real file.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from typing import Iterator, Optional, Tuple

import db
import jd_manager


def lookup_job(job_id: str, profile: Optional[str] = None) -> Optional[dict]:
    """Returns the jobs row for job_id as a dict, or None."""
    conn = db.get_db(profile)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, title, company, status, metadata_json, raw_text, created_at"
            " FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def job_payload(row: dict) -> dict:
    """The JD's own JSON for a row, from metadata_json or raw_text."""
    for column in ("metadata_json", "raw_text"):
        blob = row.get(column)
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _write_jd(path: str, payload: dict, row: dict) -> None:
    """Writes a JD file, restoring the title/company keys the exporter and
    the tailoring pipeline read. A migrated row may have lost them from
    its payload even though the columns are correct."""
    payload = dict(payload)
    payload.setdefault("job_title", row.get("title") or "")
    payload.setdefault("company_name", row.get("company") or "")
    payload.setdefault("id", row.get("id"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def sync_back(path: str, job_id: str, profile: Optional[str] = None) -> None:
    """Reads a materialized JD back into its database row.

    Actions mutate the JD file (save_application_status, save_liveness,
    save_evaluation all write into the JSON), so without this the work
    would be discarded along with the temp file.
    """
    if not os.path.exists(path):
        # run_pipeline moves a JD into completed/ on success, so the temp
        # path is legitimately gone. Nothing to read back.
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    data["id"] = job_id
    jd_manager._sync_jd_to_db(path, data, profile=profile)


@contextlib.contextmanager
def resolved_jd(
    identifier: str, profile: Optional[str] = None
) -> Iterator[Tuple[str, bool]]:
    """Yields (path, is_database_backed) for a JD file path OR a job id.

    For a database-backed job the path points at a temp file that is
    synced back and removed on exit, so callers can keep using the
    file-oriented APIs unchanged.
    """
    if os.path.exists(identifier):
        yield identifier, False
        return

    row = lookup_job(identifier, profile)
    if row is None:
        raise LookupError(
            f"No JD file at {identifier!r} and no job with that id in the database."
        )

    handle, temp_path = tempfile.mkstemp(suffix=".json", prefix="jd_")
    os.close(handle)
    _write_jd(temp_path, job_payload(row), row)

    try:
        yield temp_path, True
        sync_back(temp_path, row["id"], profile)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def materialize_permanently(job_id: str, profile: Optional[str] = None) -> str:
    """Writes a database-only job out as a real JD file and returns its path.

    Used for tailoring, which runs the full pipeline and moves the JD into
    completed/ when it succeeds -- that requires a file with a stable home,
    not a temp one. It is also the right moment to spend the disk: a job
    being tailored is one actually being pursued.

    Returns the existing path when the job already has a file.
    """
    row = lookup_job(job_id, profile)
    if row is None:
        raise LookupError(f"No job with id {job_id!r}.")

    payload = job_payload(row)
    existing = payload.get("path")
    if existing and os.path.exists(existing):
        return existing

    os.makedirs(jd_manager.JDS_DIR, exist_ok=True)
    # Same naming scheme scan.py uses when it writes a scraped JD, so a
    # materialized job is indistinguishable from a scanned one.
    today = datetime.now().strftime("%Y-%m-%d")
    company = jd_manager.sanitize_for_filename(row.get("company") or "UnknownCompany")
    title = jd_manager.sanitize_for_filename(row.get("title") or "UntitledRole")
    filename = f"{today}_{company}_{title}.json"
    path = os.path.join(jd_manager.JDS_DIR, filename)

    counter = 1
    while os.path.exists(path):
        path = os.path.join(
            jd_manager.JDS_DIR, filename.replace(".json", f"_{counter}.json")
        )
        counter += 1

    _write_jd(path, payload, row)
    return path


def set_status(job_id: str, status: str, profile: Optional[str] = None) -> None:
    """Updates a database-backed job's status directly.

    Archiving a database-only job must NOT go through jd_manager.archive_jd:
    that moves a file, and for a temp file it would deposit a stray JD in
    jds/archived/ -- creating exactly the on-disk clutter this module
    exists to avoid.
    """
    conn = db.get_db(profile)
    try:
        with conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = ?",
                (status, job_id),
            )
    finally:
        conn.close()
