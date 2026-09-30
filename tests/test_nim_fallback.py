"""NIM (NVIDIA Nemotron) fallback for evaluation.

Two defects motivated these tests, both of which made the fallback look
wired up while never running:

1. `openai` -- the OpenAI-compatible transport NIM speaks, not the OpenAI
   service -- was missing from requirements.txt, so nim_available() said
   True on the strength of the API key alone and every real call raised
   ModuleNotFoundError. At the eval site, which had no handler, that
   aborted the whole batch.
2. GeminiClient.generate() RAISES SustainedFailureError on the second
   consecutive exhausted call, and evaluate_fit() makes two back-to-back
   calls -- so a genuine quota exhaustion escaped before the fallback
   block ran. It only ever fired when exactly one stage failed, which is
   the isolated blip it was least needed for.
"""

import json
import os
import tempfile
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import nim_fallback  # noqa: E402
import orchestrator  # noqa: E402
from gemini_client import SustainedFailureError  # noqa: E402


class TestNimAvailability(unittest.TestCase):
    """nim_available() must test the thing it claims is available."""

    def test_unavailable_without_a_key(self):
        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}, clear=False):
            with patch.object(nim_fallback, "_nvidia_api_key", return_value=None):
                self.assertFalse(nim_fallback.nim_available())

    def test_unavailable_when_the_transport_is_not_installed(self):
        """The original bug: a key alone was treated as "available", so the
        first real call raised ModuleNotFoundError."""
        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}, clear=False):
            with patch.object(nim_fallback, "_nvidia_api_key", return_value="k"):
                with patch.object(
                    nim_fallback, "_openai_sdk_importable", return_value=False
                ):
                    self.assertFalse(nim_fallback.nim_available())

    def test_available_with_both_a_key_and_the_transport(self):
        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}, clear=False):
            with patch.object(nim_fallback, "_nvidia_api_key", return_value="k"):
                with patch.object(
                    nim_fallback, "_openai_sdk_importable", return_value=True
                ):
                    self.assertTrue(nim_fallback.nim_available())

    def test_never_available_under_tests_without_the_opt_in(self):
        """Same escape-hatch convention as the Gemini/websearch guards: a
        test must not reach the network by accident."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_ALLOW_TEST_NETWORK", None)
            with patch.object(nim_fallback, "_nvidia_api_key", return_value="k"):
                self.assertFalse(nim_fallback.nim_available())

    def test_transport_is_actually_installed(self):
        """requirements.txt must keep shipping the transport -- this is the
        regression guard for the missing dependency itself."""
        self.assertTrue(nim_fallback._openai_sdk_importable())


def _jd_json():
    return json.dumps(
        {
            "job_title": "Marketing Manager",
            "company_name": "Acme Co",
            "location": "Remote",
            "description": "Full job description text goes here.",
        }
    )


def _capability_payload():
    return {
        "archetype": "Lifecycle Marketing Specialist",
        "fit_subscores": {
            "functional_alignment": 5,
            "north_star_alignment": 5,
            "level_plausibility": 5,
            "work_style_sustainability": 5,
            "tools_process_overlap": 5,
        },
        "capability_gaps": [],
    }


def _recruiter_payload():
    return {
        "hard_blockers": [],
        "interview_odds_subscores": {
            "title_continuity": 5,
            "evidence_match": 5,
            "domain_credibility": 5,
            "recruiter_legibility": 5,
            "narrative_burden": 5,
            "funnel_friction": 3,
        },
        "practical_pursue_subscores": {
            "remote_quality": 5,
            "compensation_viability": 5,
            "growth_value": 5,
            "time_to_offer": 5,
            "company_reputation": 5,
            "cultural_signals": 5,
            "posting_legitimacy_score": 5,
        },
        "prestige_tier": "Tier-2",
        "recommendation": "Strong pursue",
        "why": "Excellent alignment across all variables.",
        "recruiter_read": "Instantly legible.",
        "posting_legitimacy": "High Confidence",
        "posting_legitimacy_notes": "Active posting.",
        "ghost_job_red_flags": [],
    }


@patch("orchestrator.jd_manager.compute_posting_age_days", return_value=0)
@patch("orchestrator.jd_manager.read_jd_text", return_value=_jd_json())
class TestEvalFallbackReachability(unittest.TestCase):
    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.engine.load_yaml = MagicMock(return_value={})
        self.engine.load_prompt = MagicMock()
        self.engine.build_fit_evaluation_context = MagicMock(
            return_value="=== CONTEXT ==="
        )

    def test_sustained_gemini_failure_reaches_the_nim_fallback(self, *_mocks):
        """The core regression. generate() raises on the SECOND consecutive
        exhausted call, and evaluate_fit makes two -- so this exception used
        to escape before the fallback block ran at all."""
        with patch(
            "orchestrator.GeminiClient.generate",
            side_effect=SustainedFailureError("quota gone"),
        ):
            with patch.object(nim_fallback, "nim_available", return_value=True):
                with (
                    patch.object(nim_fallback, "generate_with_nim") as mock_nim,
                    patch(
                        "orchestrator.GeminiClient.parse_json",
                        side_effect=[_capability_payload(), _recruiter_payload()],
                    ),
                ):
                    mock_nim.side_effect = [
                        ("cap_json", nim_fallback.SUPER_MODEL),
                        ("rec_json", nim_fallback.SUPER_MODEL),
                    ]
                    result = self.engine.evaluate_fit("fake_path.txt")

        self.assertIsNotNone(result, "NIM should have covered the sustained failure")
        self.assertEqual(mock_nim.call_count, 2)
        self.assertEqual(result.get("_eval_provider"), "nim")
        self.assertEqual(
            result["_nim_models"]["capability_model"], nim_fallback.SUPER_MODEL
        )

    def test_sustained_failure_is_reraised_when_nim_cannot_cover(self, *_mocks):
        """Stopping the batch is still right when nothing can score the
        role -- returning None would turn "quota gone, stop" into "this one
        role failed, carry on" and burn the rest of the backlog."""
        with patch(
            "orchestrator.GeminiClient.generate",
            side_effect=SustainedFailureError("quota gone"),
        ):
            with patch.object(nim_fallback, "nim_available", return_value=False):
                with self.assertRaises(SustainedFailureError):
                    self.engine.evaluate_fit("fake_path.txt")

    def test_a_failing_nim_call_never_aborts_the_run(self, *_mocks):
        """This site had no handler at all, so any NIM error propagated and
        killed the whole batch, discarding every role already scored. An
        ordinary (non-sustained) empty response must degrade to None."""
        with patch("orchestrator.GeminiClient.generate", return_value=(None, {})):
            with patch("orchestrator.GeminiClient.parse_json", return_value={}):
                with patch.object(nim_fallback, "nim_available", return_value=True):
                    with patch.object(
                        nim_fallback,
                        "generate_with_nim",
                        side_effect=RuntimeError("NIM exploded"),
                    ):
                        result = self.engine.evaluate_fit("fake_path.txt")
        self.assertIsNone(result)

    def test_nim_is_not_called_when_gemini_succeeds(self, *_mocks):
        with patch(
            "orchestrator.GeminiClient.generate",
            side_effect=[("cap", {}), ("rec", {})],
        ):
            with patch(
                "orchestrator.GeminiClient.parse_json",
                side_effect=[_capability_payload(), _recruiter_payload()],
            ):
                with patch.object(nim_fallback, "generate_with_nim") as mock_nim:
                    result = self.engine.evaluate_fit("fake_path.txt")

        self.assertIsNotNone(result)
        mock_nim.assert_not_called()
        self.assertNotIn("_eval_provider", result)


