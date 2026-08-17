"""
render_typst.py — Native Typst Vector PDF Generator for Resume-Builder.

Converts resume JSON directly into Typst (.typ) markup and compiles it
sub-second to clean, ATS-parseable vector PDFs without headless Chromium overhead.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def _escape_typst(text: str) -> str:
    """Escapes special Typst markup characters."""
    if not text:
        return ""
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Convert bold markdown **foo** to Typst *foo*
    clean = re.sub(r"\*\*(.+?)\*\*", r"*\1*", clean)
    # Escape Typst special symbols: #, $, @, _, [, ]
    for char in ["#", "$", "@", "_", "[", "]"]:
        clean = clean.replace(char, f"\\{char}")
    return clean


def generate_typst_markup(data: Dict[str, Any]) -> str:
    """Transforms normalized resume JSON into Typst document markup."""
    name = _escape_typst(data.get("NAME", "Candidate Name"))
    tagline = _escape_typst(data.get("TAGLINE", ""))
    phone = _escape_typst(data.get("PHONE", ""))
    email = _escape_typst(data.get("EMAIL", ""))
    location = _escape_typst(data.get("LOCATION", ""))
    linkedin = _escape_typst(data.get("LINKEDIN", ""))

    contact_parts = [p for p in [phone, email, location, linkedin] if p]
    contact_line = " | ".join(contact_parts)

    summary = _escape_typst(data.get("SUMMARY_TEXT", ""))

    # Header
    markup = [
        '#set page(paper: "us-letter", margin: (x: 0.5in, y: 0.5in))',
        '#set text(font: "DM Sans", size: 9.5pt, fill: rgb("#1e293b"))',
        "#set par(justify: true, leading: 0.52em)",
        "",
        f'= text(size: 18pt, weight: "bold", fill: rgb("#0f172a"))[{name}]',
    ]

    if tagline:
        markup.append(
            f'#text(size: 10.5pt, weight: "medium", fill: rgb("#3b82f6"))[{tagline}]'
        )

    if contact_line:
        markup.append(f'#text(size: 8.5pt, fill: rgb("#64748b"))[{contact_line}]')

    markup.append("#v(2pt)")
    markup.append('#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))')
    markup.append("#v(4pt)")

    # Summary
    if summary:
        markup.append("== Executive Summary")
        markup.append(summary)
        markup.append("#v(4pt)")

    # Skills
    skills = data.get("SKILLS", [])
    if skills:
        markup.append("== Technical & Core Competencies")
        skill_items = " • ".join([_escape_typst(s) for s in skills])
        markup.append(skill_items)
        markup.append("#v(4pt)")

    # Experience
    experience = data.get("EXPERIENCE", [])
    if experience:
        markup.append("== Professional Experience")
        for job in experience:
            title = _escape_typst(job.get("title", ""))
            company = _escape_typst(job.get("company", ""))
            period = _escape_typst(job.get("period", ""))
            location = _escape_typst(job.get("location", ""))
            meta_line = f"*{company}* — {location}" if location else f"*{company}*"

            markup.append(f'*text(weight: "bold")[{title}]* #h(1fr) {period}')
            markup.append(f'#text(size: 8.5pt, fill: rgb("#475569"))[{meta_line}]')

            achievements = job.get("achievements", [])
            for bullet in achievements:
                clean_b = _escape_typst(bullet)
                markup.append(f"- {clean_b}")
            markup.append("#v(3pt)")

    # Education & Certifications
    education = data.get("EDUCATION", [])
    if education:
        markup.append("== Education")
        for ed in education:
            degree = _escape_typst(ed.get("degree", ""))
            inst = _escape_typst(ed.get("institution", ""))
            year = _escape_typst(ed.get("year", ""))
            markup.append(f"*{degree}* — {inst} #h(1fr) {year}")

    return "\n".join(markup)


def render_typst(json_path: str, pdf_path: str) -> bool:
    """Reads resume JSON, generates .typ file, and compiles to PDF."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        typ_path = pdf_path.replace(".pdf", ".typ")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

        typ_content = generate_typst_markup(data)
        with open(typ_path, "w", encoding="utf-8") as f:
            f.write(typ_content)

        # Check for typst CLI binary
        if shutil.which("typst") is not None:
            result = subprocess.run(
                ["typst", "compile", typ_path, pdf_path], capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"✓ Typst PDF generated: {pdf_path}")
                return True
            else:
                print(f"Typst compilation warning/error: {result.stderr}")
                return False
        else:
            print(f"Typst source saved to {typ_path} (typst binary not found in PATH).")
            return True
    except Exception as e:
        print(f"Error rendering Typst PDF: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        render_typst(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python scripts/render_typst.py <input.json> <output.pdf>")
