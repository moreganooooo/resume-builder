"""A failing Gemma must not stall a build: its failure benches it, so later
bullets -- in the resume builder and the Bullet Bank alike -- start on the
fallback model instead of paying Gemma's pacing and retry ladder again."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import gemini_client  # noqa: E402
import orchestrator  # noqa: E402
import rewrite_bullets  # noqa: E402


class TestModelBench(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(gemini_client._benched_until, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_build_starts_on_gemma_when_healthy(self):
        self.assertEqual(
            orchestrator._starting_rewrite_model(), orchestrator.REWRITE_MODEL
        )

    def test_a_bench_moves_the_build_to_the_fallback(self):
        gemini_client.bench_model(orchestrator.REWRITE_MODEL)
        self.assertEqual(
            orchestrator._starting_rewrite_model(),
            orchestrator.REWRITE_FALLBACK_MODEL,
        )

    def test_the_bench_expires(self):
        with patch.object(gemini_client.time, "monotonic", return_value=1000.0):
            gemini_client.bench_model("gemma-4-31b-it")
        later = 1000.0 + gemini_client.MODEL_BENCH_SECS + 1
        with patch.object(gemini_client.time, "monotonic", return_value=later):
            self.assertFalse(gemini_client.is_benched("gemma-4-31b-it"))

    def test_bench_is_per_model(self):
        gemini_client.bench_model("gemma-4-31b-it")
        self.assertFalse(gemini_client.is_benched("gemini-3.5-flash-lite"))

    def test_builder_and_bullet_bank_share_one_bench(self):
        self.assertEqual(orchestrator.REWRITE_MODEL, rewrite_bullets.REWRITE_MODEL)

    def test_gemma_retries_are_capped_below_the_client_default(self):
        self.assertLess(orchestrator.GEMMA_REWRITE_MAX_RETRIES, 6)
        self.assertLess(rewrite_bullets.GEMMA_MAX_RETRIES, 6)


if __name__ == "__main__":
    unittest.main()
