"""refresh_verified_ledger.py -- repopulates the verified metrics/tools/
projects ledger from the profile's real bullet bank, without destroying
anything.

Why this exists instead of bootstrap_profile.write_verified_ledger():
that function is a NEW-PROFILE SEEDER. Alongside the three ledger files
it also writes blank starter versions of verified_facts.json,
evidence_graph.json, verified-claims.csv, evidence-guide.csv and more.
Those writes are correct exactly once, at bootstrap. This script touches
only the three files that are actually derived from bullets, and merges
rather than replaces.

Merge semantics: an entry already in the ledger is never modified or
dropped -- including hand-added fields the extractor knows nothing about
(category, confidence, use_notes, tr_references). Only genuinely new
entries are appended, so this is safe to run after manual curation.

It is NOT, however, idempotent. De-duplication is exact-match on the
normalized key, and the model does not return an identical set twice:
a second pass over the same bullets added 183 more metrics and 63 more
projects, because "Adobe Sign pilot program" and "Adobe Sign program"
are different keys for the same thing. Treat each run as additive and
review the result -- do not run it on a schedule expecting convergence.

Usage:
    python scripts/refresh_verified_ledger.py                  # dry run
    python scripts/refresh_verified_ledger.py --apply          # writes
    python scripts/refresh_verified_ledger.py --max-chunks 5   # cost cap
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bootstrap_extractors  # noqa: E402
import bootstrap_profile  # noqa: E402
import cli_art  # noqa: E402


def _key(*parts: str) -> str:
    """Normalized identity for de-duplication: case- and punctuation-
    insensitive, so "Salesforce CRM" and "salesforce crm" are one entry
    while the same tool at two employers stays two (matching
    _LEDGER_PROMPT's own attribution rule)."""
    joined = " ".join((p or "").strip().lower() for p in parts)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", joined).split())


def _load(path: str, list_key: str) -> Dict[str, Any]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {"_meta": {}, list_key: []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault(list_key, [])
    data.setdefault("_meta", {})
    return data


def _next_id(existing: List[dict], prefix: str) -> int:
    highest = 0
    for item in existing:
        match = re.search(r"(\d+)$", str(item.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def merge_entries(
    existing: List[dict],
    incoming: List[dict],
    key_fields: List[str],
    id_prefix: str,
) -> tuple:
    """Appends only the incoming entries whose key is not already present.

    Returns (merged_list, added_count). Existing entries are passed
    through untouched -- never rewritten, never reordered.
    """
    seen = {_key(*[str(e.get(f, "")) for f in key_fields]) for e in existing}
    merged = list(existing)
    counter = _next_id(existing, id_prefix)
    added = 0

    for entry in incoming:
        identity = _key(*[str(entry.get(f, "")) for f in key_fields])
        if not identity or identity in seen:
            continue
        seen.add(identity)
        merged.append({"id": f"{id_prefix}_{counter:03d}", **entry})
        counter += 1
        added += 1

    return merged, added


def refresh(
    apply_changes: bool = False,
    max_chunks: Optional[int] = None,
) -> Dict[str, Any]:
    source = bootstrap_profile._bullet_source_path()
    if source is None:
        raise RuntimeError(
            "No bullet source found (bullet-bank-draft.csv or "
            "bullet-bank-clean.csv). Nothing to extract from."
        )

    text = bootstrap_profile._achievements_summary_text_by_employer()
    chunks = bootstrap_extractors._chunk_lines(
        text, bootstrap_extractors.LEDGER_CHUNK_CHARS
    )
    total_chunks = len(chunks)
    if max_chunks:
        chunks = chunks[:max_chunks]

    cli_art.cli_info(
        f"Extracting from {os.path.basename(source)}: "
        f"{len(chunks)} of {total_chunks} chunks "
        f"({len(text):,} chars of bullets)."
    )

    extraction = bootstrap_extractors.extract_ledger_entries_chunked(
        "\n".join(chunks)
    )

    targets = [
        (
            bootstrap_profile.VERIFIED_METRICS_PATH,
            "metrics",
            [
                {"label": m.label, "value": m.value, "employer": m.employer}
                for m in extraction.metrics
            ],
            ["label", "value", "employer"],
            "metric",
        ),
        (
            bootstrap_profile.VERIFIED_TOOLS_PATH,
            "tools",
            [{"name": t.name, "employer": t.employer} for t in extraction.tools],
            ["name", "employer"],
            "tool",
        ),
        (
            bootstrap_profile.VERIFIED_PROJECTS_PATH,
            "projects",
            [{"name": p.name, "employer": p.employer} for p in extraction.projects],
            ["name", "employer"],
            "proj",
        ),
    ]

    stats: Dict[str, Any] = {"source": source, "chunks": len(chunks), "files": {}}

    for path, list_key, incoming, key_fields, id_prefix in targets:
        data = _load(path, list_key)
        before = len(data[list_key])
        merged, added = merge_entries(
            data[list_key], incoming, key_fields, id_prefix
        )

        stats["files"][list_key] = {
            "before": before,
            "extracted": len(incoming),
            "added": added,
            "after": len(merged),
        }

        if not apply_changes:
            continue

        if os.path.exists(path):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, f"{path}.backup-{stamp}")

        data[list_key] = merged
        data["_meta"]["total_entries"] = len(merged)
        data["_meta"]["last_updated"] = datetime.now().date().isoformat()
        data["_meta"].setdefault("source", "bullet bank extraction")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the merged ledger (default: dry run)"
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="only extract from the first N chunks (each chunk is one API call)",
    )
    args = parser.parse_args()

    try:
        stats = refresh(apply_changes=args.apply, max_chunks=args.max_chunks)
    except RuntimeError as exc:
        cli_art.display_error(str(exc))
        return 1

    verb = "added" if args.apply else "would add"
    print(f"\n  chunks extracted: {stats['chunks']}\n")
    for name, info in stats["files"].items():
        print(
            f"  {name:<10} {info['before']:>4} existing "
            f"+ {info['added']:>4} new {verb:<10} = {info['after']:>4}"
            f"   ({info['extracted']} extracted, rest were duplicates)"
        )
    if not args.apply:
        print("\n  dry run -- re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
