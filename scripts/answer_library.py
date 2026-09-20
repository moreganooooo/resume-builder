"""Opt-in promotion of a job answer into the curated voice library."""

from __future__ import annotations

import csv
import os

from scripts import profile_paths
from scripts.atomic_write import atomic_write


HEADERS = [
    "Filename",
    "Prompt / Topic",
    "Answer Length",
    "Quote Worth Pulling",
]


def add_to_library(
    question: str,
    answer: str,
    job_title: str,
    company: str,
    quote: str | None = None,
) -> bool:
    """Append a curated answer once; return False when it is already present."""
    path = os.path.join(profile_paths.kb_dir(), "application-answers-index.csv")
    rows: list[dict] = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    filename = f"app-chat:{company}::{job_title}"
    if any(row.get("Filename") == filename and row.get("Prompt / Topic") == question for row in rows):
        return False
    rows.append(
        {
            "Filename": filename,
            "Prompt / Topic": question,
            "Answer Length": str(len((answer or "").split())),
            "Quote Worth Pulling": quote or "",
        }
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with atomic_write(path, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    if quote:
        # Rebuild is intentionally opt-in; a quote-less promotion must not
        # alter voice anchors.
        from scripts.build_voice_anchors import build_voice_anchors

        voice_path = os.path.join(profile_paths.kb_dir(), "voice-anchors.md")
        content = build_voice_anchors(path)
        with atomic_write(voice_path, encoding="utf-8") as handle:
            handle.write(content)
    return True
