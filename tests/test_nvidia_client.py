import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)

import nvidia_client as client  # noqa: E402


class Schema:
    @classmethod
    def model_json_schema(cls):
        return {
            "title": "Fit Result",
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        }


def response(status, payload, headers=None):
    value = Mock()
    value.status_code = status
    value.headers = headers or {}
    value.text = json.dumps(payload)
    value.json.return_value = payload
    return value


class TestNvidiaNimClient(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "NVIDIA_API_KEY": "secret",
                "RESUME_ALLOW_TEST_NETWORK": "1",
                "RESUME_BUILDER_TESTING": "1",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_sends_real_system_context_and_strict_schema(self):
        ok = response(
            200,
            {
                "choices": [
                    {
                        "message": {"content": '{"score":4.2}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )
        with patch.object(client.requests, "post", return_value=ok) as post:
            text, meta = client.NvidiaNimClient.generate(
                model="google/gemma-4-31b-it",
                system_instruction="full profile context",
                contents="full JD context",
                response_schema=Schema,
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "google/gemma-4-31b-it")
        self.assertEqual(body["messages"][0]["content"], "full profile context")
        self.assertEqual(body["messages"][1]["content"], "full JD context")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(text, '{"score":4.2}')
        self.assertEqual(meta["provider"], "nvidia_nim")
        self.assertEqual(meta["structured_mode"], "json_schema")

    def test_schema_dialect_fallback_does_not_switch_model(self):
        unsupported = response(400, {"detail": "response_format unsupported"})
        ok = response(
            200,
            {
                "choices": [
                    {"message": {"content": '{"score":3}'}, "finish_reason": "stop"}
                ]
            },
        )
        with patch.object(
            client.requests, "post", side_effect=[unsupported, ok]
        ) as post:
            text, meta = client.NvidiaNimClient.generate(
                model="nvidia/nemotron-3.5-lightning-30b-a3b",
                system_instruction="profile",
                contents="JD",
                response_schema=Schema,
            )
        bodies = [call.kwargs["json"] for call in post.call_args_list]
        self.assertEqual(
            {body["model"] for body in bodies},
            {"nvidia/nemotron-3.5-lightning-30b-a3b"},
        )
        self.assertIn("guided_json", bodies[1]["nvext"])
        self.assertEqual(meta["structured_mode"], "guided_json")
        self.assertEqual(text, '{"score":3}')

    def test_missing_key_fails_before_network(self):
        with (
            patch.dict(os.environ, {"NVIDIA_API_KEY": "", "NGC_API_KEY": ""}),
            patch.object(client.requests, "post") as post,
        ):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA_API_KEY"):
                client.NvidiaNimClient.generate(
                    model="openai/gpt-oss-20b",
                    system_instruction="profile",
                    contents="JD",
                )
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
