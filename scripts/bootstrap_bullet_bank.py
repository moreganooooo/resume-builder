#!/usr/bin/env python3
"""
bootstrap_bullet_bank.py

Bootstraps a starter bullet bank for a new resume-builder user from a
folder of arbitrary personal documents (LinkedIn PDF export, resume,
recommendation letters, achievement notes, certificates, etc.), then
guides them through the existing six-stage pipeline (audit -> cluster ->
rewrite -> audit_keepers -> score_keeper_gems -> embed).

Phase 0 (this file's ingestion logic) is local/fast: extract, attribute to
a company via a resume/LinkedIn-anchored timeline, auto-tag, and write
bullet-bank-clean.csv directly -- there's no existing file to protect on a
first run, so no manual promotion step is needed.

Phases 1-6 call the existing pipeline scripts unmodified, as subprocesses,
with a confirmation gate before each of the two API-heavy stages
(audit_bullet_bank.py, rewrite_bullets.py). See run_full_pipeline() further
down this file (added in a later task).

Usage:
  python bootstrap_bullet_bank.py             # full run, with confirmation gates
  python bootstrap_bullet_bank.py --yes        # full run, unattended
"""

import csv
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR = profile_paths.kb_dir()

BOOTSTRAP_DIR = os.path.join(KB_DIR, "bootstrap")
SOURCE_DOCS_DIR = os.path.join(BOOTSTRAP_DIR, "source_documents")
TIMELINE_PATH = os.path.join(BOOTSTRAP_DIR, "timeline.json")
CHECKPOINT_PATH = os.path.join(BOOTSTRAP_DIR, "checkpoint.json")
DRAFT_CSV_PATH = os.path.join(BOOTSTRAP_DIR, "bullet-bank-draft.csv")
REVIEW_CSV_PATH = os.path.join(BOOTSTRAP_DIR, "review-needed.csv")
CERTIFICATIONS_PATH = os.path.join(BOOTSTRAP_DIR, "certifications.json")
BULLET_BANK_CLEAN_PATH = os.path.join(KB_DIR, "bullet-bank-clean.csv")

_FIXED_CONTENT_SCAFFOLD = '''"""fixed_content.py — this profile's contact info, company facts, and
fixed credentials. Fill in real values as they become known; every dict
here may start empty and grow over time."""

CONTACT_INFO = {
    "NAME": "",
    "PHONE": "",
    "EMAIL": "",
    "LINKEDIN_DISPLAY": "",
    "LOCATION": "",
}

COMPANY_META = {}
COMPANY_TITLE_DESCRIPTOR = {}
CLIENTS = {}
COMPANY_RENAME_NOTE = {}
COMPANY_FIXED_TITLE = {}
CAREER_NOTE = ""
CAREER_NOTE_COMPANY = ""
CERTIFICATIONS = []
CV_SECTION_KEYWORDS = []
BACKGROUND_IDENTITY = ""
BACKGROUND_TAGS = {}


def build_education(achievement_keys: dict = None) -> list:
    return []
'''

_SITUATIONAL_ROLES_SCAFFOLD = """situational_min_bullets: 2
roles: []
"""


def create_new_profile(name: str) -> str:
    """Scaffolds a fresh profiles/<name>/ directory: knowledge_base/ (plus
    its bootstrap/source_documents/ subfolder), a blank fixed_content.py,
    an empty situational_roles.yaml, and .stignore files in every one of
    this profile's sync roots (profile_paths.write_sync_ignore_files())
    so it's ready for Syncthing out of the box. Raises FileExistsError if
    the profile already exists -- never silently overwrites one."""
    import profile_paths

    profile_root = os.path.join(profile_paths.PROFILES_DIR, name)
    if os.path.isdir(profile_root):
        raise FileExistsError(f"profiles/{name}/ already exists -- refusing to overwrite it.")

    os.makedirs(os.path.join(profile_root, "knowledge_base", "bootstrap", "source_documents"))

    with open(os.path.join(profile_root, "fixed_content.py"), "w") as f:
        f.write(_FIXED_CONTENT_SCAFFOLD)

    with open(os.path.join(profile_root, "situational_roles.yaml"), "w") as f:
        f.write(_SITUATIONAL_ROLES_SCAFFOLD)

    profile_paths.write_sync_ignore_files(name)

    return profile_root


