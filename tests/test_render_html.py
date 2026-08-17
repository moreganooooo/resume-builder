import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
from render_html import build_why_html, render_html  # noqa: E402


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

    def test_tagline_pipe_is_wrapped_in_its_own_gray_separator_span(self):
        # The tagline is a single hard-coded "[Role] | [Descriptor]" string
        # with no per-segment markup, unlike contact-row/job-meta/cert-item,
        # which already build their pipes as their own <span class="sep">.
        data = _minimal_resume_data(TAGLINE="CAMPAIGN & CRM STRATEGIST | LIFECYCLE MARKETING")
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(
            'CAMPAIGN &amp; CRM STRATEGIST <span class="tagline-sep">|</span> LIFECYCLE MARKETING',
            html,
        )

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
        self.assertIn(
            '<div class="edu-header"><span class="edu-title">Bachelor of Science, Journalism</span>'
            '<span class="sep">|</span><span class="edu-meta-text">University of Kansas '
            '<span class="sep">|</span> Lawrence, KS <span class="sep">|</span> 2006 – 2008</span></div>',
            html,
        )

    def test_job_title_arrow_survives_as_html_entity_not_a_literal_codepoint(self):
        # generate-pdf.mjs's ATS text normalizer strips a literal U+2192 arrow
        # to " to " for ATS safety -- Element 8 / Strategy LLC's fixed title
        # wants to keep a visible arrow, so render_html must emit the &rarr;
        # entity reference instead of the raw arrow character, or the
        # normalizer's raw-string regex would still catch and convert it.
        data = _minimal_resume_data(EXPERIENCE=[{
            "title": "Design Assistant → Lead Designer", "company": "Element 8 / Strategy LLC", "period": "01/2011 – 10/2011",
            "achievements": ["Established the brand identity from scratch"],
        }])
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Design Assistant &rarr; Lead Designer", html)
        self.assertNotIn("Design Assistant → Lead Designer", html)

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


class TestWhySectionDropsCleanly(unittest.TestCase):
    """
    A real run's Why section, after being trimmed away, still showed the
    literal word "null" plus its own section-title/divider instead of being
    dropped entirely -- WHY_TEXT had picked up the literal string "null"
    (echoed back by the model after seeing a stray Python None rendered as
    the unquoted JSON token null in an earlier trim prompt).
    """

    def test_empty_string_drops_the_section(self):
        self.assertEqual(build_why_html("Why Acme?", ""), "")

    def test_none_drops_the_section(self):
        self.assertEqual(build_why_html(None, None), "")

    def test_literal_null_string_drops_the_section(self):
        self.assertEqual(build_why_html("null", "null"), "")
        self.assertEqual(build_why_html("Why Acme?", "NULL"), "")
        self.assertEqual(build_why_html("Why Acme?", "  null  "), "")

    def test_real_content_still_renders(self):
        html = build_why_html("Why Acme?", "<p>Real why text.</p>")
        self.assertIn("Why Acme?", html)
        self.assertIn("Real why text.", html)

    def test_falls_back_to_generic_header_if_only_the_title_is_null(self):
        html = build_why_html("null", "<p>Real why text.</p>")
        self.assertIn("Additional Relevant Experience", html)
        self.assertNotIn(">null<", html)


if __name__ == "__main__":
    unittest.main()
