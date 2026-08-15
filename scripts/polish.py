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
import shutil
import subprocess

import questionary

import cli_art
import normalize_resume
import profile_paths
import theme
import validate_coverletter
import validate_resume
from gemini_client import GeminiClient
from orchestrator import (
    BUILDER_MODEL, CoverLetterSchema, PDF_GENERATION_TIMEOUT_SECONDS, ResumeEngine, TemplateSchema,
)
from render_coverletter import render_coverletter
from render_html import render_html

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_JSON_DIR = os.path.join(profile_paths.output_dir(), "json")
OUTPUT_HTML_DIR = os.path.join(profile_paths.output_dir(), "html")
OUTPUT_PDF_DIR = os.path.join(profile_paths.output_dir(), "pdf")

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


# Flattened from cli_art's existing schema-key -> human-label map (shared
# with the fit-dimension comparison table) rather than hand-rolling a
# second one here -- see _label_for_key()'s fallback for keys this map
# doesn't cover (which is most of TemplateSchema/CoverLetterSchema's
# fields today, since that map was built for evaluation subscores, not
# the builder schema; the fallback is what actually carries this file).
_SCHEMA_KEY_LABELS: dict[str, str] = {}
for _group_label, _subscores_key, _dim_labels in cli_art._FIT_DIMENSION_GROUPS:
    _SCHEMA_KEY_LABELS.update(_dim_labels)

_EXPERIENCE_FIELD_LABELS = {
    "title": "Title", "company": "Company", "period": "Period",
    "location": "Location", "career_note": "Career Note",
}


def _label_for_key(key: str) -> str:
    """Human-readable label for a schema field -- never the raw
    ALL-CAPS/snake_case key a job seeker has no reason to recognize."""
    if key in _SCHEMA_KEY_LABELS:
        return _SCHEMA_KEY_LABELS[key]
    return key.replace("_", " ").strip().title()


def _format_value(value) -> str:
    """Readable text for a diff value -- never repr(), which would show
    Python's quote/list syntax (e.g. "['foo', 'bar']") to a job seeker
    reviewing edits to their own resume."""
    if value is None:
        return "(empty)"
    if isinstance(value, list):
        return "; ".join(str(v) for v in value) if value else "(empty)"
    text = str(value).strip()
    return text or "(empty)"


def _render_field_diff(label: str, old_val, new_val) -> list[str]:
    """One changed field as Rich-markup lines: a bold label heading, then
    the old value under the error icon/color and the new value under the
    success icon/color -- color is never the only signal, per house
    style (theme.colorize_icon() bakes color and glyph together)."""
    removed_icon = theme.colorize_icon("error")
    added_icon = theme.colorize_icon("success")
    return [
        f"[bold]{label}[/bold]",
        f"  {removed_icon} [{theme.ERROR}]{_format_value(old_val)}[/{theme.ERROR}]",
        f"  {added_icon} [{theme.SUCCESS}]{_format_value(new_val)}[/{theme.SUCCESS}]",
    ]


def _diff_list(label: str, old_list: list, new_list: list) -> list[str]:
    lines = []
    for i in range(max(len(old_list), len(new_list))):
        old_item = old_list[i] if i < len(old_list) else None
        new_item = new_list[i] if i < len(new_list) else None
        if old_item != new_item:
            lines.extend(_render_field_diff(f"{label} #{i + 1}", old_item, new_item))
    return lines


