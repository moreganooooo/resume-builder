import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from gemini_client import GeminiClient, MODEL_FALLBACKS  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