import bootstrap_extractors  # noqa: E402
import bootstrap_profile  # noqa: E402
import bootstrap_timeline  # noqa: E402
import tag_bullet_bank  # noqa: E402
import theme  # noqa: E402

DRAFT_CSV_FIELDS = ["Role / Company", "Tags", "Bullet Point", "source_file", "source_type"]


def _load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT_PATH):
        return {}
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_checkpoint(state: dict) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _process_one_file(path: str, filename: str, dry_run: bool = False) -> dict:
    kind = bootstrap_extractors.detect_file_kind(path)
    if kind == "unsupported":
        print(f"  Skipping {filename}: unsupported file type.")
        return {"status": "error", "doc_type": "other"}

    if kind == "doc":
        converted = bootstrap_extractors.convert_legacy_doc_to_pdf(path)
        if converted is None:
            print(
                f"  Skipping {filename}: legacy .doc format and LibreOffice isn't "
                f"available. Please re-save it as .docx or .pdf."
            )
            return {"status": "error", "doc_type": "other"}
        path, kind = converted, "pdf"

    text = None if kind in ("pdf", "image") else bootstrap_extractors.extract_local_text(path, kind)
    doc_type = bootstrap_extractors.classify_document_type(filename, text, dry_run=dry_run)

    if doc_type == "certificate":
        cert = (
            bootstrap_extractors.extract_certificate(upload_path=path, dry_run=dry_run)
            if text is None
            else bootstrap_extractors.extract_certificate(text=text, dry_run=dry_run)
        )
        return {"status": "done", "doc_type": doc_type, "certificate": cert.model_dump() if cert else None}

    if doc_type in ("resume", "linkedin_export"):
        resume_extraction = (
            bootstrap_extractors.extract_resume_timeline_and_achievements(upload_path=path, dry_run=dry_run)
            if text is None
            else bootstrap_extractors.extract_resume_timeline_and_achievements(text=text, dry_run=dry_run)
        )
        return {
            "status": "done",
            "doc_type": doc_type,
            "work_experience": [e.model_dump() for e in resume_extraction.experience],
            "certificates_found": [c.model_dump() for c in resume_extraction.certifications],
        }

    achievements = (
        bootstrap_extractors.extract_achievements(doc_type, upload_path=path, dry_run=dry_run)
        if text is None
        else bootstrap_extractors.extract_achievements(doc_type, text=text, dry_run=dry_run)
    )
    return {"status": "done", "doc_type": doc_type, "achievements": [a.model_dump() for a in achievements]}


