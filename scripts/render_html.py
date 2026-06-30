"""
render_html.py — Fills cv-template.html with orchestrator.py's resume JSON output.

Usage (standalone):
    python scripts/render_html.py output/json/my_resume.json output/html/my_resume.html

Called programmatically by orchestrator.py's build_tailored_resume() Step 7.
"""

import os
import json
import argparse
from pathlib import Path

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "resume-engine", "templates", "cv-template.html")


# ---------------------------------------------------------------------------
# HTML FRAGMENT BUILDERS
# Each function takes a slice of the resume JSON and returns an HTML string.
# ---------------------------------------------------------------------------

def build_skills_html(skills: list[str]) -> str:
    """Renders skills as the .skills-grid tag cloud the template expects."""
    if not skills:
        return ""
    items = "".join(f'<span class="skill-item">{s}</span>' for s in skills)
    return f'<div class="skills-grid">{items}</div>'


def build_competencies_html(competencies: list[str]) -> str:
    """Renders core competencies as .competency-tag spans."""
    return "".join(f'<span class="competency-tag">{c}</span>' for c in competencies)


def build_experience_html(jobs: list[dict]) -> str:
    """Renders the work experience section."""
    html = []
    for job in jobs:
        bullets_html = "".join(f"<li>{b}</li>" for b in job.get("bullets", []))
        career_note = f'<div class="career-note">{job["career_note"]}</div>' if job.get("career_note") else ""
        location    = f'<div class="job-location">{job["location"]}</div>'  if job.get("location")    else ""
        html.append(f"""
        <div class="job">
          <div class="job-header">
            <span class="job-company">{job.get("company","")}</span>
            <span class="job-period">{job.get("period","")}</span>
          </div>
          <div class="job-role">{job.get("role","")}</div>
          {location}
          {career_note}
          <ul>{bullets_html}</ul>
        </div>""")
    return "\n".join(html)


def build_projects_html(projects: list[dict]) -> str:
    """Renders the projects section."""
    html = []
    for p in projects:
        badge = f'<span class="project-badge">{p["badge"]}</span>' if p.get("badge") else ""
        tech  = f'<div class="project-tech">{p["tech"]}</div>'     if p.get("tech")  else ""
        html.append(f"""
        <div class="project">
          <div class="project-title">{p.get("title","")}{badge}</div>
          <div class="project-desc">{p.get("description","")}</div>
          {tech}
        </div>""")
    return "\n".join(html)


def build_certifications_html(certs: list[dict]) -> str:
    """Renders the three-column cert grid the template expects."""
    html = []
    for c in certs:
        html.append(f"""
        <div class="cert-item">
          <span class="cert-title">{c.get("title","")}</span>
          <span class="cert-org">{c.get("org","")}</span>
          <span class="cert-year">{c.get("year","")}</span>
        </div>""")
    return "\n".join(html)


def build_education_html(edu: list[dict]) -> str:
    """Renders the education section."""
    html = []
    for e in edu:
        bullets_html = ""
        if e.get("bullets"):
            lis = "".join(f"<li>{b}</li>" for b in e["bullets"])
            bullets_html = f"<ul>{lis}</ul>"
        desc = f'<div class="edu-desc">{e["desc"]}</div>' if e.get("desc") else ""
        html.append(f"""
        <div class="edu-item">
          <div class="edu-header">
            <span class="edu-title">{e.get("degree","")} — <span class="edu-org">{e.get("school","")}</span></span>
            <span class="edu-year">{e.get("year","")}</span>
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
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # --- Simple scalar tokens ---
    scalars = {
        "LANG":               resume_data.get("lang", "en"),
        "NAME":               resume_data.get("name", ""),
        "TAGLINE":            resume_data.get("tagline", ""),
        "PHONE":              resume_data.get("phone", ""),
        "EMAIL":              resume_data.get("email", ""),
        "LINKEDIN_URL":       resume_data.get("linkedin_url", ""),
        "LINKEDIN_DISPLAY":   resume_data.get("linkedin_display", ""),
        "PORTFOLIO_URL":      resume_data.get("portfolio_url", ""),
        "PORTFOLIO_DISPLAY":  resume_data.get("portfolio_display", ""),
        "LOCATION":           resume_data.get("location", ""),
        "PAGE_WIDTH":         resume_data.get("page_width", "8.5in"),
        "SUMMARY_TEXT":       resume_data.get("summary", ""),
        # Section heading labels (lets you override later if needed)
        "SECTION_SUMMARY":        resume_data.get("section_summary",        "Professional Summary"),
        "SECTION_SKILLS":         resume_data.get("section_skills",         "Core Skills"),
        "SECTION_COMPETENCIES":   resume_data.get("section_competencies",   "Core Competencies"),
        "SECTION_EXPERIENCE":     resume_data.get("section_experience",     "Work Experience"),
        "SECTION_PROJECTS":       resume_data.get("section_projects",       "Selected Projects"),
        "SECTION_CERTIFICATIONS": resume_data.get("section_certifications", "Training & Certifications"),
        "SECTION_EDUCATION":      resume_data.get("section_education",      "Education"),
    }
    for token, value in scalars.items():
        html = html.replace(f"{{{{{token}}}}}", value)

    # --- Block tokens (HTML fragments) ---
    html = html.replace("{{SKILLS}}",         build_skills_html(resume_data.get("skills", [])))
    html = html.replace("{{COMPETENCIES}}",   build_competencies_html(resume_data.get("competencies", [])))
    html = html.replace("{{EXPERIENCE}}",     build_experience_html(resume_data.get("experience", [])))
    html = html.replace("{{PROJECTS}}",       build_projects_html(resume_data.get("projects", [])))
    html = html.replace("{{CERTIFICATIONS}}", build_certifications_html(resume_data.get("certifications", [])))
    html = html.replace("{{EDUCATION}}",      build_education_html(resume_data.get("education", [])))

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