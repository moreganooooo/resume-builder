#!/usr/bin/env python3
"""
detect_hidden_gems.py

Reads a scored bullets JSON file (output of audit_and_refine_bullets),
identifies hidden gems, and reorders bullets within each job entry so
high-scoring gems appear in the top 5 positions.

Usage:
  python detect_hidden_gems.py --input tailored_resume.json --output tailored_resume_gems.json

Expects bullets to have a `hidden_gem_score` field (added by critique_bullet_v2.md).
Falls back gracefully if the field is absent (treats missing score as 0).
"""

import argparse
import json
import copy
from pathlib import Path

# Threshold from believability_v2.yaml
HIDDEN_GEM_THRESHOLD = 90
STRONG_BULLET_THRESHOLD = 75
TOP_N_POSITIONS = 5  # gems get promoted into top N positions per job


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\u2705 Saved: {path}")


def get_gem_score(bullet: dict) -> int:
    """Return hidden_gem_score; fall back to 0 if field is absent."""
    return bullet.get("hidden_gem_score", 0)


def promote_gems(bullets: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Sort bullets so hidden gems appear in the top N positions.
    Returns (reordered_bullets, gems_found).

    Promotion rules:
    - Gems (score >= 90) always move to top 5
    - Within the top 5, gems are ordered by score descending
    - Non-gems keep their original relative order below position 5
    - If no gems exist, original order is preserved
    """
    gems = [b for b in bullets if get_gem_score(b) >= HIDDEN_GEM_THRESHOLD]
    non_gems = [b for b in bullets if get_gem_score(b) < HIDDEN_GEM_THRESHOLD]

    if not gems:
        return bullets, []

    gems_sorted = sorted(gems, key=get_gem_score, reverse=True)
    reordered = gems_sorted[:TOP_N_POSITIONS] + non_gems
    return reordered, gems_sorted


def process_resume(resume: dict) -> tuple[dict, list[dict]]:
    """
    Walk the resume structure, promote gems per job entry,
    and collect a global list of all gems found.
    """
    result = copy.deepcopy(resume)
    all_gems = []

    experience = result.get("experience", [])
    for job in experience:
        bullets = job.get("bullets", [])
        if not bullets:
            continue

        reordered, gems = promote_gems(bullets)
        job["bullets"] = reordered

        # Tag the job entry with a gem count for visibility
        job["hidden_gems_promoted"] = len(gems)

        for gem in gems:
            all_gems.append({
                "company": job.get("company", "Unknown"),
                "role": job.get("role", "Unknown"),
                "bullet": gem.get("text", gem),
                "hidden_gem_score": get_gem_score(gem),
                "hidden_gem_reason": gem.get("hidden_gem_reason", "")
            })

    return result, all_gems


def print_gem_report(gems: list[dict]) -> None:
    """Print a human-readable summary of all hidden gems found."""
    if not gems:
        print("\n\u1f48e No hidden gems found (no bullets scored >= 90).")
        print("Tip: run with critique_bullet_v2.md to generate hidden_gem_score fields.")
        return

    print(f"\n\u2728 HIDDEN GEM REPORT — {len(gems)} gem(s) found and promoted\n")
    print("-" * 60)
    for i, gem in enumerate(gems, 1):
        bullet_text = gem['bullet'] if isinstance(gem['bullet'], str) else gem['bullet'].get('text', str(gem['bullet']))
        print(f"  {i}. [{gem['hidden_gem_score']}/100] {gem['company']} | {gem['role']}")
        print(f"     \"{bullet_text[:120]}{'...' if len(bullet_text) > 120 else ''}\"")
        if gem.get('hidden_gem_reason'):
            print(f"     Reason: {gem['hidden_gem_reason']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect and promote hidden gem bullets in a tailored resume JSON."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to scored resume JSON (output of audit_and_refine_bullets)"
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the gem-promoted resume JSON"
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Print gem report without writing output file"
    )
    args = parser.parse_args()

    print(f"\u1f50e Loading: {args.input}")
    resume = load_json(args.input)

    promoted_resume, gems = process_resume(resume)
    print_gem_report(gems)

    if not args.report_only:
        save_json(promoted_resume, args.output)

    # Also save a standalone gems report
    if gems:
        report_path = Path(args.output).with_suffix(".gems_report.json")
        save_json({"total_gems": len(gems), "gems": gems}, str(report_path))
        print(f"\u1f4cb Gems report saved: {report_path}")


if __name__ == "__main__":
    main()
