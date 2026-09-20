import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import gemini_client
from gemini_client import (  # noqa: E402
    MODEL_FALLBACKS,
    GeminiClient,
    SustainedFailureError,
)

_ORIG_ALLOW_NETWORK = None


def setUpModule():
    """Opt this module past gemini_client's test-network guard.

    Every test in this file patches requests.post, so nothing here reaches
    the wire -- but _get_auth_headers() is evaluated as an ARGUMENT to that
    mocked call, and the guard lives there (the one point all four post
    sites funnel through). Without this the guard fires on tests that never
    intended to touch the network.

    This is the narrow, deliberate exemption the RESUME_ALLOW_TEST_NETWORK
    escape hatch exists for: a module that exercises the client itself with
    a mocked transport. Verified with an instrumented run -- outbound calls
    from the full suite are zero. If you add a test here that does NOT mock
    requests.post, it will make a real, billable API call.
    """
    global _ORIG_ALLOW_NETWORK
    _ORIG_ALLOW_NETWORK = os.environ.get(gemini_client._TEST_NETWORK_ENV)
    os.environ[gemini_client._TEST_NETWORK_ENV] = "1"


def tearDownModule():
    if _ORIG_ALLOW_NETWORK is None:
        os.environ.pop(gemini_client._TEST_NETWORK_ENV, None)
    else:
        os.environ[gemini_client._TEST_NETWORK_ENV] = _ORIG_ALLOW_NETWORK


def _success_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 2,
            "totalTokenCount": 12,
        },
    }
    return resp


class TestModelFallbacks(unittest.TestCase):

    def test_default_flash_lite_walks_to_the_older_one_then_gemma(self):
        # The old flash-lite <-> gemma pair was each other's only rescue, so
        # when both failed at once (2026-09-15) a call bounced between them
        # until its retries ran out. Three models break that loop.
        self.assertEqual(
            MODEL_FALLBACKS["gemini-3.5-flash-lite"], "gemini-3.1-flash-lite"
        )
        self.assertEqual(MODEL_FALLBACKS["gemini-3.1-flash-lite"], "gemma-4-31b-it")

    def test_gemma_falls_back_to_the_default_flash_lite(self):
        self.assertEqual(MODEL_FALLBACKS["gemma-4-31b-it"], "gemini-3.5-flash-lite")

    def test_every_fallback_target_has_its_own_fallback(self):
        # A target with no entry is a dead end: its failures just exhaust
        # the remaining retries on the one model.
        for target in MODEL_FALLBACKS.values():
            self.assertIn(target, MODEL_FALLBACKS)


class TestGenerateFallsBackAfterRepeatedFailures(unittest.TestCase):

    def setUp(self):
        GeminiClient._last_gemma_call_ts = 0.0

    def tearDown(self):
        GeminiClient._last_gemma_call_ts = 0.0

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_switches_to_3_1_flash_lite_after_two_3_5_timeouts(self, mock_post):
        mock_post.side_effect = [
            requests.exceptions.Timeout("timeout=90"),
            requests.exceptions.Timeout("timeout=90"),
            _success_response(),
        ]
        text, usage = GeminiClient.generate(
            model="gemini-3.5-flash-lite",
            system_instruction="sys",
            contents="do the thing",
        )
        self.assertEqual(text, "ok")
        self.assertEqual(mock_post.call_count, 3)
        third_call_url = mock_post.call_args_list[2].args[0]
        self.assertIn("gemini-3.1-flash-lite", third_call_url)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_one_call_walks_the_whole_chain(self, mock_post):
        # Both original models failing at once is the case the third model
        # exists for: the call must reach gemma after 3.5-flash-lite fails
        # too, not give up.
        mock_post.side_effect = [
            requests.exceptions.Timeout("timeout=90"),
            requests.exceptions.Timeout("timeout=90"),
            requests.exceptions.Timeout("timeout=90"),
            requests.exceptions.Timeout("timeout=90"),
            _success_response(),
        ]
        text, usage = GeminiClient.generate(
            model="gemini-3.5-flash-lite",
            system_instruction="sys",
            contents="do the thing",
        )
        self.assertEqual(text, "ok")
        urls = [c.args[0] for c in mock_post.call_args_list]
        self.assertIn("gemini-3.1-flash-lite", urls[2])
        self.assertIn("gemma-4-31b-it", urls[4])

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
        self.assertIn("gemini-3.5-flash-lite", third_call_url)


