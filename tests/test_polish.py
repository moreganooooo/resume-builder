import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import polish  # noqa: E402


class TestDetectDocType(unittest.TestCase):

    def test_resume_suffix(self):
        self.assertEqual(polish.detect_doc_type("output/json/Foo_Bar_Resume.json"), "resume")

    def test_coverletter_suffix(self):
        self.assertEqual(polish.detect_doc_type("output/json/Foo_Bar_CoverLetter.json"), "coverletter")

    def test_unrecognized_suffix_returns_none(self):
        self.assertIsNone(polish.detect_doc_type("output/json/Foo_Bar.json"))


class TestStemFromJsonPath(unittest.TestCase):

    def test_resume_stem(self):
        stem = polish.stem_from_json_path(
            "output/json/MorganEscott_Title_Company_Resume.json", "resume",
        )
        self.assertEqual(stem, "MorganEscott_Title_Company")

    def test_coverletter_stem(self):
        stem = polish.stem_from_json_path(
            "output/json/MorganEscott_Title_Company_CoverLetter.json", "coverletter",
        )
        self.assertEqual(stem, "MorganEscott_Title_Company")


class TestDiffDocuments(unittest.TestCase):

    def test_identical_documents_produce_no_diff(self):
        doc = {"TAGLINE": "SAME", "SKILLS": ["Python"]}
        self.assertEqual(polish.diff_documents(doc, dict(doc), ["TAGLINE", "SKILLS"]), [])

    def test_scalar_field_change_is_reported(self):
        old = {"TAGLINE": "OLD"}
        new = {"TAGLINE": "NEW"}
        lines = polish.diff_documents(old, new, ["TAGLINE"])
        self.assertEqual(len(lines), 1)
        self.assertIn("TAGLINE", lines[0])
        self.assertIn("OLD", lines[0])
        self.assertIn("NEW", lines[0])

    def test_field_outside_keys_is_never_reported(self):
        old = {"TAGLINE": "OLD", "NAME": "Morgan Escott"}
        new = {"TAGLINE": "OLD", "NAME": "Someone Else"}
        lines = polish.diff_documents(old, new, ["TAGLINE"])
        self.assertEqual(lines, [])

    def test_plain_list_field_reports_only_changed_indices(self):
        old = {"SKILLS": ["Python", "SQL", "Excel"]}
        new = {"SKILLS": ["Python", "Postgres", "Excel"]}
        lines = polish.diff_documents(old, new, ["SKILLS"])
        self.assertEqual(len(lines), 1)
        self.assertIn("SKILLS[1]", lines[0])
        self.assertIn("SQL", lines[0])
        self.assertIn("Postgres", lines[0])

    def test_experience_reports_changed_scalar_field_by_index(self):
        old = {"EXPERIENCE": [{"title": "Old Title", "achievements": ["A"]}]}
        new = {"EXPERIENCE": [{"title": "New Title", "achievements": ["A"]}]}
        lines = polish.diff_documents(old, new, ["EXPERIENCE"])
        self.assertEqual(len(lines), 1)
        self.assertIn("EXPERIENCE[0].title", lines[0])

    def test_experience_reports_changed_achievement_by_index(self):
        old = {"EXPERIENCE": [{"title": "Same", "achievements": ["A", "B"]}]}
        new = {"EXPERIENCE": [{"title": "Same", "achievements": ["A", "B changed"]}]}
        lines = polish.diff_documents(old, new, ["EXPERIENCE"])
        self.assertEqual(len(lines), 1)
        self.assertIn("EXPERIENCE[0].achievements[1]", lines[0])

    def test_unchanged_experience_job_produces_no_lines(self):
        old = {"EXPERIENCE": [{"title": "Same", "achievements": ["A"]}]}
        new = {"EXPERIENCE": [{"title": "Same", "achievements": ["A"]}]}
        self.assertEqual(polish.diff_documents(old, new, ["EXPERIENCE"]), [])


