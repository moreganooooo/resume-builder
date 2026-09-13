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
import gemini_client  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402

_ORIG_NETWORK_ENV = None


def setUpModule():
    # embed_batch() now goes through gemini_client's test-network guard.
    # Every test here that reaches it mocks embed_bullet_bank.requests.post,
    # so opt in -- same arrangement as tests/test_gemini_client.py. A test
    # added here WITHOUT that mock would make a real call.
    global _ORIG_NETWORK_ENV
    _ORIG_NETWORK_ENV = os.environ.get(gemini_client._TEST_NETWORK_ENV)
    os.environ[gemini_client._TEST_NETWORK_ENV] = "1"


def tearDownModule():
    if _ORIG_NETWORK_ENV is None:
        os.environ.pop(gemini_client._TEST_NETWORK_ENV, None)
    else:
        os.environ[gemini_client._TEST_NETWORK_ENV] = _ORIG_NETWORK_ENV


class TestEmbedBatchReadsKeyPerCall(unittest.TestCase):
    """A key switched in .env must reach an already-running job: the old
    module-level AUTH_HEADERS froze the import-time key for hours."""

    @patch("embed_bullet_bank.requests.post")
    def test_uses_the_key_current_at_call_time(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"embeddings": [{"values": [0.0]}]}
        )
        with patch("gemini_client._get_api_key", return_value="key-after-switch"):
            embed_bullet_bank.embed_batch(["one"])
        self.assertEqual(
            mock_post.call_args.kwargs["headers"]["x-goog-api-key"], "key-after-switch"
        )


class TestBackupEmbeddingModel(unittest.TestCase):
    """gemini-embedding-001 has its own quota, so it can absorb the primary
    model's rate limits -- but only against its own index."""

    @patch("embed_bullet_bank.requests.post")
    def test_model_argument_reaches_the_request(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"embeddings": [{"values": [0.0]}]}
        )
        embed_bullet_bank.embed_batch(["one"], model=embed_bullet_bank.BACKUP_EMBED_MODEL)
        self.assertIn("gemini-embedding-001:batchEmbedContents", mock_post.call_args.args[0])
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["requests"][0]["model"],
            "models/gemini-embedding-001",
        )

    @patch("embed_bullet_bank.time.sleep", lambda *a, **kw: None)
    @patch("embed_bullet_bank.requests.post")
    def test_max_retries_caps_the_ladder(self, mock_post):
        mock_post.return_value = MagicMock(status_code=429)
        with self.assertRaises(RuntimeError):
            embed_bullet_bank.embed_batch(["one"], max_retries=1)
        self.assertEqual(mock_post.call_count, 1)

    def test_each_model_keeps_its_own_index_files(self):
        primary = embed_bullet_bank.index_paths("/kb")
        backup = embed_bullet_bank.index_paths("/kb", embed_bullet_bank.BACKUP_EMBED_MODEL)
        self.assertEqual(os.path.basename(primary[0]), "bullet_vectors_ge2_d768.npy")
        self.assertEqual(os.path.basename(backup[0]), "bullet_vectors_ge1_d768.npy")
        self.assertEqual(len(set(primary) & set(backup)), 0)


class TestCliBuildsBothIndexes(unittest.TestCase):
    """The menu's Embed stage runs this script; it must refresh the backup
    index too, or the fallback silently goes stale after every bank edit."""

    def _run(self, argv, main_side_effect=None):
        with patch("embed_bullet_bank.main", side_effect=main_side_effect) as mock_main:
            code = embed_bullet_bank.cli(argv)
        return code, [c.kwargs.get("model") for c in mock_main.call_args_list]

    def test_default_builds_primary_then_backup(self):
        code, models = self._run([])
        self.assertEqual(code, 0)
        self.assertEqual(
            models, [embed_bullet_bank.EMBED_MODEL, embed_bullet_bank.BACKUP_EMBED_MODEL]
        )

    def test_primary_only_skips_the_backup(self):
        _, models = self._run(["--primary-only"])
        self.assertEqual(models, [embed_bullet_bank.EMBED_MODEL])

    def test_model_flag_builds_exactly_that_index(self):
        _, models = self._run(["--model", embed_bullet_bank.BACKUP_EMBED_MODEL])
        self.assertEqual(models, [embed_bullet_bank.BACKUP_EMBED_MODEL])

    def test_backup_failure_does_not_fail_the_step(self):
        def fail_backup(model=None):
            if model == embed_bullet_bank.BACKUP_EMBED_MODEL:
                raise RuntimeError("quota")

        code, models = self._run([], main_side_effect=fail_backup)
        self.assertEqual(code, 0)
        self.assertEqual(len(models), 2)

    def test_primary_failure_still_fails_the_step(self):
        def fail_primary(model=None):
            raise RuntimeError("primary down")

        with self.assertRaises(RuntimeError):
            self._run([], main_side_effect=fail_primary)


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
