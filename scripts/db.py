"""
db.py — Unified SQLite Database Layer for Resume-Builder.

Replaces raw JSON filesystem directory moves (jds/<profile>/pending, completed, expired)
and flat CSV logs with atomic, ACID-compliant SQLite storage.
"""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
import profile_paths


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



def init_db(conn: sqlite3.Connection) -> None:
    """Initializes tables and indexes if they do not already exist."""
    with conn:
        conn.executescript("""
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
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
            CREATE INDEX IF NOT EXISTS idx_bullet_company ON bullet_bank(company);
            CREATE INDEX IF NOT EXISTS idx_bullet_audit_status ON bullet_bank(audit_status);
        """)


def upsert_job(job_data: Dict[str, Any], profile: Optional[str] = None) -> None:
    """Inserts or updates a job posting record in the database."""
    job_id = job_data.get("id") or job_data.get("filename") or f"{job_data.get('company', 'Unknown')}_{job_data.get('title', 'Role')}"
    conn = get_db(profile)
    
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
        
    title = job_data.get("title", "Untitled Role")
    company = job_data.get("company", "Unknown Company")
    location = job_data.get("location", "")
    raw_text = job_data.get("jd_text") or job_data.get("raw_text") or json.dumps(job_data)
    
    cap_score = job_data.get("capability_score")
    rec_score = job_data.get("recruiter_score")
    final_score = job_data.get("final_score") or job_data.get("score")
    
    deal_breakers = json.dumps(job_data.get("deal_breakers", [])) if isinstance(job_data.get("deal_breakers"), list) else str(job_data.get("deal_breakers", ""))
    metadata_json = json.dumps({k: v for k, v in job_data.items() if k not in ("id", "title", "company", "location", "jd_text", "raw_text", "status")})

    with conn:
        conn.execute("""
            INSERT INTO jobs (id, title, company, location, raw_text, status, capability_score, recruiter_score, final_score, deal_breakers, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                updated_at=CURRENT_TIMESTAMP
        """, (job_id, title, company, location, raw_text, status, cap_score, rec_score, final_score, deal_breakers, metadata_json))


def get_jobs_by_status(status: str, profile: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all job records matching a given status."""
    conn = get_db(profile)
    cursor = conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def update_job_status(job_id: str, new_status: str, profile: Optional[str] = None) -> None:
    """Updates status for a specific job ID."""
    conn = get_db(profile)
    with conn:
        conn.execute("UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, job_id))
