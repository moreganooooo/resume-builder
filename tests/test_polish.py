import json
import os
import sys
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
