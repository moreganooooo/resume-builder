import json
import os
import shutil
import sys
import numpy as np
import pandas as pd
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cluster_bullet_bank  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402


def _sim_matrix_from_groups(groups: list[list[int]], n: int) -> np.ndarray:
    """Builds an (n, n) similarity matrix where every pair of indices in
    the same group scores above threshold and every other pair scores
    below it."""
    m = np.full((n, n), 0.0)
    np.fill_diagonal(m, 1.0)
    for group in groups:
        for i in group:
            for j in group:
                m[i, j] = 0.99
    return m


class TestStableClusterIds(unittest.TestCase):
    # single_linkage_cluster()'s raw group numbers are purely positional --
    # driven by each bullet's row index in this run's bullet-bank-clean.csv.
    # stable_cluster_ids() converts those into content-derived IDs so a
    # reorder or an append elsewhere in the file can't silently renumber
    # every existing cluster and orphan every source_cluster_id pointer
    # stored in bullet-bank-keepers.csv.

    def test_same_membership_different_row_order_yields_same_ids(self):
        bullets_run1 = ["Grew pipeline by 40%", "Grew pipeline by 40 percent", "Managed a team of five"]
        raw_ids_run1 = [0, 0, 1]
        stable_run1 = cluster_bullet_bank.stable_cluster_ids(raw_ids_run1, bullets_run1)

        # Same three bullets, reordered (as if a new row were inserted
        # earlier in bullet-bank-clean.csv) -- single_linkage_cluster()
        # would hand back different raw group numbers here.
        bullets_run2 = ["Managed a team of five", "Grew pipeline by 40 percent", "Grew pipeline by 40%"]
        raw_ids_run2 = [5, 2, 2]
        stable_run2 = cluster_bullet_bank.stable_cluster_ids(raw_ids_run2, bullets_run2)

        id_by_bullet_run1 = dict(zip(bullets_run1, stable_run1))
        id_by_bullet_run2 = dict(zip(bullets_run2, stable_run2))
        for bullet in bullets_run1:
            self.assertEqual(id_by_bullet_run1[bullet], id_by_bullet_run2[bullet])

    def test_members_of_different_clusters_get_different_ids(self):
        bullets = ["Grew pipeline by 40%", "Managed a team of five"]
        stable = cluster_bullet_bank.stable_cluster_ids([0, 1], bullets)
        self.assertNotEqual(stable[0], stable[1])

    def test_membership_change_produces_a_different_id(self):
        # A cluster gaining a new member is a real change in identity --
        # its stable ID SHOULD change, unlike an unrelated row reorder.
        before = cluster_bullet_bank.stable_cluster_ids([0, 0], ["Grew pipeline by 40%", "Grew pipeline by 41%"])
        after = cluster_bullet_bank.stable_cluster_ids(
            [0, 0, 0], ["Grew pipeline by 40%", "Grew pipeline by 41%", "Grew pipeline by 42%"]
        )
        self.assertNotEqual(before[0], after[0])

    def test_ids_are_deterministic_across_calls(self):
        bullets = ["Grew pipeline by 40%", "Managed a team of five"]
        first = cluster_bullet_bank.stable_cluster_ids([0, 1], bullets)
        second = cluster_bullet_bank.stable_cluster_ids([0, 1], bullets)
        self.assertEqual(first, second)


class TestSingleLinkageClusterIntegration(unittest.TestCase):
    # End-to-end through single_linkage_cluster() + stable_cluster_ids(),
    # confirming the two compose correctly rather than just unit-testing
    # stable_cluster_ids() in isolation.

    def test_reordered_bullets_still_get_matching_stable_ids(self):
        bullets_run1 = ["Grew pipeline by 40%", "Grew pipeline by 40 percent", "Managed a team of five"]
        sim1 = _sim_matrix_from_groups([[0, 1]], n=3)
        raw1 = cluster_bullet_bank.single_linkage_cluster(sim1, cluster_bullet_bank.SIMILARITY_THRESHOLD)
        stable1 = cluster_bullet_bank.stable_cluster_ids(raw1, bullets_run1)

        bullets_run2 = ["Managed a team of five", "Grew pipeline by 40 percent", "Grew pipeline by 40%"]
        sim2 = _sim_matrix_from_groups([[1, 2]], n=3)
        raw2 = cluster_bullet_bank.single_linkage_cluster(sim2, cluster_bullet_bank.SIMILARITY_THRESHOLD)
        stable2 = cluster_bullet_bank.stable_cluster_ids(raw2, bullets_run2)

        id_by_bullet1 = dict(zip(bullets_run1, stable1))
        id_by_bullet2 = dict(zip(bullets_run2, stable2))
        for bullet in bullets_run1:
            self.assertEqual(id_by_bullet1[bullet], id_by_bullet2[bullet])


