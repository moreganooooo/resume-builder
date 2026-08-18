"""
export_formats.py -- Multi-format document exporter for resume data:
1. Clean Semantic Markdown
2. Plaintext (ASCII / ATS Text-Box Formatter)
3. Schema.org JSON-LD (Person / WorkExperience / EducationalCredential)
"""

import json
import re
from typing import Any, Dict, List, Optional


def _strip_html(text: str) -> str:
    """Removes basic HTML tags like <strong>, <em>, <span> from text."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return clean.strip()


def render_markdown(resume_data: Dict[str, Any]) -> str:
    """
    Renders structured resume data to clean, standard GitHub Flavored Markdown.
    """
    lines: List[str] = []

    # Header / Title / Contact
    name = resume_data.get("NAME") or "Candidate"
    lines.append(f"# {name}")

    tagline = resume_data.get("TAGLINE") or ""
    if tagline:
        lines.append(f"\n**{tagline}**\n")

    contact_parts = []
    if resume_data.get("LOCATION"):
        contact_parts.append(resume_data["LOCATION"])
    if resume_data.get("EMAIL"):
        contact_parts.append(resume_data["EMAIL"])
    if resume_data.get("PHONE"):
        contact_parts.append(resume_data["PHONE"])
    if resume_data.get("LINKEDIN"):
        contact_parts.append(
            f"[{resume_data['LINKEDIN']}](https://{resume_data['LINKEDIN']})"
        )
    if contact_parts:
        lines.append(" | ".join(contact_parts) + "\n")

    # Summary
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    if summary:
        lines.append("## Professional Summary\n")
        lines.append(f"{summary}\n")

    # Skills
    skills = resume_data.get("SKILLS", [])
    if skills:
        lines.append("## Core Competencies & Skills\n")
        for skill_line in skills:
            lines.append(f"- {skill_line}")
        lines.append("")

    # Experience
    experience = resume_data.get("EXPERIENCE", [])
    if experience:
        lines.append("## Professional Experience\n")
        for role in experience:
            title = role.get("title", "")
            company = role.get("company", "")
            period = role.get("period", "")
            location = role.get("location", "")

            loc_str = f" | {location}" if location else ""
            lines.append(f"### {title} — {company}")
            lines.append(f"*{period}{loc_str}*\n")

            for bullet in role.get("achievements", []):
                clean_bullet = _strip_html(bullet)
                lines.append(f"- {clean_bullet}")
            lines.append("")

    # Education
    education = resume_data.get("EDUCATION", [])
    if education:
        lines.append("## Education\n")
        for edu in education:
            degree = edu.get("degree", "")
            inst = edu.get("institution", "")
            year = edu.get("year") or edu.get("period") or ""
            year_str = f" ({year})" if year else ""
            lines.append(f"- **{degree}** — {inst}{year_str}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_plaintext(resume_data: Dict[str, Any]) -> str:
    """
    Renders structured resume data to pure plaintext formatted with ASCII delimiters,
    ideal for copy-pasting into legacy ATS text entry boxes.
    """
    lines: List[str] = []

    # Name & Header
    name = (resume_data.get("NAME") or "CANDIDATE").upper()
    lines.append(name)
    lines.append("=" * len(name))

    tagline = resume_data.get("TAGLINE") or ""
    if tagline:
        lines.append(tagline.upper())

    contact_parts = []
    if resume_data.get("LOCATION"):
        contact_parts.append(resume_data["LOCATION"])
    if resume_data.get("EMAIL"):
        contact_parts.append(resume_data["EMAIL"])
    if resume_data.get("PHONE"):
        contact_parts.append(resume_data["PHONE"])
    if resume_data.get("LINKEDIN"):
        contact_parts.append(resume_data["LINKEDIN"])
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    # Summary
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    if summary:
        lines.append("PROFESSIONAL SUMMARY")
        lines.append("-" * 20)
        lines.append(summary)
        lines.append("")

    # Skills
    skills = resume_data.get("SKILLS", [])
    if skills:
        lines.append("CORE COMPETENCIES & TECHNICAL SKILLS")
        lines.append("-" * 35)
        for s in skills:
            # Strip markdown formatting like **Category:**
            clean_s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
            lines.append(f"* {clean_s}")
        lines.append("")

    # Experience
    experience = resume_data.get("EXPERIENCE", [])
    if experience:
        lines.append("PROFESSIONAL EXPERIENCE")
        lines.append("-" * 23)
        for role in experience:
            title = role.get("title", "")
            company = role.get("company", "")
            period = role.get("period", "")
            location = role.get("location", "")
            loc_str = f" | {location}" if location else ""

            lines.append(f"{company.upper()} | {title}")
            lines.append(f"{period}{loc_str}")
            for bullet in role.get("achievements", []):
                clean_bullet = _strip_html(bullet)
                lines.append(f"  * {clean_bullet}")
            lines.append("")

    # Education
    education = resume_data.get("EDUCATION", [])
    if education:
        lines.append("EDUCATION")
        lines.append("-" * 9)
        for edu in education:
            degree = edu.get("degree", "")
            inst = edu.get("institution", "")
            year = edu.get("year") or edu.get("period") or ""
            year_str = f", {year}" if year else ""
            lines.append(f"* {degree} - {inst}{year_str}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_json_ld(
    resume_data: Dict[str, Any],
    candidate_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Renders structured resume data into Schema.org Person JSON-LD format
    for machine-readable semantic indexing.
    """
    meta = candidate_meta or {}
    name = resume_data.get("NAME") or meta.get("name") or "Candidate"

    schema: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": name,
        "jobTitle": resume_data.get("TAGLINE") or meta.get("title") or "",
        "description": _strip_html(resume_data.get("SUMMARY_TEXT", "")),
    }

    if resume_data.get("EMAIL") or meta.get("email"):
        schema["email"] = resume_data.get("EMAIL") or meta.get("email")

    if resume_data.get("PHONE") or meta.get("phone"):
        schema["telephone"] = resume_data.get("PHONE") or meta.get("phone")

    if resume_data.get("LOCATION") or meta.get("location"):
        schema["address"] = {
            "@type": "PostalAddress",
            "addressLocality": resume_data.get("LOCATION") or meta.get("location"),
        }

    # Work Experience (hasOccupation / knowsAbout)
    work_entries = []
    for exp in resume_data.get("EXPERIENCE", []):
        work_entries.append(
            {
                "@type": "Role",
                "roleName": exp.get("title", ""),
                "startDate": (
                    exp.get("period", "").split("–")[0].strip()
                    if "–" in exp.get("period", "")
                    else exp.get("period", "")
                ),
                "endDate": (
                    exp.get("period", "").split("–")[1].strip()
                    if "–" in exp.get("period", "")
                    else ""
                ),
                "worksFor": {
                    "@type": "Organization",
                    "name": exp.get("company", ""),
                },
                "description": " ".join(
                    [_strip_html(b) for b in exp.get("achievements", [])]
                ),
            }
        )
    if work_entries:
        schema["hasOccupation"] = work_entries

    # Education
    edu_entries = []
    for edu in resume_data.get("EDUCATION", []):
        edu_entries.append(
            {
                "@type": "EducationalOccupationalCredential",
                "credentialCategory": "degree",
                "name": edu.get("degree", ""),
                "recognizedBy": {
                    "@type": "EducationalOrganization",
                    "name": edu.get("institution", ""),
                },
            }
        )
    if edu_entries:
        schema["hasCredential"] = edu_entries

    # Skills (knowsAbout)
    all_skills = []
    for skill_line in resume_data.get("SKILLS", []):
        clean_line = re.sub(r"\*\*(.*?)\*\*", r"\1", skill_line)
        if ":" in clean_line:
            items = clean_line.split(":", 1)[1]
            all_skills.extend([i.strip() for i in items.split(",") if i.strip()])
        else:
            all_skills.append(clean_line.strip())
    if all_skills:
        schema["knowsAbout"] = all_skills

    return schema


def render_json_ld_string(
    resume_data: Dict[str, Any],
    candidate_meta: Optional[Dict[str, Any]] = None,
    indent: int = 2,
) -> str:
    """Returns formatted JSON-LD string."""
    return json.dumps(render_json_ld(resume_data, candidate_meta), indent=indent)


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER MULTI-FORMAT EXPORT ENGINE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print("  \033[1m\033[38;2;0;164;255mSupported Export Formats:\033[0m")
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Markdown\033[0m         \033[38;2;163;163;163m(Clean semantic GitHub Flavored Markdown)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Plaintext ASCII\033[0m  \033[38;2;163;163;163m(Tab-aligned layout for legacy ATS text boxes)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Schema.org JSON-LD\033[0m\033[38;2;163;163;163m(Structured machine-readable LD-JSON resume data)\033[0m\n"
    )


if __name__ == "__main__":
    main()