def _write_timeline(timeline: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(TIMELINE_PATH, "w", encoding="utf-8") as f:
        json.dump([e.model_dump() for e in timeline], f, indent=2)


def _write_draft_csv(matched_rows: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(DRAFT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DRAFT_CSV_FIELDS)
        writer.writeheader()
        for company, bullet, filename, doc_type, _confidence in matched_rows:
            writer.writerow({
                "Role / Company": company, "Tags": "", "Bullet Point": f"- {bullet}",
                "source_file": filename, "source_type": doc_type,
            })


def _write_review_csv(review_rows: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    if not review_rows:
        if os.path.exists(REVIEW_CSV_PATH):
            os.remove(REVIEW_CSV_PATH)
        return
    with open(REVIEW_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DRAFT_CSV_FIELDS)
        writer.writeheader()
        for company, bullet, filename, doc_type, _confidence in review_rows:
            writer.writerow({
                "Role / Company": company, "Tags": "", "Bullet Point": f"- {bullet}",
                "source_file": filename, "source_type": doc_type,
            })


def _write_certifications(certificates: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(CERTIFICATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(certificates, f, indent=2)


def _write_bullet_bank_clean(matched_rows: list) -> None:
    """Auto-tags every row (reusing tag_bullet_bank.assign_tags directly,
    in-process -- not shelled out to) and writes the final
    bullet-bank-clean.csv. No manual promotion step: a first-time user has
    no existing file at risk of being overwritten."""
    rows = []
    for company, bullet, _filename, _doc_type, _confidence in matched_rows:
        bullet_text = f"- {bullet}"
        tag_str, _needs_review = tag_bullet_bank.assign_tags(bullet_text)
        rows.append({"Role / Company": company, "Tags": tag_str, "Bullet Point": bullet_text})

    os.makedirs(os.path.dirname(BULLET_BANK_CLEAN_PATH), exist_ok=True)
    with open(BULLET_BANK_CLEAN_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point"])
        writer.writeheader()
        writer.writerows(rows)


def run_ingestion(dry_run: bool = False) -> dict:
    """Runs Phase 0 end to end: extract every file in source_documents/,
    build a timeline from any resume/LinkedIn doc(s), attribute every other
    achievement against it, then auto-tag and write bullet-bank-clean.csv.
    Returns a summary dict: {extracted, attributed, flagged, certificates}."""
    os.makedirs(SOURCE_DOCS_DIR, exist_ok=True)
    checkpoint = _load_checkpoint()

    filenames = sorted(
        f for f in os.listdir(SOURCE_DOCS_DIR)
        if os.path.isfile(os.path.join(SOURCE_DOCS_DIR, f))
    )

    for filename in filenames:
        if checkpoint.get(filename, {}).get("status") == "done":
            continue
        path = os.path.join(SOURCE_DOCS_DIR, filename)
        try:
            checkpoint[filename] = _process_one_file(path, filename, dry_run=dry_run)
        except Exception as e:
            print(f"  Error processing {filename}: {e}")
            checkpoint[filename] = {"status": "error", "doc_type": "other"}
        _save_checkpoint(checkpoint)

    by_source: dict[str, list] = {}
    already_attributed_rows = []
    pending_achievements = []
    certificates = []

    for filename, result in checkpoint.items():
        if result.get("status") != "done":
            continue
        doc_type = result["doc_type"]
        if doc_type in ("resume", "linkedin_export"):
            entries = [bootstrap_extractors.WorkExperienceEntry(**e) for e in result.get("work_experience", [])]
            by_source.setdefault(doc_type, []).extend(entries)
            for entry in entries:
                for bullet in entry.achievements:
                    already_attributed_rows.append((entry.company, bullet, filename, doc_type))
            certificates.extend(result.get("certificates_found", []))
        elif doc_type == "certificate":
            if result.get("certificate"):
                certificates.append(result["certificate"])
        else:
            for a in result.get("achievements", []):
                pending_achievements.append((bootstrap_extractors.RawAchievement(**a), filename, doc_type))

    timeline = bootstrap_timeline.build_timeline(by_source)

    matched_rows = [(company, bullet, filename, doc_type, "high")
                     for company, bullet, filename, doc_type in already_attributed_rows]
    review_rows = []

    for achievement, filename, doc_type in pending_achievements:
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, timeline, dry_run=dry_run)
        row = (company, achievement.raw_text, filename, doc_type, confidence)
        matched_rows.append(row)
        if confidence == "low":
            review_rows.append(row)

    _write_timeline(timeline)
    _write_draft_csv(matched_rows)
    _write_review_csv(review_rows)
    _write_certifications(certificates)
    _write_bullet_bank_clean(matched_rows)

    return {
        "extracted": len(matched_rows),
        "attributed": len(matched_rows) - len(review_rows),
        "flagged": len(review_rows),
        "certificates": len(certificates),
    }


def print_ingestion_summary(summary: dict) -> None:
    print(
        f"\nExtracted {summary['extracted']} achievement(s), "
        f"{summary['attributed']} confidently attributed, "
        f"{summary['flagged']} flagged for review, "
        f"{summary['certificates']} certificate(s) found."
    )


import argparse
import subprocess

import questionary

PIPELINE_STAGES = [
    "audit_bullet_bank.py",
    "cluster_bullet_bank.py",
    "rewrite_bullets.py",
    "audit_keepers.py",
    "score_keeper_gems.py",
    "embed_bullet_bank.py",
]

# Gate before index 0 (audit_bullet_bank.py) and index 2 (rewrite_bullets.py)
# -- the two stages that make a real API call per bullet.
_CONFIRMATION_GATES = {
    0: "Ready to run the quality-audit stage? This calls the API once per "
       "bullet and may take a while.",
    2: "Ready to run the rewrite stage? This is the other API-heavy step "
       "and may take a while.",
}

_STAGE_HINTS = {
    0: f"{theme.colorize_icon_ansi('hint')} Quality check time — every bullet gets scored the way a "
       "skeptical hiring manager would read it. This is the first API-heavy step.",
    1: f"{theme.colorize_icon_ansi('hint')} Grouping near-duplicate bullets and keeping only the "
       "strongest version of each.",
    2: f"{theme.colorize_icon_ansi('hint')} Rewriting anything that didn't pass the quality check — "
       "the other API-heavy step.",
    3: f"{theme.colorize_icon_ansi('hint')} Quick re-check on the rewritten bullets to make sure they "
       "actually improved.",
    4: f"{theme.colorize_icon_ansi('hint')} Flagging standout 'hidden gem' bullets — the ones a "
       "hiring manager would specifically remember.",
    5: f"{theme.colorize_icon_ansi('hint')} Last step — converting everything into a format the "
       "system can use to intelligently match bullets to a job description "
       "later.",
}


def run_stage(script_name: str) -> bool:
    """Runs one existing pipeline script, unmodified, as its own
    subprocess. Returns True if it exited successfully."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    result = subprocess.run([sys.executable, script_path])
    return result.returncode == 0


def run_full_pipeline(skip_confirm: bool = False) -> bool:
    """Runs all six existing pipeline stages in order, with a confirmation
    gate before each of the two API-heavy stages. Stops immediately (and
    does not continue to later stages) the moment any stage fails or a
    gate is declined. Since each stage already checkpoints internally,
    simply re-running this function later resumes correctly."""
    for i, script_name in enumerate(PIPELINE_STAGES):
        if i in _CONFIRMATION_GATES and not skip_confirm:
            proceed = questionary.confirm(_CONFIRMATION_GATES[i], default=True).ask()
            if not proceed:
                print("Stopped. Re-run this same command later to continue from here.")
                return False

        print(f"\n{_STAGE_HINTS[i]}")
        print(f"Stage {i + 1} of {len(PIPELINE_STAGES)}: running {script_name}...")
        if not run_stage(script_name):
            print(f"\nStage {i + 1} ({script_name}) failed. Re-run this same command to resume from here.")
            return False

    print(f"\n{theme.colorize_icon_ansi('success')} All done! Your bullet bank is ready.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="Skip confirmation gates and run the full pipeline unattended.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts instead of calling the API, and skip the real six-stage pipeline entirely.")
    parser.add_argument(
        "--scope", choices=["bullets", "profile", "both"], default="both",
        help="\"Update My Knowledge\" only: which downstream steps to run after "
             "ingesting new source_documents/ content. Phase 0 (ingestion) always "
             "runs regardless of scope, since it's what processes the new files.",
    )
    args = parser.parse_args()

    # Before Phase 0 -- run_ingestion() itself calls the Gemini API (document
    # classification/extraction), so the key needs to be in place before
    # the very first real call, not just before Phase 0.5's steps.
    bootstrap_profile.collect_secrets(dry_run=args.dry_run)

    summary = run_ingestion(dry_run=args.dry_run)
    print_ingestion_summary(summary)

    if args.scope in ("profile", "both"):
        bootstrap_profile.run_profile_setup(dry_run=args.dry_run)

    if args.dry_run:
        print("\n--dry-run set: skipping the six-stage pipeline.")
        return

    if args.scope in ("bullets", "both"):
        run_full_pipeline(skip_confirm=args.yes)


if __name__ == "__main__":
    main()
