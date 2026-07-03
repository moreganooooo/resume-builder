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


class TestContactRowAndEducationFormatting(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_contact_edu.html")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def test_contact_row_has_no_portfolio_and_linkedin_is_not_a_hyperlink(self):
        data = _minimal_resume_data(
            LINKEDIN_DISPLAY="linkedin.com/in/morganescott",
            PORTFOLIO_URL="https://example.com/portfolio",
            PORTFOLIO_DISPLAY="example.com/portfolio",
        )
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("example.com/portfolio", html)
        self.assertIn("linkedin.com/in/morganescott", html)
        self.assertNotIn('<a href="https://linkedin.com', html)

    def test_education_renders_pipe_separated_meta_with_no_bold_location(self):
        data = _minimal_resume_data(EDUCATION=[{
            "degree": "Bachelor of Science, Journalism",
            "institution": "University of Kansas",
            "location": "Lawrence, KS",
            "year": "2006 – 2008",
            "bullets": ["3.56 GPA"],
        }])
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('<div class="edu-title">Bachelor of Science, Journalism</div>', html)
        self.assertIn(
            '<div class="edu-meta">University of Kansas <span class="sep">|</span> '
            'Lawrence, KS <span class="sep">|</span> 2006 – 2008</div>',
            html,
        )

    def test_career_note_renders_after_bullets_with_bold_label(self):
        data = _minimal_resume_data(EXPERIENCE=[{
            "title": "Creative Strategy Lead", "company": "Treering Yearbooks", "period": "08/2016 – 08/2024",
            "achievements": ["Founded the Content Committee"],
            "career_note": "Returning with renewed focus.",
        }])
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        bullets_pos = html.index("Founded the Content Committee")
        career_note_pos = html.index("Returning with renewed focus.")
        self.assertLess(bullets_pos, career_note_pos, "career note must render after the bullets, not before")
        self.assertIn('<strong>Career Note:</strong> Returning with renewed focus.', html)


if __name__ == "__main__":
    unittest.main()