class TestGenerateCandidate(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    @patch("polish.GeminiClient.generate")
    def test_unparseable_response_returns_none(self, mock_generate):
        mock_generate.return_value = ("not valid json", {})
        result = polish.generate_candidate(
            {"TAGLINE": "OLD"}, "make it punchier", "resume", self.engine,
        )
        self.assertIsNone(result)

    @patch("polish.GeminiClient.generate")
    def test_resume_path_normalizes_and_reattaches_recommendation_actions(self, mock_generate):
        gemini_json = json.dumps({
            "TAGLINE": "new tagline",
            "SECTION_SUMMARY": "Professional Summary",
            "SUMMARY_TEXT": "<strong>Summary.</strong>",
            "SECTION_EXPERIENCE": "Work Experience",
            "EXPERIENCE": [],
            "KU_ACHIEVEMENT_KEY": "content_generalist",
            "KCKCC_ACHIEVEMENT_KEY": "generalist",
            "SECTION_SKILLS": "Skills",
            "SKILLS": ["Python"],
            "SECTION_WHY": "",
            "WHY_TEXT": "",
        })
        mock_generate.return_value = (gemini_json, {})

        original_doc = {
            "TAGLINE": "OLD TAGLINE",
            "_recommendation_actions": {"applied": ["x"], "skipped": []},
        }
        candidate = polish.generate_candidate(
            original_doc, "punch up the tagline", "resume", self.engine,
        )

        self.assertIsNotNone(candidate)
        # normalize_resume.normalize() upper-cases TAGLINE
        self.assertEqual(candidate["TAGLINE"], "NEW TAGLINE")
        # non-schema tracking key must survive the round trip unchanged
        self.assertEqual(candidate["_recommendation_actions"], {"applied": ["x"], "skipped": []})
        # normalize() injects fixed_content.CONTACT_INFO
        self.assertEqual(candidate["NAME"], "Morgan Escott")

    @patch("polish.GeminiClient.generate")
    def test_resume_path_with_no_recommendation_actions_does_not_add_one(self, mock_generate):
        gemini_json = json.dumps({
            "TAGLINE": "TAG", "SECTION_SUMMARY": "Professional Summary",
            "SUMMARY_TEXT": "s", "SECTION_EXPERIENCE": "Work Experience",
            "EXPERIENCE": [], "KU_ACHIEVEMENT_KEY": "content_generalist",
            "KCKCC_ACHIEVEMENT_KEY": "generalist", "SECTION_SKILLS": "Skills",
            "SKILLS": [], "SECTION_WHY": "", "WHY_TEXT": "",
        })
        mock_generate.return_value = (gemini_json, {})
        candidate = polish.generate_candidate({"TAGLINE": "TAG"}, "noop", "resume", self.engine)
        self.assertNotIn("_recommendation_actions", candidate)

    @patch("polish.GeminiClient.generate")
    def test_coverletter_path_does_not_run_resume_normalization(self, mock_generate):
        gemini_json = json.dumps({
            "company_name": "Acme",
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": ["Paragraph one.", "Paragraph two."],
            "sign_off": "Sincerely,",
        })
        mock_generate.return_value = (gemini_json, {})

        candidate = polish.generate_candidate(
            {"company_name": "Acme", "greeting": "Hi,", "body_paragraphs": [], "sign_off": ""},
            "make the greeting more formal", "coverletter", self.engine,
        )
        self.assertEqual(candidate["greeting"], "Dear Hiring Team,")
        self.assertNotIn("NAME", candidate)


class TestSaveAndRender(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_polish_save")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.resume_json_path = os.path.join(self.tmp_dir, "MorganEscott_Title_Company_Resume.json")
        self.coverletter_json_path = os.path.join(self.tmp_dir, "MorganEscott_Title_Company_CoverLetter.json")

        self._real_html_dir = polish.OUTPUT_HTML_DIR
        self._real_pdf_dir = polish.OUTPUT_PDF_DIR
        polish.OUTPUT_HTML_DIR = os.path.join(self.tmp_dir, "html")
        polish.OUTPUT_PDF_DIR = os.path.join(self.tmp_dir, "pdf")

    def tearDown(self):
        polish.OUTPUT_HTML_DIR = self._real_html_dir
        polish.OUTPUT_PDF_DIR = self._real_pdf_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    @patch("polish.subprocess.run")
    @patch("polish.render_html")
    def test_resume_paths_and_success(self, mock_render, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = polish.save_and_render({"TAGLINE": "X"}, "resume", self.resume_json_path)

        self.assertTrue(os.path.exists(self.resume_json_path))
        expected_html = os.path.join(polish.OUTPUT_HTML_DIR, "MorganEscott_Title_Company_Resume.html")
        expected_pdf = os.path.join(polish.OUTPUT_PDF_DIR, "MorganEscott_Title_Company_Resume.pdf")
        self.assertEqual(result, {"json": self.resume_json_path, "html": expected_html, "pdf": expected_pdf})
        mock_render.assert_called_once_with({"TAGLINE": "X"}, expected_html)

    @patch("polish.subprocess.run")
    @patch("polish.render_html")
    def test_pdf_failure_returns_none_pdf_but_keeps_json_and_html(self, mock_render, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        result = polish.save_and_render({"TAGLINE": "X"}, "resume", self.resume_json_path)

        self.assertTrue(os.path.exists(self.resume_json_path))
        self.assertIsNone(result["pdf"])

    @patch("polish.subprocess.run")
    @patch("polish.render_coverletter")
    def test_coverletter_uses_coverletter_renderer(self, mock_render, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = polish.save_and_render(
            {"greeting": "Hi,"}, "coverletter", self.coverletter_json_path,
        )

        expected_html = os.path.join(polish.OUTPUT_HTML_DIR, "MorganEscott_Title_Company_CoverLetter.html")
        mock_render.assert_called_once_with({"greeting": "Hi,"}, expected_html)
        self.assertEqual(result["html"], expected_html)


class TestPickPolishTarget(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_polish_picker")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_json_dir = polish.OUTPUT_JSON_DIR
        polish.OUTPUT_JSON_DIR = self.tmp_dir

    def tearDown(self):
        polish.OUTPUT_JSON_DIR = self._real_json_dir
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _touch(self, name, mtime_offset):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w") as f:
            f.write("{}")
        now = time.time()
        os.utime(path, (now + mtime_offset, now + mtime_offset))
        return path

    def test_empty_dir_returns_none(self):
        self.assertIsNone(polish.pick_polish_target())

    def test_unrecognized_files_are_excluded(self):
        self._touch("random.json", 0)
        self.assertIsNone(polish.pick_polish_target())

    @patch("polish.questionary.select")
    def test_newest_first_and_labeled(self, mock_select):
        older = self._touch("A_Resume.json", -10)
        newer = self._touch("B_CoverLetter.json", 0)
        mock_select.return_value.ask.return_value = newer

        result = polish.pick_polish_target()

        self.assertEqual(result, newer)
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].value, newer)
        self.assertEqual(choices[0].title, "[Cover Letter] B_CoverLetter.json")
        self.assertEqual(choices[1].value, older)
        self.assertEqual(choices[1].title, "[Resume] A_Resume.json")


class TestRunPolishSession(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_polish_session")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.json_path = os.path.join(self.tmp_dir, "MorganEscott_Title_Company_Resume.json")
        with open(self.json_path, "w") as f:
            json.dump({"TAGLINE": "OLD"}, f)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_unrecognized_suffix_does_not_enter_loop(self):
        bad_path = os.path.join(self.tmp_dir, "not_a_recognized_name.json")
        with open(bad_path, "w") as f:
            f.write("{}")
        with patch("polish.questionary.text") as mock_text:
            polish.run_polish_session(bad_path)
        mock_text.assert_not_called()

    def test_missing_file_does_not_enter_loop(self):
        with patch("polish.questionary.text") as mock_text:
            polish.run_polish_session(os.path.join(self.tmp_dir, "Nope_Resume.json"))
        mock_text.assert_not_called()

    @patch("polish.questionary.text")
    def test_exit_word_ends_loop_without_calling_gemini(self, mock_text):
        mock_text.return_value.ask.return_value = "done"
        with patch("polish.generate_candidate") as mock_generate:
            polish.run_polish_session(self.json_path)
        mock_generate.assert_not_called()

    @patch("polish.questionary.text")
    def test_none_from_ask_ends_loop_like_exit(self, mock_text):
        mock_text.return_value.ask.return_value = None
        with patch("polish.generate_candidate") as mock_generate:
            polish.run_polish_session(self.json_path)
        mock_generate.assert_not_called()

    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_unparseable_candidate_reprompts_without_saving(self, mock_generate, mock_text):
        mock_text.return_value.ask.side_effect = ["do a thing", "done"]
        mock_generate.return_value = None
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()

    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_no_diff_reprompts_without_saving(self, mock_generate, mock_text):
        mock_text.return_value.ask.side_effect = ["do a thing", "done"]
        mock_generate.return_value = {"TAGLINE": "OLD"}  # identical to what's on disk
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()

    @patch("polish.questionary.select")
    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_reject_keeps_state_and_does_not_save(self, mock_generate, mock_text, mock_select):
        mock_text.return_value.ask.side_effect = ["make it punchier", "done"]
        mock_generate.return_value = {"TAGLINE": "NEW"}
        mock_select.return_value.ask.return_value = "reject"
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()

    @patch("polish.questionary.select")
    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_accept_saves_the_candidate(self, mock_generate, mock_text, mock_select):
        mock_text.return_value.ask.side_effect = ["make it punchier", "done"]
        mock_generate.return_value = {"TAGLINE": "NEW"}
        mock_select.return_value.ask.return_value = "accept"
        with patch(
            "polish.save_and_render",
            return_value={"json": self.json_path, "html": "h", "pdf": "p"},
        ) as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_called_once_with({"TAGLINE": "NEW"}, "resume", self.json_path)

    @patch("polish.questionary.select")
    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_quit_choice_ends_loop(self, mock_generate, mock_text, mock_select):
        mock_text.return_value.ask.return_value = "make it punchier"
        mock_generate.return_value = {"TAGLINE": "NEW"}
        mock_select.return_value.ask.return_value = "quit"
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()


class TestRun(unittest.TestCase):

    @patch("polish.run_polish_session")
    @patch("polish.pick_polish_target")
    def test_uses_given_file_without_picker(self, mock_pick, mock_session):
        polish.run("some/path_Resume.json")
        mock_pick.assert_not_called()
        mock_session.assert_called_once_with("some/path_Resume.json")

    @patch("polish.run_polish_session")
    @patch("polish.pick_polish_target")
    def test_uses_picker_when_no_file_given(self, mock_pick, mock_session):
        mock_pick.return_value = "picked_Resume.json"
        polish.run(None)
        mock_session.assert_called_once_with("picked_Resume.json")

    @patch("polish.run_polish_session")
    @patch("polish.pick_polish_target")
    def test_nothing_to_pick_does_not_enter_session(self, mock_pick, mock_session):
        mock_pick.return_value = None
        polish.run(None)
        mock_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
