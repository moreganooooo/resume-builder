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
EXPIRED_DIR = os.path.join(JDS_DIR, "expired")
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


def sanitize_for_filename(text: str) -> str:
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
        filename = f"{today}_{sanitize_for_filename(company_name)}_{sanitize_for_filename(job_title)}.json"
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


APPLICATIONS_MD = os.path.join(PROJECT_ROOT, "data", "applications.md")

_APPLICATIONS_HEADER = (
    "# Applications Tracker\n\n"
    "| # | Date | Company | Role | Score | Status | PDF | Report | Notes |\n"
    "|---|------|---------|------|-------|--------|-----|--------|-------|\n"
)


def _next_application_row_number(path: str) -> int:
    if not os.path.exists(path):
        return 1
    with open(path, "r", encoding="utf-8") as f:
        data_rows = [
            line for line in f
            if line.startswith("| ") and not line.startswith("| #") and not line.startswith("|---")
        ]
    return len(data_rows) + 1


def append_application_row(company_name: str, job_title: str, has_pdf: bool, path: str = None) -> None:
    """Appends one row to data/applications.md, in career-ops's markdown-table
    tracker format (# | Date | Company | Role | Score | Status | PDF | Report | Notes).

    Score/Report are placeholders ("NA"/"—") until the evaluate stage exists.
    No dedup/merge logic (career-ops's merge-tracker.mjs/dedup-tracker.mjs) --
    resume-builder is the only writer to this file today.
    """
    path = path or APPLICATIONS_MD
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(_APPLICATIONS_HEADER)

    row_number = _next_application_row_number(path)
    date_str = datetime.date.today().isoformat()
    pdf_cell = "✅" if has_pdf else "❌"
    company = company_name or "unknown"
    role = job_title or "unknown"

    row = f"| {row_number} | {date_str} | {company} | {role} | NA | Tailored | {pdf_cell} | — |  |\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(row)


def _read_source_url_and_company(path: str) -> tuple:
    """Returns (source_url, company_name) for a JD file, or (None, None)
    if it's not a JSON object or reading fails."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, None
    if isinstance(data, dict):
        return data.get("source_url"), data.get("company_name")
    return None, None


def job_key_known(job_key: str, tracker: "JDTracker" = None, source_url: str = None,
                   company_name: str = None) -> bool:
    """True if job_key is already completed in the tracker, or a JD file
    for it already exists in jds/ (pending) or jds/completed/ -- matched
    either by job_key, or (when both source_url and company_name are
    given) by an existing file sharing the same source_url AND
    company_name. JobRight sometimes assigns a new source_job_id to a
    posting it's already surfaced once, under an identical apply URL and
    company name -- the company_name check guards against merging two
    genuinely different companies that happen to share application
    infrastructure (e.g. sibling brands on the same Workday tenant).
    Used by scan.py to avoid writing duplicate JD files across repeated
    scan runs."""
    tracker = tracker or JDTracker(TRACKER_CSV)
    if tracker.is_completed(job_key):
        return True

    tracker_filename = os.path.basename(TRACKER_CSV)
    for base_dir in (JDS_DIR, COMPLETED_DIR):
        if not os.path.isdir(base_dir):
            continue
        for name in os.listdir(base_dir):
            if name == tracker_filename or name.startswith("."):
                continue
            path = os.path.join(base_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                if compute_job_key(path) == job_key:
                    return True
            except OSError:
                continue
            if source_url and company_name:
                existing_url, existing_company = _read_source_url_and_company(path)
                if existing_url == source_url and existing_company == company_name:
                    return True
    return False


def _checkpoint_path(job_key: str) -> str:
    return os.path.join(CHECKPOINTS_DIR, f"{sanitize_for_filename(job_key)}.json")


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


def get_pending_jds() -> list:
    """
    Scans JDS_DIR for new work: lists all files at root (ignoring the
    completed/ subfolder), splits any batch exports first, then returns
    paths whose job_key isn't already marked completed in JDTracker.

    Returns list of file paths ready for processing.
    """
    os.makedirs(JDS_DIR, exist_ok=True)
    os.makedirs(COMPLETED_DIR, exist_ok=True)
    tracker = JDTracker(TRACKER_CSV)

    tracker_filename = os.path.basename(TRACKER_CSV)
    root_files = sorted(
        os.path.join(JDS_DIR, name)
        for name in os.listdir(JDS_DIR)
        if os.path.isfile(os.path.join(JDS_DIR, name))
        and name != tracker_filename
        and not name.startswith(".")  # skip hidden files like macOS's .DS_Store
    )

    all_paths = []
    for path in root_files:
        all_paths.extend(split_batch_jds(path))

    return [p for p in all_paths if not tracker.is_completed(compute_job_key(p))]


def get_completed_jds() -> list:
    """
    Lists JD files sitting in COMPLETED_DIR -- every one of these has a
    successfully-built resume (run_pipeline only moves a JD there on
    success; failures stay in JDS_DIR for retry). Used by the menu's
    "Write cover letter for a Specific JD" entry, since a cover letter is
    written after its resume the overwhelming majority of the time.
    """
    os.makedirs(COMPLETED_DIR, exist_ok=True)
    tracker_filename = os.path.basename(TRACKER_CSV)
    return sorted(
        os.path.join(COMPLETED_DIR, name)
        for name in os.listdir(COMPLETED_DIR)
        if os.path.isfile(os.path.join(COMPLETED_DIR, name))
        and name != tracker_filename
        and not name.startswith(".")
    )
