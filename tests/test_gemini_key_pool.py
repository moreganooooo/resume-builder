import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gemini_client  # noqa: E402

ENV = {
    "GEMINI_API_KEY": "key-one",
    "GEMINI_API_KEY_2": "key-two",
    "GEMINI_API_KEY_10": "key-ten",
    "GEMINI_API_KEYS": "key-two, key-three",
}


def _resp(status, payload=None):
    r = MagicMock(status_code=status, headers={}, reason="", text="")
    r.json.return_value = payload or {}
    return r


class KeyPoolTest(unittest.TestCase):
    def setUp(self):
        gemini_client._KEY_COOLDOWNS.clear()
        p = patch.dict(os.environ, ENV, clear=True)
        p.start()
        self.addCleanup(p.stop)
        b = patch.object(gemini_client, "_pool_limited_under_test", return_value=False)
        b.start()
        self.addCleanup(b.stop)
        d = patch.object(gemini_client, "load_dotenv")
        d.start()
        self.addCleanup(d.stop)

    def test_order_and_dedup(self):
        self.assertEqual(
            gemini_client.api_keys(), ["key-one", "key-two", "key-ten", "key-three"]
        )

    def test_cooldown_is_per_model(self):
        self.assertTrue(gemini_client.mark_key_rate_limited("key-one", "m1"))
        self.assertEqual(gemini_client._get_api_key("m1"), "key-two")
        self.assertEqual(gemini_client._get_api_key("m2"), "key-one")

    def test_all_cooled_returns_soonest_and_reports_no_fresh_key(self):
        for k, secs in (("key-one", 50), ("key-two", 10), ("key-ten", 90)):
            gemini_client.mark_key_rate_limited(k, "m", secs)
        self.assertFalse(gemini_client.mark_key_rate_limited("key-three", "m", 99))
        self.assertEqual(gemini_client._get_api_key("m"), "key-two")

    def test_grounded_switches_keys_without_spending_retries(self):
        ok = _resp(200, {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})
        sent = []

        def post(url, headers, **kw):
            sent.append(headers["x-goog-api-key"])
            return _resp(429) if len(sent) < 4 else ok

        with (
            patch.object(gemini_client, "_blocked_under_test", return_value=False),
            patch.object(gemini_client.requests, "post", side_effect=post),
            patch.object(gemini_client.time, "sleep") as sleep,
        ):
            text, _ = gemini_client.generate_grounded("m", "p", tools=[], max_retries=1)
        self.assertEqual(text, "hi")
        self.assertEqual(sent, ["key-one", "key-two", "key-ten", "key-three"])
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