class TestSustainedFailureDetection(unittest.TestCase):

    def setUp(self):
        gemini_client.GeminiClient._consecutive_full_failures = 0

    def tearDown(self):
        gemini_client.GeminiClient._consecutive_full_failures = 0

    def _rate_limited_response(self):
        resp = MagicMock()
        resp.status_code = 429
        return resp

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_first_full_exhaustion_returns_none_without_raising(self, mock_post):
        mock_post.return_value = self._rate_limited_response()
        text, usage = gemini_client.GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        self.assertIsNone(text)
        self.assertEqual(usage, {})
        self.assertEqual(gemini_client.GeminiClient._consecutive_full_failures, 1)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_second_consecutive_full_exhaustion_raises(self, mock_post):
        mock_post.return_value = self._rate_limited_response()

        gemini_client.GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        with self.assertRaises(gemini_client.SustainedFailureError):
            gemini_client.GeminiClient.generate(
                model="gemini-3.1-flash-lite",
                system_instruction="sys",
                contents="do the thing",
                max_retries=2,
            )

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_success_between_exhaustions_resets_the_counter(self, mock_post):
        mock_post.side_effect = [
            self._rate_limited_response(),
            self._rate_limited_response(),  # exhaustion 1 (max_retries=2)
            _success_response(),  # success -- resets counter
            self._rate_limited_response(),
            self._rate_limited_response(),  # exhaustion again -- only #1 now
        ]
        gemini_client.GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        gemini_client.GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        text, usage = gemini_client.GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        self.assertIsNone(text)
        self.assertEqual(gemini_client.GeminiClient._consecutive_full_failures, 1)


class TestModelFallbackOptOut(unittest.TestCase):

    # Reset through the module as well as the imported name: when another
    # test module reloads gemini_client, `gemini_client.GeminiClient` becomes
    # a new class while this file's `GeminiClient` still names the old one --
    # and generate() counts failures on the live class. Resetting only the
    # stale name let one test's exhausted retries push the next test over
    # the SustainedFailureError threshold, but only in a full-suite run.
    def _reset_client_state(self):
        for cls in [GeminiClient, gemini_client.GeminiClient]:
            cls._consecutive_full_failures = 0
            cls._last_gemma_call_ts = 0.0

    def setUp(self):
        self._reset_client_state()

    def tearDown(self):
        self._reset_client_state()

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
    def test_scoring_fallbacks_never_reach_3_5_flash_lite(self, mock_post):
        mock_post.return_value = self._rate_limited_response()
        GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="score this",
            max_retries=6,
            fallbacks=gemini_client.SCORING_FALLBACKS,
        )
        targets = [call.args[0] for call in mock_post.call_args_list]
        self.assertTrue(any("gemma-4-31b-it" in url for url in targets))
        self.assertFalse(any("gemini-3.5-flash-lite" in url for url in targets))
        self.assertNotIn("gemini-3.5-flash-lite", gemini_client.SCORING_FALLBACKS)
        self.assertNotIn(
            "gemini-3.5-flash-lite", gemini_client.SCORING_FALLBACKS.values()
        )

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_grounded_call_never_swaps_even_with_fallback_enabled(self, mock_post):
        # Grounding quota is per model family (zero for Gemini 3 on the free
        # tier), so a swap can land on a model with no grounding quota at
        # all; a grounded call stays on the model it was sent to.
        server_error = MagicMock()
        server_error.status_code = 500
        mock_post.return_value = server_error
        text, _ = GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="find the website",
            max_retries=4,
            tools=[{"google_search": {}}],
        )
        self.assertIsNone(text)
        for call in mock_post.call_args_list:
            self.assertIn("gemini-3.1-flash-lite", call.args[0])
            self.assertNotIn("gemma", call.args[0])

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_search_call_swaps_only_within_gemma(self, mock_post):
        server_error = MagicMock()
        server_error.status_code = 500
        mock_post.side_effect = [server_error, server_error, _success_response()]
        text, _ = GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction="sys",
            contents="find the website",
            tools=[{"google_search": {}}],
        )
        self.assertEqual(text, "ok")
        self.assertIn("gemma-4-26b-a4b-it", mock_post.call_args_list[2].args[0])

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_maps_grounded_call_swaps_to_the_other_flash_lite(self, mock_post):
        server_error = MagicMock()
        server_error.status_code = 503
        mock_post.side_effect = [server_error, server_error, _success_response()]
        text, _ = gemini_client.generate_grounded(
            "gemini-3.5-flash-lite", "where?", tools=[{"google_maps": {}}]
        )
        self.assertEqual(text, "ok")
        self.assertIn("gemini-3.1-flash-lite", mock_post.call_args_list[2].args[0])

    def test_unknown_or_mixed_tools_get_no_fallback(self):
        self.assertEqual(gemini_client.grounded_fallbacks([{"code_execution": {}}]), {})
        self.assertEqual(
            gemini_client.grounded_fallbacks(
                [{"google_search": {}}, {"google_maps": {}}]
            ),
            {},
        )

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_generate_grounded_returns_text_and_grounding(self, mock_post):
        # The Maps lookup must SEE the grounding to trust an address.
        ok = MagicMock()
        ok.status_code = 200
        ok.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "thinking...", "thought": True},
                            {"text": "140 Otter St"},
                        ]
                    },
                    "groundingMetadata": {"groundingChunks": [{"maps": {"uri": "u"}}]},
                }
            ]
        }
        server_error = MagicMock()
        server_error.status_code = 500
        mock_post.side_effect = [server_error, ok]
        text, grounding = gemini_client.generate_grounded(
            "gemini-3.1-flash-lite",
            "q",
            tools=[{"google_maps": {}}],
            tool_config={"retrievalConfig": {}},
        )
        self.assertEqual(text, "140 Otter St")
        self.assertEqual(grounding["groundingChunks"][0]["maps"]["uri"], "u")
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["toolConfig"], {"retrievalConfig": {}}
        )

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
        self.assertIn("gemini-3.5-flash-lite", third_call_url)


