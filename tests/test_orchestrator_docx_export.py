import contextlib
import io
import json
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import orchestrator  # noqa: E402


class TestCoverLetterDocxExport(unittest.TestCase):
    """Group C: build_tailored_coverletter() must call
    render_coverletter_docx() after its PDF subprocess succeeds, and a
    DOCX-generation failure must block the build the same way a PDF
    failure does."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_coverletter_docx_export.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({
                "job_title": "Content Strategist",
                "company_name": "Acme Corp",
                "description": "We are hiring a Content Strategist.",
            }, f)

        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.json_out = os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json")
        self.html_out = os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html")

    def tearDown(self):
        for path in (self.jd_path, self.json_out, self.html_out):
            if os.path.exists(path):
                os.remove(path)

    def _clean_letter_json(self):
        return json.dumps({
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "contact_name": "",
            "contact_title": "",
            "body_paragraphs": [
                "I'm excited to apply for this role at Acme Corp.",
                "My background lines up well with what you need.",
            ],
            "sign_off": "Sincerely,",
        })

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.render_coverletter_docx")
    def test_docx_is_rendered_after_pdf_succeeds(self, mock_render_docx, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            result = self.engine.build_tailored_coverletter(self.jd_path)

        self.assertTrue(result)
        mock_render_docx.assert_called_once()
        called_data, called_path = mock_render_docx.call_args[0]
        self.assertTrue(called_path.endswith(".docx"))
        self.assertIn(os.path.join(orchestrator.profile_paths.output_dir(), "docx"), called_path)
        self.assertEqual(called_data.get("company_name"), "Acme Corp")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.render_coverletter_docx", side_effect=Exception("docx boom"))
    def test_docx_failure_blocks_the_build_like_a_pdf_failure_does(
        self, mock_render_docx, mock_generate, mock_research
    ):
        mock_generate.return_value = (self._clean_letter_json(), {})
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            result = self.engine.build_tailored_coverletter(self.jd_path)

        self.assertEqual(result, {})


def _pass_critique_json():
    return json.dumps({
        "manager_test": "PASS",
        "believability_score": 95,
        "hidden_gem_score": 10,
        "hidden_gem_flag": False,
        "hidden_gem_reason": "",
        "weaknesses": "",
    })


class TestResumeDocxExport(unittest.TestCase):
    """Group C: build_tailored_resume() must call render_resume_docx() with
    the FINAL (post-trim-loop) resume_data, after the PDF text-layer check
    passes -- not from inside the trim-retry loop, where resume_data is
    still mutating. A DOCX-generation failure must block the build the same
    way a PDF failure does."""

    def setUp(self):
        self._roster_patch = patch("orchestrator._required_role_roster", return_value=[])
        self._roster_patch.start()
        self.addCleanup(self._roster_patch.stop)

        def _regex_parse_pdf_result(stdout, pdf_path=None):
            m = re.search(r"Pages:\s*(\d+)", stdout)
            page_count = int(m.group(1)) if m else None
            sm = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
            size_str = sm.group(1) if sm else "unknown size"
            return page_count, size_str

        self._parse_pdf_patch = patch("orchestrator._parse_pdf_result", side_effect=_regex_parse_pdf_result)
        self._parse_pdf_patch.start()
        self.addCleanup(self._parse_pdf_patch.stop)

        self._validate_pdf_text_patch = patch(
            "orchestrator.validate_pdf_text.validate_pdf_text", return_value=([], [])
        )
        self._validate_pdf_text_patch.start()
        self.addCleanup(self._validate_pdf_text_patch.stop)

        real_exists = os.path.exists

        def _fake_exists(path):
            if str(path).endswith(".pdf"):
                return True
            return real_exists(path)

        self._pdf_exists_patch = patch("orchestrator.os.path.exists", side_effect=_fake_exists)
        self._pdf_exists_patch.start()
        self.addCleanup(self._pdf_exists_patch.stop)

        self._research_patch = patch.object(
            orchestrator.ResumeEngine, "research_company", return_value=None
        )
        self._research_patch.start()
        self.addCleanup(self._research_patch.stop)

        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_for_docx_export.txt")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            f.write("We are hiring a Widget Engineer.")
        self.job_key = "test-docx-export-job"
        self.output_filename = "TESTONLY_docx_export_resume.json"
        self.output_path = os.path.join(self.engine.output_json_dir, self.output_filename)

        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

    def tearDown(self):
        if os.path.exists(self.jd_path):
            os.remove(self.jd_path)
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        jd_manager.delete_checkpoint(self.job_key)

    def _generate_side_effect(self, *args, **kwargs):
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

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.render_resume_docx")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_docx_is_rendered_with_final_resume_data_after_a_successful_build(
        self, mock_generate, mock_render_docx, mock_render_html, mock_subprocess_run
    ):
        mock_generate.side_effect = self._generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        stdout_buf = io.StringIO()
        with patch.object(self.engine, "mine_bullet_bank"), \
                contextlib.redirect_stdout(stdout_buf):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        mock_render_docx.assert_called_once()
        called_data, called_path = mock_render_docx.call_args[0]
        self.assertTrue(called_path.endswith(".docx"))
        self.assertIn(os.path.join(orchestrator.profile_paths.output_dir(), "docx"), called_path)
        self.assertIsInstance(called_data, dict)
        self.assertEqual(mock_render_html.call_count, 1)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.render_resume_docx", side_effect=Exception("docx boom"))
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_docx_failure_blocks_the_build_like_a_pdf_failure_does(
        self, mock_generate, mock_render_docx, mock_render_html, mock_subprocess_run
    ):
        mock_generate.side_effect = self._generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        stdout_buf = io.StringIO()
        with patch.object(self.engine, "mine_bullet_bank"), \
                contextlib.redirect_stdout(stdout_buf):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
