"""
jd_manager.py — JD intake, identity, completion tracking, and per-job
checkpointing for the batch resume-building pipeline.

Used by orchestrator.py so it can process every not-yet-completed JD in
jds/ without a per-JD command-line invocation.
"""

import csv
import datetime
import hashlib
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

JDS_DIR = os.path.join(PROJECT_ROOT, "jds")
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
CHECKPOINTS_DIR = os.path.join(PROJECT_ROOT, "output", "checkpoints")
TRACKER_CSV = os.path.join(JDS_DIR, "jd_tracker_log.csv")


def _meta_from_dict(job: dict) -> tuple:
    return job.get("job_title", ""), job.get("company_name", "")


def compute_job_key(jd_path: str) -> str:
    """
    Returns the tracking identity for a JD file: its source_job_id if the
    file is a JSON object carrying one, otherwise a SHA-256 hash of the
    file's raw bytes (covers plain-text drop-ins and any JSON without an id).
    """
    with open(jd_path, "rb") as f:
        raw_bytes = f.read()

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = None

    if isinstance(data, dict) and data.get("source_job_id"):
        return str(data["source_job_id"])

    return hashlib.sha256(raw_bytes).hexdigest()


def extract_job_meta(jd_path: str) -> tuple:
    """Returns (job_title, company_name) for a JD file, or ("", "") if it's
    not a JSON object or the fields are absent."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "", ""

    if isinstance(data, dict):
        return _meta_from_dict(data)
    return "", ""


def _sanitize_for_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", text or "")
    return cleaned or "Unknown"


def split_batch_jds(jd_path: str) -> list:
    """
    If jd_path contains a JSON array (a batch export), writes one file per
    array element into JDS_DIR named "YYYY-MM-DD_Company_JobTitle.json" and
    deletes the original. Returns the list of new file paths.

    If jd_path is anything else (single JSON object, plain text, invalid
    JSON), returns [jd_path] unchanged.
    """
    with open(jd_path, "r", encoding="utf-8") as f:
        raw = f.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [jd_path]

    if not isinstance(data, list):
        return [jd_path]

    os.makedirs(JDS_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    new_paths = []

    for job in data:
        job_title, company_name = _meta_from_dict(job) if isinstance(job, dict) else ("", "")
        filename = f"{today}_{_sanitize_for_filename(company_name)}_{_sanitize_for_filename(job_title)}.json"
        dest = os.path.join(JDS_DIR, filename)

        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(JDS_DIR, filename.replace(".json", f"_{counter}.json"))
            counter += 1

        with open(dest, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)
        new_paths.append(dest)

    os.remove(jd_path)
    return new_paths


TRACKER_FIELDNAMES = [
    "job_key", "job_title", "company_name", "source_file",
    "status", "date_processed", "output_json", "output_pdf", "error_message",
]


class JDTracker:
    """Thin CSV-backed completion log, keyed by job_key."""

    def __init__(self, csv_path: str = None):
        self.csv_path = csv_path or TRACKER_CSV

    def _read_rows(self) -> list:
        if not os.path.exists(self.csv_path):
            return []
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _append_row(self, row: dict) -> None:
        parent = os.path.dirname(self.csv_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        file_exists = os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def is_completed(self, job_key: str) -> bool:
        return any(row["job_key"] == job_key and row["status"] == "completed"
                   for row in self._read_rows())

    def mark_completed(self, job_key, job_title="", company_name="", source_file="",
                        output_json="", output_pdf="") -> None:
        self._append_row({
            "job_key": job_key,
            "job_title": job_title,
            "company_name": company_name,
            "source_file": source_file,
            "status": "completed",
            "date_processed": datetime.datetime.now().isoformat(timespec="seconds"),
            "output_json": output_json,
            "output_pdf": output_pdf,
            "error_message": "",
        })

    def mark_failed(self, job_key, job_title="", company_name="", source_file="",
                     error_message="") -> None:
        self._append_row({
            "job_key": job_key,
            "job_title": job_title,
            "company_name": company_name,
            "source_file": source_file,
            "status": "failed",
            "date_processed": datetime.datetime.now().isoformat(timespec="seconds"),
            "output_json": "",
            "output_pdf": "",
            "error_message": error_message,
        })


def _checkpoint_path(job_key: str) -> str:
    return os.path.join(CHECKPOINTS_DIR, f"{job_key}.json")


def load_checkpoint(job_key: str) -> dict:
    path = _checkpoint_path(job_key)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_checkpoint(job_key: str, data: dict) -> None:
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    with open(_checkpoint_path(job_key), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_checkpoint(job_key: str) -> None:
    path = _checkpoint_path(job_key)
    if os.path.exists(path):
        os.remove(path)