class TestGemmaPacing(unittest.TestCase):

    def setUp(self):
        gemini_client.GeminiClient._last_gemma_call_ts = 0.0

    def tearDown(self):
        gemini_client.GeminiClient._last_gemma_call_ts = 0.0

    @patch("gemini_client.time.sleep")
    @patch("gemini_client.time.time")
    @patch("gemini_client.requests.post")
    def test_waits_out_the_remainder_when_last_gemma_call_was_recent(
        self, mock_post, mock_time, mock_sleep
    ):
        mock_post.return_value = _success_response()
        gemini_client.GeminiClient._last_gemma_call_ts = 1000.0
        mock_time.return_value = 1010.0  # only 10s since the last Gemma call

        gemini_client.GeminiClient.generate(
            model="gemma-4-31b-it", system_instruction="sys", contents="do the thing"
        )

        mock_sleep.assert_called_once()
        self.assertAlmostEqual(
            mock_sleep.call_args.args[0], 55.0
        )  # 65s cap - 10s elapsed

    @patch("gemini_client.time.sleep")
    @patch("gemini_client.time.time")
    @patch("gemini_client.requests.post")
    def test_no_wait_once_the_interval_has_already_elapsed(
        self, mock_post, mock_time, mock_sleep
    ):
        mock_post.return_value = _success_response()
        gemini_client.GeminiClient._last_gemma_call_ts = 1000.0
        mock_time.return_value = (
            1070.0  # 70s since the last Gemma call -- past the 65s floor
        )

        gemini_client.GeminiClient.generate(
            model="gemma-4-31b-it", system_instruction="sys", contents="do the thing"
        )

        mock_sleep.assert_not_called()

    @patch("gemini_client.time.sleep")
    @patch("gemini_client.requests.post")
    def test_flash_lite_calls_are_never_paced(self, mock_post, mock_sleep):
        mock_post.return_value = _success_response()
        gemini_client.GeminiClient._last_gemma_call_ts = (
            0.0  # as if a Gemma call just happened at epoch 0
        )

        gemini_client.GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
        )

        mock_sleep.assert_not_called()


