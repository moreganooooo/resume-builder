"""
test_gemini_rate_limiter.py -- Unit tests for TokenBucketRateLimiter and GeminiClient rate limiting.
"""

import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import gemini_client
from gemini_client import GeminiClient, TokenBucketRateLimiter


class TestTokenBucketRateLimiter(unittest.TestCase):
    """Tests for TokenBucketRateLimiter logic, burst handling, and time replenishment."""

    def test_default_initialization(self):
        limiter = TokenBucketRateLimiter(rpm=12.0, capacity=4.0)
        self.assertEqual(limiter.rpm, 12.0)
        self.assertEqual(limiter.capacity, 4.0)
        self.assertEqual(limiter.tokens, 4.0)
        self.assertAlmostEqual(limiter.refill_rate, 0.2)  # 12 / 60 = 0.2 tokens/sec

    def test_env_var_override(self):
        with patch.dict(os.environ, {"GEMINI_RPM_LIMIT": "30"}):
            limiter = TokenBucketRateLimiter.from_env()
            self.assertEqual(limiter.rpm, 30.0)
            self.assertAlmostEqual(limiter.refill_rate, 0.5)

    def test_acquire_available_tokens_no_wait(self):
        limiter = TokenBucketRateLimiter(rpm=12.0, capacity=4.0)
        wait_time = limiter.acquire(tokens=1.0, block=False)
        self.assertEqual(wait_time, 0.0)
        self.assertAlmostEqual(limiter.tokens, 3.0)

    def test_burst_capacity_depletion(self):
        limiter = TokenBucketRateLimiter(rpm=12.0, capacity=3.0)
        # Consume all 3 tokens
        self.assertEqual(limiter.acquire(1.0, block=False), 0.0)
        self.assertEqual(limiter.acquire(1.0, block=False), 0.0)
        self.assertEqual(limiter.acquire(1.0, block=False), 0.0)
        self.assertAlmostEqual(limiter.tokens, 0.0, places=3)

        # 4th token requires waiting 5.0 seconds (1 token / 0.2 tokens/sec)
        wait_time = limiter.acquire(1.0, block=False)
        self.assertAlmostEqual(wait_time, 5.0, places=2)

    def test_replenishment_over_time(self):
        limiter = TokenBucketRateLimiter(rpm=12.0, capacity=4.0)
        limiter.tokens = 0.0
        limiter.last_refill_ts = 100.0

        # Simulate 10 seconds later -> 10 * 0.2 = 2.0 tokens added
        with patch("time.monotonic", return_value=110.0):
            limiter._refill()
            self.assertAlmostEqual(limiter.tokens, 2.0)

        # Simulate 30 seconds later -> 30 * 0.2 = 6.0 tokens -> capped at capacity (4.0)
        with patch("time.monotonic", return_value=130.0):
            limiter._refill()
            self.assertAlmostEqual(limiter.tokens, 4.0)

    def test_thread_safety_concurrent_acquisitions(self):
        limiter = TokenBucketRateLimiter(
            rpm=0.0, capacity=100.0
        )  # no refill during run
        acquired_count = [0]
        lock = threading.Lock()

        def worker():
            for _ in range(10):
                wait = limiter.acquire(tokens=1.0, block=False)
                if wait == 0.0:
                    with lock:
                        acquired_count[0] += 1

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(acquired_count[0], 100)
        self.assertAlmostEqual(limiter.tokens, 0.0)


_ORIG_ALLOW_NETWORK = None


def setUpModule():
    global _ORIG_ALLOW_NETWORK
    _ORIG_ALLOW_NETWORK = os.environ.get(gemini_client._TEST_NETWORK_ENV)
    os.environ[gemini_client._TEST_NETWORK_ENV] = "1"


def tearDownModule():
    if _ORIG_ALLOW_NETWORK is None:
        os.environ.pop(gemini_client._TEST_NETWORK_ENV, None)
    else:
        os.environ[gemini_client._TEST_NETWORK_ENV] = _ORIG_ALLOW_NETWORK


class TestGeminiClientRateLimiting(unittest.TestCase):
    """Tests integration of TokenBucketRateLimiter inside GeminiClient."""

    @patch("gemini_client.rate_limiter.acquire")
    @patch("gemini_client.requests.post")
    def test_generate_invokes_rate_limiter(self, mock_post, mock_acquire):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "response text"}]}}],
            "usageMetadata": {"totalTokenCount": 10},
        }
        mock_post.return_value = mock_resp

        res, usage = GeminiClient.generate("gemini-3.1-flash-lite", "inst", "cont")
        self.assertEqual(res, "response text")
        mock_acquire.assert_called()

    @patch("gemini_client.rate_limiter.acquire")
    @patch("gemini_client.requests.post")
    def test_embed_invokes_rate_limiter(self, mock_post, mock_acquire):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": {"values": [0.1, 0.2, 0.3]}}
        mock_post.return_value = mock_resp

        emb = GeminiClient.embed("sample text")
        self.assertEqual(emb, [0.1, 0.2, 0.3])
        mock_acquire.assert_called()


if __name__ == "__main__":
    unittest.main()
