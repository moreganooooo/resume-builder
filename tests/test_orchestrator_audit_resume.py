import json
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


def _pass_critique_json():
    return json.dumps({
        "manager_test": "PASS",
        "believability_score": 95,
        "hidden_gem_score": 10,
        "hidden_gem_flag": False,
        "hidden_gem_reason": "",
        "weaknesses": "",
    })


class TestAuditResume(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.bullet_tuples = [
            ("Grew revenue 20% via new outbound program.", "CompanyA", "sales"),
            ("Led a team of 5 engineers to ship a new platform.", "CompanyB", "leadership"),
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


if __name__ == "__main__":
    unittest.main()