class TestExtraSchemaProperties(unittest.TestCase):
    """
    orchestrator.py's per-profile education achievement-key fields (see
    ResumeEngine.build_education_achievement_schema_fields()) can't be
    static fields on the Pydantic response_schema class, since their valid
    enum values differ per profile. extra_schema_properties/extra_required
    let a caller merge real, per-call fields into whatever response_schema
    it passed -- these tests confirm the merge actually reaches the request
    body sent to Gemini, survives the same resolve_refs/sanitize_schema
    pipeline every other property goes through, and stays a no-op when
    unused (the vast majority of calls, which never pass either kwarg).
    """

    @patch("gemini_client.requests.post")
    def test_extra_properties_and_required_merge_into_a_dict_response_schema(
        self, mock_post
    ):
        mock_post.return_value = _success_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="content",
            response_schema={
                "type": "object",
                "properties": {"TAGLINE": {"type": "string"}},
                "required": ["TAGLINE"],
            },
            extra_schema_properties={
                "EDU_ACHIEVEMENT_KEY_1": {"type": "string", "enum": ["a", "b"]}
            },
            extra_required=["EDU_ACHIEVEMENT_KEY_1"],
        )

        sent_schema = mock_post.call_args.kwargs["json"]["generationConfig"][
            "responseSchema"
        ]
        self.assertEqual(sent_schema["properties"]["TAGLINE"], {"type": "string"})
        self.assertEqual(
            sent_schema["properties"]["EDU_ACHIEVEMENT_KEY_1"],
            {"type": "string", "enum": ["a", "b"]},
        )
        self.assertEqual(
            set(sent_schema["required"]), {"TAGLINE", "EDU_ACHIEVEMENT_KEY_1"}
        )

    @patch("gemini_client.requests.post")
    def test_no_extra_kwargs_leaves_the_schema_unchanged(self, mock_post):
        mock_post.return_value = _success_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="content",
            response_schema={
                "type": "object",
                "properties": {"TAGLINE": {"type": "string"}},
                "required": ["TAGLINE"],
            },
        )

        sent_schema = mock_post.call_args.kwargs["json"]["generationConfig"][
            "responseSchema"
        ]
        self.assertEqual(list(sent_schema["properties"].keys()), ["TAGLINE"])
        self.assertEqual(sent_schema["required"], ["TAGLINE"])


class TestToolsParameter(unittest.TestCase):
    """company_research.find_company_website() is the first real caller of
    tools= (Google Search grounding) -- these confirm it reaches the
    request body, and that combining it with response_schema is rejected
    up front rather than surfacing as a confusing API-level 400, since the
    two are mutually exclusive on Gemini's API."""

    @patch("gemini_client.requests.post")
    def test_tools_reaches_the_request_body(self, mock_post):
        mock_post.return_value = _success_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="content",
            tools=[{"google_search": {}}],
        )

        sent_body = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_body["tools"], [{"google_search": {}}])

    @patch("gemini_client.requests.post")
    def test_no_tools_key_when_tools_not_passed(self, mock_post):
        mock_post.return_value = _success_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys", contents="content"
        )

        sent_body = mock_post.call_args.kwargs["json"]
        self.assertNotIn("tools", sent_body)

    def test_tools_with_response_schema_raises_before_any_request(self):
        with self.assertRaises(ValueError):
            GeminiClient.generate(
                model="gemini-3.1-flash-lite",
                system_instruction="sys",
                contents="content",
                tools=[{"google_search": {}}],
                response_schema={"type": "object", "properties": {}},
            )