class TestKeyIsReadFromTheProfileEnv(unittest.TestCase):
    """Secrets live in profiles/<name>/.env, not the shell.

    Reading os.environ directly was correct only by accident: the eval
    fallback always follows a Gemini call, and gemini_client.api_keys()
    load_dotenv()s on its way there. build_nim_index() calls no Gemini API,
    so it reported "NVIDIA_API_KEY not set" for a key sitting in .env.
    """

    def test_loads_the_profile_env_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("NVIDIA_API_KEY=nvapi-from-the-profile-env\n")
            previous = os.environ.pop("NVIDIA_API_KEY", None)
            self.addCleanup(
                lambda: (
                    os.environ.__setitem__("NVIDIA_API_KEY", previous)
                    if previous is not None
                    else os.environ.pop("NVIDIA_API_KEY", None)
                )
            )
            with patch("profile_paths.env_path", return_value=env_path):
                self.assertEqual(
                    nim_fallback._nvidia_api_key(), "nvapi-from-the-profile-env"
                )

    def test_a_missing_env_file_is_not_an_error(self):
        with patch("profile_paths.env_path", return_value="/nope/.env"):
            # Must not raise; the environment may legitimately carry the key.
            nim_fallback._nvidia_api_key()


if __name__ == "__main__":
    unittest.main()