def _diff_experience(old_jobs: list, new_jobs: list) -> list[str]:
    lines = []
    for i in range(max(len(old_jobs), len(new_jobs))):
        old_job = old_jobs[i] if i < len(old_jobs) else {}
        new_job = new_jobs[i] if i < len(new_jobs) else {}
        if old_job == new_job:
            continue
        role_label = f"Experience #{i + 1}"
        for field, field_label in _EXPERIENCE_FIELD_LABELS.items():
            if old_job.get(field) != new_job.get(field):
                lines.extend(_render_field_diff(
                    f"{role_label} — {field_label}", old_job.get(field), new_job.get(field),
                ))
        lines.extend(_diff_list(
            f"{role_label} — Achievement",
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
    comparison. Every line is Rich markup (icon + theme color), meant to
    be printed through cli_art.console, not plain print()."""
    lines = []
    for key in keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val == new_val:
            continue
        label = _label_for_key(key)
        if key == "EXPERIENCE" and isinstance(old_val, list) and isinstance(new_val, list):
            lines.extend(_diff_experience(old_val, new_val))
        elif isinstance(old_val, list) and isinstance(new_val, list):
            lines.extend(_diff_list(label, old_val, new_val))
        else:
            lines.extend(_render_field_diff(label, old_val, new_val))
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
    if doc_type != "resume":
        # B54 (phase-9-backlog.md): resume-engine/scoring/ predates the
        # cover-letter path, so polish_coverletter.md ran with no scoring
        # rubric at all -- believability.yaml and ai_risk.yaml are the
        # smallest useful attachment (metric-credibility and AI-pattern
        # checks apply to cover-letter prose just as much as to a resume).
        believability_rules = json.dumps(engine.load_yaml(engine.scoring_dir, "believability.yaml"))
        ai_risk_rules = json.dumps(engine.load_yaml(engine.scoring_dir, "ai_risk.yaml"))
        system_instruction += (
            f"\n\nBELIEVABILITY SCORING RUBRIC:\n{believability_rules}"
            f"\n\nAI RISK SCORING RUBRIC:\n{ai_risk_rules}"
        )
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


# A confirm-before-save was tried here first and reverted -- the user has
# already deliberately chosen "accept" by that point, so a second gate is
# just friction on the common case, not real protection. Undo is the
# actual fix: the previous version is always one file away, so a bad
# Gemini edit is recoverable without ever needing to answer a prompt.
#
# One backup per document (not a numbered history) is a deliberate
# simplicity choice: it recovers the one accident that actually happens
# in practice -- "that last edit was wrong" -- without turning
# output/json/ into an ever-growing pile of *.bak.N files nobody prunes.
BACKUP_SUFFIX = ".bak"


def backup_path_for(json_path: str) -> str:
    """Sibling backup path for a polish target -- one per document, so a
    second accept overwrites the first backup rather than stacking up."""
    return json_path + BACKUP_SUFFIX


def save_and_render(doc: dict, doc_type: str, json_path: str) -> dict:
    """Saves `doc` to json_path, re-renders its HTML, and regenerates its
    PDF via generate-pdf.mjs. Returns {"json": ..., "html": ..., "pdf":
    ..., "backup": ...} -- "pdf" is None if PDF generation failed
    (JSON/HTML are still saved in that case; the caller decides what to
    tell the user). "backup" is the path the PREVIOUS on-disk version was
    copied to before being overwritten, or None on a document's first
    save (nothing existed yet to back up). Only the JSON is backed up --
    HTML/PDF are both fully derived from it, so restoring the JSON and
    re-rendering recovers everything a bad edit could have broken."""
    backup_path = None
    if os.path.exists(json_path):
        backup_path = backup_path_for(json_path)
        shutil.copy2(json_path, backup_path)

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
    try:
        result = subprocess.run(
            ["node", pdf_script, html_path, pdf_path, "--format=letter"],
            capture_output=True, text=True, timeout=PDF_GENERATION_TIMEOUT_SECONDS,
            env={**os.environ, "RESUME_BUILDER_ICONS": theme.icon_set_name()},
        )
    except subprocess.TimeoutExpired:
        cli_art.console.print(
            f"{cli_art.WARNING} PDF generation timed out after {PDF_GENERATION_TIMEOUT_SECONDS}s "
            "(JSON/HTML were still saved)."
        )
        return {"json": json_path, "html": html_path, "pdf": None, "backup": backup_path}
    if result.returncode != 0:
        cli_art.friendly_subprocess_error(result.stderr, "creating the polished PDF")
        # Stated after the error, not inside it: the failure is the headline,
        # but a user who just spent Gemini calls on this needs to know their
        # edits survived and only the render step is missing.
        cli_art.cli_info("Your polished JSON and HTML were still saved -- only the PDF is missing.")
        return {"json": json_path, "html": html_path, "pdf": None, "backup": backup_path}

    return {"json": json_path, "html": html_path, "pdf": pdf_path, "backup": backup_path}


_POLISH_PAGE_SIZE = 50
_POLISH_NAV_PREV = "__polish_prev_page__"
_POLISH_NAV_NEXT = "__polish_next_page__"
_POLISH_NAV_BACK = "__polish_back__"


def pick_polish_target(page_size: int = _POLISH_PAGE_SIZE) -> str | None:
    """Interactive picker over every recognized output/json file, newest
    first -- paginated the same way as the JD pickers in picker.py (a
    bordered "blue box" table per page via cli_art.render_polish_table(),
    prominent bold/colored Previous/Next nav choices), for visual
    consistency across every large picker in this program. This one is a
    single-select prompt (exactly one document gets polished per
    session), so choosing a real document ends the picker immediately --
    there's no separate "Done" step the way the multi-select JD pickers
    need. Returns None if there's nothing to pick (empty dir, or the
    user cancels)."""
    paths = sorted(
        glob.glob(os.path.join(OUTPUT_JSON_DIR, "*.json")),
        key=os.path.getmtime, reverse=True,
    )
    paths = [p for p in paths if detect_doc_type(p) is not None]
    if not paths:
        return None

    total_pages = (len(paths) + page_size - 1) // page_size
    page = 0

    while True:
        start = page * page_size
        end = min(start + page_size, len(paths))
        page_paths = paths[start:end]
        page_rows = [
            {"path": p, "label": "Resume" if detect_doc_type(p) == "resume" else "Cover Letter"}
            for p in page_paths
        ]

        cli_art.render_polish_table(
            page_rows, start_index=start + 1,
            title=f"Page {page + 1}/{total_pages} -- rows {start + 1}-{end} of {len(paths)} document(s)",
        )

        choices = [
            questionary.Choice(title=f"{i:>4}  [{r['label']}] {os.path.basename(r['path'])}", value=r["path"])
            for i, r in enumerate(page_rows, start=start + 1)
        ]
        choices.append(questionary.Separator())
        if page > 0:
            choices.append(questionary.Choice(
                title=[(f"fg:{theme.BRAND_ACCENT} bold", f"{theme.ICONS['prev']} Previous page")], value=_POLISH_NAV_PREV,
            ))
        if page < total_pages - 1:
            choices.append(questionary.Choice(
                title=[(f"fg:{theme.BRAND_ACCENT} bold", f"{theme.ICONS['next']} Next page")], value=_POLISH_NAV_NEXT,
            ))
        choices.append(questionary.Choice(
            title=[(f"fg:{theme.BRAND_ACCENT} bold", f"{theme.ICONS['back']} Back to Main Menu")], value=_POLISH_NAV_BACK,
        ))

        result = questionary.select(
            "Which document do you want to polish?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if result is None or result == _POLISH_NAV_BACK:
            return None
        if result == _POLISH_NAV_PREV:
            page -= 1
        elif result == _POLISH_NAV_NEXT:
            page += 1
        else:
            return result


_EXIT_WORDS = {"", "done", "exit", "quit"}


def run_polish_session(json_path: str) -> None:
    """Runs the interactive polish loop against json_path until the user
    exits. Each turn: prompt for an instruction, generate a candidate,
    show its diff, then accept (save + re-render) / reject (discard,
    keep chatting) / quit."""
    doc_type = detect_doc_type(json_path)
    if doc_type is None:
        cli_art.console.print(
            f"{cli_art.ERROR} {json_path} doesn't end in {RESUME_SUFFIX} or {COVERLETTER_SUFFIX} -- "
            "can't tell which schema to polish against."
        )
        return
    if not os.path.exists(json_path):
        cli_art.console.print(f"{cli_art.ERROR} File not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    engine = ResumeEngine()
    fields = RESUME_FIELDS if doc_type == "resume" else COVERLETTER_FIELDS

    cli_art.console.print(f"\nPolishing {os.path.basename(json_path)}. Type 'done' to finish.\n")

    while True:
        try:
            instruction = questionary.text("polish>", style=cli_art.QUESTIONARY_STYLE).ask()
        except (KeyboardInterrupt, EOFError):
            instruction = None

        if instruction is None or instruction.strip().lower() in _EXIT_WORDS:
            break

        candidate = generate_candidate(doc, instruction, doc_type, engine)
        if candidate is None:
            cli_art.console.print(f"{cli_art.WARNING} No parseable response -- try rephrasing.")
            continue

        diff_lines = diff_documents(doc, candidate, fields)
        if not diff_lines:
            cli_art.console.print("Nothing changed -- try rephrasing.")
            continue

        cli_art.console.print("\n".join(diff_lines))
        decision = questionary.select(
            "Apply this change?",
            choices=[
                questionary.Choice(title="Accept", value="accept"),
                questionary.Choice(title="Reject and rephrase", value="reject"),
                questionary.Choice(title="Quit", value="quit"),
            ],
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if decision == "quit" or decision is None:
            break
        if decision == "reject":
            continue

        doc = candidate
        paths = save_and_render(doc, doc_type, json_path)
        cli_art.console.print(f"{cli_art.SUCCESS} Saved -> {paths['json']}")
        if paths["pdf"]:
            cli_art.console.print(f"{cli_art.SUCCESS} PDF -> {paths['pdf']}")
        # No confirm-before-save here on purpose (see save_and_render's own
        # comment) -- "accept" already IS the user's confirmation. This is
        # the actual safety net: the version that was just overwritten is
        # still sitting right next to it.
        if paths.get("backup"):
            cli_art.console.print(
                f"{cli_art.HINT} Previous version backed up -> {paths['backup']} "
                "(copy it back over the JSON above to undo this edit)"
            )

    cli_art.console.print("\nDone polishing.\n")


def run(file: str | None = None) -> None:
    """Entry point wired from cli.py's `resume polish [FILE]` command and
    menu.py's interactive-menu entry. Uses `file` if given, otherwise
    launches the interactive picker."""
    json_path = file or pick_polish_target()
    if not json_path:
        cli_art.console.print("Nothing to polish -- no output/json files found.")
        return
    run_polish_session(json_path)
