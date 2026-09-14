"""
render_html.py — Fills cv-template.html with orchestrator.py's resume JSON output.

Usage (standalone):
    python scripts/render_html.py output/json/my_resume.json output/html/my_resume.html

Called programmatically by orchestrator.py's build_tailored_resume() Step 7.
"""

import argparse
import json
import os
import re as _re
from html import escape
from pathlib import Path

import cli_art
import theme

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(
    PROJECT_ROOT, "resume-engine", "templates", "cv-template.html"
)


# ---------------------------------------------------------------------------
# HTML FRAGMENT BUILDERS
# Each function takes a slice of the resume JSON and returns an HTML string.
# ---------------------------------------------------------------------------


def _wrap_tagline_pipe(escaped_tagline: str) -> str:
    """
    tailor_resume.md's tagline format is "[Role] | [Archetype Descriptor]" --
    a single hard-coded string with no per-segment markup, unlike the
    contact-row/job-meta/cert-item pipes, which are already built as their
    own <span class="sep">. Wraps the pipe the same way so it can be styled
    gray (#9aa3af) to match those.
    """
    return escaped_tagline.replace(" | ", ' <span class="tagline-sep">|</span> ')


def _preserve_arrow_glyph(text: str) -> str:
    """
    generate-pdf.mjs's ATS text normalizer strips any literal U+2192 arrow
    to " to " (arrows often get mangled by resume-parsing software) -- right
    for prose, but Element 8 / Strategy LLC's fixed title wants to keep its
    visible "->" showing the in-role promotion. Swapping in the HTML entity
    reference means the normalizer's raw-string regex (which only matches a
    literal U+2192 codepoint) has nothing to match, while the browser still
    renders the identical glyph once it parses the entity.
    """
    return text.replace("→", "&rarr;")


def _sanitize_copy(text: str) -> str:
    """Basic post-render copy sanitizer to reduce marketing-buzzword phrasing.

    This is intentionally conservative: it applies a small, auditable set of
    replacements (regex, case-insensitive) that convert vague phrases like
    "drive engagement" into more concrete, template-friendly wording. Keep
    the list short and review replacements if candidates are too aggressive.
    """
    if not text:
        return text
    replacements = [
        (
            r"\bactivation-ready assets\b",
            "campaign-ready email sequences, landing pages, and social posts",
        ),
        (
            r"\bassets that drive engagement across\b",
            "campaign-ready email sequences, landing pages, and social posts",
        ),
        (
            r"\bdrive engagement\b",
            "generate measurable email and landing-page interactions",
        ),
        (r"\bLeverages AI-assisted workflows\b", "Uses AI-assisted workflows"),
    ]
    out = text
    for pat, repl in replacements:
        out = _re.sub(pat, repl, out, flags=_re.IGNORECASE)
    return out


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
        return _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

    items = "".join(
        f'<span class="skill-item">{render_skill(s)}</span>' for s in skills
    )
    return f'<div class="skills-grid">{items}</div>'


def build_experience_html(jobs: list[dict]) -> str:
    """
    Renders the work experience section.

    Job title comes first (bold, its own line); the job-meta line below it
    combines company, size/revenue (if known -- see fixed_content.COMPANY_META
    and normalize_resume.normalize), location or work type, and dates, all
    pipe-separated, per ResumeDesignSystem.md's .job-title/.job-meta split.
    """
    sep = '<span class="sep">|</span>'
    html = []
    for job in jobs:
        bullets_html = "".join(
            f"<li>{escape(b)}</li>" for b in job.get("achievements", [])
        )
        career_note = (
            f'<div class="career-note"><strong>Career Note:</strong> {escape(job["career_note"])}</div>'
            if job.get("career_note")
            else ""
        )

        # company is pre-escaped (it may already contain the escaped
        # size/revenue parenthetical); the other parts are escaped inline.
        company = escape(job.get("company", ""))
        if job.get("size_revenue"):
            company = f"{company} ({escape(job['size_revenue'])})"
        meta_parts = [
            p for p in (company, job.get("location", ""), job.get("period", "")) if p
        ]
        meta_line = (
            f" {sep} ".join(
                part if part is company else escape(part) for part in meta_parts
            )
            if meta_parts
            else ""
        )

        clients = (
            f'<div class="job-clients"><strong>Clients:</strong> {escape(job["clients"])}</div>'
            if job.get("clients")
            else ""
        )

        html.append(f"""
        <div class="job">
          <div class="job-title">{_preserve_arrow_glyph(escape(job.get("title","")))}</div>
          <div class="job-meta">{meta_line}</div>
          {clients}
          <ul>{bullets_html}</ul>
          {career_note}
        </div>""")
    return "\n".join(html)


