"""Tests for db.py's SQLite layer. Every test here patches profile_paths
so db.get_db() resolves to a temp directory -- never the real
profiles/<name>/data.db (see F4's cleanup story in
docs/review/master_audit_document.md for why that isolation matters)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402


class TestDbSchema(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        patcher = patch("profile_paths.profile_root", return_value=self._tmpdir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: shutil.rmtree(self._tmpdir, ignore_errors=True))

    def test_get_db_creates_all_three_tables(self):
        conn = db.get_db("isolated")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        self.assertTrue({"jobs", "bullet_bank", "application_log"}.issubset(tables))

    def test_get_db_sets_wal_journal_mode_and_busy_timeout(self):
        conn = db.get_db("isolated")
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")
        self.assertEqual(timeout, 5000)

    def test_upsert_job_round_trips_a_record(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_001",
                "title": "Marketing Manager",
                "company": "Acme",
                "status": "pending",
                "jd_text": "sample text",
            },
            conn=conn,
        )
        rows = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Marketing Manager")
        self.assertEqual(rows[0]["company"], "Acme")

    def test_upsert_job_on_conflict_updates_existing_row_not_duplicates(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_001",
                "title": "A",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "job_001",
                "title": "B",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        rows = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "B")

    def test_upsert_job_accepts_every_check_constraint_status(self):
        """Regression pin for the CHECK constraint fix -- every pipeline
        status the app actually uses must be insertable without raising
        sqlite3.IntegrityError."""
        conn = db.get_db("isolated")
        statuses = [
            "pending",
            "evaluating",
            "completed",
            "applied",
            "interview",
            "offer",
            "responded",
            "rejected",
            "discarded",
            "expired",
            "archived",
            "skip",
        ]
        for i, status in enumerate(statuses):
            db.upsert_job(
                {
                    "id": f"job_{i}",
                    "title": "T",
                    "company": "C",
                    "status": status,
                    "jd_text": "x",
                },
                conn=conn,
            )
        conn.close()  # would raise IntegrityError on commit if any status were rejected

    def test_update_job_status_only_touches_the_targeted_row(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_a",
                "title": "A",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "job_b",
                "title": "B",
                "company": "Acme",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )

        db.update_job_status("job_a", "completed", conn=conn)

        completed = db.get_jobs_by_status("completed", conn=conn)
        still_pending = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual([r["id"] for r in completed], ["job_a"])
        self.assertEqual([r["id"] for r in still_pending], ["job_b"])

    def test_get_jobs_by_status_returns_empty_list_not_none_when_no_matches(self):
        conn = db.get_db("isolated")
        rows = db.get_jobs_by_status("offer", conn=conn)
        conn.close()
        self.assertEqual(rows, [])

    def test_get_db_path_is_scoped_under_the_given_profile_root(self):
        path = db.get_db_path("isolated")
        self.assertTrue(path.startswith(self._tmpdir))
        self.assertTrue(path.endswith("data.db"))

    def test_checkpoint_truncates_the_wal_file(self):
        """F6: writes sitting in the local -wal file (Syncthing-excluded
        via .stignore) never reach a second machine until checkpointed
        into data.db itself."""
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "job_001",
                "title": "T",
                "company": "C",
                "status": "pending",
                "jd_text": "x",
            },
            conn=conn,
        )
        conn.close()

        db.checkpoint("isolated")

        wal_path = db.get_db_path("isolated") + "-wal"
        wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
        self.assertEqual(wal_size, 0)

        # And the write is still there, safely in the main file.
        conn2 = db.get_db("isolated")
        rows = db.get_jobs_by_status("pending", conn=conn2)
        conn2.close()
        self.assertEqual(len(rows), 1)

    def test_compute_job_dedup_hash_is_deterministic(self):
        hash1 = db.compute_job_dedup_hash(
            "Senior Product Manager", "Acme Corp", "Remote"
        )
        hash2 = db.compute_job_dedup_hash(
            "senior product manager ", " acme corp", "remote"
        )
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    def test_log_and_get_human_verifications(self):
        conn = db.get_db("isolated")
        row_id = db.log_human_verification(
            job_id="job_001",
            profile="test_profile",
            reviewer_action="approved",
            notes="Passed compliance check",
            conn=conn,
        )
        self.assertGreater(row_id, 0)

        records = db.get_human_verifications(job_id="job_001", conn=conn)
        conn.close()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["profile"], "test_profile")
        self.assertEqual(records[0]["reviewer_action"], "approved")
        self.assertTrue(len(records[0]["candidate_signoff_hash"]) > 0)

    def test_upsert_and_get_contacts(self):
        conn = db.get_db("isolated")
        c_id = db.upsert_contact(
            {
                "company": "Stripe",
                "name": "Jane Doe",
                "title": "Recruiter",
                "email": "jane@stripe.com",
                "interaction_type": "referral_chat",
                "notes": "Spoke about infra role",
            },
            conn=conn,
        )
        self.assertTrue(len(c_id) > 0)

        contacts = db.get_contacts(company="Stripe", conn=conn)
        conn.close()
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["name"], "Jane Doe")
        self.assertEqual(contacts[0]["interaction_type"], "referral_chat")

    def test_calculate_funnel_velocity(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "j1",
                "title": "A",
                "company": "C1",
                "status": "applied",
                "jd_text": "x",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "j2",
                "title": "B",
                "company": "C2",
                "status": "interview",
                "jd_text": "x",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "j3",
                "title": "C",
                "company": "C3",
                "status": "offer",
                "jd_text": "x",
            },
            conn=conn,
        )

        stats = db.calculate_funnel_velocity(conn=conn)
        conn.close()
        self.assertEqual(stats["applied_count"], 3)
        self.assertEqual(stats["interview_count"], 2)
        self.assertEqual(stats["offer_count"], 1)
        self.assertEqual(stats["interview_conversion_pct"], 66.7)
        self.assertEqual(stats["offer_conversion_pct"], 50.0)

    def test_integrity_check_and_orphan_cleanup(self):
        conn = db.get_db("isolated")
        # Insert a job
        db.upsert_job(
            {
                "id": "valid_job",
                "title": "PM",
                "company": "Co",
                "status": "pending",
                "jd_text": "text",
            },
            conn=conn,
        )

        # Insert valid and orphan application logs
        conn.execute(
            "INSERT INTO application_log (job_id, company, role, status) VALUES ('valid_job', 'Co', 'PM', 'applied')"
        )
        conn.execute(
            "INSERT INTO application_log (job_id, company, role, status) VALUES ('orphan_job', 'GhostCo', 'Eng', 'applied')"
        )
        conn.execute(
            "INSERT INTO verification_audit_log (job_id, profile, reviewer_action) VALUES ('orphan_job', 'test', 'approved')"
        )
        conn.commit()

        # Check integrity
        report = db.run_integrity_check(conn=conn)
        self.assertFalse(report["healthy"])
        self.assertEqual(report["orphaned_application_logs"], 1)
        self.assertEqual(report["orphaned_audit_logs"], 1)

        # Clean orphans
        cleaned = db.clean_orphaned_records(conn=conn)
        self.assertEqual(cleaned["deleted_application_logs"], 1)
        self.assertEqual(cleaned["deleted_audit_logs"], 1)

        # Re-check integrity
        clean_report = db.run_integrity_check(conn=conn)
        conn.close()
        self.assertTrue(clean_report["healthy"])
        self.assertEqual(clean_report["orphaned_application_logs"], 0)

    def test_metadata_json_stores_location_enrichment(self):
        conn = db.get_db("isolated")
        enrichment = {
            "status": "resolved",
            "resolved_address": "500 Audubon Pkwy, Amherst, NY 14228",
            "resolved_zip": "62702",
            "lat": 39.772,
            "lon": -89.6843,
            "source": "jd_text_override",
        }
        db.upsert_job(
            {
                "id": "job_enriched",
                "title": "Software Engineer",
                "company": "Tech Corp",
                "status": "pending",
                "location": "Buffalo, NY",
                "_location_enrichment": enrichment,
            },
            conn=conn,
        )

        rows = db.get_jobs_by_status("pending", conn=conn)
        conn.close()
        self.assertEqual(len(rows), 1)
        meta = json.loads(rows[0]["metadata_json"])
        self.assertIn("_location_enrichment", meta)
        self.assertEqual(meta["_location_enrichment"]["status"], "resolved")
        self.assertEqual(meta["_location_enrichment"]["resolved_zip"], "62702")

    def test_log_application_status_and_query(self):
        conn = db.get_db("isolated")
        # Pre-seed a job
        db.upsert_job(
            {
                "id": "job_123",
                "title": "Backend Lead",
                "company": "Stripe",
                "status": "pending",
                "jd_text": "text",
            },
            conn=conn,
        )

        # Log an application status change
        log_id = db.log_application_status(
            job_id="job_123",
            company="Stripe",
            role="Backend Lead",
            status="Interview",
            notes="Recruiter screen scheduled",
            conn=conn,
        )
        self.assertGreater(log_id, 0)

        # Verify application_log entry
        logs = db.get_application_logs(job_id="job_123", conn=conn)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["company"], "Stripe")
        self.assertEqual(logs[0]["role"], "Backend Lead")
        self.assertEqual(logs[0]["status"], "Interview")
        self.assertEqual(logs[0]["notes"], "Recruiter screen scheduled")

        # Verify job status updated in jobs table
        job_rows = db.get_jobs_by_status("applied", conn=conn)
        conn.close()
        self.assertEqual(len(job_rows), 1)
        self.assertEqual(job_rows[0]["id"], "job_123")

    def test_get_job_count_active_jobs_and_completed_resumes(self):
        conn = db.get_db("isolated")
        db.upsert_job(
            {
                "id": "j_pend",
                "title": "Dev",
                "company": "Co A",
                "status": "pending",
                "jd_text": "t",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "j_eval",
                "title": "Lead",
                "company": "Co B",
                "status": "evaluating",
                "jd_text": "t",
            },
            conn=conn,
        )
        db.upsert_job(
            {
                "id": "j_comp",
                "title": "Staff",
                "company": "Co C",
                "status": "completed",
                "jd_text": "t",
            },
            conn=conn,
        )
        self.assertEqual(db.get_job_count(conn=conn), 3)
        self.assertEqual(db.get_job_count("pending", conn=conn), 1)
        self.assertEqual(db.get_job_count("completed", conn=conn), 1)

        active = db.get_active_jobs(conn=conn)
        self.assertEqual(len(active), 2)
        active_ids = {a["id"] for a in active}
        self.assertEqual(active_ids, {"j_pend", "j_eval"})

        comp_count = db.get_completed_resumes_count(conn=conn)
        self.assertEqual(comp_count, 1)

        # Divergent sets: add application_log entry with distinct job_id
        db.log_application_status(
            job_id="j_app_distinct",
            company="Co D",
            role="Principal",
            status="Applied",
            conn=conn,
        )
        # Should now be 2 distinct jobs completed (1 from jobs table + 1 from application_log)
        self.assertEqual(db.get_completed_resumes_count(conn=conn), 2)
        conn.close()


if __name__ == "__main__":
    unittest.main()
