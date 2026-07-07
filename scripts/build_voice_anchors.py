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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

INDEX_CSV = os.path.join(KB_DIR, "application-answers-index.csv")
OUTPUT_MD = os.path.join(KB_DIR, "voice-anchors.md")


def build_voice_anchors(index_csv: str = INDEX_CSV) -> str:
    """Reads index_csv and returns the voice-anchors.md content as a string."""
    with open(index_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sections = []
    for row in rows:
        parts = [f"### {row['Prompt / Topic']}", row["Themes & Highlights"]]
        quote = (row.get("Quote Worth Pulling") or "").strip()
        if quote:
            parts.append(f"> {quote}")
        sections.append("\n\n".join(parts))

    return "\n\n".join(sections) + "\n"


def main():
    if not os.path.exists(INDEX_CSV):
        raise SystemExit(f"ERROR: {INDEX_CSV} not found.")
    content = build_voice_anchors()
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
