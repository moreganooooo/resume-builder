"""Tests for scripts/dedup_pending_roles.py's clustering.

A file-backed job also has its own data.db row (keyed by the file's name),
and the two share a dedup_hash. Clustering both made every file-backed job
a "duplicate" of itself: a 2026-09-13 --apply run archived the database row
of 131 and 445 jobs whose files were still pending. These pin the fix.
Everything runs against a temporary SQLite database and temporary files.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import dedup_pending_roles  # noqa: E402


class TestDedupClustering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db_path = os.path.join(self.tmp, "data.db")
        con = sqlite3.connect(self.db_path)
        con.execute(
            "CREATE TABLE jobs (id TEXT, title TEXT, company TEXT, location TEXT, "
            "status TEXT, final_score REAL, metadata_json TEXT, dedup_hash TEXT, "
            "created_at TEXT)"
        )
        con.commit()
        con.close()
        self.files = []
        for target, kwargs in (
            ("dedup_pending_roles.db.get_db", {"side_effect": self._connect}),
            ("dedup_pending_roles.db.checkpoint", {}),
            ("dedup_pending_roles.jd_manager.get_pending_jds", {"side_effect": lambda: list(self.files)}),
        ):
            p = patch(target, **kwargs)
            p.start()
            self.addCleanup(p.stop)

    def _connect(self, *_args, **_kwargs):
        return sqlite3.connect(self.db_path)

    def _add_file(self, name, company, title, dedup_hash, source_job_id=None, **extra):
        path = os.path.join(self.tmp, name)
        data = {"company_name": company, "job_title": title, "dedup_hash": dedup_hash}
        data.update(extra)
        if source_job_id:
            data["source_job_id"] = source_job_id
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.files.append(path)
        return path

    def _add_row(self, row_id, company, title, dedup_hash):
        con = sqlite3.connect(self.db_path)
        con.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, '', 'pending', 0, '{}', ?, '')",
            (row_id, title, company, dedup_hash),
        )
        con.commit()
        con.close()

    def test_a_file_and_its_own_database_row_are_not_duplicates(self):
        # jd_manager._sync_jd_to_db keys a file's own row by its source_job_id
        # (NOT its filename -- the first version of this fix assumed that,
        # and so did this test, which is how it passed while broken).
        self._add_file("2026-09-01_Acme_Writer.json", "Acme", "Writer", "h1", source_job_id="src-1")
        self._add_row("src-1", "Acme", "Writer", "h1")
        result = dedup_pending_roles.run_deduplication(dry_run=True)
        self.assertEqual(result["total_clusters"], 0)

    def test_own_row_of_a_file_without_an_id_is_keyed_by_content_hash(self):
        import jd_manager

        path = self._add_file("2026-09-01_Acme_Writer.json", "Acme", "Writer", "h1")
        self._add_row(jd_manager.compute_job_key(path), "Acme", "Writer", "h1")
        result = dedup_pending_roles.run_deduplication(dry_run=True)
        self.assertEqual(result["total_clusters"], 0)

    def test_two_genuine_duplicate_files_still_cluster(self):
        self._add_file("2026-09-01_Acme_Writer.json", "Acme", "Writer", "h1")
        self._add_file("2026-09-02_Acme_Writer.json", "Acme", "Writer", "h2")
        result = dedup_pending_roles.run_deduplication(dry_run=True)
        self.assertEqual(result["total_clusters"], 1)

    def test_sibling_roles_sharing_a_listing_url_are_not_merged(self):
        # Live: "Data Scientist, Level 2" was archived as a duplicate of
        # "Level 1" at the same employer because both carried one listing URL.
        url = "https://careers.example.com/search?team=data"
        self._add_file("a.json", "STI Federal", "Data Scientist, Level 1", "h1", source_url=url)
        self._add_file("b.json", "STI Federal", "Data Scientist, Level 2", "h2", source_url=url)
        result = dedup_pending_roles.run_deduplication(dry_run=True)
        self.assertEqual(result["total_clusters"], 0)

    def test_same_title_sharing_a_listing_url_still_clusters(self):
        url = "https://careers.example.com/jobs/123"
        self._add_file("a.json", "STI Federal", "Data Scientist", "h1", source_url=url)
        self._add_file("b.json", "STI  Federal!", "Data  Scientist.", "h2", source_url=url)
        result = dedup_pending_roles.run_deduplication(dry_run=True)
        self.assertEqual(result["total_clusters"], 1)

    def test_database_only_duplicate_of_a_file_still_clusters(self):
        # A scan-sourced (hash-keyed) row for the same posting is a real
        # duplicate of the file, unlike the file's own filename-keyed row.
        self._add_file("2026-09-01_Acme_Writer.json", "Acme", "Writer", "h1")
        self._add_row("a1b2c3d4", "Acme", "Writer", "h9")
        result = dedup_pending_roles.run_deduplication(dry_run=True)
        self.assertEqual(result["total_clusters"], 1)


if __name__ == "__main__":
    unittest.main()
