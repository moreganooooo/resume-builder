import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from gemini_client import GeminiClient, MODEL_FALLBACKS, SustainedFailureError  # noqa: E402


def _success_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2, "totalTokenCount": 12},
    }
    return resp


class TestModelFallbacks(unittest.TestCase):

    def test_flash_lite_falls_back_to_gemma_with_unlimited_tpm(self):
        # gemini-3.1-flash-lite has a 250k TPM cap and, before this mapping
        # existed, had nowhere to fall back to (REWRITE_FALLBACK_MODEL
        # pointed at itself) -- gemma-4-31b-it has TPM Unlimited on this
        # account's quota tiers, a real rescue path when flash-lite alone
        # is under high demand.
        self.assertEqual(MODEL_FALLBACKS["gemini-3.1-flash-lite"], "gemma-4-31b-it")

    def test_gemma_still_falls_back_to_flash_lite(self):
        self.assertEqual(MODEL_FALLBACKS["gemma-4-31b-it"], "gemini-3.1-flash-lite")


class TestGenerateFallsBackAfterRepeatedFailures(unittest.TestCase):

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_switches_to_gemma_after_two_flash_lite_timeouts(self, mock_post):
        mock_post.side_effect = [
            requests.exceptions.Timeout("timeout=90"),
            requests.exceptions.Timeout("timeout=90"),
            _success_response(),
        ]
        text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
        )
        self.assertEqual(text, "ok")
        self.assertEqual(mock_post.call_count, 3)
        third_call_url = mock_post.call_args_list[2].args[0]
        self.assertIn("gemma-4-31b-it", third_call_url)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_switches_to_flash_lite_after_two_gemma_timeouts(self, mock_post):
        mock_post.side_effect = [
            requests.exceptions.Timeout("timeout=90"),
            requests.exceptions.Timeout("timeout=90"),
            _success_response(),
        ]
        text, usage = GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction="sys",
            contents="do the thing",
        )
        self.assertEqual(text, "ok")
        third_call_url = mock_post.call_args_list[2].args[0]
        self.assertIn("gemini-3.1-flash-lite", third_call_url)


class TestSustainedFailureDetection(unittest.TestCase):

    def setUp(self):
        # Class-level counter persists across tests in the same process --
        # reset before and after every test in this class for isolation.
        GeminiClient._consecutive_full_failures = 0

    def tearDown(self):
        GeminiClient._consecutive_full_failures = 0

    def _rate_limited_response(self):
        resp = MagicMock()
        resp.status_code = 429
        return resp

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_first_full_exhaustion_returns_none_without_raising(self, mock_post):
        mock_post.return_value = self._rate_limited_response()
        text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        self.assertIsNone(text)
        self.assertEqual(usage, {})
        self.assertEqual(GeminiClient._consecutive_full_failures, 1)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_second_consecutive_full_exhaustion_raises(self, mock_post):
        mock_post.return_value = self._rate_limited_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        with self.assertRaises(SustainedFailureError):
            GeminiClient.generate(
                model="gemini-3.1-flash-lite", system_instruction="sys",
                contents="do the thing", max_retries=2,
            )

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_success_between_exhaustions_resets_the_counter(self, mock_post):
        mock_post.side_effect = [
            self._rate_limited_response(), self._rate_limited_response(),  # exhaustion 1 (max_retries=2)
            _success_response(),                                          # success -- resets counter
            self._rate_limited_response(), self._rate_limited_response(),  # exhaustion again -- only #1 now
        ]
        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        self.assertIsNone(text)
        self.assertEqual(GeminiClient._consecutive_full_failures, 1)


class TestModelFallbackOptOut(unittest.TestCase):

    def setUp(self):
        GeminiClient._consecutive_full_failures = 0

    def tearDown(self):
        GeminiClient._consecutive_full_failures = 0

    def _rate_limited_response(self):
        resp = MagicMock()
        resp.status_code = 429
        return resp

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_no_swap_when_model_fallback_false(self, mock_post):
        mock_post.return_value = self._rate_limited_response()
        text, usage = GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction="sys",
            contents="do the thing",
            max_retries=3,
            model_fallback=False,
        )
        self.assertIsNone(text)
        self.assertEqual(usage, {})
        # Every call must still target the original model -- no silent swap.
        for call in mock_post.call_args_list:
            self.assertIn("gemma-4-31b-it", call.args[0])
        self.assertEqual(mock_post.call_count, 3)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_default_still_swaps_after_two_failures(self, mock_post):
        mock_post.side_effect = [
            self._rate_limited_response(),
            self._rate_limited_response(),
            _success_response(),
        ]
        text, usage = GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction="sys",
            contents="do the thing",
        )
        self.assertEqual(text, "ok")
        third_call_url = mock_post.call_args_list[2].args[0]
        self.assertIn("gemini-3.1-flash-lite", third_call_url)


if __name__ == "__main__":
    unittest.main()
