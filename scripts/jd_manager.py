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
import logging
import os
import re
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

JDS_DIR = profile_paths.jds_dir()
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
EXPIRED_DIR = os.path.join(JDS_DIR, "expired")
ARCHIVED_DIR = os.path.join(JDS_DIR, "archived")
CHECKPOINTS_DIR = profile_paths.checkpoints_dir()
TRACKER_CSV = profile_paths.tracker_csv_path()


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


def extract_source_url(jd_path: str) -> str:
    """Returns the source_url for a JD file, or "" if it's not a JSON
    object, the field is absent, or reading fails. This is where you'd
    go to actually view the posting and start an application -- surfaced
    in data/applications.md's Link column."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return ""
    if isinstance(data, dict):
        return data.get("source_url") or ""
    return ""


def save_evaluation(jd_path: str, evaluation: dict) -> None:
    """Persists an evaluate_fit() result into the JD's own JSON file under
    an _evaluation key, so a later picker can filter/sort/label by it
    without re-running the (real, costly) Gemini evaluation call. No-ops
    silently for non-JSON-dict JDs (e.g. plain-text fixtures) -- they
    simply never become eligible for the evaluated-only picker."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    data["_evaluation"] = {
        "composite_score": evaluation.get("composite_score"),
        "fit_score": evaluation.get("fit_score"),
        "interview_odds_score": evaluation.get("interview_odds_score"),
        "practical_pursue_score": evaluation.get("practical_pursue_score"),
        "recommendation": evaluation.get("recommendation"),
        "why": evaluation.get("why") or "",
        "recruiter_read": evaluation.get("recruiter_read") or "",
        "hard_blockers": evaluation.get("hard_blockers") or [],
        "posting_legitimacy": evaluation.get("posting_legitimacy") or "",
        "posting_legitimacy_notes": evaluation.get("posting_legitimacy_notes") or "",
        "archetype": evaluation.get("archetype") or "",
        "fit_subscores": evaluation.get("fit_subscores") or {},
        "interview_odds_subscores": evaluation.get("interview_odds_subscores") or {},
        "practical_pursue_subscores": evaluation.get("practical_pursue_subscores") or {},
        "posting_age_days": evaluation.get("posting_age_days"),
        "evaluated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with atomic_write(jd_path, encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_evaluation(jd_path: str) -> dict | None:
    """Reads back a persisted _evaluation (see save_evaluation()), or None
    if the JD isn't a JSON dict or has never been evaluated."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_evaluation")


def save_research(jd_path: str, research: dict) -> None:
    """Persists a company research result into the JD's own JSON file under
    an _research key, so the dashboard or picker can display it without
    re-running the Gemini research call."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    data["_research"] = {
        "_research_source": research.get("_research_source") or "",
        "overall_tone_adjective": research.get("overall_tone_adjective") or "",
        "tone_register": research.get("tone_register") or "",
        "pronoun_framing": research.get("pronoun_framing") or "",
        "sentence_style": research.get("sentence_style") or "",
        "jargon_density": research.get("jargon_density") or "",
        "recurring_keywords": research.get("recurring_keywords") or [],
        "company_facts": research.get("company_facts") or [],
        "company_hq_location": research.get("company_hq_location") or "",
        "notable_highlights": research.get("notable_highlights") or [],
        "vocabulary_substitutions": research.get("vocabulary_substitutions") or [],
        "researched_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with atomic_write(jd_path, encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_research(jd_path: str) -> dict | None:
    """Reads back a persisted _research (see save_research()), or None
    if the JD isn't a JSON dict or has never been researched."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_research")


def save_coverage(jd_path: str, coverage: dict) -> None:
    """Persists a computed keyword coverage result into the JD's own JSON file
    under a _coverage key (score, band, matched, missing, checked_at),
    following the same underscore-prefixed metadata pattern as _evaluation."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    data["_coverage"] = {
        "score": coverage.get("score"),
        "band": coverage.get("band"),
        "matched": coverage.get("matched") or [],
        "missing": coverage.get("missing") or [],
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with atomic_write(jd_path, encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_coverage(jd_path: str) -> dict | None:
    """Reads back a persisted _coverage (see save_coverage()), or None
    if the JD isn't a JSON dict or has never had its coverage computed."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_coverage")



def save_liveness(jd_path: str, result: str, reason: str = "") -> None:
    """Persists a liveness result into the JD's own JSON file under a
    _liveness key (result, reason, checked_at), matching _evaluation's
    existing pattern -- lets liveness.py skip re-checking any JD whose
    _liveness.checked_at is still within the recency window. No-ops
    silently for non-JSON-dict JDs, same as save_evaluation()."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    data["_liveness"] = {
        "result": result,
        "reason": reason,
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with atomic_write(jd_path, encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def move_jd_to(jd_path: str, dest_dir: str) -> str:
    """Moves a JD into dest_dir WITHOUT ever clobbering a file already
    there, returning the destination path actually used.

    The collision loop is the whole point. `shutil.move` overwrites its
    destination silently, and several independent writers target the same
    directories -- liveness.py and stale_sweep.py both move into
    EXPIRED_DIR -- so two postings that happen to share a basename (same
    company and title from two sources is entirely ordinary) meant one
    JD, with its evaluation and application history, simply vanished. No
    error, no log.

    shutil.move rather than os.rename because these directories can sit
    on a different filesystem from the source (a synced volume); rename
    fails across devices where move falls back to copy+delete."""
    os.makedirs(dest_dir, exist_ok=True)
    basename = os.path.basename(jd_path)
    dest = os.path.join(dest_dir, basename)
    counter = 1
    while os.path.exists(dest):
        stem, ext = os.path.splitext(basename)
        dest = os.path.join(dest_dir, f"{stem}_{counter}{ext}")
        counter += 1
    shutil.move(jd_path, dest)
    return dest


def save_discovered_at(jd_path: str, when: str | None = None, source: str = "scan") -> None:
    """Stamps when this posting first entered the queue, under a
    _discovered_at key (date, source) -- same underscore-prefixed
    persisted-metadata convention as _evaluation/_liveness/_application.

    Exists because roughly a third of a real queue carries no posted date
    at all: plenty of sources simply don't publish one, and those
    postings were consequently un-ageable -- never devalued by the
    staleness curve, never sweepable, permanently resident. A discovery
    date is a weaker signal than a real posted date (a posting may have
    been open a while before a scan first saw it) which is exactly why it
    is recorded separately and consulted only as a fallback, rather than
    being written into posted_at where it would masquerade as source
    truth.

    `source` records how the date was arrived at -- "scan" when a scan
    saw it live, "backfill-mtime" when inferred from the file's own
    modification time for a posting that predates this mechanism. Keeping
    that distinction visible matters: one is observed, the other inferred.

    Never overwrites an existing stamp -- first sighting is the one that
    counts, and re-stamping would make a posting perpetually young."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict) or data.get("_discovered_at"):
        return

    data["_discovered_at"] = {
        "date": when or datetime.datetime.now().isoformat(timespec="seconds"),
        "source": source,
    }
    with atomic_write(jd_path, encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_discovered_at(jd_path: str) -> dict | None:
    """Reads back a persisted _discovered_at (see save_discovered_at()),
    or None if the JD isn't a JSON dict or was never stamped."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_discovered_at")


def read_liveness(jd_path: str) -> dict | None:
    """Reads back a persisted _liveness (see save_liveness()), or None if
    the JD isn't a JSON dict or has never had a liveness check recorded."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_liveness")


# Real posted-date field names vary by source: resume-builder's own board/
# ATS providers (scan_boards.py/scan_ats.py) normalize to posted_at (ISO
# string); JobRight and LinkedIn (scan_jobright.py/scan_linkedin.py) use
# publish_time (JobRight: unix ms; LinkedIn: whatever the scraper library
# hands back -- treated the same way here since _parse_flexible_date
# tries both ISO and numeric-timestamp parsing regardless of source).
_POSTED_DATE_FIELDS = ("posted_at", "publish_time")


def _parse_flexible_date(raw) -> datetime.datetime | None:
    """Best-effort parse of a date value that could be an ISO-8601
    string, a unix timestamp (seconds or milliseconds, by magnitude), or
    a numeric string. Returns None rather than raising on anything else
    -- an unparseable/missing date should mean "no age signal," not a
    crash."""
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                raw = float(raw)
            except ValueError:
                return None
    if isinstance(raw, (int, float)):
        ts = raw / 1000 if raw > 10**12 else raw
        try:
            return datetime.datetime.fromtimestamp(ts)
        except (ValueError, OSError, OverflowError):
            return None
    return None


def compute_posting_age_days(jd_path: str) -> int | None:
    """Best-effort days-since-posted for a JD, checked in priority order:
    a real posted-date field (_POSTED_DATE_FIELDS, however the source
    encoded it), else the _liveness "confirmed to exist by scan"
    timestamp (the date this JD was actually discovered by a scan in
    this program -- the fallback Morgan asked for when a real posted
    date isn't available), else None (no age signal at all -- callers
    should treat that as "don't penalize," not "assume old"). Reads the
    raw JD file directly (not read_jd_text(), which strips underscore-
    prefixed keys including _liveness -- exactly the fallback this
    needs)."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    posted = None
    for field in _POSTED_DATE_FIELDS:
        raw = data.get(field)
        if raw:
            posted = _parse_flexible_date(raw)
            if posted:
                break

    if not posted:
        # Explicit discovery stamp (see save_discovered_at()) -- checked
        # ahead of the _liveness fallback below because it is written the
        # moment a posting is first saved, whereas _liveness only carries
        # a usable date when a scan happened to run a verify pass. Both
        # are "first seen by this program", but this one is recorded for
        # that purpose rather than inferred from a side effect.
        discovered = data.get("_discovered_at") or {}
        if discovered.get("date"):
            posted = _parse_flexible_date(discovered["date"])

    if not posted:
        liveness = data.get("_liveness") or {}
        if liveness.get("reason") == "confirmed to exist by scan" and liveness.get("checked_at"):
            posted = _parse_flexible_date(liveness["checked_at"])

    if not posted:
        return None

    now = datetime.datetime.now(posted.tzinfo)
    return max((now - posted).days, 0)


APPLICATION_STATUSES = ["Applied", "Responded", "Interview", "Offer", "Rejected", "Withdrawn"]


def save_application_status(jd_path: str, status: str, log_followup: bool = False) -> None:
    """Persists real-world application progress into the JD's own JSON
    under an _application key -- the prerequisite the follow-up cadence
    tracker needs (career-ops's classification depends on status
    transitions this repo's tracker never recorded before). status must
    be one of APPLICATION_STATUSES. applied_at is set once, the first
    time status becomes "Applied", and never overwritten by a later
    status change, so cadence math always has a stable anchor date.
    log_followup=True additionally increments follow_up_count and stamps
    last_followup_at -- pass it alongside a status update, or on its own
    call to log a follow-up without changing status. No-ops silently for
    non-JSON-dict JDs, matching save_evaluation()/save_liveness()."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    now = datetime.datetime.now().isoformat(timespec="seconds")
    existing = data.get("_application") or {}

    applied_at = existing.get("applied_at")
    if status == "Applied" and not applied_at:
        applied_at = now

    follow_up_count = existing.get("follow_up_count", 0)
    last_followup_at = existing.get("last_followup_at")
    if log_followup:
        follow_up_count += 1
        last_followup_at = now

    data["_application"] = {
        "status": status,
        "applied_at": applied_at,
        "status_changed_at": now,
        "follow_up_count": follow_up_count,
        "last_followup_at": last_followup_at,
    }
    with atomic_write(jd_path, encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_application_status(jd_path: str) -> dict | None:
    """Reads back a persisted _application (see save_application_status()),
    or None if the JD isn't a JSON dict or has never had a status set."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_application")


def read_jd_text(jd_path: str) -> str:
    """Reads a JD file's content for prompt use, stripping any persisted
    underscore-prefixed metadata key (_evaluation, _liveness, ...; see
    save_evaluation()/save_liveness()) if present so a prior evaluation's
    score/recommendation or a liveness result never leaks into a Gemini
    prompt as if it were job-description content. Passes plain-text (or
    otherwise non-JSON-dict) JDs through unchanged. Raises
    FileNotFoundError exactly like a raw open() would, so existing
    call-site error handling needs no changes."""
    with open(jd_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(data, dict) and any(k.startswith("_") for k in data):
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        return json.dumps(data, indent=2)
    return raw_text


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

        with atomic_write(dest, encoding="utf-8") as f:
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

    def count_completed(self) -> int:
        """Number of 'completed' rows in the ledger. Append-only, so this
        only ever grows -- unlike a count of COMPLETED_DIR, which archive_jd()
        can decrement."""
        return sum(1 for row in self._read_rows() if row.get("status") == "completed")

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


APPLICATIONS_MD = profile_paths.applications_md_path()

_APPLICATIONS_HEADER = (
    "# Applications Tracker\n\n"
    "| # | Date | Company | Role | Score | Status | PDF | Link | Report | Notes |\n"
    "|---|------|---------|------|-------|--------|-----|------|--------|-------|\n"
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


def append_application_row(company_name: str, job_title: str, has_pdf: bool,
                            source_url: str = "", path: str = None,
                            evaluation: dict = None, jd_data: dict = None,
                            notes: str = "") -> None:
    """Appends one row to data/applications.md, in career-ops's markdown-table
    tracker format (# | Date | Company | Role | Score | Status | PDF | Link |
    Report | Notes). Link is a clickable "[Apply](source_url)" -- this is
    where to actually go read the posting and start an application once a
    resume's built; "—" when no source_url is known (e.g. a manually
    dropped-in JD).

    Score/Report are filled from a persisted evaluation (see
    save_evaluation()/read_evaluation()) when one is passed in -- Score as
    "X.XX/5", Report as the recommendation label (e.g. "Strong pursue").
    Both fall back to "NA"/"—" when no evaluation exists, e.g. a JD tailored
    without ever running through `resume evaluate` first.
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
    pdf_cell = "✓" if has_pdf else "—"
    company = company_name or "unknown"
    role = job_title or "unknown"
    link_cell = f"[Apply]({source_url})" if source_url else "—"

    status = (jd_data or {}).get("_application", {}).get("status") or "Tailored"

    composite_score = (evaluation or {}).get("composite_score")
    score_cell = f"{composite_score:.2f}/5" if isinstance(composite_score, (int, float)) else "NA"
    report_cell = (evaluation or {}).get("recommendation") or "—"

    row = (
        f"| {row_number} | {date_str} | {company} | {role} | {score_cell} | "
        f"{status} | {pdf_cell} | {link_cell} | {report_cell} | {notes} |\n"
    )
    with open(path, "a", encoding="utf-8") as f:
        f.write(row)


def _read_dedup_fields(path: str) -> tuple:
    """Returns (source_url, company_name, job_title) for a JD file, or
    (None, None, None) if it's not a JSON object or reading fails."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, None, None
    if isinstance(data, dict):
        return data.get("source_url"), data.get("company_name"), data.get("job_title")
    return None, None, None


def _normalize_for_match(text: str) -> str:
    """Lowercase, alphanumeric-only normalization for comparing values
    that may differ cosmetically (case, punctuation, whitespace) but
    represent the same real thing -- e.g. a job title scraped from two
    different platforms."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def build_known_jobs_index() -> dict:
    """Walks jds/, jds/completed/, jds/archived/, and jds/expired/ exactly
    once and returns an in-memory index of every job identity found there,
    for job_key_known() to match against via its index= param instead of
    re-walking all four directories (and re-running compute_job_key()'s
    file-open-and-parse on every file found) on every single call --
    candidates x total_JD_files file opens on a mature profile, attributed
    to nothing the user can see (B35). run_scan() builds one of these once
    per scan and reuses it across every candidate, updating it in memory
    via add_to_known_jobs_index() as new JDs are written so later
    candidates in the same run are still deduped correctly. Omitting
    index= from job_key_known() rebuilds one on that single call, so
    existing single-call callers/tests are unaffected."""
    tracker_filename = os.path.basename(TRACKER_CSV)
    job_keys = set()
    url_company_pairs = set()
    normalized_pairs = set()

    for base_dir in (JDS_DIR, COMPLETED_DIR, ARCHIVED_DIR, EXPIRED_DIR):
        if not os.path.isdir(base_dir):
            continue
        for name in os.listdir(base_dir):
            if name == tracker_filename or name.startswith("."):
                continue
            path = os.path.join(base_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                job_keys.add(compute_job_key(path))
            except OSError:
                continue

            existing_url, existing_company, existing_title = _read_dedup_fields(path)
            if existing_url and existing_company:
                url_company_pairs.add((existing_url, existing_company))
            normalized_pair = (_normalize_for_match(existing_company), _normalize_for_match(existing_title))
            if normalized_pair[0] and normalized_pair[1]:
                normalized_pairs.add(normalized_pair)

    return {
        "job_keys": job_keys,
        "url_company_pairs": url_company_pairs,
        "normalized_pairs": normalized_pairs,
    }


def add_to_known_jobs_index(index: dict, job_key: str, source_url: str = None,
                             company_name: str = None, job_title: str = None) -> None:
    """Updates an index from build_known_jobs_index() in place with a job
    just written during the same run_scan() pass, so later candidates in
    that pass are still deduped against it without a fresh disk walk."""
    index["job_keys"].add(job_key)
    if source_url and company_name:
        index["url_company_pairs"].add((source_url, company_name))
    normalized_pair = (_normalize_for_match(company_name), _normalize_for_match(job_title))
    if normalized_pair[0] and normalized_pair[1]:
        index["normalized_pairs"].add(normalized_pair)


def job_key_known(job_key: str, tracker: "JDTracker" = None, source_url: str = None,
                   company_name: str = None, job_title: str = None, index: dict = None) -> bool:
    """True if job_key is already completed in the tracker, or a JD file
    for it already exists in jds/, jds/completed/, jds/archived/, or
    jds/expired/ -- matched by any of: job_key; (when both source_url and
    company_name are given) an existing file sharing the same source_url
    AND company_name; or (when both company_name and job_title are given)
    an existing file whose company_name and job_title normalize to the
    same thing. JobRight sometimes assigns a new source_job_id to a
    posting it's already surfaced once, under an identical apply URL and
    company name -- the company_name check guards against merging two
    genuinely different companies that happen to share application
    infrastructure (e.g. sibling brands on the same Workday tenant). The
    normalized company+title check separately catches the same real job
    cross-posted across two different scan sources entirely (e.g.
    JobRight's aggregated ATS URL vs. a separate LinkedIn scrape of the
    same opening) -- these share no source_job_id or source_url at all,
    so only company+title can catch them. archived/ and expired/ are
    included so a posting Morgan already said no to (Skip -> auto-
    archived) or that's already confirmed dead doesn't get silently
    rediscovered as "new" and re-run through the whole pipeline on the
    next scan. Used by scan.py to avoid writing duplicate JD files
    across repeated scan runs. index, when given (see
    build_known_jobs_index()), is matched in memory instead of walking
    the four directories fresh on this call."""
    tracker = tracker or JDTracker(TRACKER_CSV)
    if tracker.is_completed(job_key):
        return True

    index = index if index is not None else build_known_jobs_index()

    if job_key in index["job_keys"]:
        return True

    if source_url and company_name and (source_url, company_name) in index["url_company_pairs"]:
        return True

    normalized_company = _normalize_for_match(company_name) if company_name else None
    normalized_title = _normalize_for_match(job_title) if job_title else None
    if (normalized_company and normalized_title
            and (normalized_company, normalized_title) in index["normalized_pairs"]):
        return True

    return False


def _checkpoint_path(job_key: str) -> str:
    return os.path.join(CHECKPOINTS_DIR, f"{sanitize_for_filename(job_key)}.json")


def load_checkpoint(job_key: str) -> dict:
    """Returns the persisted checkpoint for job_key, or {} if none exists
    yet. A corrupt checkpoint (truncated/partial JSON -- the exact failure
    mode save_checkpoint's atomic_write() now prevents going forward, but
    not for files written before this fix, or corrupted some other way,
    e.g. a `.sync-conflict-*` merge) also falls back to {}, but is logged
    loudly first: silently treating "corrupt" the same as "no checkpoint"
    means the pipeline re-spends this JD's entire progress on the next
    run without any indication why."""
    path = _checkpoint_path(job_key)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.error(
            f"Corrupt checkpoint at {path}: {e}. Falling back to an empty "
            f"checkpoint -- job {job_key!r} will re-run from scratch."
        )
        return {}


def save_checkpoint(job_key: str, data: dict) -> None:
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    with atomic_write(_checkpoint_path(job_key), encoding="utf-8") as f:
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


def count_completed_resumes() -> int:
    """
    All-time count of resumes actually built, read from the append-only
    tracker CSV rather than from COMPLETED_DIR's file count.

    The directory is the wrong source for an "all-time" figure because it is
    mutable in both directions: archive_jd() moves files *out* of it, so
    archiving an old application would silently decrement a total that is
    supposed to only ever grow. The tracker gets exactly one row per
    mark_completed() and is never rewritten, which is what "all-time" means.

    Counts completion *events*, not distinct job_keys -- rebuilding a resume
    for the same role really is another resume customized.
    """
    return JDTracker(TRACKER_CSV).count_completed()


def archive_jd(jd_path: str) -> str:
    """Moves a JD file (from JDS_DIR root or COMPLETED_DIR -- wherever it
    currently lives) into ARCHIVED_DIR, a new terminal state distinct from
    completed/ (no resume was necessarily built) and expired/ (a person
    decided this, not liveness). One-way for now -- no un-archive UI;
    move the file back out of jds/archived/ by hand if that's ever
    needed. Returns the new path. Archived JDs are naturally excluded
    from get_pending_jds()/get_completed_jds() (both only scan their own
    specific directory), so no separate exclusion logic is needed."""
    os.makedirs(ARCHIVED_DIR, exist_ok=True)
    dest = os.path.join(ARCHIVED_DIR, os.path.basename(jd_path))
    shutil.move(jd_path, dest)
    return dest
