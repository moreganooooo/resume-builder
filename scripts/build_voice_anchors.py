"""
build_voice_anchors.py -- projects application-answers-index.csv (a small,
already-curated set of past real application-question answers, copied once
from career-ops) into voice-anchors.md, a compact reference of themes and
"quote worth pulling" lines for the resume/cover-letter pipeline to draw on.

Usage:
    python build_voice_anchors.py
"""

import csv
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402
import cli_art

KB_DIR = profile_paths.kb_dir()

INDEX_CSV = os.path.join(KB_DIR, "application-answers-index.csv")
OUTPUT_MD = os.path.join(KB_DIR, "voice-anchors.md")


def build_voice_anchors(index_csv: str = INDEX_CSV) -> str:
    """Reads index_csv and returns the voice-anchors.md content as a string.

    Only rows with a genuine "Quote Worth Pulling" become a section.
    "Themes & Highlights" is third-person paraphrase written for a human
    skimming the index (e.g. "Describes agency internship experience;
    emphasizes creativity...") -- it teaches a model nothing about this
    candidate's actual register, so it used to make up ~70% of this file's
    bytes while the real, verbatim signal sat in the blockquotes (B30,
    phase-9-backlog.md). A topic with no quote has no voice signal to
    offer here and is skipped rather than padded with paraphrase alone --
    this file's only job is specimens, not topical coverage (that's
    profile.yml/verified_facts.json's job).
    """
    with open(index_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sections = []
    for row in rows:
        quote = (row.get("Quote Worth Pulling") or "").strip()
        if not quote:
            continue
        sections.append(f"### {row['Prompt / Topic']}\n\n> {quote}")

    return "\n\n".join(sections) + "\n"


def main():
    if not os.path.exists(INDEX_CSV):
        cli_art.cli_error(f"{INDEX_CSV} not found.")
        raise SystemExit(1)
    content = build_voice_anchors()
    with atomic_write(OUTPUT_MD, encoding="utf-8") as f:
        f.write(content)
    cli_art.print_literal(f"Wrote {cli_art._escape_markup(OUTPUT_MD)}")


if __name__ == "__main__":
    main()
