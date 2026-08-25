"""
db.py — Unified SQLite Database Layer for Resume-Builder.

Replaces raw JSON filesystem directory moves (jds/<profile>/pending, completed, expired)
and flat CSV logs with atomic, ACID-compliant SQLite storage.
"""

import hashlib
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional

import profile_paths

# The profiles/ directory as it exists in a real checkout. Captured at
# import time so a test that redirects profile_paths.PROFILES_DIR to a
# temp dir no longer matches it -- that redirection is exactly what marks
# a test as properly isolated.
_REAL_PROFILES_DIR = os.path.abspath(profile_paths.PROFILES_DIR)


def _is_unisolated_test_write(profile: Optional[str] = None) -> bool:
    """True when a test is about to write into the developer's own
    profile database.

    Dozens of tests exercise code paths that reach upsert_job incidentally
    -- liveness moves, jd_manager round-trips, orchestrator batches -- and
    none of them assert on the row that gets written. Left unguarded they
    appended junk rows ("Test"/"Role" @ "Acme Corp") to a real 61 MB
    data.db on every single run, where the dashboard then showed them as
    genuine jobs. Purging them is pointless while the next test run
    recreates them, so the write is dropped at the source.

    The isolation signal is the resolved database path, not any single
    module attribute: tests isolate themselves by patching whichever hook
    they happen to know about (profile_paths.PROFILES_DIR in
    test_application_package, profile_paths.profile_root in
    test_jd_discovery_and_moves), and both are legitimate. Asking where
    the write would actually land covers every such patch point.

    Comparison is case-folded because macOS resolves profiles/morgan and
    profiles/Morgan to the same file while os.path.abspath reports two
    different strings -- the exact reason this went unnoticed.
    """
    if "unittest" not in sys.modules:
        return False
    try:
        target = os.path.abspath(profile_paths.profile_root(profile))
    except Exception:
        return False
    return target.lower().startswith(_REAL_PROFILES_DIR.lower() + os.sep)


def compute_job_dedup_hash(title: str, company: str, location: str = "") -> str:
    """Computes a deterministic SHA-256 hash for cross-board job deduplication."""
    norm_title = " ".join((title or "").lower().split())
    norm_company = " ".join((company or "").lower().split())
    norm_loc = " ".join((location or "").lower().split())
    raw = f"{norm_title}|{norm_company}|{norm_loc}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_db_path(profile: Optional[str] = None) -> str:
    """Returns absolute path to profiles/<profile>/data.db."""
    profile_root = profile_paths.profile_root(profile)
    os.makedirs(profile_root, exist_ok=True)
    return os.path.join(profile_root, "data.db")


