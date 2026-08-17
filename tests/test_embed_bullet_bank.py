import os
import shutil
import sys
import tempfile
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

    @patch("embed_bullet_bank.time.sleep")
    @patch("embed_bullet_bank.requests.post")
    def test_retry_on_429_then_success(self, mock_post, mock_sleep):
        res_429 = MagicMock(status_code=429)
        res_200 = MagicMock(
            status_code=200,
            json=lambda: {"embeddings": [{"values": [0.1]}]},
        )
        mock_post.side_effect = [res_429, res_200]
        result = embed_bullet_bank.embed_batch(["bullet one"])
        self.assertEqual(result, [[0.1]])
        mock_sleep.assert_called_once()

    @patch("embed_bullet_bank.time.sleep")
    @patch("embed_bullet_bank.requests.post")
    def test_max_retries_exceeded_raises(self, mock_post, mock_sleep):
        res_429 = MagicMock(status_code=429)
        mock_post.side_effect = [res_429, res_429, res_429, res_429]
        with self.assertRaises(RuntimeError) as cm:
            embed_bullet_bank.embed_batch(["bullet one"])
        self.assertIn("failed after 4 retries", str(cm.exception))


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


class TestMainFlow(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv")
        self.npy_path = os.path.join(self.tmp_dir, "bullet_vectors.npy")
        self.meta_path = os.path.join(self.tmp_dir, "bullet_vectors.meta")
        self.checkpoint_path = os.path.join(self.tmp_dir, "checkpoint.npz")

        self.orig_api = embed_bullet_bank.API_KEY
        self.orig_csv = embed_bullet_bank.CSV_PATH
        self.orig_npy = embed_bullet_bank.NPY_PATH
        self.orig_meta = embed_bullet_bank.META_PATH
        self.orig_ckpt = embed_bullet_bank.CHECKPOINT_PATH

        embed_bullet_bank.API_KEY = "test_key"
        embed_bullet_bank.CSV_PATH = self.csv_path
        embed_bullet_bank.NPY_PATH = self.npy_path
        embed_bullet_bank.META_PATH = self.meta_path
        embed_bullet_bank.CHECKPOINT_PATH = self.checkpoint_path

    def tearDown(self):
        embed_bullet_bank.API_KEY = self.orig_api
        embed_bullet_bank.CSV_PATH = self.orig_csv
        embed_bullet_bank.NPY_PATH = self.orig_npy
        embed_bullet_bank.META_PATH = self.orig_meta
        embed_bullet_bank.CHECKPOINT_PATH = self.orig_ckpt
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_main_missing_api_key_raises(self):
        embed_bullet_bank.API_KEY = None
        with self.assertRaises(EnvironmentError):
            embed_bullet_bank.main()

    def test_main_missing_csv_raises(self):
        with self.assertRaises(FileNotFoundError):
            embed_bullet_bank.main()

    def test_main_missing_bullet_column_raises(self):
        import pandas as pd

        pd.DataFrame({"foo": ["bar"]}).to_csv(self.csv_path, index=False)
        with self.assertRaises(ValueError):
            embed_bullet_bank.main()

    @patch("embed_bullet_bank.time.sleep")
    @patch("embed_bullet_bank.embed_batch")
    def test_main_success_flow(self, mock_embed, mock_sleep):
        import pandas as pd

        mock_embed.return_value = [
            [0.1] * embed_bullet_bank.EMBED_DIM,
            [0.2] * embed_bullet_bank.EMBED_DIM,
        ]
        pd.DataFrame({"Bullet Point": ["Bullet 1", "Bullet 2"]}).to_csv(
            self.csv_path, index=False
        )

        embed_bullet_bank.main()
        self.assertTrue(os.path.exists(self.npy_path))
        self.assertTrue(os.path.exists(self.meta_path))


if __name__ == "__main__":
    unittest.main()