class TestElectRepresentativeIsOrderIndependent(unittest.TestCase):
    """B10: elect_representative used a bare idxmax(), which returns the first
    maximum. accuracy_score is a 0-100 integer over near-duplicate cluster
    members, so ties are the common case and "first" meant raw-CSV row order --
    appending an unrelated row could change which bullet reached the resume."""

    BULLET_COL = "Bullet Point"

    def _group(self, rows):
        return pd.DataFrame(rows)

    def test_tied_scores_elect_the_same_bullet_regardless_of_row_order(self):
        rows = [
            {self.BULLET_COL: "Ran the quarterly retention audit.", "accuracy_score": 90},
            {self.BULLET_COL: "Analyzed the quarterly retention audit.", "accuracy_score": 90},
            {self.BULLET_COL: "Built the quarterly retention audit.", "accuracy_score": 90},
        ]
        elected = []
        for order in ([0, 1, 2], [2, 0, 1], [1, 2, 0]):
            group = self._group([rows[i] for i in order])
            idx = cluster_bullet_bank.elect_representative(group, self.BULLET_COL)
            elected.append(group.at[idx, self.BULLET_COL])
        self.assertEqual(len(set(elected)), 1, f"election was order-dependent: {elected}")

    def test_a_strictly_higher_score_still_wins(self):
        group = self._group([
            {self.BULLET_COL: "Aaa lower score but sorts first.", "accuracy_score": 70},
            {self.BULLET_COL: "Zzz highest score.", "accuracy_score": 95},
        ])
        idx = cluster_bullet_bank.elect_representative(group, self.BULLET_COL)
        self.assertEqual(group.at[idx, self.BULLET_COL], "Zzz highest score.")

    def test_tied_lengths_without_scores_are_also_order_independent(self):
        rows = [
            {self.BULLET_COL: "Bbbb"},
            {self.BULLET_COL: "Aaaa"},
            {self.BULLET_COL: "Cccc"},
        ]
        elected = []
        for order in ([0, 1, 2], [2, 1, 0]):
            group = self._group([rows[i] for i in order])
            idx = cluster_bullet_bank.elect_representative(group, self.BULLET_COL)
            elected.append(group.at[idx, self.BULLET_COL])
        self.assertEqual(len(set(elected)), 1, f"election was order-dependent: {elected}")

    def test_longest_bullet_still_wins_when_no_scores_are_present(self):
        group = self._group([
            {self.BULLET_COL: "- Short one."},
            {self.BULLET_COL: "- A considerably longer bullet that should win on length."},
        ])
        idx = cluster_bullet_bank.elect_representative(group, self.BULLET_COL)
        self.assertIn("considerably longer", group.at[idx, self.BULLET_COL])


class TestEmbedBatchLengthGuard(unittest.TestCase):
    """B20 (phase-9-backlog.md): same guard as embed_bullet_bank.py's --
    a short "embeddings" response must raise, not silently misalign rows."""

    @patch("cluster_bullet_bank.requests.post")
    def test_raises_when_fewer_embeddings_come_back_than_sent(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embeddings": [{"values": [0.1, 0.2]}]},
        )
        with self.assertRaises(RuntimeError):
            cluster_bullet_bank.embed_batch(["bullet one", "bullet two"])

    @patch("cluster_bullet_bank.requests.post")
    def test_matching_counts_return_normally(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embeddings": [{"values": [0.1]}, {"values": [0.2]}]},
        )
        result = cluster_bullet_bank.embed_batch(["bullet one", "bullet two"])
        self.assertEqual(result, [[0.1], [0.2]])