class TestContextCaching(unittest.TestCase):

    def setUp(self):
        GeminiClient._cache_map.clear()
        GeminiClient._cache_unavailable_models.clear()

    def tearDown(self):
        GeminiClient._cache_map.clear()
        GeminiClient._cache_unavailable_models.clear()

    @patch("gemini_client.requests.post")
    def test_system_instruction_under_threshold_skips_cache(self, mock_post):
        mock_post.return_value = _success_response()
        sys_prompt = "x" * 15000  # Less than 131072 chars (32k tokens)
        cache_name = GeminiClient._get_or_create_cache(
            model="gemini-2.0-flash", system_instruction=sys_prompt
        )
        self.assertIsNone(cache_name)
        self.assertEqual(mock_post.call_count, 0)

    @patch("gemini_client.requests.post")
    def test_system_instruction_over_threshold_creates_cache(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "name": "cachedContents/sample-cache-123",
            "expireTime": "2026-12-31T23:59:59Z",
        }
        mock_post.return_value = resp

        sys_prompt = "x" * 140000
        cache_name = GeminiClient._get_or_create_cache(
            model="gemini-2.0-flash", system_instruction=sys_prompt
        )
        self.assertEqual(cache_name, "cachedContents/sample-cache-123")
        self.assertEqual(mock_post.call_count, 1)
        self.assertIn("cachedContents", mock_post.call_args.args[0])

    @patch("gemini_client.requests.post")
    def test_non_gemini_model_skips_cache(self, mock_post):
        sys_prompt = "x" * 140000
        cache_name = GeminiClient._get_or_create_cache(
            model="claude-3-5-sonnet", system_instruction=sys_prompt
        )
        self.assertIsNone(cache_name)
        self.assertEqual(mock_post.call_count, 0)

    @patch("gemini_client.requests.post")
    def test_cache_attached_to_generate_body(self, mock_post):
        # First call is to create cache, second call is generate()
        cache_resp = MagicMock()
        cache_resp.status_code = 200
        cache_resp.json.return_value = {
            "name": "cachedContents/gen-cache-456",
            "expireTime": "2026-12-31T23:59:59Z",
        }

        mock_post.side_effect = [cache_resp, _success_response()]

        sys_prompt = "x" * 140000
        text, usage = GeminiClient.generate(
            model="gemini-2.0-flash",
            system_instruction=sys_prompt,
            contents="test prompt",
        )
        self.assertEqual(text, "ok")
        self.assertEqual(mock_post.call_count, 2)
        generate_body = mock_post.call_args_list[1].kwargs["json"]
        self.assertEqual(generate_body["cachedContent"], "cachedContents/gen-cache-456")
        self.assertNotIn("systemInstruction", generate_body)


class TestInlineFile(unittest.TestCase):
    """inline_file (jd_image_ingest.py's screenshot-JD path) must add a
    second `parts` entry alongside the text prompt, base64-encoded, and
    must never appear at all when unused -- the vast majority of calls."""

    @patch("gemini_client.requests.post")
    def test_inline_file_becomes_a_second_part_base64_encoded(self, mock_post):
        import base64

        mock_post.return_value = _success_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="Transcribe this.",
            inline_file=(b"\x89PNG raw bytes", "image/png"),
        )

        parts = mock_post.call_args.kwargs["json"]["contents"][0]["parts"]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], {"text": "Transcribe this."})
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/png")
        self.assertEqual(
            base64.b64decode(parts[1]["inlineData"]["data"]), b"\x89PNG raw bytes"
        )

    @patch("gemini_client.requests.post")
    def test_no_inline_file_means_one_part_only(self, mock_post):
        mock_post.return_value = _success_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="content",
        )

        parts = mock_post.call_args.kwargs["json"]["contents"][0]["parts"]
        self.assertEqual(parts, [{"text": "content"}])