def build_certifications_html(certs: list[dict]) -> str:
    """Renders each certification as a single pipe-separated line: Title | Org | Year."""
    html = []
    for c in certs:
        html.append(f"""
        <div class="cert-item">
          <span class="cert-title">{escape(c.get("title",""))}</span><span class="cert-sep">|</span><span class="cert-org">{escape(c.get("org",""))}</span><span class="cert-sep">|</span><span class="cert-year">{escape(c.get("year",""))}</span>
        </div>""")
    return "\n".join(html)


def build_certifications_section_html(section_title: str, certs: list) -> str:
    """The whole Training & Certifications section, or "" when there is
    nothing to list -- the template used to print the heading regardless, so
    a profile without certifications got an empty titled section on page 1."""
    certs = [c for c in (certs or []) if isinstance(c, dict) and (c.get("title") or "").strip()]
    if not certs:
        return ""
    return f"""
  <div class="section avoid-break">
    <div class="section-title">{escape(section_title or "Training & Certifications")}</div>
    {build_certifications_html(certs)}
  </div>"""


# A profile whose content runs short (profile.yml `resume_layout: relaxed`)
# gets more breathing room so page 2 doesn't look empty next to a dense
# page 1. The default layout is untouched.
LAYOUT_CSS = {
    "compact": "",
    # Line height only (1.20 vs the template's 1.15), gaps unchanged -- a
    # little air for a resume that fills its pages without room to spare
    # for the full "relaxed" treatment.
    "balanced": """
  body,
  .summary-text, .skills-grid, .skills-text, .job-title, .job-meta,
  .job-clients, .job li, .career-note,
  .cert-item, .edu-header, .edu-desc, .edu-item li, .why-text { line-height: 1.2; }
""",
    # One leading for every text block (1.25 at 9.75pt, about 12.2pt line
    # to line -- a middle ground between the compact 1.15 and a 1.32 that
    # read as airy). The first version raised it only for the summary,
    # skills and job bullets, so Education/certifications/Why kept 1.15 and
    # page 2 read tighter than page 1.
    "relaxed": """
  body,
  .summary-text, .skills-grid, .skills-text, .job-title, .job-meta,
  .job-clients, .job li, .career-note,
  .cert-item, .edu-header, .edu-desc, .edu-item li, .why-text { line-height: 1.25; }
  .header { margin-bottom: 16px; }
  .section { margin-bottom: 16px; }
  .section-title { margin-bottom: 6px; }
  .skills-grid { gap: 3px; }
  .job { margin-bottom: 14px; }
  .job + .job .job-title { margin-top: 6px; }
  .job-meta { margin-bottom: 5px; }
  .job ul, .edu-item ul { margin-top: 5px; }
  .job li, .edu-item li { margin-bottom: 3px; }
  .cert-item { margin-bottom: 3px; }
  .edu-item { margin-bottom: 10px; }
  .edu-header { margin-bottom: 5px; }
  .why-text p { margin-bottom: 10px; }
""",
}


def _profile_layout() -> str:
    try:
        import profile_paths

        value = (profile_paths.profile_yaml() or {}).get("resume_layout")
    except Exception:
        return "compact"
    return str(value).strip().lower() if value else "compact"


