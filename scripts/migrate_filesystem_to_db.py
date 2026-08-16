#!/usr/bin/env python3
"""
migrate_filesystem_to_db.py — Automated Migration Script

Imports existing JSON job descriptions from jds/<profile>/(pending|completed|expired)
and bullet bank CSV records into profiles/<profile>/data.db (SQLite).
"""

import csv
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import db
import profile_paths


def migrate_jobs(profile: str) -> int:
    """Migrates all JSON files across jds/<profile>/ subdirectories into SQLite."""
    jd_base = profile_paths.jd_dir(profile) if hasattr(profile_paths, "jd_dir") else os.path.join(profile_paths.PROJECT_ROOT, "jds", profile)
    
    subdirs = {
        "pending": os.path.join(jd_base),
        "completed": os.path.join(jd_base, "completed"),
        "expired": os.path.join(jd_base, "expired")
    }
    
    count = 0
    for status, folder in subdirs.items():
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(folder, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Standardize payload
                data["id"] = fname
                data["status"] = status if status != "pending" else (data.get("status") or status)
                db.upsert_job(data, profile=profile)
                count += 1
            except Exception as e:
                print(f"Error migrating {fpath}: {e}")
                
    return count


def migrate_bullet_bank(profile: str) -> int:
    """Migrates audited bullet bank CSV records into SQLite."""
    kb_dir = profile_paths.kb_dir(profile)
    audited_csv = os.path.join(kb_dir, "bullet-bank-keepers-audited.csv")
    if not os.path.exists(audited_csv):
        audited_csv = os.path.join(kb_dir, "bullet-bank-keepers.csv")
    
    if not os.path.exists(audited_csv):
        return 0

    conn = db.get_db(profile)
    count = 0
    with open(audited_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        with conn:
            for i, row in enumerate(reader):
                bullet_id = row.get("id") or f"bullet_{i+1:04d}"
                conn.execute("""
                    INSERT INTO bullet_bank (id, company, title, raw_bullet, polished_bullet, category, metric_value, action_verb, audit_status, source_cluster_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        company=excluded.company,
                        title=excluded.title,
                        raw_bullet=excluded.raw_bullet,
                        polished_bullet=excluded.polished_bullet,
                        category=excluded.category,
                        metric_value=excluded.metric_value,
                        action_verb=excluded.action_verb,
                        audit_status=excluded.audit_status,
                        source_cluster_id=excluded.source_cluster_id
                """, (
                    bullet_id,
                    row.get("company", ""),
                    row.get("title", ""),
                    row.get("raw_bullet") or row.get("bullet", ""),
                    row.get("polished_bullet") or row.get("bullet", ""),
                    row.get("category", ""),
                    row.get("metric_value", ""),
                    row.get("action_verb", ""),
                    row.get("audit_status", "CLEAN"),
                    row.get("source_cluster_id", "")
                ))
                count += 1
    return count


def main():
    profile = profile_paths.active_profile()
    print(f"Migrating profile '{profile}' filesystem records to SQLite data.db...")
    jobs_count = migrate_jobs(profile)
    bullets_count = migrate_bullet_bank(profile)
    print(f"✓ Migration Complete: {jobs_count} job postings & {bullets_count} bullet records migrated to SQLite.")


if __name__ == "__main__":
    main()
