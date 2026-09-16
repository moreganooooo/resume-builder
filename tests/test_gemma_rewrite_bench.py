"""A failing Gemma must not stall a build: its failure benches it, so later
bullets start on the fallback model instead of paying Gemma's pacing and
retry ladder again."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


class TestGemmaRewriteBench(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(orchestrator, "_gemma_rewrite_benched_until", 0.0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_starts_on_gemma_when_healthy(self):
        self.assertEqual(
            orchestrator._starting_rewrite_model(), orchestrator.REWRITE_MODEL
        )

    def test_a_failure_benches_gemma(self):
        orchestrator._bench_gemma_rewrites()
        self.assertEqual(
            orchestrator._starting_rewrite_model(),
            orchestrator.REWRITE_FALLBACK_MODEL,
        )

    def test_the_bench_expires(self):
        with patch.object(orchestrator.time, "monotonic", return_value=1000.0):
            orchestrator._bench_gemma_rewrites()
        later = 1000.0 + orchestrator.GEMMA_REWRITE_BENCH_SECS + 1
        with patch.object(orchestrator.time, "monotonic", return_value=later):
            self.assertEqual(
                orchestrator._starting_rewrite_model(), orchestrator.REWRITE_MODEL
            )

    def test_gemma_retries_are_capped_below_the_client_default(self):
        self.assertLess(orchestrator.GEMMA_REWRITE_MAX_RETRIES, 6)


if __name__ == "__main__":
    unittest.main()
