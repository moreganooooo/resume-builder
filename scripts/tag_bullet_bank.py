#!/usr/bin/env python3
"""
tag_bullet_bank.py

Auto-assigns the [tag] category to bullet-bank rows that don't have one yet.
The tag taxonomy and its keyword lists come from profile.yml's tags: --
generated per-profile during bootstrap from that candidate's own target
roles and real achievement text (bootstrap_extractors.generate_tag_taxonomy()),
not a hardcoded list. See profile_paths.tags()'s docstring: this used to be
a module constant here duplicating (and, by 2026-07-17, having already
drifted from) orchestrator.py's/rewrite_bullets.py's own separate copies of
the same marketing-specific taxonomy -- every consumer now reads the same
profile.yml source instead.

Each bullet gets one tag, or two when there's independent (non-shared-keyword)
evidence for both — e.g. a sales-enablement content bullet legitimately
earning both [content] and [enablement]. Never more than two.

Rows that already have a non-empty Tags value are left untouched.

Inputs:  a bullet-bank CSV with Role / Company, Tags, Bullet Point columns
Outputs (written next to the input file):
  <name>-tagged.csv       full CSV with blanks filled in
  tag-review-needed.csv   rows where even the winning tag's match was weak
                          (only shared/generic keywords, no unique-keyword
                          hit) — a fast heuristic can't be fully sure on
                          these, so they need a glance

Usage:
  python tag_bullet_bank.py path/to/bullet-bank-clean.csv
  python tag_bullet_bank.py path/to/bullet-bank-clean.csv -o path/to/out.csv
"""

import argparse
import csv
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402


def tag_keywords() -> dict:
    """Bracket-tag ("[ops]") -> keywords, from profile.yml's tags:."""
    return {f"[{t['name']}]": (t.get("keywords") or []) for t in profile_paths.tags()}


def fallback_tag() -> str:
    """The catch-all tag -- generate_tag_taxonomy() always produces exactly
    one tag with an empty keywords list for this purpose. Falls back to the
    literal "[generalist]" if somehow missing (e.g. a hand-edited
    profile.yml with no such entry) rather than crashing."""
    for t in profile_paths.tags():
        if not t.get("keywords"):
            return f"[{t['name']}]"
    return "[generalist]"


def _keyword_tag_counts(keywords_by_tag: dict) -> dict:
    """Several keyword lists can share generic words ("campaign",
    "training", "sequence") across 2-3 tags. A single occurrence of a
    SHARED word is weak evidence; a single occurrence of a word unique to
    one tag (e.g. "salesforce", only in [ops]) is strong evidence. Weight
    each keyword by 1 / (number of tags it appears in) so unique words
    count full strength and shared words get diluted instead of
    manufacturing false ties."""
    counts = {}
    for kws in keywords_by_tag.values():
        for kw in kws:
            counts[kw] = counts.get(kw, 0) + 1
    return counts


def score_bullet(text: str, keywords_by_tag: dict = None) -> dict:
    """Returns {tag: weighted_score} for every tag with at least one hit."""
    keywords_by_tag = keywords_by_tag if keywords_by_tag is not None else tag_keywords()
    keyword_tag_counts = _keyword_tag_counts(keywords_by_tag)
    t = text.lower()
    scores = {}
    for tag, keywords in keywords_by_tag.items():
        weight = sum(1 / keyword_tag_counts[kw] for kw in keywords if kw in t)
        if weight:
            scores[tag] = weight
    return scores


def assign_tags(text: str) -> tuple:
    """
    Returns (tag_string, needs_review: bool).
    A tag reaching a weighted score of 1.0 means at least one keyword unique
    to it was found (full-strength evidence) — that's a confident call and
    doesn't need review. Below 1.0 means every hit was a word shared with
    other tags, which is genuinely weaker and worth a glance.
      - the highest-scoring tag wins outright; ties break by priority order
        (profile.yml's tags: list order)
      - a second tag rides along (up to 2 total) whenever it independently
        reaches 1.0 too (its own unique-keyword evidence, not just
        shared-word overlap) — a confident two-tag bullet is a normal,
        expected outcome, not something that needs a second look
      - flagged for review only when the winner's own score is < 1.0, i.e.
        the whole call rests on shared/generic words
    """
    keywords_by_tag = tag_keywords()
    scores = score_bullet(text, keywords_by_tag)
    if not scores:
        return fallback_tag(), False

    priority = list(keywords_by_tag.keys())
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], priority.index(kv[0])))
    top_tag, top_score = ranked[0]
    winners = [top_tag]

    if len(ranked) > 1:
        second_tag, second_score = ranked[1]
        if second_score >= 1.0:
            winners.append(second_tag)

    needs_review = top_score < 1.0
    return "".join(winners), needs_review


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_csv")
    ap.add_argument("-o", "--output", default=None, help="Output path (default: <input>-tagged.csv)")
    args = ap.parse_args()

    out_path = args.output or args.input_csv.replace(".csv", "-tagged.csv")
    review_path = os.path.join(os.path.dirname(out_path) or ".", "tag-review-needed.csv")

    with open(args.input_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fallback = fallback_tag()
    tagged, skipped_existing, fell_back = 0, 0, 0
    review_rows = []
    for r in rows:
        if r.get("Tags", "").strip():
            skipped_existing += 1
            continue
        tag_str, tied = assign_tags(r["Bullet Point"])
        r["Tags"] = tag_str
        tagged += 1
        if tag_str == fallback:
            fell_back += 1
        if tied:
            review_rows.append({
                "Role / Company": r["Role / Company"],
                "Tags": tag_str,
                "Bullet Point": r["Bullet Point"],
            })

    with atomic_write(out_path, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point"])
        w.writeheader()
        try:
            w.writerows(rows)
        except ValueError as e:
            extra = sorted(set(rows[0].keys()) - set(w.fieldnames)) if rows else []
            raise ValueError(
                f"{args.input_csv} has column(s) this script doesn't expect: {extra}. "
                "tag_bullet_bank.py only accepts a 3-column bullet-bank CSV "
                "(Role / Company, Tags, Bullet Point) -- point it at "
                "bullet-bank-clean.csv, not a richer CSV like bullet-bank-keepers.csv."
            ) from e

    if review_rows:
        with atomic_write(review_path, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point"])
            w.writeheader()
            w.writerows(review_rows)

    print(f"{args.input_csv}: {len(rows)} rows")
    print(f"  Already tagged (left alone): {skipped_existing}")
    print(f"  Newly tagged: {tagged}  (of which {fell_back} fell back to {fallback})")
    print(f"  Weak match, no unique keyword hit (flagged for review): {len(review_rows)}")
    print(f"  Wrote: {out_path}")
    if review_rows:
        print(f"  Wrote: {review_path}")


if __name__ == "__main__":
    main()
