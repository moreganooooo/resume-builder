"""
test_vector_store.py — Focused unit tests for vector_store.py.

F13 (docs/review/master_audit_document.md) named vector_store.py as one of
four modules with zero dedicated test coverage; the remediation pass added
two regression tests to test_remediation_protections.py (the SHA-mismatch
and row-count-mismatch re-embed triggers) but never gave the module its
own test file, so search_bullet_bank()'s actual search/scoring logic and
its other early-return branches stayed untested. This file covers that
remaining surface without duplicating the two re-embed-trigger tests that
already exist elsewhere.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts import vector_store


class TestCosineSimilarityMatrix(unittest.TestCase):
    def test_identical_vectors_score_one(self):
        v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        matrix = np.array([v], dtype=np.float32)
        scores = vector_store.cosine_similarity_matrix(v, matrix)
        self.assertAlmostEqual(float(scores[0]), 1.0, places=5)

    def test_orthogonal_vectors_score_zero(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        matrix = np.array([[0.0, 1.0]], dtype=np.float32)
        scores = vector_store.cosine_similarity_matrix(query, matrix)
        self.assertAlmostEqual(float(scores[0]), 0.0, places=5)

    def test_zero_query_vector_returns_zeros_not_nan(self):
        query = np.zeros(3, dtype=np.float32)
        matrix = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
        scores = vector_store.cosine_similarity_matrix(query, matrix)
        self.assertEqual(list(scores), [0.0, 0.0])

    def test_zero_row_in_matrix_does_not_divide_by_zero(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        matrix = np.array([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
        scores = vector_store.cosine_similarity_matrix(query, matrix)
        self.assertFalse(np.isnan(scores).any())
        self.assertAlmostEqual(float(scores[0]), 0.0, places=5)
        self.assertAlmostEqual(float(scores[1]), 1.0, places=5)


class TestSearchBulletBankEarlyReturns(unittest.TestCase):
    def test_missing_csv_or_npy_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                self.assertEqual(vector_store.search_bullet_bank("query"), [])

    def test_corrupt_csv_returns_empty_list_not_a_raise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
            # Deliberately malformed CSV (unterminated quote) so pd.read_csv raises.
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write('Bullet Point\n"unterminated quote\n')
            np.save(npy_path, np.zeros((1, 768)))

            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                self.assertEqual(vector_store.search_bullet_bank("query"), [])

    def test_missing_bullet_point_column_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Some Other Column\nvalue\n")
            np.save(npy_path, np.zeros((1, 768)))

            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                self.assertEqual(vector_store.search_bullet_bank("query"), [])

    def test_none_embedding_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
            meta_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.meta")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nBullet One\n")
            np.save(npy_path, np.zeros((1, 768)))
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"bullets_sha": vector_store.bullets_sha(["Bullet One"])}, f)

            with (
                patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir),
                patch("scripts.vector_store.GeminiClient.embed", return_value=None),
            ):
                self.assertEqual(vector_store.search_bullet_bank("query"), [])


class TestSearchBulletBankHappyPath(unittest.TestCase):
    def _write_bank(self, tmpdir, bullets, companies=None, tags=None, dim=4):
        csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
        npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
        meta_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.meta")

        import pandas as pd

        data = {"Bullet Point": bullets}
        if companies is not None:
            data["Role / Company"] = companies
        if tags is not None:
            data["Tags"] = tags
        pd.DataFrame(data).to_csv(csv_path, index=False)

        # One distinct orthogonal-ish embedding per bullet, scaled by index
        # so a descending sort has an unambiguous, checkable order.
        embs = np.array(
            [[float(i + 1)] + [0.0] * (dim - 1) for i in range(len(bullets))],
            dtype=np.float32,
        )
        np.save(npy_path, embs)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"bullets_sha": vector_store.bullets_sha(bullets)}, f)
        return csv_path, npy_path, meta_path

    def test_results_are_sorted_descending_by_score_and_shaped_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bullets = ["Bullet A", "Bullet B", "Bullet C"]
            companies = ["Co A", "Co B", "Co C"]
            tags = ["tag-a", "tag-b", "tag-c"]
            self._write_bank(tmpdir, bullets, companies=companies, tags=tags)

            # Query vector aligned with the highest-index (Bullet C) embedding.
            query_vec = [0.0, 0.0, 0.0, 0.0]
            fake_embed = [0.0] * 4
            fake_embed[0] = 1.0

            with (
                patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir),
                patch(
                    "scripts.vector_store.GeminiClient.embed",
                    return_value=fake_embed,
                ),
            ):
                results = vector_store.search_bullet_bank("query", top_k=3)

            self.assertEqual(len(results), 3)
            # All three embeddings point the same direction as the query
            # (only magnitude differs), so cosine similarity ties at 1.0 for
            # all of them -- assert the tuple shape and membership instead
            # of a specific order, which numpy's stable-sort tie-breaking
            # doesn't guarantee.
            returned_bullets = {r[0] for r in results}
            self.assertEqual(returned_bullets, set(bullets))
            for bullet, company, tag, score in results:
                self.assertIn(bullet, bullets)
                self.assertIn(company, companies)
                self.assertIn(tag, tags)
                self.assertAlmostEqual(score, 1.0, places=5)

    def test_top_k_limits_result_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bullets = [f"Bullet {i}" for i in range(10)]
            self._write_bank(tmpdir, bullets)
            fake_embed = [1.0, 0.0, 0.0, 0.0]

            with (
                patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir),
                patch(
                    "scripts.vector_store.GeminiClient.embed",
                    return_value=fake_embed,
                ),
            ):
                results = vector_store.search_bullet_bank("query", top_k=3)

            self.assertEqual(len(results), 3)

    def test_missing_optional_columns_fall_back_to_empty_strings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bullets = ["Only Bullet"]
            self._write_bank(tmpdir, bullets)  # no companies/tags columns
            fake_embed = [1.0, 0.0, 0.0, 0.0]

            with (
                patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir),
                patch(
                    "scripts.vector_store.GeminiClient.embed",
                    return_value=fake_embed,
                ),
            ):
                results = vector_store.search_bullet_bank("query", top_k=5)

            self.assertEqual(len(results), 1)
            bullet, company, tag, _score = results[0]
            self.assertEqual(bullet, "Only Bullet")
            self.assertEqual(company, "")
            self.assertEqual(tag, "")


class TestNeedsReembedAndReembed(unittest.TestCase):
    def test_needs_reembed_when_no_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                stale, reason = vector_store.needs_reembed()
                self.assertFalse(stale)
                self.assertIn("No bullet bank CSV found", reason)

    def test_needs_reembed_when_no_npy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nBullet 1\n")
            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                stale, reason = vector_store.needs_reembed()
                self.assertTrue(stale)
                self.assertIn("missing", reason)

    def test_needs_reembed_when_row_counts_differ(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nBullet 1\nBullet 2\n")
            np.save(npy_path, np.zeros((1, 4)))
            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                stale, reason = vector_store.needs_reembed()
                self.assertTrue(stale)
                self.assertIn("Row count mismatch", reason)

    def test_needs_reembed_when_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")
            meta_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.meta")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nBullet 1\n")
            np.save(npy_path, np.zeros((1, 4)))
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"bullets_sha": vector_store.bullets_sha(["Bullet 1"])}, f)
            with patch(
                "scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir
            ):
                stale, reason = vector_store.needs_reembed()
                self.assertFalse(stale)
                self.assertIn("up to date", reason)

    def test_reembed_async_spawns_thread(self):
        with patch("embed_bullet_bank.main") as mock_main:
            thread = vector_store.reembed(blocking=False)
            self.assertIsNotNone(thread)
            thread.join(timeout=2.0)
            mock_main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
