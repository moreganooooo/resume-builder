import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
from render_html import render_html  # noqa: E402


def _minimal_resume_data(**overrides):
    data = {
        "NAME": "Test Candidate",
        "TAGLINE": "TEST TAGLINE",
        "SUMMARY_TEXT": "<strong>Test summary.</strong>",
        "SKILLS": [],
        "EXPERIENCE": [],
        "EDUCATION": [],
        "CERTIFICATIONS": [],
    }
    data.update(overrides)
    return data


class TestNoProjectsOrCompetencies(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_no_projects.html")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def test_template_schema_has_no_competencies_or_projects_fields(self):
        fields = orchestrator.TemplateSchema.model_fields
        self.assertNotIn("COMPETENCIES", fields)
        self.assertNotIn("SECTION_COMPETENCIES", fields)
        self.assertNotIn("PROJECTS", fields)
        self.assertNotIn("SECTION_PROJECTS", fields)

    def test_rendered_html_has_no_competencies_or_projects_markup(self):
        render_html(_minimal_resume_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("Core Competencies", html)
        self.assertNotIn("competency-tag", html)
        self.assertNotIn("Selected Projects", html)
        self.assertNotIn("project-title", html)

    def test_missing_section_skills_key_falls_back_to_skills_not_core_skills(self):
        data = _minimal_resume_data()
        data.pop("SECTION_SKILLS", None)  # confirm it's absent
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(">Skills<", html)
        self.assertNotIn("Core Skills", html)


if __name__ == "__main__":
    unittest.main()
