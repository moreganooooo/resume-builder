"""dedupe_verified_ledger.py -- collapses near-duplicate entries in the
verified tools/projects/metrics ledger.

refresh_verified_ledger.py de-duplicates on exact normalized keys, which
cannot see that "Adobe Sign pilot program" and "Adobe Sign program" are
one project, or that "Illustrator" and "Adobe Illustrator" are one tool.
Re-running extraction therefore accumulates variants. This collapses
them.

Two different rules, because the two lists fragment differently:

TOOLS -- merge only when the longer name adds nothing but vendor or
generic tokens ("Illustrator" -> "Adobe Illustrator", "Outreach" ->
"Outreach.io"). Plain containment would wrongly fuse genuinely distinct
tools: "Facebook" and "Facebook Ads" are different products, and "Adobe"
is not "Adobe Illustrator".

PROJECTS -- merge on a shared leading-token prefix within one employer.
The extractor splits a single initiative into a dozen phrasings ("Adobe
Sign pilot", "Adobe Sign ABM pilot messaging strategy", ...), and those
share a prefix by construction. The shortest name in a cluster wins as
the canonical form.

METRICS are left alone. A metric is label+value+employer, and two
similar labels with different values are usually two real measurements,
not a duplicate.

Nothing is deleted without a backup, and the default is a dry run that
prints the full merge plan for review.

Usage:
    python scripts/dedupe_verified_ledger.py            # show the plan
    python scripts/dedupe_verified_ledger.py --apply    # collapse
"""

import argparse
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bootstrap_profile  # noqa: E402
import cli_art  # noqa: E402

# Tokens that carry no distinguishing meaning in a tool name: vendor
# prefixes and product-category suffixes. If the ONLY difference between
# two names is tokens from this set, they name the same tool.
GENERIC_TOKENS = {
    "adobe",
    "google",
    "microsoft",
    "ms",
    "io",
    "com",
    "inc",
    "crm",
    "cms",
    "suite",
    "platform",
    "software",
    "tool",
    "app",
    "online",
    "pro",
}

# How many leading tokens two project names must share to be considered
# the same initiative. Two is enough to bind "Adobe Sign *" together
# without fusing unrelated projects that happen to share one word.
PROJECT_PREFIX_TOKENS = 2


def _tokens(name: str) -> List[str]:
    return re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()


def _norm(name: str) -> str:
    return " ".join(_tokens(name))


def plan_tool_merges(tools: List[dict]) -> Dict[str, str]:
    """Returns {duplicate_normalized_name: canonical_name}.

    A name merges into another only when the other contains all its
    tokens and adds nothing but GENERIC_TOKENS.
    """
    by_employer = defaultdict(list)
    for tool in tools:
        by_employer[_norm(tool.get("employer", ""))].append(tool.get("name", ""))

    merges: Dict[str, str] = {}
    for names in by_employer.values():
        unique = sorted({n for n in names if n}, key=lambda n: (len(_tokens(n)), n))
        for short in unique:
            short_set = set(_tokens(short))
            if not short_set:
                continue
            for long in unique:
                if long == short:
                    continue
                long_set = set(_tokens(long))
                if not short_set < long_set:
                    continue
                if long_set - short_set <= GENERIC_TOKENS:
                    merges[_norm(short)] = long
                    break
    return merges


def plan_project_merges(projects: List[dict]) -> Dict[str, str]:
    """Returns {normalized_name: canonical_name} for projects sharing an
    employer and a leading token prefix."""
    clusters = defaultdict(list)
    for project in projects:
        name = project.get("name", "")
        tokens = _tokens(name)
        if len(tokens) < PROJECT_PREFIX_TOKENS:
            continue
        key = (
            _norm(project.get("employer", "")),
            tuple(tokens[:PROJECT_PREFIX_TOKENS]),
        )
        clusters[key].append(name)

    merges: Dict[str, str] = {}
    for names in clusters.values():
        unique = {n for n in names if n}
        if len(unique) < 2:
            continue
        canonical = sorted(unique, key=lambda n: (len(_tokens(n)), n))[0]
        for name in unique:
            if name != canonical:
                merges[_norm(name)] = canonical
    return merges


def apply_merges(entries: List[dict], merges: Dict[str, str]) -> List[dict]:
    """Rewrites duplicate names to their canonical form, then drops rows
    that have become identical (same name + employer). The first entry of
    each surviving pair is kept, so hand-added fields on the earliest --
    typically hand-curated -- row survive."""
    seen = set()
    out = []
    for entry in entries:
        name = entry.get("name", "")
        canonical = merges.get(_norm(name), name)
        key = (_norm(canonical), _norm(entry.get("employer", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append({**entry, "name": canonical})
    return out


def dedupe(apply_changes: bool = False) -> dict:
    targets = [
        (bootstrap_profile.VERIFIED_TOOLS_PATH, "tools", plan_tool_merges),
        (bootstrap_profile.VERIFIED_PROJECTS_PATH, "projects", plan_project_merges),
    ]

    report = {}
    for path, list_key, planner in targets:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get(list_key, [])

        # Iterate to a fixed point. Renaming a duplicate to its canonical
        # form can expose a further merge that was invisible beforehand
        # ("Adobe Sign ABM campaigns" only becomes mergeable into "Adobe
        # Sign" once its siblings have collapsed onto it), so a single
        # pass leaves the ledger one step short of stable.
        collapsed = entries
        merges: Dict[str, str] = {}
        for _ in range(10):
            round_merges = planner(collapsed)
            if not round_merges:
                break
            merges.update(round_merges)
            collapsed = apply_merges(collapsed, round_merges)

        report[list_key] = {
            "before": len(entries),
            "after": len(collapsed),
            "merges": merges,
        }

        if not apply_changes or len(collapsed) == len(entries):
            continue

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, f"{path}.backup-{stamp}")

        data[list_key] = collapsed
        data.setdefault("_meta", {})["total_entries"] = len(collapsed)
        data["_meta"]["last_updated"] = datetime.now().date().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the collapsed ledger"
    )
    parser.add_argument(
        "--show", type=int, default=25, help="how many merges to print (default 25)"
    )
    args = parser.parse_args()

    report = dedupe(apply_changes=args.apply)
    verb = "collapsed" if args.apply else "would collapse"

    for list_key, info in report.items():
        removed = info["before"] - info["after"]
        print(
            f"\n  {list_key}: {info['before']} -> {info['after']}  ({verb} {removed})"
        )
        for dup, canonical in list(info["merges"].items())[: args.show]:
            print(f"      {dup!r}  ->  {canonical!r}")
        if len(info["merges"]) > args.show:
            print(f"      ... and {len(info['merges']) - args.show} more")

    if not args.apply:
        print("\n  dry run -- re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
