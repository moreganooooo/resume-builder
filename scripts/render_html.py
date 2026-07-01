"""
render_html.py — Fills cv-template.html with orchestrator.py's resume JSON output.

Usage (standalone):
    python scripts/render_html.py output/json/my_resume.json output/html/my_resume.html

Called programmatically by orchestrator.py's build_tailored_resume() Step 7.
"""

import os
import json
import argparse
import re
from html import escape
from pathlib import Path

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "resume-engine", "templates", "cv-template.html")


# ---------------------------------------------------------------------------
# HTML FRAGMENT BUILDERS
# Each function takes a slice of the resume JSON and returns an HTML string.
# ---------------------------------------------------------------------------

def build_skills_html(skills: list[str]) -> str:
    """
    Renders skills as the .skills-grid tag cloud the template expects.

    tailor_resume.md specs each SKILLS string as markdown-style
    "**Category Label:** Item, Item" -- the template has no markdown
    handling, so without conversion these rendered as literal asterisks.
    """
    if not skills:
        return ""
    def render_skill(s: str) -> str:
        escaped = escape(s)
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    items = "".join(f'<span class="skill-item">{render_skill(s)}</span>' for s in skills)
    return f'<div class="skills-grid">{items}</div>'


def build_experience_html(jobs: list[dict]) -> str:
    """
    Renders the work experience section.

    BUG FIX: was reading job.get("bullets") and job.get("role"), but
    tailor_resume.md's output spec (and the builder's actual JSON) uses
    "achievements" and "title". Those mismatches meant every job entry
    rendered with a blank title and an empty bullet list -- the resume
    silently lost all of its actual content here.
    """
    html = []
    for job in jobs:
        bullets_html = "".join(f"<li>{escape(b)}</li>" for b in job.get("achievements", []))
        career_note = f'<div class="career-note">{escape(job["career_note"])}</div>' if job.get("career_note") else ""
        location    = f'<div class="job-location">{escape(job["location"])}</div>'  if job.get("location")    else ""
        html.append(f"""
        <div class="job">
          <div class="job-header">
            <span class="job-company">{escape(job.get("company",""))}</span>
            <span class="job-period">{escape(job.get("period",""))}</span>
          </div>
          <div class="job-role">{escape(job.get("title",""))}</div>
          {location}
          {career_note}
          <ul>{bullets_html}</ul>
        </div>""")
    return "\n".join(html)


def build_certifications_html(certs: list[dict]) -> str:
    """Renders the three-column cert grid the template expects."""
    html = []
    for c in certs:
        html.append(f"""
        <div class="cert-item">
          <span class="cert-title">{escape(c.get("title",""))}</span>
          <span class="cert-org">{escape(c.get("org",""))}</span>
          <span class="cert-year">{escape(c.get("year",""))}</span>
        </div>""")
    return "\n".join(html)


def build_why_html(section_title: str, why_text: str) -> str:
    """
    Renders the conditional "Why [Company]?" section. tailor_resume.md says to
    include this only when space allows on a 2-page resume -- if the builder
    leaves WHY_TEXT blank, this drops the section (including its header)
    entirely rather than leaving an empty div with just a title.

    WHY_TEXT is intentionally NOT escaped, same as SUMMARY_TEXT -- tailor_resume.md
    requires <p> paragraph tags and <em> tags around the first and last sentences
    of the section.
    """
    if not why_text:
        return ""
    return f"""
    <div class="section avoid-break">
      <div class="section-title">{escape(section_title)}</div>
      <div class="why-text">{why_text}</div>
    </div>"""


def build_education_html(edu: list[dict]) -> str:
    """
    Renders the education section.

    BUG FIX: was reading e.get("school") and e.get("desc"), but
    tailor_resume.md's output spec uses "institution" and "description".
    Those mismatches meant every education entry rendered with a blank
    school name and a blank description line.
    """
    html = []
    for e in edu:
        bullets_html = ""
        if e.get("bullets"):
            lis = "".join(f"<li>{escape(b)}</li>" for b in e["bullets"])
            bullets_html = f"<ul>{lis}</ul>"
        desc = f'<div class="edu-desc">{escape(e["description"])}</div>' if e.get("description") else ""
        html.append(f"""
        <div class="edu-item">
          <div class="edu-header">
            <span class="edu-title">{escape(e.get("degree",""))} — <span class="edu-org">{escape(e.get("institution",""))}</span></span>
            <span class="edu-year">{escape(e.get("year",""))}</span>
          </div>
          {desc}
          {bullets_html}
        </div>""")
    return "\n".join(html)


