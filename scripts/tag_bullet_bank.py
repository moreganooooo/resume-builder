#!/usr/bin/env python3
"""
tag_bullet_bank.py

Auto-assigns the [tag] category to bullet-bank rows that don't have one yet.
Tags are the manual convention documented in bullet-bank.md ([email]
[enablement] [content] [ops] [mgmt] [writing] [generalist]), extended here
with [brand] and [design] — both already fully defined in rewrite_bullets.py
(TAG_CONTEXT, BACKGROUND_TAGS, CLAIM_TAG_KEYWORDS) but missing from
bullet-bank.md's list, which left ~27% of the bank (VML, Callahan Creek,
Element 8/Strategy LLC, Bernstein Rein — creative/agency work) with no tag
that actually fits, mistagged [email] off the generic word "campaign" or
dumped into [generalist]. If you add tags here, update bullet-bank.md too.

Keyword lists mirror rewrite_bullets.py's CLAIM_TAG_KEYWORDS (kept in sync by
hand — if you change the tag vocabulary there, update TAG_KEYWORDS here too).
That dict has one extra tag ([sales]) not used here — Treering/IST sales
content is already well covered by [ops]/[mgmt]/[enablement].

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

# Mirrors rewrite_bullets.py's CLAIM_TAG_KEYWORDS, plus [brand]/[design]
# (see module docstring).
TAG_KEYWORDS = {
    "[email]":      ["email", "open rate", "reply rate", "sequence", "outreach", "campaign",
                      "pta", "hot zone", "mailchimp", "persistiq"],
    "[ops]":        ["salesforce", "crm", "pipeline", "territory", "hygiene", "data",
                      "hot zone", "import", "outreach", "integration"],
    "[content]":    ["content", "committee", "asset", "library", "governance", "voice",
                      "sequence", "playbook", "onboarding", "training"],
    "[enablement]": ["training", "onboarding", "playbook", "sdr", "enablement",
                      "committee", "process map", "coaching"],
    "[mgmt]":       ["team", "coach", "manage", "sdr", "direct report", "training"],
    "[writing]":    ["copy", "writing", "email", "sequence", "campaign", "authored"],
    "[brand]":      ["brand", "voice", "tone", "agency", "campaign", "creative"],
    "[design]":     ["design", "deck", "slide", "flyer", "illustrator", "canva"],
}
FALLBACK_TAG = "[generalist]"  # matches CLAIM_TAG_KEYWORDS's empty-keyword-list role

# Several keyword lists share generic words ("campaign", "training",
# "sequence") across 2-3 tags. A single occurrence of a SHARED word is weak
# evidence; a single occurrence of a word unique to one tag (e.g.
# "salesforce", only in [ops]) is strong evidence. Weight each keyword by
# 1 / (number of tags it appears in) so unique words count full strength and
# shared words get diluted instead of manufacturing false ties.
_KEYWORD_TAG_COUNTS = {}
for _kws in TAG_KEYWORDS.values():
    for _kw in _kws:
        _KEYWORD_TAG_COUNTS[_kw] = _KEYWORD_TAG_COUNTS.get(_kw, 0) + 1


def score_bullet(text):
    """Returns {tag: weighted_score} for every tag with at least one hit."""
    t = text.lower()
    scores = {}
    for tag, keywords in TAG_KEYWORDS.items():
        weight = sum(1 / _KEYWORD_TAG_COUNTS[kw] for kw in keywords if kw in t)
        if weight:
            scores[tag] = weight
    return scores


def assign_tags(text):
    """
    Returns (tag_string, needs_review: bool).
    A tag reaching a weighted score of 1.0 means at least one keyword unique
    to it was found (full-strength evidence) — that's a confident call and
    doesn't need review. Below 1.0 means every hit was a word shared with
    other tags, which is genuinely weaker and worth a glance.
      - the highest-scoring tag wins outright; ties break by priority order
        (the order tags are defined in TAG_KEYWORDS above)
      - a second tag rides along (up to 2 total) whenever it independently
        reaches 1.0 too (its own unique-keyword evidence, not just
        shared-word overlap) — a confident two-tag bullet is a normal,
        expected outcome, not something that needs a second look
      - flagged for review only when the winner's own score is < 1.0, i.e.
        the whole call rests on shared/generic words
    """
    scores = score_bullet(text)
    if not scores:
        return FALLBACK_TAG, False

    priority = list(TAG_KEYWORDS.keys())
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

    tagged, skipped_existing, fell_back = 0, 0, 0
    review_rows = []
    for r in rows:
        if r.get("Tags", "").strip():
            skipped_existing += 1
            continue
        tag_str, tied = assign_tags(r["Bullet Point"])
        r["Tags"] = tag_str
        tagged += 1
        if tag_str == FALLBACK_TAG:
            fell_back += 1
        if tied:
            review_rows.append({
                "Role / Company": r["Role / Company"],
                "Tags": tag_str,
                "Bullet Point": r["Bullet Point"],
            })

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point"])
        w.writeheader()
        w.writerows(rows)

    if review_rows:
        with open(review_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point"])
            w.writeheader()
            w.writerows(review_rows)

    print(f"{args.input_csv}: {len(rows)} rows")
    print(f"  Already tagged (left alone): {skipped_existing}")
    print(f"  Newly tagged: {tagged}  (of which {fell_back} fell back to {FALLBACK_TAG})")
    print(f"  Weak match, no unique keyword hit (flagged for review): {len(review_rows)}")
    print(f"  Wrote: {out_path}")
    if review_rows:
        print(f"  Wrote: {review_path}")


if __name__ == "__main__":
    main()