class TestClusterBulletBankCheckpointStaleness(unittest.TestCase):
    """B20 (phase-9-backlog.md): cluster_bullet_bank.py used to persist
    `total` in its checkpoint and never read it back -- editing the bank
    during a rate-limit pause went undetected on resume."""

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_cluster_checkpoint")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_checkpoint_path = cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH
        cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH = os.path.join(self.tmp_dir, "checkpoint.npz")

    def tearDown(self):
        cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH = self._real_checkpoint_path
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_matching_sha_and_total_resumes(self):
        sha = bullets_sha(["a", "b", "c"])
        cluster_bullet_bank.save_checkpoint([[0.1], [0.2]], 2, 3, sha)
        vectors, next_index = cluster_bullet_bank.load_checkpoint(sha, 3)
        self.assertEqual(next_index, 2)
        self.assertEqual(len(vectors), 2)

    def test_mismatched_sha_discards_checkpoint(self):
        old_sha = bullets_sha(["a", "b", "c"])
        cluster_bullet_bank.save_checkpoint([[0.1], [0.2]], 2, 3, old_sha)
        new_sha = bullets_sha(["a", "b (edited)", "c"])
        vectors, next_index = cluster_bullet_bank.load_checkpoint(new_sha, 3)
        self.assertEqual((vectors, next_index), ([], 0))
        self.assertFalse(os.path.exists(cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH))

    def test_mismatched_total_discards_checkpoint_even_with_same_sha(self):
        # Defends the exact bug named in the backlog: total was persisted
        # but never read back on resume.
        sha = bullets_sha(["a", "b", "c"])
        cluster_bullet_bank.save_checkpoint([[0.1], [0.2]], 2, 3, sha)
        vectors, next_index = cluster_bullet_bank.load_checkpoint(sha, 4)
        self.assertEqual((vectors, next_index), ([], 0))


class TestLoadOrBuildVectorsStaleness(unittest.TestCase):
    """A same-shape cached matrix whose underlying bank content changed
    must not be reused silently -- only the .meta sidecar's content hash
    can catch that; shape alone cannot (B20, phase-9-backlog.md)."""

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_cluster_vector_cache")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_cache = cluster_bullet_bank.VECTOR_CACHE
        self._real_cache_meta = cluster_bullet_bank.VECTOR_CACHE_META
        self._real_checkpoint = cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH
        cluster_bullet_bank.VECTOR_CACHE = os.path.join(self.tmp_dir, "vectors.npy")
        cluster_bullet_bank.VECTOR_CACHE_META = os.path.join(self.tmp_dir, "vectors.meta")
        cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH = os.path.join(self.tmp_dir, "checkpoint.npz")

    def tearDown(self):
        cluster_bullet_bank.VECTOR_CACHE = self._real_cache
        cluster_bullet_bank.VECTOR_CACHE_META = self._real_cache_meta
        cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH = self._real_checkpoint
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("cluster_bullet_bank.embed_batch")
    def test_matching_meta_reuses_cache_without_reembedding(self, mock_embed_batch):
        bullets = ["a", "b"]
        np.save(cluster_bullet_bank.VECTOR_CACHE, np.zeros((2, cluster_bullet_bank.EMBED_DIM), dtype=np.float32))
        with open(cluster_bullet_bank.VECTOR_CACHE_META, "w") as f:
            json.dump({"bullets_sha": bullets_sha(bullets)}, f)

        result = cluster_bullet_bank.load_or_build_vectors(bullets)

        mock_embed_batch.assert_not_called()
        self.assertEqual(result.shape, (2, cluster_bullet_bank.EMBED_DIM))

    @patch("cluster_bullet_bank.embed_batch")
    def test_content_change_with_same_shape_triggers_reembed(self, mock_embed_batch):
        # Same row count as the cache, different bullet text -- shape alone
        # would wrongly say the cache is still valid.
        cached_bullets = ["a", "b"]
        np.save(cluster_bullet_bank.VECTOR_CACHE, np.zeros((2, cluster_bullet_bank.EMBED_DIM), dtype=np.float32))
        with open(cluster_bullet_bank.VECTOR_CACHE_META, "w") as f:
            json.dump({"bullets_sha": bullets_sha(cached_bullets)}, f)

        mock_embed_batch.return_value = [[0.1] * cluster_bullet_bank.EMBED_DIM] * 2
        changed_bullets = ["a", "b (edited)"]
        result = cluster_bullet_bank.load_or_build_vectors(changed_bullets)

        mock_embed_batch.assert_called_once()
        self.assertEqual(result.shape, (2, cluster_bullet_bank.EMBED_DIM))

    @patch("cluster_bullet_bank.embed_batch")
    def test_missing_meta_triggers_reembed_even_with_matching_shape(self, mock_embed_batch):
        bullets = ["a", "b"]
        np.save(cluster_bullet_bank.VECTOR_CACHE, np.zeros((2, cluster_bullet_bank.EMBED_DIM), dtype=np.float32))
        # No .meta sidecar written at all.

        mock_embed_batch.return_value = [[0.1] * cluster_bullet_bank.EMBED_DIM] * 2
        cluster_bullet_bank.load_or_build_vectors(bullets)

        mock_embed_batch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
