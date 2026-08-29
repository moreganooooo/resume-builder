import contextlib
import io
import json
import os
import re
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jd_manager  # noqa: E402
import orchestrator  # noqa: E402

# Captured before any test's setUp() patches orchestrator.os.path.exists (B17
# tests below) -- os.path is one shared module process-wide, so a patch on
# "orchestrator.os.path.exists" replaces this same name everywhere, and a
# reference taken after that point would be the mock, not the real function.
_REAL_OS_PATH_EXISTS = os.path.exists


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


class TestBuildCheckpointResume(unittest.TestCase):

    def setUp(self):
        # ResumeEngine() resolves the ACTIVE profile, so this whole class
        # required one to already exist -- 23 errors on a checkout that has
        # not been bootstrapped yet, which is exactly the state a new user
        # is in when `resume doctor` runs the suite for them. A persona
        # sandbox supplies a complete profile of its own.
        import persona

        self._sandbox = persona.sandbox_profile()
        self._sandbox.__enter__()
        self.addCleanup(self._sandbox.__exit__, None, None, None)

        # These fixtures build a synthetic 1-company resume against the
        # profile, whose roster declares several. B60's roster check is
        # correct to reject that, but it isn't what any test in this class
        # is about -- _check_role_roster has its own coverage in
        # test_validate_resume.py.
        self._roster_patch = patch(
            "orchestrator._required_role_roster", return_value=[]
        )
        self._roster_patch.start()
        self.addCleanup(self._roster_patch.stop)

        # _parse_pdf_result now reads the page count from a real PDF via
        # pypdf (B38) instead of regexing subprocess.run's stdout -- these
        # tests fake the PDF-generation subprocess and never write a real
        # file, so restore the old stdout-regex behavior here rather than
        # rewriting every test to fabricate a PDF pypdf can open.
        def _regex_parse_pdf_result(stdout, pdf_path=None):
            m = re.search(r"Pages:\s*(\d+)", stdout)
            page_count = int(m.group(1)) if m else None
            sm = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
            size_str = sm.group(1) if sm else "unknown size"
            return page_count, size_str

        self._parse_pdf_patch = patch(
            "orchestrator._parse_pdf_result", side_effect=_regex_parse_pdf_result
        )
        self._parse_pdf_patch.start()
        self.addCleanup(self._parse_pdf_patch.stop)

        # B17: validate_pdf_text() now returns (fatal, advisories), and a
        # non-empty `fatal` (e.g. the real function's own "file not found"
        # from a fake PDF path) makes build_tailored_resume() fail the build.
        # Same reason as the _parse_pdf_result patch above -- these tests
        # fake the PDF-generation subprocess and never write a real file, so
        # report the text-layer check clean rather than fabricating PDFs.
        self._validate_pdf_text_patch = patch(
            "orchestrator.validate_pdf_text.validate_pdf_text", return_value=([], [])
        )
        self._validate_pdf_text_patch.start()
        self.addCleanup(self._validate_pdf_text_patch.stop)

        # B17 also gates the success path on os.path.exists(pdf_out), for
        # the same "no real file was written" reason -- delegate everything
        # else to the real filesystem so unrelated exists() checks (KB
        # files, checkpoints) still behave normally.
        real_exists = os.path.exists

        def _fake_exists(path):
            if str(path).endswith(".pdf"):
                return True
            return real_exists(path)

        self._pdf_exists_patch = patch(
            "orchestrator.os.path.exists", side_effect=_fake_exists
        )
        self._pdf_exists_patch.start()
        self.addCleanup(self._pdf_exists_patch.stop)

        # research_company() gained a third tier (2026-08-11) that falls back
        # to the JD's own text, so it now always makes a CompanyResearchSchema
        # extraction call -- where before, a fixture with no company_website
        # bailed out before any call. Every generate_side_effect below
        # dispatches on response_schema and raises on an unexpected one, and
        # none of these tests are about company research (it has its own
        # coverage in test_orchestrator_research_company.py). Stub it to the
        # None these fixtures effectively produced already.
        self._research_patch = patch.object(
            orchestrator.ResumeEngine, "research_company", return_value=None
        )
        self._research_patch.start()
        self.addCleanup(self._research_patch.stop)

        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_for_build.txt")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            f.write("We are hiring a Widget Engineer.")
        self.job_key = "test-build-checkpoint-job"
        self.output_filename = "TESTONLY_build_checkpoint_resume.json"
        self.output_path = os.path.join(
            self.engine.output_json_dir, self.output_filename
        )

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
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

        stdout_buf = io.StringIO()
        with (
            patch.object(self.engine, "mine_bullet_bank") as mock_mine,
            contextlib.redirect_stdout(stdout_buf),
        ):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )
            mock_mine.assert_not_called()

        self.assertTrue(result)
        self.assertIn("_output_paths", result)
        # B17 non-regression: a genuinely successful build must still print
        # the success message and carry a real pdf path in _output_paths.
        self.assertIn("Pipeline complete!", stdout_buf.getvalue())
        self.assertTrue(result["_output_paths"]["pdf"])
        # jd_keywords/bullet_tuples were cached, so GeminiClient.generate should
        # only have been called for: 1 bullet critique + 1 builder call + 1 resume critique.
        self.assertEqual(mock_generate.call_count, 3)
        # Full success deletes the checkpoint.
        self.assertEqual(jd_manager.load_checkpoint(self.job_key), {})

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_builder_call_tags_each_bullet_with_its_company(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # A flat, untagged bullet list gave the builder no way to know which
        # company each bullet belonged to, and was a likely contributor to it
        # giving up and emitting empty Experience entries. The builder's
        # combined_contents must carry a "[Company]" tag per bullet.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        captured_contents = {}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                captured_contents["combined_contents"] = kwargs.get("contents")
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(self.engine, "mine_bullet_bank"):
            self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertIn(
            "[Acme] Shipped a widget platform used by 10k users.",
            captured_contents["combined_contents"],
        )

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_verb_duplication_fix_attempt_sees_every_verb_already_in_use(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # A fix prompt naming only the 2 colliding bullets per violation risks
        # whack-a-mole: a replacement verb picked to fix one pair can collide
        # with some other, unflagged bullet, since uniqueness is a whole-CV
        # constraint. The fix call must see every verb already in use.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        template_call_count = {"n": 0}
        captured_fix_contents = {}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                template_call_count["n"] += 1
                if template_call_count["n"] == 1:
                    return (
                        json.dumps(
                            {
                                "SUMMARY": "Test summary.",
                                "EXPERIENCE": [
                                    {
                                        "title": "Engineer",
                                        "company": "Acme",
                                        "period": "2020 - 2021",
                                        "achievements": [
                                            "Managed a team of 5 engineers across two products",
                                            "Managed the migration to a new billing platform",
                                        ],
                                    }
                                ],
                            }
                        ),
                        {},
                    )
                captured_fix_contents["contents"] = kwargs.get("contents")
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch.object(self.engine, "mine_bullet_bank"),
            patch(
                "orchestrator.auto_fix_duplicate_opening_verbs",
                side_effect=lambda data, rules: (data, False),
            ),
        ):
            self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertIn(
            "ALL OPENING VERBS CURRENTLY USED", captured_fix_contents["contents"]
        )
        self.assertIn("managed", captured_fix_contents["contents"].lower())

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_skills_widow_fix_attempt_gets_reminded_of_all_three_fix_options(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # Repeated Skills-widow violations across retry attempts (seen in a
        # real run) suggest the model needs the fix options spelled out
        # again in the fix prompt, not just relying on tailor_resume.md's
        # rules buried earlier in a huge system prompt.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        template_call_count = {"n": 0}
        captured_fix_contents = {}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                template_call_count["n"] += 1
                if template_call_count["n"] == 1:
                    # Plain length 115 (5 chars past the 110-char limit) -- a
                    # short widow, not a clean wrap to a fuller 2nd line.
                    return (
                        json.dumps(
                            {
                                "SUMMARY": "Test summary.",
                                "SKILLS": ["**Cat:** " + "X" * 110],
                            }
                        ),
                        {},
                    )
                captured_fix_contents["contents"] = kwargs.get("contents")
                return (json.dumps({"SUMMARY": "Test summary.", "SKILLS": []}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch.object(self.engine, "mine_bullet_bank"),
            patch(
                "orchestrator.repair_violations_surgically",
                side_effect=lambda data, violations, *a, **kw: (data, violations),
            ),
        ):
            self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertIn("FIXING A SKILLS LINE WIDOW", captured_fix_contents["contents"])
        self.assertIn(
            "summaries-and-skills-clean.csv", captured_fix_contents["contents"]
        )

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_fix_loop_survives_one_unparseable_attempt_and_still_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # A transient failure (e.g. GeminiClient.generate() exhausting its own
        # inner retries/fallback and returning None) on one outer fix attempt
        # must not burn the whole loop when attempts remain -- previously this
        # `break`-ed out immediately, wasting any remaining max_fix_attempts.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        bad_resume = {
            "SUMMARY_TEXT": "<strong>A results-driven lifecycle marketer.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        good_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        template_call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                template_call_count["n"] += 1
                if template_call_count["n"] == 1:
                    return (
                        json.dumps(bad_resume),
                        {},
                    )  # initial build, has a violation
                if template_call_count["n"] == 2:
                    return (None, {})  # fix attempt 1/3: total failure, unparseable
                return (json.dumps(good_resume), {})  # fix attempt 2/3: resolves it
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        self.assertEqual(template_call_count["n"], 3)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_pdf_failure_leaves_checkpoint_and_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="node crashed"
        )

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
    def test_pdf_timeout_leaves_checkpoint_and_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # B21 "same class" fix: a hung Chromium/font-load used to block this
        # call forever (no timeout=). Confirms a timeout is now caught and
        # handled the same way a nonzero returncode already is, rather than
        # propagating as an uncaught exception.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd="node", timeout=180
        )

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

    def test_pdf_text_layer_fatal_is_not_reported_as_pipeline_success(self):
        # B17: reproduces the real captured bug -- the PDF text-layer check
        # can't parse the rendered file ("Could not parse generated PDF ...
        # No such file or directory") yet the pipeline used to print
        # "Pipeline complete!" and hand back a usable result anyway, which
        # then let run_pipeline() move the JD to completed/ and record a
        # tracker row for a resume that was never written. A fatal finding
        # from validate_pdf_text() must now fail the build outright instead.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        fatal_message = "Could not parse generated PDF for verification: [Errno 2] No such file or directory"

        stdout_buf = io.StringIO()
        with (
            patch(
                "orchestrator.GeminiClient.generate", side_effect=generate_side_effect
            ),
            patch("orchestrator.render_html"),
            patch("orchestrator.time.sleep", lambda *a, **kw: None),
            patch(
                "orchestrator.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="▤ Pages: 2\n", stderr=""),
            ),
            patch(
                "orchestrator.validate_pdf_text.validate_pdf_text",
                return_value=([fatal_message], []),
            ),
            patch.object(self.engine, "mine_bullet_bank"),
            contextlib.redirect_stdout(stdout_buf),
        ):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result, {})
        self.assertNotIn("Pipeline complete!", stdout_buf.getvalue())
        self.assertIn(fatal_message, stdout_buf.getvalue())

    def test_pdf_missing_on_disk_is_not_reported_as_pipeline_success(self):
        # B17's second, independent gate: even when the text-layer check
        # itself reports clean, the success print and _output_paths
        # assignment must still be gated on os.path.exists(pdf_out) --
        # belt-and-suspenders on top of the fatal-signal test above, for a
        # PDF that vanishes (or was never written) without validate_pdf_text
        # noticing.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        def _fake_exists_missing_pdf(path):
            if str(path).endswith(".pdf"):
                return False
            return _REAL_OS_PATH_EXISTS(path)

        stdout_buf = io.StringIO()
        with (
            patch(
                "orchestrator.GeminiClient.generate", side_effect=generate_side_effect
            ),
            patch("orchestrator.render_html"),
            patch("orchestrator.time.sleep", lambda *a, **kw: None),
            patch(
                "orchestrator.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="▤ Pages: 2\n", stderr=""),
            ),
            patch(
                "orchestrator.validate_pdf_text.validate_pdf_text",
                return_value=([], []),
            ),
            patch("orchestrator.os.path.exists", side_effect=_fake_exists_missing_pdf),
            patch.object(self.engine, "mine_bullet_bank"),
            contextlib.redirect_stdout(stdout_buf),
        ):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result, {})
        self.assertNotIn("Pipeline complete!", stdout_buf.getvalue())

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_captures_page_count_from_pdf_stdout(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pdf_call_count["n"] += 1
            pages = 3 if pdf_call_count["n"] == 1 else 2
            return MagicMock(
                returncode=0,
                stdout=f"▥ Input:  x\n◰ Output: y\n⊢ Format: LETTER\n✓ PDF generated: y\n▤ Pages: {pages}\n▣ Size: 42.0 KB\n",
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
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        seen_critique_system_instructions = []

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                seen_critique_system_instructions.append(
                    kwargs.get("system_instruction", "")
                )
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 85,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

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
        self.assertIn(
            "buzzword_openers", system_instruction
        )  # from summary_score.yaml (unique identifier)
        self.assertIn(
            "hidden_gem_rules", system_instruction
        )  # from top_third_score.yaml (unique identifier)

    @patch("orchestrator.validate_resume.validate")
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_validator_retry_fixes_a_violation_then_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run, mock_validate
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        builder_call_count = {"n": 0}
        validation_call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                builder_call_count["n"] += 1
                if builder_call_count["n"] == 1:
                    return (
                        json.dumps(
                            {
                                "SUMMARY_TEXT": "<strong>A results-driven marketer.</strong>",
                                "SKILLS": [],
                                "EXPERIENCE": [],
                                "WHY_TEXT": "",
                                "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
                                "EDU_ACHIEVEMENT_KEY_2": "writing_content",
                            }
                        ),
                        {},
                    )
                return (
                    json.dumps(
                        {
                            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
                            "SKILLS": [],
                            "EXPERIENCE": [],
                            "WHY_TEXT": "",
                            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
                            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
                        }
                    ),
                    {},
                )
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        def validate_side_effect(
            resume_data, rules, role_roster=None, role_bullet_minimums=None, **kwargs
        ):
            validation_call_count["n"] += 1
            # First validation call: return a violation
            if validation_call_count["n"] == 1:
                return ["SUMMARY_TEXT contains forbidden keyword: 'results-driven'"]
            # After the fix: no violations
            return []

        mock_generate.side_effect = generate_side_effect
        mock_validate.side_effect = validate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

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
    def test_a_regressing_attempt_does_not_discard_the_best_resume_so_far(
        self, mock_generate, mock_render_html, mock_subprocess_run, mock_validate
    ):
        # Each retry re-generates the WHOLE resume, so an attempt can regress
        # anything despite "change nothing else" -- observed live, an attempt
        # 2 violations from clean was replaced by one with 11. The loop must
        # anchor on the best state reached, not the most recent one.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        builder_calls = {"n": 0}

        def _resume(marker):
            return (
                json.dumps(
                    {
                        "SUMMARY_TEXT": f"<strong>{marker}</strong>",
                        "SKILLS": [],
                        "EXPERIENCE": [],
                        "WHY_TEXT": "",
                        "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
                        "EDU_ACHIEVEMENT_KEY_2": "writing_content",
                    }
                ),
                {},
            )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            if schema is orchestrator.TemplateSchema:
                builder_calls["n"] += 1
                return _resume(
                    ["initial", "NEARLY CLEAN", "regressed"][
                        min(builder_calls["n"] - 1, 2)
                    ]
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        # 3 violations initially, 1 after the good attempt, 9 after the bad one.
        counts = iter([3, 1, 9, 9, 9, 9])

        def validate_side_effect(
            resume_data, rules, role_roster=None, role_bullet_minimums=None, **kwargs
        ):
            return [f"v{i}" for i in range(next(counts))]

        mock_generate.side_effect = generate_side_effect
        mock_validate.side_effect = validate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        # Builder calls: 1 initial, then one per retry. Call 3 produces the
        # regression, so call 4 is the first prompt that can differ: it must
        # be handed the 1-violation resume to fix, not the 9-violation one.
        builder_prompts = [
            c.kwargs["contents"]
            for c in mock_generate.call_args_list
            if c.kwargs.get("response_schema") is orchestrator.TemplateSchema
        ]
        self.assertGreaterEqual(len(builder_prompts), 4)
        self.assertIn("NEARLY CLEAN", builder_prompts[3])
        self.assertNotIn("regressed", builder_prompts[3])

    @patch("orchestrator.validate_resume.validate")
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_validator_retry_exhaustion_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run, mock_validate
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        always_bad = {
            "SUMMARY_TEXT": "<strong>A results-driven marketer.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(always_bad), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        def validate_side_effect(
            resume_data, rules, role_roster=None, role_bullet_minimums=None, **kwargs
        ):
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
    def test_trim_loop_survives_one_unparseable_attempt_and_still_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        # Same class of bug as the fix-loop test above, but trim_attempt is
        # incremented in a different spot in this loop (after the API call,
        # not before) -- the unparseable-JSON branch has to bump it manually
        # before continuing, or the loop would spin on the same index forever.
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        good_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        template_call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                template_call_count["n"] += 1
                if template_call_count["n"] == 1:
                    return (json.dumps(good_resume), {})  # initial build
                if template_call_count["n"] == 2:
                    return (None, {})  # trim attempt 1: total failure, unparseable
                return (json.dumps(good_resume), {})  # trim attempt 2: succeeds
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        # HTML is only re-rendered after a *successful* trim, so the unparseable
        # attempt's re-check of the same (unchanged) HTML still reports 3 pages.
        page_counts = [3, 3, 2]
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pages = page_counts[pdf_call_count["n"]]
            pdf_call_count["n"] += 1
            return MagicMock(returncode=0, stdout=f"▤ Pages: {pages}\n", stderr="")

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
        self.assertEqual(pdf_call_count["n"], 3)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_page_count_trim_loop_retries_then_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        good_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(good_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pdf_call_count["n"] += 1
            pages = 3 if pdf_call_count["n"] == 1 else 2
            return MagicMock(returncode=0, stdout=f"▤ Pages: {pages}\n", stderr="")

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
        self.assertEqual(
            pdf_call_count["n"], 2
        )  # 1 over-length render + 1 trimmed re-render

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_why_drop_is_deterministic_and_cannot_be_discarded_by_a_violation(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        """Regression test: the Why-drop trim step used to go through the
        LLM, so a violation anywhere in that response (even one unrelated to
        Why) discarded the whole attempt and Why stuck around forever (see
        the resume-builder memory note on the trim loop never converging).
        Blanking SECTION_WHY/WHY_TEXT is now a deterministic pre-step, so it
        never needs a Gemini call and can't be discarded by the validator."""
        seeded_resume_data = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "SECTION_WHY": "Why Acme?",
            "WHY_TEXT": "Because reasons.",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
                "resume_data": seeded_resume_data,
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(
                f"Unexpected response_schema in test: {schema} -- the Why-drop "
                "step must never call the builder LLM"
            )

        mock_generate.side_effect = generate_side_effect
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pdf_call_count["n"] += 1
            pages = 3 if pdf_call_count["n"] == 1 else 2
            return MagicMock(returncode=0, stdout=f"▤ Pages: {pages}\n", stderr="")

        mock_subprocess_run.side_effect = subprocess_side_effect

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        self.assertEqual(result["SECTION_WHY"], "")
        self.assertEqual(result["WHY_TEXT"], "")
        self.assertEqual(
            pdf_call_count["n"], 2
        )  # 1 over-length render + 1 Why-dropped re-render

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_page_count_trim_loop_exhausts_and_returns_empty(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        """Every trim attempt still comes back over-length -- the loop must
        cap out at max_trim_attempts and return {} rather than an exception
        or partial/invalid resume."""
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        always_long_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                # Both the initial build and every trim attempt return
                # parseable JSON that never actually shrinks the page count.
                return (json.dumps(always_long_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        # Every render reports 3 pages, no matter how many trim attempts run.
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 3\n", stderr=""
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertFalse(result)
        self.assertEqual(result, {})
        # 1 initial render + 3 LLM trim attempts (max_trim_attempts == len(trim_instructions) == 3).
        # The free Why-drop pre-step doesn't cost a render here since WHY_TEXT
        # is already blank in always_long_resume, so it's skipped without a
        # PDF re-check.
        self.assertEqual(mock_subprocess_run.call_count, 4)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_trim_loop_after_checkpoint_resumed_resume_data_does_not_raise(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        """Regression test for Bug 1: when Step 4 resumes resume_data from a
        checkpoint (the `if resume_data is not None:` branch), the old code
        never assigned build_prompt, since that assignment lived only in the
        fresh-build `else:` branch. Step 7's trim loop references build_prompt
        unconditionally, so an over-length PDF on a checkpoint-resumed run
        used to raise UnboundLocalError instead of returning {} per contract.
        """
        seeded_resume_data = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
                "resume_data": seeded_resume_data,
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                # Trim attempts: keep returning parseable but still over-length JSON.
                return (json.dumps(seeded_resume_data), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        # Always over-length -- forces the trim loop to run to exhaustion.
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 3\n", stderr=""
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            try:
                result = self.engine.build_tailored_resume(
                    jd_path=self.jd_path,
                    master_resume={},
                    output_filename=self.output_filename,
                    job_key=self.job_key,
                )
            except UnboundLocalError as e:
                self.fail(
                    f"build_tailored_resume raised UnboundLocalError (Bug 1 regression): {e}"
                )

        # Trim attempts exhausted (page count never drops below 3), so the
        # contract is to return {} gracefully -- not raise, not return partial data.
        self.assertEqual(result, {})
        self.assertEqual(
            mock_subprocess_run.call_count, 4
        )  # 1 initial + 3 LLM trim attempts

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_recommendation_pass_applies_actionable_and_skips_the_rest(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        base_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }

        rec_call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.RecommendationApplySchema:
                # B40 regression guard: without extra_schema_properties/
                # extra_required merged in here, a real Gemini call would
                # drop EDU_ACHIEVEMENT_KEY_<n> from its response entirely
                # (not in the schema), so normalize_resume.py would default
                # both to "" and fixed_content.build_education() would
                # silently revert to each school's first option -- see
                # phase-9-backlog.md's B40.
                self.assertIn(
                    "EDU_ACHIEVEMENT_KEY_1", kwargs.get("extra_schema_properties") or {}
                )
                self.assertIn(
                    "EDU_ACHIEVEMENT_KEY_1", kwargs.get("extra_required") or []
                )
                rec_call_count["n"] += 1
                if rec_call_count["n"] == 1:
                    # First recommendation: a concrete resume edit -- applied.
                    return (
                        json.dumps(
                            {
                                **base_resume,
                                "SUMMARY_TEXT": "<strong>A lifecycle marketer skilled in ChatGPT and Claude.</strong>",
                                "applied_recommendations": [
                                    "Name the specific AI tools used."
                                ],
                                "skipped_recommendations": [],
                            }
                        ),
                        {},
                    )
                # Second recommendation: networking advice, not a resume edit -- skipped.
                return (
                    json.dumps(
                        {
                            **base_resume,
                            "SUMMARY_TEXT": "<strong>A lifecycle marketer skilled in ChatGPT and Claude.</strong>",
                            "applied_recommendations": [],
                            "skipped_recommendations": [
                                "Reach out to the KU alumni contact for a referral."
                            ],
                        }
                    ),
                    {},
                )
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(base_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [
                                "Name the specific AI tools used.",
                                "Reach out to the KU alumni contact for a referral.",
                            ],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

        # Sandboxed: the EDU_ACHIEVEMENT_KEY_<n> schema fields asserted in
        # generate_side_effect are derived from the ACTIVE profile's
        # fixed_credentials.education, so on a freshly bootstrapped profile
        # there are none and the B40 guard above silently checks nothing.
        import persona

        with persona.sandbox_profile(), patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(
            rec_call_count["n"], 2, "each recommendation must get its own call"
        )
        self.assertIn("ChatGPT and Claude", result["SUMMARY_TEXT"])
        actions = result["_recommendation_actions"]
        self.assertEqual(actions["applied"], ["Name the specific AI tools used."])
        self.assertEqual(
            actions["skipped"], ["Reach out to the KU alumni contact for a referral."]
        )

    @patch("orchestrator.validate_resume.validate")
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_recommendation_pass_discards_result_that_introduces_a_violation(
        self, mock_generate, mock_render_html, mock_subprocess_run, mock_validate
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        base_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.RecommendationApplySchema:
                return (
                    json.dumps(
                        {
                            **base_resume,
                            "SUMMARY_TEXT": "<strong>Broke something.</strong>",
                            "applied_recommendations": [
                                "Name the specific AI tools used."
                            ],
                            "skipped_recommendations": [],
                        }
                    ),
                    {},
                )
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(base_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": ["Name the specific AI tools used."],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )
        # Step 4's own initial validation call must stay clean (call 1); the
        # recommendation pass's candidate (call 2) is the one that must fail.
        mock_validate.side_effect = [[], ["FAKE VIOLATION FOR TEST"]]

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(
            result["SUMMARY_TEXT"],
            base_resume["SUMMARY_TEXT"],
            "must discard the violating rewrite",
        )
        actions = result["_recommendation_actions"]
        self.assertEqual(actions["applied"], [])
        self.assertEqual(len(actions["skipped"]), 1)
        self.assertIn("introduced a validator violation", actions["skipped"][0])

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_needs_personal_input_lands_in_needs_polish_bucket(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        base_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.RecommendationApplySchema:
                return (
                    json.dumps(
                        {
                            **base_resume,
                            "applied_recommendations": [],
                            "skipped_recommendations": [],
                            "needs_personal_input": [
                                "What made this project personally satisfying to you?"
                            ],
                        }
                    ),
                    {},
                )
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(base_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": [
                                "What made this project personally satisfying to you?"
                            ],
                            "distinctive_moments": [],
                            "flat_sections": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        actions = result["_recommendation_actions"]
        self.assertEqual(
            actions["needs_polish"],
            ["What made this project personally satisfying to you?"],
        )
        self.assertEqual(actions["applied"], [])
        self.assertEqual(actions["skipped"], [])
        self.assertEqual(
            result["SUMMARY_TEXT"],
            base_resume["SUMMARY_TEXT"],
            "unchanged -- nothing was fabricated",
        )

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_distinctive_moments_are_injected_into_recommendation_prompt(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
            },
        )
        base_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        captured_contents = {}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.RecommendationApplySchema:
                captured_contents["value"] = kwargs.get("contents", "")
                return (
                    json.dumps(
                        {
                            **base_resume,
                            "applied_recommendations": [
                                "Name the specific AI tools used."
                            ],
                            "skipped_recommendations": [],
                            "needs_personal_input": [],
                        }
                    ),
                    {},
                )
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(base_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (
                    json.dumps(
                        {
                            "summary_alignment_score": 90,
                            "skills_relevance_score": 90,
                            "overall_fit_score": 90,
                            "top_third_score": 90,
                            "flags": [],
                            "recommendations": ["Name the specific AI tools used."],
                            "distinctive_moments": [
                                "I love building systems that work quietly in the background."
                            ],
                            "flat_sections": [],
                        }
                    ),
                    {},
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(self.engine, "mine_bullet_bank"):
            self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertIn("PROTECTED DISTINCTIVE MOMENTS", captured_contents["value"])
        self.assertIn(
            "I love building systems that work quietly in the background.",
            captured_contents["value"],
        )

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_recommendation_pass_resumes_from_checkpoint_without_a_new_api_call(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        base_resume = {
            "SUMMARY_TEXT": "<strong>Already applied.</strong>",
            "SKILLS": [],
            "EXPERIENCE": [],
            "WHY_TEXT": "",
            "EDU_ACHIEVEMENT_KEY_1": "content_generalist",
            "EDU_ACHIEVEMENT_KEY_2": "writing_content",
        }
        jd_manager.save_checkpoint(
            self.job_key,
            {
                "jd_keywords": {"hard_skills": ["python"]},
                "bullet_tuples": [
                    ["Shipped a widget platform used by 10k users.", "Acme", "eng"]
                ],
                "refined_bullets": ["Shipped a widget platform used by 10k users."],
                "resume_data": base_resume,
                "critique_data": {
                    "summary_alignment_score": 90,
                    "skills_relevance_score": 90,
                    "overall_fit_score": 90,
                    "recommendations": ["Name the specific AI tools used."],
                },
                "recommendation_actions": {
                    "resume_data": dict(base_resume),
                    "applied": ["Name the specific AI tools used."],
                    "skipped": [],
                    "next_index": 1,
                },
            },
        )

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.RecommendationApplySchema:
                raise AssertionError(
                    "must not re-call the API when resuming from checkpoint"
                )
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="▤ Pages: 2\n", stderr=""
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(
            result["_recommendation_actions"]["applied"],
            ["Name the specific AI tools used."],
        )
        mock_generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
