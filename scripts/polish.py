"""
polish.py -- interactive chat loop for polishing an already-generated
resume or cover letter's JSON. Each turn sends the current document plus
one plain-English instruction to Gemini (schema-constrained, same
schema/model the builder already uses) and gets back the complete
updated document; a diff of exactly what changed is shown before
anything is saved. Accepting a turn re-renders HTML and regenerates the
PDF immediately, same as the main tailoring pipeline.
"""

import glob
import json
import os
import subprocess

import questionary

import cli_art
import normalize_resume
import validate_coverletter
import validate_resume
from gemini_client import GeminiClient
from orchestrator import BUILDER_MODEL, CoverLetterSchema, ResumeEngine, TemplateSchema
from render_coverletter import render_coverletter
from render_html import render_html

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_JSON_DIR = os.path.join(PROJECT_ROOT, "output", "json")
OUTPUT_HTML_DIR = os.path.join(PROJECT_ROOT, "output", "html")
OUTPUT_PDF_DIR = os.path.join(PROJECT_ROOT, "output", "pdf")

RESUME_SUFFIX = "_Resume.json"
COVERLETTER_SUFFIX = "_CoverLetter.json"

RESUME_FIELDS = list(TemplateSchema.model_fields.keys())
COVERLETTER_FIELDS = list(CoverLetterSchema.model_fields.keys())


def detect_doc_type(path: str) -> str | None:
    """Returns "resume", "coverletter", or None if the filename doesn't
    end in a recognized suffix."""
    name = os.path.basename(path)
    if name.endswith(RESUME_SUFFIX):
        return "resume"
    if name.endswith(COVERLETTER_SUFFIX):
        return "coverletter"
    return None


def stem_from_json_path(path: str, doc_type: str) -> str:
    """Strips the doc_type's known suffix, returning the shared stem used
    to derive matching html/pdf output paths."""
    name = os.path.basename(path)
    suffix = RESUME_SUFFIX if doc_type == "resume" else COVERLETTER_SUFFIX
    return name[: -len(suffix)]


def _diff_list(label: str, old_list: list, new_list: list) -> list[str]:
    lines = []
    for i in range(max(len(old_list), len(new_list))):
        old_item = old_list[i] if i < len(old_list) else None
        new_item = new_list[i] if i < len(new_list) else None
        if old_item != new_item:
            lines.append(f"{label}[{i}]:\n  - {old_item!r}\n  + {new_item!r}")
    return lines


def _diff_experience(old_jobs: list, new_jobs: list) -> list[str]:
    lines = []
    scalar_fields = ("title", "company", "period", "location", "career_note")
    for i in range(max(len(old_jobs), len(new_jobs))):
        old_job = old_jobs[i] if i < len(old_jobs) else {}
        new_job = new_jobs[i] if i < len(new_jobs) else {}
        if old_job == new_job:
            continue
        for field in scalar_fields:
            if old_job.get(field) != new_job.get(field):
                lines.append(
                    f"EXPERIENCE[{i}].{field}:\n  - {old_job.get(field)!r}\n  + {new_job.get(field)!r}"
                )
        lines.extend(_diff_list(
            f"EXPERIENCE[{i}].achievements",
            old_job.get("achievements", []),
            new_job.get("achievements", []),
        ))
    return lines


def diff_documents(old: dict, new: dict, keys: list[str]) -> list[str]:
    """Field-by-field diff restricted to `keys` (a schema's own field
    list -- contact info/certifications/education/_recommendation_actions
    are never in `keys`, so they never surface here, since a polish turn
    can't touch them anyway). EXPERIENCE gets element-and-field-level
    treatment via _diff_experience; other list fields (e.g.
    body_paragraphs) via _diff_list; everything else is a plain scalar
    comparison."""
    lines = []
    for key in keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val == new_val:
            continue
        if key == "EXPERIENCE" and isinstance(old_val, list) and isinstance(new_val, list):
            lines.extend(_diff_experience(old_val, new_val))
        elif isinstance(old_val, list) and isinstance(new_val, list):
            lines.extend(_diff_list(key, old_val, new_val))
        else:
            lines.append(f"{key}:\n  - {old_val!r}\n  + {new_val!r}")
    return lines


