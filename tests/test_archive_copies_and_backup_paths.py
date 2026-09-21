"""Archiving a posting reaches its duplicate copies, and the two remaining
query-side embedding paths (bank search, cover-letter grounding) fall back to
the backup model against the backup's own index."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402
import dedup_pending_roles  # noqa: E402
import embed_bullet_bank  # noqa: E402
import validate_coverletter  # noqa: E402
import vector_store  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402


class TestArchiveCopies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = patch("profile_paths.profile_root", return_value=self.tmp)
        p.start()
        self.addCleanup(p.stop)
        for job_id, title, text in (
            ("a", "Data Analyst", "posting text one"),
            ("c", "Data Engineer", "a different opening"),
        ):
            db.upsert_job(
                {
                    "id": job_id,
                    "title": title,
                    "company": "Acme LLC",
                    "status": "pending",
                    "raw_text": text,
                }
            )
        # upsert_job itself folds a same company+title row into the existing
        # one, so a real stray copy (created under another id by another path)
        # is inserted directly: row "a" duplicated as "b" with its own hash.
        conn = db.get_db(None)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(jobs)")]
        select = ", ".join(
            "'b'" if c == "id" else "'legacy-copy'" if c == "dedup_hash" else c
            for c in cols
        )
        # Interpolated from PRAGMA table_info, never from input: nosec B608.
        conn.execute(  # nosec B608
            f"INSERT INTO jobs ({', '.join(cols)}) SELECT {select} FROM jobs WHERE id = 'a'"  # nosec B608
        )
        conn.commit()
        conn.close()

    def test_archiving_one_copy_archives_the_others_but_not_siblings(self):
        archived = dedup_pending_roles.archive_copies_of_id("a")
        self.assertEqual(archived, 1)
        self.assertEqual([r["id"] for r in db.get_jobs_by_status("archived")], ["b"])
        pending = {r["id"] for r in db.get_jobs_by_status("pending")}
        self.assertEqual(pending, {"a", "c"})  # the caller archives "a" itself


class TestCoverLetterGroundingBackup(unittest.TestCase):
    SENTENCE = (
        "Built lifecycle automation that doubled onboarding completion across accounts."
    )

    def _violations(self, backup_matrix):
        letter = {"body_paragraphs": [self.SENTENCE]}
        with (
            patch("gemini_client.GeminiClient.embed", return_value=None),
            patch(
                "embed_bullet_bank.embed_batch", return_value=[[1.0, 0.0, 0.0]]
            ) as mock_embed,
        ):
            v = validate_coverletter._check_semantic_grounding(
                letter, ["bullet"], np.array([[0.0, 1.0, 0.0]]), backup_matrix
            )
        return v, mock_embed

    def test_backup_index_is_used_when_the_primary_fails(self):
        v, mock_embed = self._violations(np.array([[1.0, 0.0, 0.0]]))
        self.assertEqual(v, [])  # matches the backup index, not the primary
        self.assertEqual(
            mock_embed.call_args.kwargs["model"], embed_bullet_bank.BACKUP_EMBED_MODEL
        )

    def test_backup_uses_its_own_cutoff(self):
        # similarity 0.7: passes the primary's 0.60 but not the backup's 0.72
        v, _ = self._violations(np.array([[0.7, 0.714, 0.0]]))
        self.assertEqual(len(v), 1)

    def test_no_backup_index_skips_the_sentence(self):
        v, mock_embed = self._violations(None)
        self.assertEqual(v, [])
        mock_embed.assert_not_called()


class TestBankSearchBackup(unittest.TestCase):
    def setUp(self):
        self.kb = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.kb, True)
        bullets = ["First bullet about email", "Second bullet about data"]
        pd.DataFrame(
            {"Bullet Point": bullets, "Role / Company": ["A", "B"], "Tags": ["", ""]}
        ).to_csv(os.path.join(self.kb, "bullet-bank-keepers-audited.csv"), index=False)
        sha = bullets_sha(bullets)
        for model, matrix in (
            (embed_bullet_bank.EMBED_MODEL, [[1.0, 0.0], [0.0, 1.0]]),
            (embed_bullet_bank.BACKUP_EMBED_MODEL, [[1.0, 0.0], [0.0, 1.0]]),
        ):
            npy, meta, _ = embed_bullet_bank.index_paths(self.kb, model)
            np.save(npy, np.array(matrix, dtype=np.float32))
            with open(meta, "w") as f:
                json.dump({"bullets_sha": sha}, f)
        p = patch("vector_store.profile_paths.kb_dir", return_value=self.kb)
        p.start()
        self.addCleanup(p.stop)

    def test_primary_failure_ranks_with_the_backup_index(self):
        with (
            patch("vector_store.GeminiClient.embed", return_value=None),
            patch("embed_bullet_bank.embed_batch", return_value=[[0.0, 1.0]]),
        ):
            results = vector_store.search_bullet_bank("anything", top_k=1)
        self.assertEqual(results[0][0], "Second bullet about data")


if __name__ == "__main__":
    unittest.main()
