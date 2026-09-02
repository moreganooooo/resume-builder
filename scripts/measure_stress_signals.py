"""measure_stress_signals.py -- corpus hit-rate report for stress_signals.py.

Read-only. Runs the deterministic phrase detector against every stored
posting's description and reports how often each category fires, plus a
handful of sample matches per category for eyeballing precision. This is
the measurement step docs/superpowers/specs/2026-09-01-stress-challenge-scoring-design.md
calls for BEFORE any category is promoted to a scored subscore or a
dashboard badge -- the same order work_hours.py and compensation.py were
built in, both of which turned out to need correction after their first
real-corpus measurement.

Usage: python3 scripts/measure_stress_signals.py [--profile NAME] [--samples N]
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402
import stress_signals  # noqa: E402


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _description_of(stored: str) -> str:
    stored = (stored or "").strip()
    if not stored.startswith("{"):
        return _strip_html(stored)
    try:
        return _strip_html(str(json.loads(stored).get("description") or ""))
    except (ValueError, AttributeError):
        return ""


def load_descriptions(profile: str | None) -> list[tuple[str, str]]:
    root = (
        profile_paths.profile_root(profile) if profile else profile_paths.profile_root()
    )
    conn = sqlite3.connect(f"{root}/data.db")
    try:
        raw = conn.execute("select id, coalesce(raw_text,'') from jobs").fetchall()
    finally:
        conn.close()
    out = []
    for job_id, stored in raw:
        body = _description_of(stored)
        if body:
            out.append((job_id, body))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--samples", type=int, default=3, help="Sample matches shown per category"
    )
    args = parser.parse_args()

    rows = load_descriptions(args.profile)
    total = len(rows)
    if total == 0:
        print("No postings with a description found.")
        return 0

    per_category: dict[str, list[tuple[str, str]]] = {}
    postings_with_any_signal = 0

    for job_id, body in rows:
        hits = stress_signals.detect(body)
        if hits:
            postings_with_any_signal += 1
        seen_categories = set()
        for hit in hits:
            if hit.category in seen_categories:
                continue
            seen_categories.add(hit.category)
            per_category.setdefault(hit.category, []).append((job_id, hit.text))

    print(f"Corpus: {total} postings with a description\n")
    print(f"{'Category':<32} {'Postings':>10} {'%':>7}")
    print("-" * 51)
    for category, label, _, _ in stress_signals._CATEGORIES:
        matches = per_category.get(category, [])
        pct = 100 * len(matches) / total
        print(f"{label:<32} {len(matches):>10} {pct:>6.1f}%")

    print(
        f"\n{'ANY signal':<32} {postings_with_any_signal:>10} "
        f"{100 * postings_with_any_signal / total:>6.1f}%"
    )

    print("\nSample matches per category (for precision eyeballing):")
    for category, label, _, _ in stress_signals._CATEGORIES:
        matches = per_category.get(category, [])
        if not matches:
            continue
        print(f"\n  {label}:")
        for job_id, text in matches[: args.samples]:
            print(f'    [{job_id}] "{text}"')

    return 0


if __name__ == "__main__":
    sys.exit(main())