# ---------------------------------------------------------------------------
# MAIN RENDER FUNCTION
# ---------------------------------------------------------------------------

def render_html(resume_data: dict, output_path: str) -> str:
    """
    Fill cv-template.html with resume_data and write to output_path.
    Returns the output_path on success.

    BUG FIX: this was reading resume_data with lowercase keys ("name",
    "tagline", "experience", etc.), but TemplateSchema's fields -- and
    tailor_resume.md's output spec, which says outright "Your JSON output
    MUST use these exact uppercase field names" -- are all uppercase
    (NAME, TAGLINE, EXPERIENCE, ...). Every lowercase .get() call was
    falling through to its empty default every time, regardless of what
    the builder actually returned. This was the main reason PDFs rendered
    as a mostly-blank template no matter how good the builder's output was.
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # --- Simple scalar tokens ---
    # SUMMARY_TEXT is intentionally NOT escaped -- tailor_resume.md requires
    # the first sentence to be wrapped in a literal <strong> tag.
    scalars = {
        "LANG":               resume_data.get("LANG", "en"),
        "NAME":               escape(resume_data.get("NAME", "")),
        "TAGLINE":            escape(resume_data.get("TAGLINE", "")),
        "PHONE":              escape(resume_data.get("PHONE", "")),
        "EMAIL":              escape(resume_data.get("EMAIL", "")),
        "LINKEDIN_URL":       escape(resume_data.get("LINKEDIN_URL", "")),
        "LINKEDIN_DISPLAY":   escape(resume_data.get("LINKEDIN_DISPLAY", "")),
        "PORTFOLIO_URL":      escape(resume_data.get("PORTFOLIO_URL", "")),
        "PORTFOLIO_DISPLAY":  escape(resume_data.get("PORTFOLIO_DISPLAY", "")),
        "LOCATION":           escape(resume_data.get("LOCATION", "")),
        "PAGE_WIDTH":         resume_data.get("PAGE_WIDTH", "8.5in"),
        "SUMMARY_TEXT":       resume_data.get("SUMMARY_TEXT", ""),
        # Section heading labels (lets you override later if needed)
        "SECTION_SUMMARY":        resume_data.get("SECTION_SUMMARY",        "Professional Summary"),
        "SECTION_SKILLS":         resume_data.get("SECTION_SKILLS",         "Skills"),
        "SECTION_EXPERIENCE":     resume_data.get("SECTION_EXPERIENCE",     "Work Experience"),
        "SECTION_CERTIFICATIONS": resume_data.get("SECTION_CERTIFICATIONS", "Training & Certifications"),
        "SECTION_EDUCATION":      resume_data.get("SECTION_EDUCATION",      "Education"),
    }
    for token, value in scalars.items():
        html = html.replace(f"{{{{{token}}}}}", value)

    # --- Block tokens (HTML fragments) ---
    html = html.replace("{{SKILLS}}",         build_skills_html(resume_data.get("SKILLS", [])))
    html = html.replace("{{EXPERIENCE}}",     build_experience_html(resume_data.get("EXPERIENCE", [])))
    html = html.replace("{{CERTIFICATIONS}}", build_certifications_html(resume_data.get("CERTIFICATIONS", [])))
    html = html.replace("{{EDUCATION}}",      build_education_html(resume_data.get("EDUCATION", [])))
    html = html.replace("{{WHY_SECTION}}",    build_why_html(
        resume_data.get("SECTION_WHY", ""),
        resume_data.get("WHY_TEXT", ""),
    ))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ HTML rendered → {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI ENTRYPOINT (standalone use)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render resume JSON → HTML")
    parser.add_argument("json_path", help="Path to resume JSON file")
    parser.add_argument("html_path", help="Output HTML path")
    args = parser.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    render_html(data, args.html_path)