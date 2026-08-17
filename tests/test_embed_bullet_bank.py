import os
import shutil
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import embed_bullet_bank  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402


class TestEmbedBatchLengthGuard(unittest.TestCase):
    """B20 (phase-9-backlog.md): a response with a missing/short
    "embeddings" key used to silently contribute fewer rows than sent,
    shifting every later bullet's vector out of alignment with its CSV
    row -- embed_batch must raise instead."""

    @patch("embed_bullet_bank.requests.post")
    def test_raises_when_fewer_embeddings_come_back_than_sent(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "embeddings": [{"values": [0.1, 0.2]}]
            },  # only 1, for 2 texts sent
        )
        with self.assertRaises(RuntimeError):
            embed_bullet_bank.embed_batch(["bullet one", "bullet two"])

    @patch("embed_bullet_bank.requests.post")
    def test_raises_when_embeddings_key_is_entirely_missing(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        with self.assertRaises(RuntimeError):
            embed_bullet_bank.embed_batch(["bullet one", "bullet two"])

    @patch("embed_bullet_bank.requests.post")
    def test_matching_counts_return_normally(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embeddings": [{"values": [0.1]}, {"values": [0.2]}]},
        )
        result = embed_bullet_bank.embed_batch(["bullet one", "bullet two"])
        self.assertEqual(result, [[0.1], [0.2]])


class TestEmbedBulletBankCheckpointStaleness(unittest.TestCase):
    """A checkpoint saved against one version of the bank must not be
    resumed against a since-edited bank -- row i of the checkpointed
    matrix would silently stop corresponding to bullet i (B20,
    phase-9-backlog.md)."""

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_embed_checkpoint")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_checkpoint_path = embed_bullet_bank.CHECKPOINT_PATH
        embed_bullet_bank.CHECKPOINT_PATH = os.path.join(self.tmp_dir, "checkpoint.npz")

    def tearDown(self):
        embed_bullet_bank.CHECKPOINT_PATH = self._real_checkpoint_path
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_matching_sha_resumes(self):
        sha = bullets_sha(["a", "b", "c"])
        embed_bullet_bank.save_checkpoint([[0.1], [0.2]], 2, sha)
        vectors, start_index = embed_bullet_bank.load_checkpoint(sha)
        self.assertEqual(start_index, 2)
        self.assertEqual(len(vectors), 2)

    def test_mismatched_sha_discards_checkpoint_and_starts_over(self):
        old_sha = bullets_sha(["a", "b", "c"])
        embed_bullet_bank.save_checkpoint([[0.1], [0.2]], 2, old_sha)
        new_sha = bullets_sha(["a", "b (edited)", "c"])
        vectors, start_index = embed_bullet_bank.load_checkpoint(new_sha)
        self.assertEqual(start_index, 0)
        self.assertEqual(vectors, [])
        self.assertFalse(
            os.path.exists(embed_bullet_bank.CHECKPOINT_PATH),
            "stale checkpoint file should be removed",
        )

    def test_no_checkpoint_file_starts_fresh(self):
        vectors, start_index = embed_bullet_bank.load_checkpoint(bullets_sha(["a"]))
        self.assertEqual((vectors, start_index), ([], 0))


if __name__ == "__main__":
    unittest.main()
