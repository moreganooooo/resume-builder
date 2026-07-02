import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import jd_manager  # noqa: E402


def _pass_critique_json():
    return json.dumps({
        "manager_test": "PASS",
        "believability_score": 95,
        "hidden_gem_score": 10,
        "hidden_gem_flag": False,
        "hidden_gem_reason": "",
        "weaknesses": "",
    })


class TestBuildCheckpointResume(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_for_build.txt")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            f.write("We are hiring a Widget Engineer.")
        self.job_key = "test-build-checkpoint-job"
        self.output_filename = "TESTONLY_build_checkpoint_resume.json"
        self.output_path = os.path.join(self.engine.output_json_dir, self.output_filename)

    def tearDown(self):
        if os.path.exists(self.jd_path):
            os.remove(self.jd_path)
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        jd_manager.delete_checkpoint(self.job_key)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_skips_keyword_extraction_and_mining_when_checkpointed(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # Pre-seed a checkpoint as if steps 1 and 2 already ran.
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90,
                    "skills_relevance_score": 90,
                    "overall_fit_score": 90,
                    "flags": [],
                    "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(self.engine, "mine_bullet_bank") as mock_mine:
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )
            mock_mine.assert_not_called()

        self.assertTrue(result)
        self.assertIn("_output_paths", result)
        # jd_keywords/bullet_tuples were cached, so GeminiClient.generate should
        # only have been called for: 1 bullet critique + 1 builder call + 1 resume critique.
        self.assertEqual(mock_generate.call_count, 3)
        # Full success deletes the checkpoint.
        self.assertEqual(jd_manager.load_checkpoint(self.job_key), {})

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_pdf_failure_leaves_checkpoint_and_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="", stderr="node crashed")

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result, {})
        # Checkpoint must survive so the next run doesn't redo the API calls.
        self.assertNotEqual(jd_manager.load_checkpoint(self.job_key), {})

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_captures_page_count_from_pdf_stdout(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pdf_call_count["n"] += 1
            pages = 3 if pdf_call_count["n"] == 1 else 2
            return MagicMock(
                returncode=0,
                stdout=f"📄 Input:  x\n📁 Output: y\n📏 Format: LETTER\n✅ PDF generated: y\n📊 Pages: {pages}\n📦 Size: 42.0 KB\n",
                stderr="",
            )

        mock_subprocess_run.side_effect = subprocess_side_effect

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result.get("_page_count"), 2)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_critique_call_attaches_summary_and_top_third_scoring_yaml(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        seen_critique_system_instructions = []

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                seen_critique_system_instructions.append(kwargs.get("system_instruction", ""))
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "top_third_score": 85,
                    "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result["_critique"]["top_third_score"], 85)
        self.assertEqual(len(seen_critique_system_instructions), 1)
        system_instruction = seen_critique_system_instructions[0]
        self.assertIn("buzzword_openers", system_instruction)     # from summary_score.yaml (unique identifier)
        self.assertIn("hidden_gem_rules", system_instruction)     # from top_third_score.yaml (unique identifier)

    @patch("orchestrator.validate_resume.validate")
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_validator_retry_fixes_a_violation_then_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run, mock_validate
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        builder_call_count = {"n": 0}
        validation_call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                builder_call_count["n"] += 1
                if builder_call_count["n"] == 1:
                    return (json.dumps({
                        "SUMMARY_TEXT": "<strong>A results-driven marketer.</strong>",
                        "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
                        "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
                    }), {})
                return (json.dumps({
                    "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
                    "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
                    "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
                }), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "top_third_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        def validate_side_effect(resume_data, rules):
            validation_call_count["n"] += 1
            # First validation call: return a violation
            if validation_call_count["n"] == 1:
                return ["SUMMARY_TEXT contains forbidden keyword: 'results-driven'"]
            # After the fix: no violations
            return []

        mock_generate.side_effect = generate_side_effect
        mock_validate.side_effect = validate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        self.assertNotIn("results-driven", result["SUMMARY_TEXT"])
        self.assertEqual(builder_call_count["n"], 2)  # 1 initial + 1 targeted fix

    @patch("orchestrator.validate_resume.validate")
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_validator_retry_exhaustion_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run, mock_validate
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        always_bad = {
            "SUMMARY_TEXT": "<strong>A results-driven marketer.</strong>",
            "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
            "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(always_bad), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        def validate_side_effect(resume_data, rules):
            # Always return a violation
            return ["SUMMARY_TEXT contains forbidden keyword: 'results-driven'"]

        mock_generate.side_effect = generate_side_effect
        mock_validate.side_effect = validate_side_effect

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result, {})
        mock_subprocess_run.assert_not_called()  # never reached PDF generation

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_page_count_trim_loop_retries_then_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        good_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
            "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(good_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "top_third_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pdf_call_count["n"] += 1
            pages = 3 if pdf_call_count["n"] == 1 else 2
            return MagicMock(returncode=0, stdout=f"📊 Pages: {pages}\n", stderr="")

        mock_subprocess_run.side_effect = subprocess_side_effect

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        self.assertEqual(result["_page_count"], 2)
        self.assertEqual(pdf_call_count["n"], 2)  # 1 over-length render + 1 trimmed re-render


if __name__ == "__main__":
    unittest.main()