def link_display(url: str) -> str:
    """A URL as shown on the page: no scheme, no "www.", no trailing slash
    ("https://www.linkedin.com/in/x/" -> "linkedin.com/in/x")."""
    text = str(url or "").strip()
    text = _re.sub(r"^https?://", "", text, flags=_re.IGNORECASE)
    text = _re.sub(r"^www\.", "", text, flags=_re.IGNORECASE)
    return text.rstrip("/")


def profile_header_links() -> list:
    """Extra header links a profile opts into (profile.yml
    `resume_header_links:` names keys of its `candidate:` block, e.g.
    [extra_link, portfolio_url]). Opt-in because normalize_resume
    deliberately keeps a portfolio off resumes that never asked for one."""
    try:
        import profile_paths

        profile = profile_paths.profile_yaml() or {}
    except Exception:
        return []
    candidate = profile.get("candidate") or {}
    return [
        str(candidate.get(key)).strip()
        for key in (profile.get("resume_header_links") or [])
        if str(candidate.get(key) or "").strip()
    ]


def header_links_row_html(links: list) -> str:
    """A second contact row for extra links, or "" when there are none."""
    shown = [escape(link_display(link)) for link in (links or []) if str(link or "").strip()]
    if not shown:
        return ""
    sep = '<span class="separator">|</span>'
    return '<div class="contact-row">' + sep.join(f"<span>{s}</span>" for s in shown) + "</div>"


def build_patents_section_html(patents: list, section_title: str = "Patents") -> str:
    """Patents, one line each (Title | Number), styled like certifications;
    "" when the profile has none."""
    rows = [p for p in (patents or []) if isinstance(p, dict) and (p.get("title") or "").strip()]
    if not rows:
        return ""
    items = []
    for patent in rows:
        parts = [f'<span class="cert-title">{escape(patent["title"])}</span>']
        for key in ("number", "role"):
            value = str(patent.get(key) or "").strip()
            if value:
                parts.append(f'<span class="cert-sep">|</span><span class="cert-org">{escape(value)}</span>')
        items.append(f'<div class="cert-item patent-item">{"".join(parts)}</div>')
    return f"""
  <div class="section avoid-break">
    <div class="section-title">{escape(section_title or "Patents")}</div>
    {"".join(items)}
  </div>"""


