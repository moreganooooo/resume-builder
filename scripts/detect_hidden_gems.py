#!/usr/bin/env python3
"""
detect_hidden_gems.py

Reads a scored bullets JSON file (output of audit_and_refine_bullets),
identifies hidden gems, and reorders bullets within each job entry so
high-scoring gems appear in the top 5 positions.

Usage (standalone):
  python detect_hidden_gems.py --input tailored_resume.json --output tailored_resume_gems.json

Usage (imported by orchestrator — preferred):
  from scripts.detect_hidden_gems import process_resume, print_gem_report, save_json

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
        json.dump(data, f, indent=2)


def get_score(bullet: str | dict) -> int:
    """Extract hidden_gem_score from a bullet (str or dict)."""
    if isinstance(bullet, dict):
        return bullet.get("hidden_gem_score", 0) or 0
    return 0  # plain string bullets have no score field


def promote_gems(bullets: list, top_n: int = TOP_N_POSITIONS) -> list:
    """
    Reorder bullets so hidden gems appear in the first `top_n` positions.
    Non-gem bullets retain their original relative order after the gems.
    """
    gems     = [b for b in bullets if get_score(b) >= HIDDEN_GEM_THRESHOLD]
    non_gems = [b for b in bullets if get_score(b) < HIDDEN_GEM_THRESHOLD]

    # Fill top_n slots with gems (sorted by score desc), then append the rest
    gems_sorted = sorted(gems, key=get_score, reverse=True)
    reordered   = gems_sorted[:top_n] + non_gems

    # If we have more gems than top_n slots, append the overflow after non-gems
    if len(gems_sorted) > top_n:
        reordered += gems_sorted[top_n:]

    return reordered


def process_resume(resume_data: dict) -> tuple[dict, list]:
    """
    Iterate over each job in EXPERIENCE, promote gems within each role.
    Returns the mutated resume dict and a flat gem report list.
    """
    updated = copy.deepcopy(resume_data)
    gem_report = []

    for job in updated.get("EXPERIENCE", []):
        bullets = job.get("achievements", [])
        if not bullets:
            continue

        job["achievements"] = promote_gems(bullets)

        for bullet in job["achievements"]:
            score = get_score(bullet)
            if score >= HIDDEN_GEM_THRESHOLD:
                gem_report.append({
                    "company": job.get("company", "Unknown"),
                    "title":   job.get("title",   "Unknown"),
                    "score":   score,
                    "bullet":  bullet if isinstance(bullet, str) else bullet.get("text", str(bullet)),
                })

    return updated, gem_report


def print_gem_report(gem_report: list) -> None:
    if not gem_report:
        print("  No hidden gems found (score >= 90) in this resume.")
        return
    print(f"\n💎 Hidden Gem Report — {len(gem_report)} gem(s) promoted:\n")
    for gem in sorted(gem_report, key=lambda x: x["score"], reverse=True):
        preview = gem["bullet"][:120] + ("..." if len(gem["bullet"]) > 120 else "")
        print(f"  [{gem['score']:>3}] {gem['company']} / {gem['title']}")
        print(f"       {preview}\n")


def main():
    parser = argparse.ArgumentParser(description="Detect and promote hidden gem bullets.")
    parser.add_argument("--input",  required=True, help="Path to scored resume JSON")
    parser.add_argument("--output", required=True, help="Path to write gem-promoted resume JSON")
    parser.add_argument("--top-n",  type=int, default=TOP_N_POSITIONS,
                        help=f"Number of top positions to reserve for gems (default: {TOP_N_POSITIONS})")
    args = parser.parse_args()

    print(f"\n📥 Loading resume: {args.input}")
    resume_data = load_json(args.input)

    updated, gem_report = process_resume(resume_data)
    print_gem_report(gem_report)

    save_json(updated, args.output)
    print(f"✅  Gem-promoted resume saved: {args.output}")


if __name__ == "__main__":
    main()