def generate_candidate(doc: dict, instruction: str, doc_type: str, engine: ResumeEngine) -> dict | None:
    """Sends the current document's schema-relevant fields plus one
    instruction to Gemini and returns the complete updated document, or
    None if the response was unparseable. Resume responses are re-run
    through normalize_resume.normalize() (idempotent -- reapplies fixed
    contact/cert/education fields and formatting rules) and have
    _recommendation_actions (not part of TemplateSchema) reattached
    unchanged if the original had it."""
    if doc_type == "resume":
        schema = TemplateSchema
        prompt_file = "polish_resume.md"
        fields = RESUME_FIELDS
    else:
        schema = CoverLetterSchema
        prompt_file = "polish_coverletter.md"
        fields = COVERLETTER_FIELDS

    sendable = {k: doc.get(k) for k in fields}
    system_instruction = engine.load_prompt(prompt_file)
    contents = (
        f"=== CURRENT DOCUMENT JSON ===\n{json.dumps(sendable, indent=2)}\n\n"
        f"=== REQUESTED EDIT ===\n{instruction}"
    )

    text, _usage = GeminiClient.generate(
        model=BUILDER_MODEL,
        system_instruction=system_instruction,
        contents=contents,
        response_schema=schema,
        temperature=0.0,
    )
    result = GeminiClient.parse_json(text or "")
    if not result:
        return None

    style_rules = engine.load_yaml(engine.rules_dir, "style_rules.yaml")
    if doc_type == "resume":
        candidate = normalize_resume.normalize(result)
        if "_recommendation_actions" in doc:
            candidate["_recommendation_actions"] = doc["_recommendation_actions"]
        violations = validate_resume.validate(candidate, style_rules)
    else:
        candidate = result
        violations = validate_coverletter.validate(candidate, style_rules)

    if violations:
        cli_art.console.print(f"{cli_art.WARNING} Validator found {len(violations)} issue(s) in this edit:")
        for v in violations:
            cli_art.console.print(f"  - {v}")

    return candidate


def save_and_render(doc: dict, doc_type: str, json_path: str) -> dict:
    """Saves `doc` to json_path, re-renders its HTML, and regenerates its
    PDF via generate-pdf.mjs. Returns {"json": ..., "html": ..., "pdf":
    ...} -- "pdf" is None if PDF generation failed (JSON/HTML are still
    saved in that case; the caller decides what to tell the user)."""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    stem = stem_from_json_path(json_path, doc_type)
    suffix = "_Resume" if doc_type == "resume" else "_CoverLetter"
    html_path = os.path.join(OUTPUT_HTML_DIR, f"{stem}{suffix}.html")
    pdf_path = os.path.join(OUTPUT_PDF_DIR, f"{stem}{suffix}.pdf")
    os.makedirs(os.path.dirname(html_path), exist_ok=True)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    if doc_type == "resume":
        render_html(doc, html_path)
    else:
        render_coverletter(doc, html_path)

    pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
    result = subprocess.run(
        ["node", pdf_script, html_path, pdf_path, "--format=letter"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        cli_art.console.print(
            f"{cli_art.WARNING} PDF generation failed (JSON/HTML were still saved):\n{result.stderr}"
        )
        return {"json": json_path, "html": html_path, "pdf": None}

    return {"json": json_path, "html": html_path, "pdf": pdf_path}


def pick_polish_target() -> str | None:
    """Interactive picker over every recognized output/json file, newest
    first. Returns None if there's nothing to pick (empty dir, or the
    user cancels)."""
    paths = sorted(
        glob.glob(os.path.join(OUTPUT_JSON_DIR, "*.json")),
        key=os.path.getmtime, reverse=True,
    )
    choices = []
    for p in paths:
        doc_type = detect_doc_type(p)
        if doc_type is None:
            continue
        label = "Resume" if doc_type == "resume" else "Cover Letter"
        choices.append(questionary.Choice(title=f"[{label}] {os.path.basename(p)}", value=p))
    if not choices:
        return None
    return questionary.select(
        "Which document do you want to polish?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
