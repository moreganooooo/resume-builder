import json
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


def _pass_critique_json():
    return json.dumps(
        {
            "manager_test": "PASS",
            "believability_score": 95,
            "hidden_gem_score": 10,
            "hidden_gem_flag": False,
            "hidden_gem_reason": "",
            "weaknesses": "",
        }
    )


def _fail_critique_json():
    return json.dumps(
        {
            "manager_test": "FAIL",
            "believability_score": 50,
            "hidden_gem_score": 0,
            "hidden_gem_flag": False,
            "hidden_gem_reason": "",
            "weaknesses": "too vague",
        }
    )


class TestAuditResume(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.bullet_tuples = [
            ("Grew revenue 20% via new outbound program.", "CompanyA", "sales"),
            (
                "Led a team of 5 engineers to ship a new platform.",
                "CompanyB",
                "leadership",
            ),
        ]
        self.static_prefix = "STATIC PREFIX FOR TEST"

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_resumes_from_partial_refined_bullets(self, mock_generate):
        mock_generate.return_value = (_pass_critique_json(), {})
        checkpoints = []

        result = self.engine.audit_and_refine_bullets(
            self.bullet_tuples,
            self.static_prefix,
            resume_from=[self.bullet_tuples[0][0]],
            on_bullet_complete=lambda partial: checkpoints.append(list(partial)),
        )

        # Only the second (not-yet-refined) bullet should trigger a Gemini call.
        self.assertEqual(mock_generate.call_count, 1)
        # The checkpoint callback fires exactly once, for the newly completed bullet.
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(result, [self.bullet_tuples[0][0], self.bullet_tuples[1][0]])

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_no_resume_processes_every_bullet(self, mock_generate):
        mock_generate.return_value = (_pass_critique_json(), {})
        checkpoints = []

        result = self.engine.audit_and_refine_bullets(
            self.bullet_tuples,
            self.static_prefix,
            on_bullet_complete=lambda partial: checkpoints.append(list(partial)),
        )

        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(len(result), 2)

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_fully_resumed_skips_loop_entirely(self, mock_generate):
        already_done = [b for b, _, _ in self.bullet_tuples]
        result = self.engine.audit_and_refine_bullets(
            self.bullet_tuples,
            self.static_prefix,
            resume_from=already_done,
        )
        mock_generate.assert_not_called()
        self.assertEqual(result, already_done)

    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_bullet_with_missing_critique_data_is_not_dropped_by_sort(
        self, mock_generate
    ):
        """Bug 2 regression: a bullet whose critique call fails (empty
        response, exception, or malformed JSON -> critique_data=None) must
        still appear in the final refined_bullets list after the end-of-run
        sort. It should sort last (worst tier via _bullet_sort_key({}))
        rather than silently vanish because it was never added to a
        critique-only pairs list."""
        three_bullets = self.bullet_tuples + [
            (
                "Cut onboarding time in half through process redesign.",
                "CompanyC",
                "ops",
            ),
        ]
        call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                # Simulate an empty critique response -> _record(bullet, None).
                return ("", {})
            return (_pass_critique_json(), {})

        mock_generate.side_effect = generate_side_effect

        result = self.engine.audit_and_refine_bullets(
            three_bullets,
            self.static_prefix,
        )

        # All three bullets must survive the sort, including the one with
        # missing critique data -- before the fix, it was silently dropped.
        self.assertEqual(len(result), 3)
        self.assertIn(three_bullets[1][0], result)
        # The bullet with missing critique data sorts last (worst tier).
        self.assertEqual(result[-1], three_bullets[1][0])

    def test_bullet_sort_key_ranks_pass_before_fail(self):
        pass_result = {"manager_test": "PASS", "believability_score": 50}
        fail_result = {"manager_test": "FAIL", "believability_score": 99}
        self.assertLess(
            orchestrator._bullet_sort_key(pass_result),
            orchestrator._bullet_sort_key(fail_result),
        )

    def test_bullet_sort_key_ranks_higher_believability_first_within_same_pass_status(
        self,
    ):
        higher = {"manager_test": "PASS", "believability_score": 90}
        lower = {"manager_test": "PASS", "believability_score": 40}
        self.assertLess(
            orchestrator._bullet_sort_key(higher),
            orchestrator._bullet_sort_key(lower),
        )


class TestAuditResumeRewritePath(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.bullet_tuples = [("Managed stuff.", "CompanyA", "sales")]
        self.static_prefix = "STATIC PREFIX FOR TEST"

    @patch("orchestrator.bullet_feedback.queue_accepted_rewrite", return_value=False)
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    @patch("orchestrator.GeminiClient.generate")
    def test_gemma_rewrite_gets_slim_prompt_flash_lite_gets_full(
        self, mock_generate, mock_queue
    ):
        # A FAIL critique triggers the rewrite loop. Two empty Gemma
        # responses exhaust MAX_REWRITE_PARSE_FAILURES and hand off to
        # flash-lite (mirrors rewrite_bullets.py's process_bullet()), which
        # then succeeds. Verifies (1) Gemma gets the slim rules block,
        # flash-lite the full one -- the 2026-07-16 fix for Gemma's 16k TPM
        # cap -- and (2) the model_fallback/max_output_tokens guards match
        # rewrite_bullets.py exactly.
        mock_generate.side_effect = [
            (_fail_critique_json(), {}),  # critique -> FAIL
            ("", {}),  # rewrite attempt 0 (gemma) -> empty
            ("", {}),  # rewrite attempt 1 (gemma) -> empty, triggers fallback
            (
                json.dumps({"rewritten_bullet": "Directed 5 initiatives."}),
                {},
            ),  # rewrite attempt 2 (flash-lite)
            (_pass_critique_json(), {}),  # rescore -> PASS, accepted
        ]

        self.engine.audit_and_refine_bullets(self.bullet_tuples, self.static_prefix)

        calls = mock_generate.call_args_list
        gemma_call = calls[1]
        flash_call = calls[3]

        self.assertEqual(gemma_call.kwargs["model"], "gemma-4-31b-it")
        self.assertEqual(flash_call.kwargs["model"], "gemini-3.1-flash-lite")
        self.assertLess(
            len(gemma_call.kwargs["system_instruction"]),
            len(flash_call.kwargs["system_instruction"]),
        )
        self.assertFalse(gemma_call.kwargs["model_fallback"])
        self.assertEqual(
            gemma_call.kwargs["max_output_tokens"],
            orchestrator.REWRITE_MAX_OUTPUT_TOKENS,
        )


if __name__ == "__main__":
    unittest.main()