def build_why_html(section_title: str, why_text: str) -> str:
    """
    Renders the conditional "Why [Company]?" section. tailor_resume.md says to
    include this only when space allows on a 2-page resume -- if the builder
    leaves WHY_TEXT blank, this drops the section (including its header)
    entirely rather than leaving an empty div with just a title.

    A real run trimmed Why away, but a *later* trim step's prompt re-dumped
    resume_data with a stray Python None in WHY_TEXT (rendered by
    json.dumps as the unquoted JSON token null) -- the model then echoed
    that back as the literal string "null" instead of leaving it blank,
    which rendered as a visible "null" plus the section's own title/divider
    instead of being dropped. Treat None and a literal "null" string
    (whitespace/case-insensitive) as blank too, not just empty string.

    WHY_TEXT is intentionally NOT escaped, same as SUMMARY_TEXT -- tailor_resume.md
    requires <p> paragraph tags and <em> tags around the first and last sentences
    of the section.
    """
    if not why_text or why_text.strip().lower() == "null":
        return ""
    if not section_title or section_title.strip().lower() == "null":
        section_title = "Additional Relevant Experience"
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
    sep = '<span class="sep">|</span>'
    html = []
    for e in edu:
        bullets_html = ""
        if e.get("bullets"):
            lis = "".join(f"<li>{escape(b)}</li>" for b in e["bullets"])
            bullets_html = f"<ul>{lis}</ul>"
        desc = (
            f'<div class="edu-desc">{escape(e["description"])}</div>'
            if e.get("description")
            else ""
        )
        meta_parts = [
            escape(p)
            for p in (
                e.get("institution", ""),
                e.get("location", ""),
                e.get("year", ""),
            )
            if p
        ]
        meta_line = f" {sep} ".join(meta_parts)
        html.append(f"""
        <div class="edu-item">
          <div class="edu-header"><span class="edu-title">{escape(e.get("degree",""))}</span>{sep}<span class="edu-meta-text">{meta_line}</span></div>
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
        "LANG": resume_data.get("LANG", "en"),
        "NAME": escape(resume_data.get("NAME", "")),
        "TAGLINE": _wrap_tagline_pipe(escape(resume_data.get("TAGLINE", ""))),
        "PHONE": escape(resume_data.get("PHONE", "")),
        "EMAIL": escape(resume_data.get("EMAIL", "")),
        "LINKEDIN_DISPLAY": escape(link_display(resume_data.get("LINKEDIN_DISPLAY", ""))),
        "LOCATION": escape(resume_data.get("LOCATION", "")),
        "PAGE_WIDTH": resume_data.get("PAGE_WIDTH", "8.5in"),
        "SUMMARY_TEXT": _sanitize_copy(resume_data.get("SUMMARY_TEXT", "")),
        # Section heading labels (lets you override later if needed)
        "SECTION_SUMMARY": resume_data.get("SECTION_SUMMARY", "Professional Summary"),
        "SECTION_SKILLS": resume_data.get("SECTION_SKILLS", "Skills"),
        "SECTION_EXPERIENCE": resume_data.get("SECTION_EXPERIENCE", "Work Experience"),
        "SECTION_CERTIFICATIONS": resume_data.get(
            "SECTION_CERTIFICATIONS", "Training & Certifications"
        ),
        "SECTION_EDUCATION": resume_data.get("SECTION_EDUCATION", "Education"),
    }
    for token, value in scalars.items():
        html = html.replace(f"{{{{{token}}}}}", value)

    # --- Block tokens (HTML fragments) ---
    html = html.replace("{{SKILLS}}", build_skills_html(resume_data.get("SKILLS", [])))
    html = html.replace(
        "{{EXPERIENCE}}", build_experience_html(resume_data.get("EXPERIENCE", []))
    )
    html = html.replace(
        "{{CERTIFICATIONS_SECTION}}",
        build_certifications_section_html(
            scalars["SECTION_CERTIFICATIONS"], resume_data.get("CERTIFICATIONS", [])
        ),
    )
    html = html.replace("{{LAYOUT_CSS}}", LAYOUT_CSS.get(_profile_layout(), ""))
    html = html.replace(
        "{{PATENTS_SECTION}}",
        build_patents_section_html(
            resume_data.get("PATENTS", []), resume_data.get("SECTION_PATENTS") or "Patents"
        ),
    )
    header_links = resume_data.get("HEADER_LINKS")
    if header_links is None:
        header_links = profile_header_links()
    html = html.replace("{{EXTRA_LINKS_ROW}}", header_links_row_html(header_links))
    html = html.replace(
        "{{EDUCATION}}", build_education_html(resume_data.get("EDUCATION", []))
    )
    html = html.replace(
        "{{WHY_SECTION}}",
        build_why_html(
            resume_data.get("SECTION_WHY") or "",
            _sanitize_copy(resume_data.get("WHY_TEXT") or ""),
        ),
    )

    # Final HTML-level cleanup: some buzzword phrases may survive
    # because they were split or wrapped in HTML in the source. Apply a
    # conservative set of case-insensitive replacements directly to the
    # rendered HTML to catch any remaining instances flagged by detectors.
    final_replacements = [
        (
            r"activation-ready assets that drive engagement across email, web, and social",
            "campaign-ready email sequences, landing pages, and social posts",
        ),
        (
            r"assets that drive engagement across email, web, and social",
            "campaign-ready email sequences, landing pages, and social posts",
        ),
        (
            r"assets that drive engagement across",
            "campaign-ready email sequences, landing pages, and social posts",
        ),
        (
            r"drive engagement across",
            "generate measurable email and landing-page interactions across",
        ),
    ]
    for pat, repl in final_replacements:
        html = _re.sub(pat, repl, html, flags=_re.IGNORECASE)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    cli_art.console.print(
        f"  {theme.colorize_icon('success')} HTML rendered → {output_path}",
        soft_wrap=True,
    )
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
