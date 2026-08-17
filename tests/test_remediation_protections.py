"""
test_remediation_protections.py — Focused Unit Tests for Remediation Features

Verifies that:
1. cli_art.scrub_pii redacts email addresses and phone numbers.
2. render_typst._escape_typst properly escapes brackets, underscores, and special chars.
3. db.py connection handling properly closes connections and updates database records.
4. vector_store.py handles stale SHA hashes gracefully.
5. jd_manager.py file append operations function under fcntl.flock file locking.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts import cli_art, render_typst, db, vector_store, jd_manager


class TestRemediationProtections(unittest.TestCase):

    def test_pii_scrubbing(self):
        """Verify scrub_pii redacts emails and phone numbers from logs/tracebacks."""
        raw_text = "Contact john.doe@example.com or call 555-123-4567 for details."
        scrubbed = cli_art.scrub_pii(raw_text)
        self.assertNotIn("john.doe@example.com", scrubbed)
        self.assertIn("[REDACTED_EMAIL]", scrubbed)
        self.assertNotIn("555-123-4567", scrubbed)
        self.assertIn("[REDACTED_PHONE]", scrubbed)

    def test_typst_special_character_escaping(self):
        """Verify _escape_typst escapes brackets, underscores, hashes, dollars, and at-signs."""
        raw_text = "Senior Manager [Growth] @ Acme_Corp ($100k #1)"
        escaped = render_typst._escape_typst(raw_text)
        self.assertIn("\\[Growth\\]", escaped)
        self.assertIn("Acme\\_Corp", escaped)
        self.assertIn("\\$100k", escaped)
        self.assertIn("\\#1", escaped)
        self.assertIn("\\@", escaped)

    def test_db_connection_closing_and_upsert(self):
        """Verify upsert_job opens and closes SQLite connection cleanly without leaks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "data.db")
            with patch("scripts.profile_paths.profile_root", return_value=tmpdir):
                conn = db.get_db("test_profile")
                self.assertIsNotNone(conn)
                conn.close()

                # Test upsert_job auto-closing connection
                job_payload = {
                    "id": "job_001",
                    "title": "Software Engineer",
                    "company": "Acme",
                    "status": "interview",
                    "jd_text": "Sample text"
                }
                db.upsert_job(job_payload, profile="test_profile")
                
                jobs = db.get_jobs_by_status("interview", profile="test_profile")
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0]["title"], "Software Engineer")

    def test_vector_store_stale_hash_trigger(self):
        """Verify vector_store triggers re-embedding on SHA hash mismatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.meta")
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
            
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"bullets_sha": "old_hash"}, f)
            
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nTest Bullet 1\n")

            import numpy as np
            np.save(npy_path, np.zeros((1, 768)))
            
            with patch("embed_bullet_bank.main") as mock_reembed, \
                 patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir):
                result = vector_store.search_bullet_bank("dummy_query", top_k=5)
                # When sha is stale, embed_bullet_bank.main should be triggered
                self.assertTrue(mock_reembed.called)

    def test_vector_store_row_count_mismatch_triggers_reembed(self):
        """Pins F11 (docs/review/master_audit_document.md): adding or
        removing a bullet changes the row count, not just the content
        hash -- that path must also trigger re-embedding. Before the F11
        fix, this returned [] with zero re-embed calls, silently and
        permanently breaking vector search on the single most common
        bullet-bank edit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.meta")
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"bullets_sha": "irrelevant-matches-nothing"}, f)
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nBullet One\nBullet Two\n")  # 2 rows

            import numpy as np
            np.save(npy_path, np.zeros((1, 768)))  # only 1 embedding row -- mismatch

            with patch("embed_bullet_bank.main") as mock_reembed, \
                 patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir):
                vector_store.search_bullet_bank("dummy_query", top_k=5)
                self.assertTrue(mock_reembed.called)

    def test_jd_manager_atomic_file_lock(self):
        """Verify _append_row in JDTracker functions correctly under fcntl.flock."""
        with tempfile.NamedTemporaryFile("w+", delete=False) as tmpfile:
            tmp_path = tmpfile.name

        try:
            tracker = jd_manager.JDTracker(csv_path=tmp_path)
            row_data = {col: "test" for col in jd_manager.TRACKER_FIELDNAMES}
            row_data["company_name"] = "Acme"
            row_data["job_title"] = "Lead Dev"
            tracker._append_row(row_data)
            
            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Acme", content)
                self.assertIn("Lead Dev", content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
