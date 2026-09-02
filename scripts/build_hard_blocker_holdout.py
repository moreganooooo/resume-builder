"""Draw a blind, stratified sample of roles for hand-labeling years/degree
hard-blocker judgments.

WHY THIS EXISTS

hard_blockers was, until this change, an unmeasured, unconditional gate:
any non-empty list from the recruiter-eval LLM call zeroed composite_score
and forced Skip -- a stronger, less-validated gate than role_track was
before ITS holdout measurement. Categorizing blockers (years_experience,
degree, certification, citizenship_clearance, onsite_commute, other) let
the years_experience/degree subset stop auto-zeroing, but "stop doing an
unmeasured thing automatically" is not the same as "safe to gate on once
measured" -- the same >=90% precision bar role_track cleared applies here
before any opt-in filter gets built on top of experience_blockers.

CANDIDATE-SPECIFIC, UNLIKE role_track

role_track asks "does this posting describe a people-manager role" --
answerable from the posting alone. This asks "does this posting's stated
years/degree requirement actually disqualify THIS candidate" -- not
answerable from the posting alone. You (the labeler) bring your own
background to each row: a "5+ years in finance" requirement blocks a
candidate with 2 years and doesn't block one with 8. There is no way to
automate that half of the judgment; this script only automates finding
and presenting the right rows to look at.

DESIGN

Blind on purpose, same as build_role_track_holdout.py: no model
prediction appears in the output, so a labeler can't rubber-stamp a
guess.

Stratified on a cheap regex signal for years/degree language
(YEARS_SIGNAL / DEGREE_SIGNAL) -- not on whether the current pipeline
already tagged a blocker that way, since categorization only just
shipped and essentially no persisted evaluation carries it yet.

Usage:
    python scripts/build_hard_blocker_holdout.py            # write the CSV
    python scripts/build_hard_blocker_holdout.py --status   # labeling progress
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import sqlite3
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402

# Cheap signals used ONLY to decide which stratum a role is sampled into
# -- not a classifier. A false positive here costs nothing but a row in
# the wrong band.
YEARS_SIGNAL = re.compile(
    r"\b\d+\+?\s*(?:-\s*\d+\+?\s*)?years?\b.{0,30}\b(experience|exp\.?)\b"
    r"|\b(experience|exp\.?)\b.{0,30}\b\d+\+?\s*years?\b",
    re.I,
)
DEGREE_SIGNAL = re.compile(
    r"\b(bachelor'?s?|master'?s?|b\.?a\.?|b\.?s\.?|m\.?b\.?a\.?|associate'?s?)\b"
    r".{0,40}\b(degree|diploma)\b"
    r"|\bdegree\b.{0,40}\b(required|preferred|in [a-z])",
    re.I,
)

# "n/a" is a real verdict: the stratum regex is cheap and sometimes wrong
# -- a row with no genuine years/degree requirement at all belongs here,
# not forced into "does_not_block" (which would claim there WAS a
# requirement and it happened not to apply).
LABEL_VALUES = ("blocks", "does_not_block", "unclear", "n/a")

LABEL_ALIASES = {
    "na": "n/a",
    "n\\a": "n/a",
    "not applicable": "n/a",
    "none": "n/a",
    "no requirement": "n/a",
    "block": "blocks",
    "blocking": "blocks",
    "disqualifying": "blocks",
    "disqualifies": "blocks",
    "not blocking": "does_not_block",
    "does not disqualify": "does_not_block",
    "doesn't block": "does_not_block",
    "no block": "does_not_block",
    "unsure": "unclear",
    "unknown": "unclear",
}

DEFAULT_PER_STRATUM = 40

# Same reasoning as build_role_track_holdout.py's MAX_FULL_EXCERPT_CHARS:
# a posting with no signal match used to fall back to body[:900], mostly
# "About us..." boilerplate -- worthless for judging a requirements list
# that usually appears further down.
MAX_FULL_EXCERPT_CHARS = 6000
EXCERPT_CHARS = 3000


def _stratum(body: str) -> str:
    years = bool(YEARS_SIGNAL.search(body))
    degree = bool(DEGREE_SIGNAL.search(body))
    if years and degree:
        return "years+degree"
    if years:
        return "years-only"
    if degree:
        return "degree-only"
    return "neither"  # should mostly be n/a -- checks the regex isn't over-firing


def _description_of(stored: str) -> str:
    """Same extraction as build_role_track_holdout.py -- raw_text is the
    whole JD document, description plus underscore-prefixed metadata keys
    that must never reach a labeler (scores, timestamps)."""
    stored = (stored or "").strip()
    if not stored.startswith("{"):
        return _strip_html(stored)
    try:
        return _strip_html(str(json.loads(stored).get("description") or ""))
    except (ValueError, AttributeError):
        return ""


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _excerpt(body: str) -> str:
    """Centers on the years/degree signal, same windowing logic as
    build_role_track_holdout.py's _excerpt()."""
    if len(body) <= MAX_FULL_EXCERPT_CHARS:
        return " ".join(body.split())
    match = YEARS_SIGNAL.search(body) or DEGREE_SIGNAL.search(body)
    if match:
        start = max(0, match.start() - EXCERPT_CHARS // 3)
        if start:
            space = body.find(" ", start)
            start = space + 1 if 0 <= space < start + 40 else start
        window = body[start : start + EXCERPT_CHARS]
        prefix = "..." if start else ""
    else:
        window = body[:EXCERPT_CHARS]
        prefix = ""
    return prefix + " ".join(window.split())


def load_rows(profile: str | None) -> list[dict]:
    root = (
        profile_paths.profile_root(profile) if profile else profile_paths.profile_root()
    )
    db = sqlite3.connect(f"{root}/data.db")
    try:
        raw = db.execute(
            "select id, coalesce(title,''), coalesce(company,''), "
            "coalesce(raw_text,'') from jobs"
        ).fetchall()
    finally:
        db.close()
    rows = []
    sources = {}
    for job_id, title, company, stored in raw:
        body = _description_of(stored)
        if not title or len(body) < 200:
            continue
        rows.append(
            {
                "job_id": job_id,
                "title": title,
                "company": company,
                "stratum": _stratum(body),
                "excerpt": _excerpt(body),
            }
        )
        sources[job_id] = {"raw_text": stored}
    return rows, sources


def sample(rows: list[dict], per_stratum: int, seed: int) -> list[dict]:
    by_stratum: dict[str, list[dict]] = {}
    for row in rows:
        by_stratum.setdefault(row["stratum"], []).append(row)
    rng = random.Random(seed)
    picked: list[dict] = []
    for stratum in sorted(by_stratum):
        pool = by_stratum[stratum]
        rng.shuffle(pool)
        picked.extend(pool[:per_stratum])
    rng.shuffle(picked)
    return picked


def write_holdout(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["job_id", "title", "company", "stratum", "label", "note", "excerpt"]
        )
        for row in rows:
            writer.writerow(
                [
                    row["job_id"],
                    row["title"],
                    row["company"],
                    row["stratum"],
                    "",  # you fill this in: blocks | does_not_block | unclear | n/a
                    "",
                    row["excerpt"],
                ]
            )


def write_source(path: str, sources: dict, picked_ids: set) -> None:
    """Preserves picked rows' raw_text so eval_hard_blocker.py measures
    against the exact text a human labeled, not whatever the posting
    looks like (edited/expired/gone) whenever the eval script later runs."""
    subset = {job_id: sources[job_id] for job_id in picked_ids if job_id in sources}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(subset, fh)


def read_labels(path: str) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def normalize_label(raw: str) -> str:
    """Same qualifier-tolerant normalization as build_role_track_holdout.py's
    normalize_label() -- accepts "blocks, borderline" as "blocks", not a typo."""
    text = (raw or "").strip().lower()
    if not text:
        return ""
    if text in LABEL_VALUES or text in LABEL_ALIASES:
        return LABEL_ALIASES.get(text, text)
    head = re.split(r"[,;(/]", text)[0].strip()
    return (
        LABEL_ALIASES.get(head, head)
        if head in LABEL_VALUES or head in LABEL_ALIASES
        else ""
    )


def status(path: str) -> int:
    rows = read_labels(path)
    done = [r for r in rows if (r.get("label") or "").strip()]
    bad = sorted(
        {
            (r.get("label") or "").strip()
            for r in done
            if not normalize_label(r.get("label", ""))
        }
    )
    print(f"labeled {len(done)}/{len(rows)}")

    counts: dict[str, int] = {}
    for r in done:
        counts[normalize_label(r["label"]) or "?"] = (
            counts.get(normalize_label(r["label"]) or "?", 0) + 1
        )
    for label, n in sorted(counts.items()):
        print(f"  {label:<15} {n}")

    grid: dict[str, dict[str, int]] = {}
    for r in done:
        label = normalize_label(r["label"]) or "?"
        grid.setdefault(r["stratum"], {})[label] = (
            grid.setdefault(r["stratum"], {}).get(label, 0) + 1
        )
    if grid:
        cols = list(LABEL_VALUES)
        print(
            f"\n{'stratum':<14} " + " ".join(f"{c:>15}" for c in cols) + f"{'total':>8}"
        )
        for stratum in sorted(grid):
            cells = grid[stratum]
            total = sum(cells.values())
            row = " ".join(f"{cells.get(c, 0):>15}" for c in cols)
            print(f"{stratum:<14} {row}{total:>8}")

    remaining: dict[str, int] = {}
    for r in rows:
        if not (r.get("label") or "").strip():
            remaining[r["stratum"]] = remaining.get(r["stratum"], 0) + 1
    if remaining:
        print("\nunlabeled per stratum:", dict(sorted(remaining.items())))

    if bad:
        print(f"\nUNRECOGNIZED LABELS: {bad}  (allowed: {', '.join(LABEL_VALUES)})")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profile")
    parser.add_argument("--per-stratum", type=int, default=DEFAULT_PER_STRATUM)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out")
    parser.add_argument(
        "--status", action="store_true", help="report labeling progress and stop"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing holdout, discarding any labels in it",
    )
    args = parser.parse_args()

    root = (
        profile_paths.profile_root(args.profile)
        if args.profile
        else profile_paths.profile_root()
    )
    path = args.out or f"{root}/hard_blocker_holdout.csv"
    source_path = f"{root}/hard_blocker_holdout_source.json"

    if args.status:
        if not os.path.exists(path):
            print(f"no holdout at {path}")
            return 1
        return status(path)

    if os.path.exists(path) and not args.force:
        labeled = sum(1 for r in read_labels(path) if (r.get("label") or "").strip())
        print(f"{path} already exists ({labeled} rows labeled).")
        print("Refusing to overwrite. Pass --force to discard those labels.")
        return 1

    rows, sources = load_rows(args.profile)
    picked = sample(rows, args.per_stratum, args.seed)
    write_holdout(path, picked)
    write_source(source_path, sources, {r["job_id"] for r in picked})

    totals: dict[str, int] = {}
    for row in rows:
        totals[row["stratum"]] = totals.get(row["stratum"], 0) + 1
    print(f"corpus: {len(rows)} judgeable roles")
    for stratum in sorted(totals):
        drawn = sum(1 for r in picked if r["stratum"] == stratum)
        print(f"  {stratum:<14} {totals[stratum]:>5} in corpus, {drawn} sampled")
    print(f"\nwrote {len(picked)} rows to {path}")
    print(f"preserved source text for {len(picked)} rows to {source_path}")
    print(textwrap.dedent(f"""
            Fill the `label` column with one of: {', '.join(LABEL_VALUES)}.
              blocks          -- you don't meet this years/degree
                                 requirement and it would realistically
                                 disqualify you
              does_not_block  -- there's a stated requirement, but you
                                 meet it, or it reads as a soft
                                 preference rather than a hard bar
              unclear         -- the posting states a requirement but
                                 it's genuinely ambiguous whether it'd
                                 block you
              n/a             -- no real years/degree requirement here
                                 (the regex signal was a false hit)

            "unclear" and "n/a" are real answers -- forcing a guess
            would put noise in the ground truth the classifier gets
            measured against.

            Progress: python scripts/build_hard_blocker_holdout.py --status
            """).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
