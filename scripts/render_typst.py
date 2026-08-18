"""
render_typst.py — Native Typst Vector PDF Generator for Resume-Builder.

Converts resume JSON directly into Typst (.typ) markup across multiple design
templates (Standard, Executive, Compact, Tech) and compiles it sub-second to clean,
ATS-parseable vector PDFs without headless Chromium overhead.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "templates")


def _escape_typst(text: str) -> str:
    """Escapes special Typst markup characters."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\*\*(.+?)\*\*", r"*\1*", clean)
    for char in ["#", "$", "@", "_", "[", "]"]:
        clean = clean.replace(char, f"\\{char}")
    return clean


def generate_typst_markup(data: Dict[str, Any], template: str = "standard") -> str:
    """Transforms normalized resume JSON into Typst document markup based on selected template."""
    name = _escape_typst(data.get("NAME", "Candidate Name"))
    tagline = _escape_typst(data.get("TAGLINE", ""))
    phone = _escape_typst(data.get("PHONE", ""))
    email = _escape_typst(data.get("EMAIL", ""))
    location = _escape_typst(data.get("LOCATION", ""))
    linkedin = _escape_typst(data.get("LINKEDIN", ""))

    contact_parts = [p for p in [phone, email, location, linkedin] if p]
    contact_line = " | ".join(contact_parts)
    summary = _escape_typst(data.get("SUMMARY_TEXT", ""))
    skills = data.get("SKILLS", [])
    experience = data.get("EXPERIENCE", [])
    education = data.get("EDUCATION", [])

    if template == "executive":
        markup = [
            '#set page(paper: "us-letter", margin: (x: 0.6in, y: 0.6in))',
            '#set text(font: "Libertinus Serif", size: 10pt, fill: rgb("#111827"))',
            "#set par(justify: true, leading: 0.55em)",
            "",
            f'#align(center)[#text(size: 20pt, weight: "bold", tracking: 0.05em)[{name.upper()}]]',
        ]
        if tagline:
            markup.append(
                f'#align(center)[#text(size: 11pt, style: "italic", fill: rgb("#374151"))[{tagline}]]'
            )
        if contact_line:
            markup.append(
                f'#align(center)[#text(size: 8.5pt, fill: rgb("#4b5563"))[{contact_line}]]'
            )
        markup.extend(
            [
                "#v(6pt)",
                '#line(length: 100%, stroke: 1pt + rgb("#111827"))',
                "#v(4pt)",
            ]
        )
        if summary:
            markup.extend(
                [
                    '*#text(size: 11pt, weight: "bold")[EXECUTIVE PROFILE]*',
                    "#v(2pt)",
                    summary,
                    "#v(6pt)",
                ]
            )
        if skills:
            markup.extend(
                [
                    '*#text(size: 11pt, weight: "bold")[CORE LEADERSHIP & TECHNICAL COMPETENCIES]*',
                    "#v(2pt)",
                    " • ".join([_escape_typst(s) for s in skills]),
                    "#v(6pt)",
                ]
            )
        if experience:
            markup.extend(
                [
                    '*#text(size: 11pt, weight: "bold")[PROFESSIONAL EXPERIENCE]*',
                    "#v(2pt)",
                ]
            )
            for job in experience:
                title = _escape_typst(job.get("title", ""))
                company = _escape_typst(job.get("company", ""))
                period = _escape_typst(job.get("period", ""))
                location = _escape_typst(job.get("location", ""))
                markup.append(
                    f'*#text(weight: "bold")[{title}]* — {company} #h(1fr) {period}'
                )
                if location:
                    markup.append(
                        f'#text(size: 8.5pt, style: "italic", fill: rgb("#4b5563"))[{location}]'
                    )
                for bullet in job.get("achievements", []):
                    markup.append(f"- {_escape_typst(bullet)}")
                markup.append("#v(4pt)")
        if education:
            markup.extend(
                [
                    '*#text(size: 11pt, weight: "bold")[EDUCATION & CREDENTIALS]*',
                    "#v(2pt)",
                ]
            )
            for ed in education:
                degree = _escape_typst(ed.get("degree", ""))
                inst = _escape_typst(ed.get("institution", ""))
                year = _escape_typst(ed.get("year", ""))
                year_str = f" ({year})" if year else ""
                markup.append(f"- *{degree}* — {inst}{year_str}")
        return "\n".join(markup)

    elif template == "compact":
        markup = [
            '#set page(paper: "us-letter", margin: (x: 0.4in, y: 0.4in))',
            '#set text(font: "DM Sans", size: 9pt, fill: rgb("#0f172a"))',
            "#set par(justify: true, leading: 0.45em)",
            "",
            f'= text(size: 15pt, weight: "bold")[{name}]',
        ]
        if tagline:
            markup.append(
                f'#text(size: 9.5pt, weight: "medium", fill: rgb("#2563eb"))[{tagline}]'
            )
        if contact_line:
            markup.append(f'#text(size: 8pt, fill: rgb("#475569"))[{contact_line}]')
        markup.extend(
            [
                "#v(2pt)",
                '#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))',
                "#v(2pt)",
            ]
        )
        if summary:
            markup.extend(
                [
                    '*#text(size: 9.5pt, weight: "bold")[SUMMARY]*',
                    summary,
                    "#v(3pt)",
                ]
            )
        if skills:
            markup.extend(
                [
                    '*#text(size: 9.5pt, weight: "bold")[SKILLS]*',
                    " | ".join([_escape_typst(s) for s in skills]),
                    "#v(3pt)",
                ]
            )
        if experience:
            markup.extend(
                [
                    '*#text(size: 9.5pt, weight: "bold")[EXPERIENCE]*',
                    "#v(1pt)",
                ]
            )
            for job in experience:
                title = _escape_typst(job.get("title", ""))
                company = _escape_typst(job.get("company", ""))
                period = _escape_typst(job.get("period", ""))
                markup.append(f"*{title}*, {company} #h(1fr) {period}")
                for bullet in job.get("achievements", []):
                    markup.append(f"- {_escape_typst(bullet)}")
                markup.append("#v(2pt)")
        if education:
            markup.extend(
                [
                    '*#text(size: 9.5pt, weight: "bold")[EDUCATION]*',
                    "#v(1pt)",
                ]
            )
            for ed in education:
                degree = _escape_typst(ed.get("degree", ""))
                inst = _escape_typst(ed.get("institution", ""))
                year = _escape_typst(ed.get("year", ""))
                year_str = f" ({year})" if year else ""
                markup.append(f"- *{degree}*, {inst}{year_str}")
        return "\n".join(markup)

    elif template == "tech":
        markup = [
            '#set page(paper: "us-letter", margin: (x: 0.5in, y: 0.5in))',
            '#set text(font: "DM Sans", size: 9.5pt, fill: rgb("#0f172a"))',
            "#set par(justify: true, leading: 0.5em)",
            "",
            f'= text(size: 18pt, weight: "bold", fill: rgb("#0f172a"))[{name}]',
        ]
        if tagline:
            markup.append(
                f'#text(size: 10pt, weight: "medium", fill: rgb("#0284c7"))[// {tagline}]'
            )
        if contact_line:
            markup.append(f'#text(size: 8.5pt, fill: rgb("#64748b"))[{contact_line}]')
        markup.extend(
            [
                "#v(4pt)",
                '#line(length: 100%, stroke: 1pt + rgb("#0284c7"))',
                "#v(4pt)",
            ]
        )
        if summary:
            markup.extend(
                [
                    '== #text(size: 10.5pt, fill: rgb("#0284c7"))[01 // TECHNICAL SUMMARY]',
                    summary,
                    "#v(5pt)",
                ]
            )
        if skills:
            markup.extend(
                [
                    '== #text(size: 10.5pt, fill: rgb("#0284c7"))[02 // CORE TECHNOLOGIES]',
                    " • ".join([_escape_typst(s) for s in skills]),
                    "#v(5pt)",
                ]
            )
        if experience:
            markup.extend(
                [
                    '== #text(size: 10.5pt, fill: rgb("#0284c7"))[03 // SYSTEMS & ENGINEERING EXPERIENCE]',
                ]
            )
            for job in experience:
                title = _escape_typst(job.get("title", ""))
                company = _escape_typst(job.get("company", ""))
                period = _escape_typst(job.get("period", ""))
                location = _escape_typst(job.get("location", ""))
                meta = f"*{company}* — {location}" if location else f"*{company}*"
                markup.append(f'*text(weight: "bold")[{title}]* #h(1fr) {period}')
                markup.append(f'#text(size: 8.5pt, fill: rgb("#475569"))[{meta}]')
                for bullet in job.get("achievements", []):
                    markup.append(f"- {_escape_typst(bullet)}")
                markup.append("#v(3pt)")
        if education:
            markup.extend(
                [
                    '== #text(size: 10.5pt, fill: rgb("#0284c7"))[04 // EDUCATION & RESEARCH]',
                ]
            )
            for ed in education:
                degree = _escape_typst(ed.get("degree", ""))
                inst = _escape_typst(ed.get("institution", ""))
                year = _escape_typst(ed.get("year", ""))
                markup.append(f"*{degree}* — {inst} #h(1fr) {year}")
        return "\n".join(markup)

    # Standard / Default template
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
    markup.extend(
        [
            "#v(2pt)",
            '#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))',
            "#v(4pt)",
        ]
    )
    if summary:
        markup.extend(["== Executive Summary", summary, "#v(4pt)"])
    if skills:
        markup.extend(
            [
                "== Technical & Core Competencies",
                " • ".join([_escape_typst(s) for s in skills]),
                "#v(4pt)",
            ]
        )
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
            for bullet in job.get("achievements", []):
                markup.append(f"- {_escape_typst(bullet)}")
            markup.append("#v(3pt)")
    if education:
        markup.append("== Education")
        for ed in education:
            degree = _escape_typst(ed.get("degree", ""))
            inst = _escape_typst(ed.get("institution", ""))
            year = _escape_typst(ed.get("year", ""))
            markup.append(f"*{degree}* — {inst} #h(1fr) {year}")

    return "\n".join(markup)


def render_typst(json_path: str, pdf_path: str, template: str = "standard") -> bool:
    """Reads resume JSON, generates .typ file, and compiles to PDF."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        typ_path = pdf_path.replace(".pdf", ".typ")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

        typ_content = generate_typst_markup(data, template=template)
        with open(typ_path, "w", encoding="utf-8") as f:
            f.write(typ_content)

        if shutil.which("typst") is not None:
            result = subprocess.run(
                ["typst", "compile", typ_path, pdf_path],
                capture_output=True,
                text=True,
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


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Render Typst vector PDF from JSON.")
    parser.add_argument("json_file", help="Path to resume JSON file")
    parser.add_argument("pdf_file", help="Path to target output PDF file")
    parser.add_argument(
        "-t",
        "--template",
        choices=["standard", "executive", "compact", "tech"],
        default="standard",
        help="Template style to render",
    )
    args = parser.parse_args(argv)
    success = render_typst(args.json_file, args.pdf_file, template=args.template)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