class TestEmbedWithRetryLoop(unittest.TestCase):
    """GeminiClient.embed() now cycles through keys and falls back to backup model."""

    def setUp(self):
        gemini_client._KEY_COOLDOWNS.clear()

    def _embed_success_response(self):
        """Mock response with valid embedding vector."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"embedding": {"values": [0.1, 0.2, 0.3]}}
        return resp

    def _embed_429_response(self):
        """Mock 429 rate limit response."""
        resp = MagicMock()
        resp.status_code = 429
        resp.json.return_value = {"error": {"details": []}}
        return resp

    @patch("gemini_client.api_keys", return_value=["key-one"])
    @patch("gemini_client.time.sleep")
    @patch("gemini_client.requests.post")
    def test_embed_basic_success(self, mock_post, mock_sleep, mock_keys):
        """Basic success case: single key, single attempt."""
        mock_post.return_value = self._embed_success_response()

        result = GeminiClient.embed("test")

        self.assertEqual(result, [0.1, 0.2, 0.3])
        mock_post.assert_called_once()

    @patch("gemini_client.time.sleep")
    @patch("gemini_client.requests.post")
    def test_embed_retries_on_429_with_key_switching(self, mock_post, mock_sleep):
        """First call 429, second call succeeds → returns result."""
        mock_post.side_effect = [
            self._embed_429_response(),
            self._embed_success_response(),
        ]

        with patch("gemini_client.api_keys", return_value=["key-one", "key-two"]):
            result = GeminiClient.embed("test")

        self.assertEqual(result, [0.1, 0.2, 0.3])
        self.assertEqual(mock_post.call_count, 2)

    @patch("gemini_client.time.sleep")
    @patch("gemini_client.requests.post")
    def test_embed_returns_none_when_primary_exhausted(self, mock_post, mock_sleep):
        """Primary model exhausts all keys with 429 → return None."""
        mock_post.return_value = self._embed_429_response()

        with patch("gemini_client.api_keys", return_value=["key-one"]):
            result = GeminiClient.embed("test", max_retries=1)

        self.assertIsNone(result)

    @patch("gemini_client.time.sleep")
    @patch("gemini_client.requests.post")
    def test_embed_falls_back_to_backup_model(self, mock_post, mock_sleep):
        """Primary model fails repeatedly, backup model succeeds."""
        models_called = []

        def respond(url, **kw):
            if "gemini-embedding-2" in url:
                models_called.append("ge2")
                return self._embed_429_response()
            else:
                models_called.append("ge1")
                return self._embed_success_response()

        mock_post.side_effect = respond

        with patch("gemini_client.api_keys", return_value=["key-one"]):
            result = GeminiClient.embed("test", max_retries=2)

        self.assertEqual(result, [0.1, 0.2, 0.3])
        self.assertIn("ge2", models_called)
        self.assertIn("ge1", models_called)
        # ge1 should come after ge2 failed
        self.assertGreater(models_called.index("ge1"), models_called.index("ge2"))

    @patch("gemini_client.api_keys", return_value=["key-one"])
    @patch("gemini_client.time.sleep")
    @patch("gemini_client.requests.post")
    def test_embed_honors_server_retry_info_from_429(
        self, mock_post, mock_sleep, mock_keys
    ):
        """Server 429 with RetryInfo delay is honored."""
        resp_with_delay = MagicMock()
        resp_with_delay.status_code = 429
        resp_with_delay.json.return_value = {
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "2.5s",
                    }
                ]
            }
        }
        mock_post.side_effect = [resp_with_delay, self._embed_success_response()]

        result = GeminiClient.embed("test")

        self.assertEqual(result, [0.1, 0.2, 0.3])
        # Verify sleep was called (with server's delay + buffer)
        self.assertTrue(mock_sleep.called)

    @patch("gemini_client.requests.post")
    def test_embed_with_no_api_keys_returns_none(self, mock_post):
        """Empty key pool → return None without calling post."""
        with patch("gemini_client.api_keys", return_value=[]):
            result = GeminiClient.embed("test")

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch("gemini_client.requests.post")
    def test_embed_respects_test_network_guard(self, mock_post):
        """Test network guard blocks embed() calls."""
        with patch("gemini_client.api_keys", return_value=["key-one"]):
            with patch("gemini_client._blocked_under_test", return_value=True):
                with self.assertRaises(gemini_client.TestNetworkBlockedError):
                    GeminiClient.embed("test")

        mock_post.assert_not_called()

    @patch("gemini_client.api_keys", return_value=["key-one"])
    @patch("gemini_client.requests.post")
    def test_embed_returns_valid_vector(self, mock_post, mock_keys):
        """Successful embed returns vector with correct dimensions."""
        mock_post.return_value = self._embed_success_response()

        result = GeminiClient.embed("test sentence")

        self.assertEqual(len(result), 3)
        self.assertEqual(result, [0.1, 0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
