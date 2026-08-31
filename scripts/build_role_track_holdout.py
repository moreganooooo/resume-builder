"""Draw a blind, stratified sample of roles for hand-labeling IC vs. manager.

WHY THIS EXISTS, AND WHY IT COMES FIRST

Role track is the highest-value filter in the role-attribute spec and the
only one with no deterministic path. Measured over this profile's 2,510
jobs: 49% of titles contain manager/director/lead/VP/head-of, but title
is near-useless as a label -- every sampled "Manager" was an individual
contributor marketing role. Body evidence is strong on only 8.4% of
postings. So the classifier must be an LLM field, and an LLM field with
no labeled holdout is a filter that hides jobs for reasons nobody can
audit.

The spec sets an asymmetric bar: >=90% precision on the EXCLUDED class.
Hiding a job you wanted is unrecoverable -- you never see it to correct
it -- while showing one you did not want costs a glance. This file is
what makes that bar measurable rather than aspirational.

DESIGN

Blind on purpose: no model prediction appears in the output. A labeler
shown a guess agrees with it, and a holdout that agrees with the model
by construction measures nothing.

Stratified on purpose: a uniform sample would be ~half obvious ICs, and
the sample size that matters is the AMBIGUOUS band -- manager-signal
titles, where the classifier will actually be wrong. Strata are recorded
per row so precision can be reported per band instead of pooled into one
flattering number.

Usage:
    python scripts/build_role_track_holdout.py            # write the CSV
    python scripts/build_role_track_holdout.py --status   # labeling progress
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

# Title tokens that merely SUGGEST people leadership. Deliberately not a
# classifier -- this only decides which stratum a role is sampled into,
# so a false positive here costs nothing but a row in the harder band.
MANAGER_SIGNAL = re.compile(
    r"\b(manager|director|head of|vp|vice president|chief|lead|supervisor|principal)\b",
    re.I,
)

# Phrases that genuinely indicate reports. Used ONLY to split the
# manager-signal stratum into "signal in title AND body" vs. "title
# only", which is exactly where the classifier's errors will cluster.
REPORTS_EVIDENCE = re.compile(
    r"\b(direct reports?|manage a team|managing a team|people manager|"
    r"lead a team|leading a team|hire,? (?:train|develop)|"
    r"coach(?:ing)? and develop|team of \d+|mentor(?:ing)? and manag)",
    re.I,
)

# "n/a" is a real verdict, not a skipped row. The sample is drawn from
# the whole corpus, so it catches roles that have no IC/manager axis at
# all -- an in-person retail associate, for one. Forcing that into "ic"
# to satisfy a three-value vocabulary would put a wrong label in the
# ground truth the classifier is measured against, which is a worse
# outcome than admitting the question does not apply. Excluded from
# accuracy scoring rather than counted as either class.
LABEL_VALUES = ("ic", "manager", "unclear", "n/a")

# Spellings a human actually types for the same verdicts.
LABEL_ALIASES = {
    "na": "n/a",
    "n\\a": "n/a",
    "not applicable": "n/a",
    "none": "n/a",
    "individual contributor": "ic",
    "people manager": "manager",
    "unsure": "unclear",
    "unknown": "unclear",
}

DEFAULT_PER_STRATUM = 40
EXCERPT_CHARS = 900


def _stratum(title: str, body: str) -> str:
    """Which sampling band a role belongs to."""
    title_signal = bool(MANAGER_SIGNAL.search(title))
    body_signal = bool(REPORTS_EVIDENCE.search(body))
    if title_signal and body_signal:
        return "title+body"  # should be easy; a miss here is alarming
    if title_signal:
        return "title-only"  # the ambiguous band -- most errors live here
    if body_signal:
        return "body-only"  # IC-sounding title, real reports described
    return "neither"  # should be easy IC


def _description_of(stored: str) -> str:
    """The posting's prose, out of the JSON blob jobs.raw_text actually holds.

    raw_text is not text: it is the whole JD document, description plus
    the underscore-prefixed metadata keys (_evaluation, _liveness). Reading
    it directly puts scores and timestamps in front of a human labeler and
    lets a salary regex match a number out of _evaluation rather than out
    of the job. Same hazard jd_manager.read_jd_text() exists to prevent
    before text reaches a prompt.
    """
    stored = (stored or "").strip()
    if not stored.startswith("{"):
        return _strip_html(stored)
    try:
        return _strip_html(str(json.loads(stored).get("description") or ""))
    except (ValueError, AttributeError):
        return ""


def _strip_html(text: str) -> str:
    """Tags out, block boundaries kept as spaces.

    Most descriptions are stored as HTML. Dropping tags without
    substituting a space would weld the last word of one list item to the
    first of the next ("direct reportsManage"), which breaks the very
    \\b-anchored phrase matching the strata depend on.
    """
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _excerpt(body: str) -> str:
    """The evidence a human needs, biased toward where reports are named.

    A leading slice is mostly boilerplate ("About us..."), so if the body
    describes reports anywhere, centre the excerpt there instead.
    """
    match = REPORTS_EVIDENCE.search(body)
    if match:
        start = max(0, match.start() - EXCERPT_CHARS // 3)
        # Advance to a word boundary so the excerpt does not open
        # mid-word ("llow-up, providing..."), which costs the labeler a
        # second of re-orientation on every single row.
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
    for job_id, title, company, stored in raw:
        body = _description_of(stored)
        if not title or len(body) < 200:
            continue  # nothing for a human to judge
        rows.append(
            {
                "job_id": job_id,
                "title": title,
                "company": company,
                "stratum": _stratum(title, body),
                "excerpt": _excerpt(body),
            }
        )
    return rows


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
    # Shuffle across strata so the labeler cannot infer a row's stratum
    # from its position and start pattern-matching instead of reading.
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
                    "",  # you fill this in: ic | manager | unclear | n/a
                    "",
                    row["excerpt"],
                ]
            )


def read_labels(path: str) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def normalize_label(raw: str) -> str:
    """Accept what a human actually types, or "" if it is unrecognized.

    Real labeling produced "IC", "ic", and "unclear, likely IC". Rejecting
    those as typos would be pedantry -- the intent is unambiguous. A
    qualified label resolves to its LEADING term ("unclear, likely IC" is
    unclear), because the qualifier is the labeler's uncertainty, not a
    second verdict, and scoring it as "ic" would silently promote a
    hedge into a confident answer.
    """
    text = (raw or "").strip().lower()
    if not text:
        return ""
    # Checked BEFORE the split, because "/" is both a qualifier separator
    # and a character inside "n/a" -- splitting first silently yields "n".
    if text in LABEL_VALUES or text in LABEL_ALIASES:
        return LABEL_ALIASES.get(text, text)
    head = re.split(r"[,;(/]", text)[0].strip()
    return (
        LABEL_ALIASES.get(head, head)
        if head in LABEL_VALUES or head in LABEL_ALIASES
        else ""
    )


def status(path: str) -> int:
    """Progress, plus the cross-tab that shows whether strata predict label."""
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
        print(f"  {label:<10} {n}")

    # The cross-tab is the point. Pooled accuracy hides the only thing
    # that matters: whether a cheap stratum already separates the
    # classes, and which band the classifier actually has to earn.
    grid: dict[str, dict[str, int]] = {}
    for r in done:
        label = normalize_label(r["label"]) or "?"
        grid.setdefault(r["stratum"], {})[label] = (
            grid.setdefault(r["stratum"], {}).get(label, 0) + 1
        )
    if grid:
        cols = list(LABEL_VALUES)
        print(
            f"\n{'stratum':<12} " + " ".join(f"{c:>8}" for c in cols) + f"{'total':>8}"
        )
        for stratum in sorted(grid):
            cells = grid[stratum]
            total = sum(cells.values())
            row = " ".join(f"{cells.get(c, 0):>8}" for c in cols)
            print(f"{stratum:<12} {row}{total:>8}")

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
    path = args.out or f"{root}/role_track_holdout.csv"

    if args.status:
        if not os.path.exists(path):
            print(f"no holdout at {path}")
            return 1
        return status(path)

    # Never silently destroy hand-labeling. Same reasoning as
    # write_verified_ledger()'s bail-out: the expensive artifact here is
    # the human judgement in the file, not the file.
    if os.path.exists(path) and not args.force:
        labeled = sum(1 for r in read_labels(path) if (r.get("label") or "").strip())
        print(f"{path} already exists ({labeled} rows labeled).")
        print("Refusing to overwrite. Pass --force to discard those labels.")
        return 1

    rows = load_rows(args.profile)
    picked = sample(rows, args.per_stratum, args.seed)
    write_holdout(path, picked)

    totals: dict[str, int] = {}
    for row in rows:
        totals[row["stratum"]] = totals.get(row["stratum"], 0) + 1
    print(f"corpus: {len(rows)} judgeable roles")
    for stratum in sorted(totals):
        drawn = sum(1 for r in picked if r["stratum"] == stratum)
        print(f"  {stratum:<12} {totals[stratum]:>5} in corpus, {drawn} sampled")
    print(f"\nwrote {len(picked)} rows to {path}")
    print(textwrap.dedent(f"""
            Fill the `label` column with one of: {', '.join(LABEL_VALUES)}.
              ic       -- no direct reports; may still "lead" projects
              manager  -- has or will have direct reports
              unclear  -- the posting genuinely does not say

            "unclear" is a real answer, not a cop-out: if you cannot tell
            from the posting, the model cannot either, and those rows
            belong in a separate bucket rather than forced into a guess
            that would score the classifier against noise.

            Progress: python scripts/build_role_track_holdout.py --status
            """).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
