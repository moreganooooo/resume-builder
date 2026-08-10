#!/usr/bin/env python3
"""
Enhanced sync script:
- Reads job JSON files from `jds/<profile>/`.
- Updates (or creates) `data/<profile>/applications.md` for the dashboard.
- Supports arbitrary `status` values (e.g. Evaluated, Applied, Interview, Offer, etc.).
- Renders a PDF indicator column (`✓` when `has_pdf` is true).
- **Preserves existing manual notes**: if a row already exists in the markdown file, the `Notes` column is kept unless the JSON explicitly provides a new `notes` value.

The JSON schema used throughout the repo includes (at minimum)::

    {
        "date": "2026-08-01",
        "company": "Acme Corp",
        "role": "Senior Product Designer",
        "status": "Evaluated",            # optional – defaults to "Evaluated"
        "has_pdf": true,                   # optional – renders a ✓ in the PDF column
        "source_url": "https://example.com/job/1",
        "evaluation": {
            "composite_score": 4.6,
            "recommendation": "Strong pursue"
        },
        "report_path": "reports/xyz.pdf", # optional – shown in the Report column
        "notes": "First contact made, great cultural fit."
    }

Any missing fields fall back to sensible placeholders ("—", "NA", "unknown").
"""

import json
import os
import sys
from pathlib import Path
import cli_art

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------

def load_json(path: Path) -> dict:
    """Read a JSON file and return its dict representation.
    Robustly handles empty files or files with extra data.
    Returns an empty dict on any parsing failure so the sync can continue.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Try to decode the first JSON object if extra data is present
        try:
            with path.open("r", encoding="utf-8") as f:
                text = f.read().strip()
                if not text:
                    return {}
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text)
                return obj
        except Exception:
            return {}
    except Exception:
        return {}


def parse_existing_md(md_path: Path) -> dict:
    """Parse an existing applications.md file.

    Returns a mapping keyed by a tuple (date, company, role) → notes string.
    This is used to preserve manual notes when the JSON does not provide
    a replacement.
    """
    existing = {}
    if not md_path.is_file():
        return existing
    with md_path.open("r", encoding="utf-8") as f:
        lines = [ln.rstrip() for ln in f.readlines()]
    # Skip the header (first two lines)
    for line in lines[2:]:
        if not line.startswith("|"):
            continue
        # Split on pipe, strip whitespace – the line starts and ends with '|'
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 10:
            continue
        # Columns order: #, Date, Company, Role, Score, Status, PDF, Link, Report, Notes
        _, date, company, role, _, _, _, _, _, notes = parts
        key = (date, company, role)
        existing[key] = notes
    return existing


def format_score(evaluation: dict) -> str:
    """Return a human‑readable score string, or 'NA' if missing."""
    score = evaluation.get("composite_score")
    if isinstance(score, (int, float)):
        return f"{score:.2f}/5"
    return "NA"


def format_row(idx: int, data: dict, preserved_notes: str | None) -> str:
    """Build a markdown table row from a JSON payload.

    `preserved_notes` is taken from the existing file if the JSON does not
    provide a `notes` field. If the JSON does contain notes we honour those.
    """
    date = data.get("date", "—")
    company = data.get("company", "unknown")
    role = data.get("role", "unknown")
    evaluation = data.get("evaluation", {})
    score = format_score(evaluation)
    status = data.get("status", "Evaluated")
    pdf_flag = "✓" if data.get("has_pdf") else "—"
    url = data.get("source_url")
    link = f"[Apply]({url})" if url else "—"
    report = data.get("report_path", "—")
    notes = data.get("notes")
    if notes is None:
        notes = preserved_notes if preserved_notes is not None else "—"
    # Assemble the exact 10‑column format expected by the dashboard
    return f"| {idx} | {date} | {company} | {role} | {score} | {status} | {pdf_flag} | {link} | {report} | {notes} |"

# ----------------------------------------------------------------------
# Main sync routine
# ----------------------------------------------------------------------

def main(profile: str = "morgan"):
    project_root = Path(__file__).resolve().parents[1]
    jds_dir = project_root / "jds" / profile
    data_dir = project_root / "data" / profile
    md_path = data_dir / "applications.md"

    # Load existing notes (if any) to preserve manual edits
    existing_notes = parse_existing_md(md_path)

    # Gather JSON payloads, sorted for deterministic ordering
    json_files = sorted(jds_dir.glob("*.json"))
    if not json_files:
        cli_art.cli_error(f"[sync] No JSON files found under {jds_dir}")
        sys.exit(1)

    rows = []
    for idx, jf in enumerate(json_files, start=1):
        payload = load_json(jf)
        key = (payload.get("date", "—"), payload.get("company", "unknown"), payload.get("role", "unknown"))
        preserved = existing_notes.get(key)
        rows.append(format_row(idx, payload, preserved))

    # Header lines – must match the dashboard parser exactly
    header = (
        "| # | Date | Company | Role | Score | Status | PDF | Link | Report | Notes |\n"
        "|---|------|---------|------|-------|--------|-----|------|--------|-------|"
    )
    content = "\n".join([header] + rows) + "\n"

    os.makedirs(data_dir, exist_ok=True)
    md_path.write_text(content, encoding="utf-8")
    cli_art.console.print(f"[sync] Wrote {len(rows)} rows to {md_path}", markup=False, soft_wrap=True)

if __name__ == "__main__":
    profile_arg = sys.argv[1] if len(sys.argv) > 1 else "morgan"
    main(profile_arg)