def get_db(profile: Optional[str] = None) -> sqlite3.Connection:
    """Connects to profile SQLite database and ensures schema migrations are applied."""
    db_path = get_db_path(profile)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def checkpoint(profile: Optional[str] = None) -> None:
    """Forces a WAL checkpoint so every committed write lands in data.db
    itself, not just the (Syncthing-excluded, per .stignore) -wal file.
    Call this at the end of any flow after which a Syncthing sync is
    likely to happen soon -- otherwise writes sitting in the local WAL
    that haven't been checkpointed yet simply never reach a second
    machine, silently and with no error (F6)."""
    conn = get_db(profile)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection | str) -> None:
    """Initializes tables and indexes if they do not already exist."""
    if isinstance(conn, str):
        c = sqlite3.connect(conn)
        try:
            init_db(c)
        finally:
            c.close()
        return

    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                raw_text TEXT NOT NULL,
                status TEXT CHECK(status IN ('pending', 'evaluating', 'completed', 'applied', 'interview', 'offer', 'responded', 'rejected', 'discarded', 'expired', 'archived', 'skip')) DEFAULT 'pending',
                capability_score REAL,
                recruiter_score REAL,
                final_score REAL,
                deal_breakers TEXT,
                metadata_json TEXT,
                dedup_hash TEXT,
                visa_sponsored INTEGER DEFAULT 0,
                ghost_probability REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bullet_bank (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                raw_bullet TEXT NOT NULL,
                polished_bullet TEXT,
                category TEXT,
                metric_value TEXT,
                action_verb TEXT,
                audit_status TEXT DEFAULT 'CLEAN',
                source_cluster_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS application_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT REFERENCES jobs(id),
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                responded_at TIMESTAMP,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS verification_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT REFERENCES jobs(id),
                profile TEXT NOT NULL,
                reviewer_action TEXT NOT NULL,
                candidate_signoff_hash TEXT,
                notes TEXT,
                reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                name TEXT NOT NULL,
                title TEXT,
                email TEXT,
                linkedin_url TEXT,
                interaction_type TEXT DEFAULT 'general',
                notes TEXT,
                follow_up_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
            CREATE INDEX IF NOT EXISTS idx_bullet_company ON bullet_bank(company);
            CREATE INDEX IF NOT EXISTS idx_bullet_audit_status ON bullet_bank(audit_status);
            CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
            CREATE INDEX IF NOT EXISTS idx_verification_job ON verification_audit_log(job_id);
        """
        )

        # Dynamic schema migrations for new columns
        existing_cols = {
            row["name"] if isinstance(row, sqlite3.Row) else row[1]
            for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "dedup_hash" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN dedup_hash TEXT;")
        if "visa_sponsored" not in existing_cols:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN visa_sponsored INTEGER DEFAULT 0;"
            )
        if "ghost_probability" not in existing_cols:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN ghost_probability REAL DEFAULT 0.0;"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_dedup ON jobs(dedup_hash);")

        # Dynamic schema migrations for application_log
        existing_app_cols = {
            row["name"] if isinstance(row, sqlite3.Row) else row[1]
            for row in conn.execute("PRAGMA table_info(application_log)").fetchall()
        }
        if "responded_at" not in existing_app_cols:
            conn.execute(
                "ALTER TABLE application_log ADD COLUMN responded_at TIMESTAMP;"
            )
        if "notes" not in existing_app_cols:
            conn.execute("ALTER TABLE application_log ADD COLUMN notes TEXT;")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_log_job ON application_log(job_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_log_status ON application_log(status);"
        )


def upsert_job(
    job_data: Dict[str, Any],
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Inserts or updates a job posting record in the database."""
    job_id = (
        job_data.get("id")
        or job_data.get("filename")
        or f"{job_data.get('company', 'Unknown')}_{job_data.get('title', 'Role')}"
    )
    if conn is None and _is_unisolated_test_write(profile):
        return

    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True

    raw_status = (job_data.get("status") or "pending").lower()
    if "expire" in raw_status:
        status = "expired"
    elif "interview" in raw_status:
        status = "interview"
    elif "offer" in raw_status:
        status = "offer"
    elif "reject" in raw_status:
        status = "rejected"
    elif "discard" in raw_status:
        status = "discarded"
    elif "skip" in raw_status:
        status = "skip"
    elif "respond" in raw_status:
        status = "responded"
    elif raw_status in ("completed", "tailored"):
        status = "completed"
    elif raw_status == "applied":
        status = "applied"
    elif "archive" in raw_status:
        status = "archived"
    elif "evaluat" in raw_status:
        status = "evaluating"
    else:
        status = "pending"

    # Accept both spellings. Scraped JD JSON files use the source
    # platform's own keys (job_title/company_name) -- only rows that came
    # through jd_manager.list_* have already been normalized to
    # title/company. Reading just the normalized spelling is what left
    # 1,876 rows at "Untitled Role" and 3,438 at "Unknown Company" with
    # the real values sitting untouched in metadata_json; see
    # backfill_job_columns.py, which repairs exactly that damage.
    title = job_data.get("title") or job_data.get("job_title") or "Untitled Role"
    company = (
        job_data.get("company") or job_data.get("company_name") or "Unknown Company"
    )
    location = job_data.get("location", "")
    raw_text = (
        job_data.get("jd_text") or job_data.get("raw_text") or json.dumps(job_data)
    )

    # Same failure mode for the score: an evaluated JD carries it under
    # _evaluation.composite_score (see CLAUDE.md's "JD JSON metadata
    # convention"), not as a bare final_score/score key.
    evaluation = job_data.get("_evaluation")
    if not isinstance(evaluation, dict):
        evaluation = {}

    cap_score = job_data.get("capability_score") or evaluation.get("fit_score")
    rec_score = job_data.get("recruiter_score") or evaluation.get(
        "interview_odds_score"
    )
    final_score = (
        job_data.get("final_score")
        or job_data.get("score")
        or evaluation.get("composite_score")
    )

    dedup_hash = job_data.get("dedup_hash") or compute_job_dedup_hash(
        title, company, location
    )
    visa_sponsored = 1 if job_data.get("visa_sponsored") else 0
    ghost_prob = float(
        job_data.get("ghost_probability") or job_data.get("ghost_prob") or 0.0
    )

    deal_breakers = (
        json.dumps(job_data.get("deal_breakers", []))
        if isinstance(job_data.get("deal_breakers"), list)
        else str(job_data.get("deal_breakers", ""))
    )
    metadata_json = json.dumps(
        {
            k: v
            for k, v in job_data.items()
            if k
            not in (
                "id",
                "title",
                "company",
                "location",
                "jd_text",
                "raw_text",
                "status",
                "dedup_hash",
                "visa_sponsored",
                "ghost_probability",
            )
        }
    )

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO jobs (id, title, company, location, raw_text, status, capability_score, recruiter_score, final_score, deal_breakers, metadata_json, dedup_hash, visa_sponsored, ghost_probability, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    company=excluded.company,
                    location=excluded.location,
                    raw_text=excluded.raw_text,
                    status=excluded.status,
                    capability_score=excluded.capability_score,
                    recruiter_score=excluded.recruiter_score,
                    final_score=excluded.final_score,
                    deal_breakers=excluded.deal_breakers,
                    metadata_json=excluded.metadata_json,
                    dedup_hash=excluded.dedup_hash,
                    visa_sponsored=excluded.visa_sponsored,
                    ghost_probability=excluded.ghost_probability,
                    updated_at=CURRENT_TIMESTAMP
            """,
                (
                    job_id,
                    title,
                    company,
                    location,
                    raw_text,
                    status,
                    cap_score,
                    rec_score,
                    final_score,
                    deal_breakers,
                    metadata_json,
                    dedup_hash,
                    visa_sponsored,
                    ghost_prob,
                ),
            )
    finally:
        if close_conn:
            conn.close()


def get_jobs_by_status(
    status: str,
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Returns all job records matching a given status."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        cursor = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        if close_conn:
            conn.close()


def get_job_count(
    status: Optional[str] = None,
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Returns total job count from SQLite, optionally filtered by status."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        if status:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
        return cursor.fetchone()[0]
    finally:
        if close_conn:
            conn.close()


def get_active_jobs(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Returns all active jobs ('pending' or 'evaluating') from SQLite."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        cursor = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('pending', 'evaluating') ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        if close_conn:
            conn.close()


def get_completed_resumes_count(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Returns all-time count of completed resumes from SQLite by computing the
    true distinct union of job IDs across application_log and jobs tables."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT job_id AS id FROM application_log WHERE job_id IS NOT NULL AND job_id != ''
                UNION
                SELECT id FROM jobs WHERE status IN ('completed', 'applied', 'interview', 'offer', 'responded')
            )
            """
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        if close_conn:
            conn.close()


def update_job_status(
    job_id: str,
    new_status: str,
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Updates status for a specific job ID."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        with conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_status, job_id),
            )
    finally:
        if close_conn:
            conn.close()


def log_human_verification(
    job_id: str,
    profile: Optional[str] = None,
    reviewer_action: str = "approved",
    candidate_signoff_hash: Optional[str] = None,
    notes: str = "",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Logs a California SB 53 & NYC Local Law 144 compliance verification entry."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        prof_name = profile or "default"
        if not candidate_signoff_hash:
            sign_raw = f"{job_id}|{prof_name}|{reviewer_action}|{notes}"
            candidate_signoff_hash = hashlib.sha256(
                sign_raw.encode("utf-8")
            ).hexdigest()

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO verification_audit_log (job_id, profile, reviewer_action, candidate_signoff_hash, notes, reviewed_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (job_id, prof_name, reviewer_action, candidate_signoff_hash, notes),
            )
            return cursor.lastrowid
    finally:
        if close_conn:
            conn.close()


def get_human_verifications(
    job_id: Optional[str] = None,
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Retrieves verification audit log entries."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        if job_id:
            cursor = conn.execute(
                "SELECT * FROM verification_audit_log WHERE job_id = ? ORDER BY reviewed_at DESC",
                (job_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM verification_audit_log ORDER BY reviewed_at DESC"
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if close_conn:
            conn.close()


def upsert_contact(
    contact_data: Dict[str, Any],
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> str:
    """Inserts or updates a networking CRM contact."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True

    company = contact_data.get("company", "Unknown")
    name = contact_data.get("name", "Unknown Contact")
    contact_id = (
        contact_data.get("id")
        or hashlib.sha256(f"{company}|{name}".encode("utf-8")).hexdigest()[:16]
    )
    title = contact_data.get("title", "")
    email = contact_data.get("email", "")
    linkedin_url = contact_data.get("linkedin_url", "")
    interaction_type = contact_data.get("interaction_type", "general")
    notes = contact_data.get("notes", "")
    follow_up_date = contact_data.get("follow_up_date", "")

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO contacts (id, company, name, title, email, linkedin_url, interaction_type, notes, follow_up_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    company=excluded.company,
                    name=excluded.name,
                    title=excluded.title,
                    email=excluded.email,
                    linkedin_url=excluded.linkedin_url,
                    interaction_type=excluded.interaction_type,
                    notes=excluded.notes,
                    follow_up_date=excluded.follow_up_date,
                    updated_at=CURRENT_TIMESTAMP
            """,
                (
                    contact_id,
                    company,
                    name,
                    title,
                    email,
                    linkedin_url,
                    interaction_type,
                    notes,
                    follow_up_date,
                ),
            )
            return contact_id
    finally:
        if close_conn:
            conn.close()


def log_application_status(
    job_id: Optional[str],
    company: str,
    role: str,
    status: str,
    applied_at: Optional[str] = None,
    responded_at: Optional[str] = None,
    notes: Optional[str] = None,
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Inserts an event into application_log and updates jobs table status.

    Returns the inserted application_log record ID.
    """
    if conn is None and _is_unisolated_test_write(profile):
        return 0

    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO application_log (job_id, company, role, status, applied_at, responded_at, notes)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?)
                """,
                (
                    job_id,
                    company,
                    role,
                    status,
                    applied_at,
                    responded_at,
                    notes,
                ),
            )
            log_id = cursor.lastrowid
            if job_id:
                # Update status in jobs table if the job exists
                normalized_status = status.lower()
                if normalized_status in (
                    "applied",
                    "responded",
                    "interview",
                    "offer",
                    "rejected",
                    "withdrawn",
                ):
                    db_status = (
                        "applied"
                        if normalized_status
                        in ("applied", "responded", "interview", "offer")
                        else (
                            "archived"
                            if normalized_status in ("rejected", "withdrawn")
                            else normalized_status
                        )
                    )
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (db_status, job_id),
                    )
            return log_id
    finally:
        if close_conn:
            conn.close()


def get_application_logs(
    profile: Optional[str] = None,
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Retrieves application log history."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        query = "SELECT * FROM application_log"
        params = []
        clauses = []
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC"
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"
        cursor = conn.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if close_conn:
            conn.close()


def get_contacts(
    profile: Optional[str] = None,
    company: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Retrieves contacts from the CRM table."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        if company:
            cursor = conn.execute(
                "SELECT * FROM contacts WHERE company = ? ORDER BY name ASC", (company,)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM contacts ORDER BY company ASC, name ASC"
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if close_conn:
            conn.close()


def calculate_funnel_velocity(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Calculates funnel progression metrics, stage conversion rates, and velocity."""
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        cursor = conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        )
        status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

        total_tracked = sum(status_counts.values())
        applied = (
            status_counts.get("applied", 0)
            + status_counts.get("interview", 0)
            + status_counts.get("offer", 0)
            + status_counts.get("rejected", 0)
            + status_counts.get("responded", 0)
        )
        interviews = status_counts.get("interview", 0) + status_counts.get("offer", 0)
        offers = status_counts.get("offer", 0)

        interview_rate = (interviews / applied * 100.0) if applied > 0 else 0.0
        offer_rate = (offers / interviews * 100.0) if interviews > 0 else 0.0

        return {
            "total_tracked": total_tracked,
            "status_counts": status_counts,
            "applied_count": applied,
            "interview_count": interviews,
            "offer_count": offers,
            "interview_conversion_pct": round(interview_rate, 1),
            "offer_conversion_pct": round(offer_rate, 1),
        }
    finally:
        if close_conn:
            conn.close()


def run_integrity_check(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """
    Runs database integrity check and detects orphaned records and duplicates.
    """
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        # SQLite internal integrity
        cursor = conn.execute("PRAGMA integrity_check;")
        sqlite_integrity = [row[0] for row in cursor.fetchall()]

        # Orphaned application logs
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM application_log WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)"
        )
        orphaned_app_logs = cursor.fetchone()["count"]

        # Orphaned audit logs
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM verification_audit_log WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)"
        )
        orphaned_audit_logs = cursor.fetchone()["count"]

        # Duplicate dedup hashes in jobs
        cursor = conn.execute(
            "SELECT dedup_hash, COUNT(*) as count FROM jobs WHERE dedup_hash IS NOT NULL AND dedup_hash != '' GROUP BY dedup_hash HAVING count > 1"
        )
        dup_hashes = cursor.fetchall()

        is_healthy = (
            sqlite_integrity == ["ok"]
            and orphaned_app_logs == 0
            and orphaned_audit_logs == 0
            and len(dup_hashes) == 0
        )

        return {
            "healthy": is_healthy,
            "sqlite_integrity": sqlite_integrity,
            "orphaned_application_logs": orphaned_app_logs,
            "orphaned_audit_logs": orphaned_audit_logs,
            "duplicate_job_hashes": len(dup_hashes),
        }
    finally:
        if close_conn:
            conn.close()


def clean_orphaned_records(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, int]:
    """
    Cleans orphaned application logs and audit records, and reindexes tables.
    """
    close_conn = False
    if conn is None:
        conn = get_db(profile)
        close_conn = True
    try:
        with conn:
            c1 = conn.execute(
                "DELETE FROM application_log WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)"
            ).rowcount
            c2 = conn.execute(
                "DELETE FROM verification_audit_log WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)"
            ).rowcount
            conn.execute("REINDEX;")
        return {
            "deleted_application_logs": c1,
            "deleted_audit_logs": c2,
            "total_cleaned": c1 + c2,
        }
    finally:
        if close_conn:
            conn.close()
