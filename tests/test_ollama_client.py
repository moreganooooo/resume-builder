"""Unit tests for OllamaClient offline LLM execution."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from gemini_client import OllamaClient


class TestOllamaClient(unittest.TestCase):

    @patch("gemini_client.requests.get")
    def test_is_available_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        self.assertTrue(OllamaClient.is_available())

    @patch("gemini_client.requests.get")
    def test_is_available_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        self.assertFalse(OllamaClient.is_available())

    @patch("gemini_client.requests.post")
    def test_generate_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Local response"}
        mock_post.return_value = mock_resp

        result = OllamaClient.generate(prompt="Hello", system_instruction="Be concise")
        self.assertEqual(result, "Local response")

    @patch("gemini_client.requests.post")
    def test_generate_error(self, mock_post):
        mock_post.side_effect = Exception("Timeout")
        result = OllamaClient.generate(prompt="Hello")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
