import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestOrchestratorCoverletterVoice(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_voice.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "job_title": "Content Strategist",
                    "company_name": "Acme Corp",
                    "description": "We are hiring a Content Strategist with strong writing skills.",
                },
                f,
            )
        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.json_out = os.path.join(
            self.engine.output_json_dir, f"{self.stem}_CoverLetter.json"
        )
        self.html_out = os.path.join(
            self.engine.output_html_dir, f"{self.stem}_CoverLetter.html"
        )
        self.pdf_out = os.path.join(
            self.engine.output_pdf_dir, f"{self.stem}_CoverLetter.pdf"
        )
        self.docx_out = os.path.join(
            self.engine.output_docx_dir, f"{self.stem}_CoverLetter.docx"
        )

    def tearDown(self):
        for path in (
            self.jd_path,
            self.json_out,
            self.html_out,
            self.pdf_out,
            self.docx_out,
        ):
            if os.path.exists(path):
                os.remove(path)

    def test_voice_rules_loaded_in_engine_init(self):
        self.assertTrue(hasattr(self.engine, "voice_rules"))
        self.assertIsInstance(self.engine.voice_rules, dict)
        self.assertIn("thresholds", self.engine.voice_rules)

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.render_coverletter_docx", return_value="dummy.docx")
    @patch("orchestrator.render_coverletter", return_value="dummy.html")
    @patch("validate_pdf_text.validate_coverletter_pdf_text", return_value=[])
    @patch("subprocess.run")
    @patch("orchestrator.GeminiClient.generate")
    def test_voice_violations_trigger_retry_with_issues_block(
        self,
        mock_gen,
        mock_subp,
        mock_val_pdf,
        mock_render_html,
        mock_render_docx,
        mock_research,
    ):
        mock_subp.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        # Monotonous repetitive body paragraphs on attempt 1 (fails voice std dev / spacing, ~320 words total)
        # Each sentence is exactly 16 words, giving std dev = 0.0
        s16 = "The quick brown fox jumps over the very lazy sleeping dog today in the warm summer."
        bad_p1 = " ".join([s16] * 10)
        bad_p2 = " ".join([s16] * 10)
        bad_letter = {
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "body_paragraphs": [bad_p1, bad_p2],
            "sign_off": "Sincerely,",
        }

        # Dynamic high-variance prose on attempt 2 (passes all voice & word count checks, ~340 words total)
        good_p1 = (
            "I love building systems that work quietly in the background — so people do not have to. "
            "Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. "
            "Clarity and empathy win every time. "
            "When scaling new platforms, communication operations must balance operational rigor with genuine human connection to prevent audience churn and fatigue. "
            "Every campaign touchpoint deserves meticulous measurement and narrative intentionality."
        )
        good_p2 = (
            "That loop of ideate, execute, and optimize is where I do my very best work. "
            "Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader's time while earning their trust. "
            "I partner closely with engineering teams to instrument accurate tracking for every user touchpoint, then use that behavioral data to prioritize messaging sequences most likely to convert cold leads. "
            "I look forward to bringing that same disciplined energy to the Content Strategist role at Acme Corp."
        )
        # Add another supporting paragraph to reach 300-450 word target
        good_p3 = (
            "Beyond tactical execution, I champion collaborative workflows across product and sales teams. "
            "I thrive in fast-paced environments where priorities shift quickly and cross-functional clarity is paramount. "
            "Thank you for considering my application, and I look forward to the opportunity to discuss how my background aligns with your vision."
        )
        good_letter = {
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "body_paragraphs": [good_p1, good_p2, good_p3],
            "sign_off": "Sincerely,",
        }

        # Side effect sequence:
        # 1. On-demand keyword extraction call (if no checkpoint)
        # 2. Initial cover letter generation attempt (returns bad_letter)
        # 3. Validation retry fix call (returns good_letter)
        keywords_resp = json.dumps(
            {"hard_skills": ["content strategy"], "domain_keywords": ["CRM"]}
        )
        mock_gen.side_effect = [
            (
                keywords_resp,
                MagicMock(prompt_token_count=50, candidates_token_count=50),
            ),
            (
                json.dumps(bad_letter),
                MagicMock(prompt_token_count=100, candidates_token_count=100),
            ),
            (
                json.dumps(good_letter),
                MagicMock(prompt_token_count=100, candidates_token_count=100),
            ),
        ]

        result = self.engine.build_tailored_coverletter(self.jd_path)
        self.assertTrue(result)
        # Verify that Gemini generate was called 3 times (keywords + initial attempt + retry)
        self.assertEqual(mock_gen.call_count, 3)
        retry_contents = mock_gen.call_args_list[2][1]["contents"]
        self.assertIn("=== ISSUES TO FIX", retry_contents)
        self.assertTrue(
            "monotonous" in retry_contents.lower()
            or "std dev" in retry_contents.lower()
            or "sentence rhythm" in retry_contents.lower()
        )


if __name__ == "__main__":
    unittest.main()
