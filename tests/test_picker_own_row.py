"""picker._database_only_rows must not list a file's own row a second time.

A pending posting is usually one JD file plus one data.db row. That row is
NOT always keyed by the file's name: db.upsert_job merges a file's sync
into an existing row with the same dedup_hash, so when a scan wrote the
row first, the surviving row keeps the scanner's id. Recognizing a file's
row by id alone therefore listed the posting twice on the Jobs screen --
which is what "duplicates cropping up" was (2026-09-15), rather than any
failure of the dedupe step.
"""

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

import db  # noqa: E402
import picker  # noqa: E402


class TestDatabaseOnlyRowsSkipsAFilesOwnRow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db_path = os.path.join(self.tmp, "data.db")
        con = sqlite3.connect(self.db_path)
        con.execute(
            "CREATE TABLE jobs (id TEXT, title TEXT, company TEXT, location TEXT, "
            "status TEXT, final_score REAL, metadata_json TEXT, dedup_hash TEXT, "
            "created_at TEXT, raw_text TEXT)"
        )
        con.commit()
        con.close()
        p = patch("picker.db.get_db", side_effect=self._connect)
        p.start()
        self.addCleanup(p.stop)

    def _connect(self, *_args, **_kwargs):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _add_row(self, row_id, company, title, location, dedup_hash, metadata="{}"):
        con = sqlite3.connect(self.db_path)
        con.execute(
            "INSERT INTO jobs (id, title, company, location, status, final_score,"
            " metadata_json, dedup_hash, created_at, raw_text)"
            " VALUES (?, ?, ?, ?, 'pending', 4.0, ?, ?, '', '')",
            (row_id, title, company, location, metadata, dedup_hash),
        )
        con.commit()
        con.close()

    def _file_row(self):
        return {
            "path": os.path.join(self.tmp, "2026-09-01_MTB_Data_Engineer.json"),
            "title": "Data Engineer",
            "company": "M&T Bank",
            "location": "Buffalo, NY",
        }

    def test_a_row_merged_under_the_scanners_id_is_recognized_by_dedup_hash(self):
        file_row = self._file_row()
        self._add_row(
            "a8bba43919",
            file_row["company"],
            file_row["title"],
            file_row["location"],
            db.compute_job_dedup_hash(
                file_row["title"], file_row["company"], file_row["location"]
            ),
        )
        self.assertEqual(picker._database_only_rows([file_row]), [])

    def test_a_row_with_no_dedup_hash_is_recognized_by_company_and_title(self):
        # Backstop for rows predating dedup_hash: normalized company+title
        # is the same second rule dedup_pending_roles clusters on.
        file_row = self._file_row()
        self._add_row(
            "a8bba43919",
            "  m&t   BANK ",
            "data engineer",
            file_row["location"],
            "",
        )
        self.assertEqual(picker._database_only_rows([file_row]), [])

    def test_a_genuinely_different_posting_is_still_listed(self):
        # The skip must not swallow real database-only rows -- those are
        # most of the pending corpus.
        file_row = self._file_row()
        self._add_row(
            "hash-id-for-another-job",
            "KeyBank",
            "Quant Analytics Senior Associate",
            "Buffalo, NY",
            "some-other-hash",
            metadata='{"_evaluation": {"composite_score": 4.7}}',
        )
        extra = picker._database_only_rows([file_row])
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0].get("company"), "KeyBank")
