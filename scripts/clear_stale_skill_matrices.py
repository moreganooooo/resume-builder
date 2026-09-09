"""clear_stale_skill_matrices.py -- clears a cached evaluation["skill_matrix"]
so a later `resume` batch-matrix run treats it as missing and recomputes it.

Why this exists: dashboard_actions._batch_matrix() (the "[M]" bulk action
in Browse & Manage Jobs) only computes a matrix for jobs that don't have
one yet -- `if not (jd.get("evaluation") or {}).get("skill_matrix")`. That
means updating verified_tools.json (adding skills via the Skills Bank
Builder) and re-running scripts/embed_verified_skills.py never refreshes a
job that was already scored once. This script is the missing "make it
eligible again" step -- it only clears the cache, it never recomputes
anything itself (re-run the batch/single-job matrix action afterward for
that).

Two modes:

`--all` clears EVERY cached matrix. Needed after a change to how coverage
is computed at all (e.g. dashboard_actions._compute_skill_matrix_for_jd
switching from bullet-bank matching to matching a JD skill directly
against verified_tools.json) -- every existing matrix was scored under
the OLD method regardless of what values it holds, so "flat" is the wrong
test for that case.

Without `--all`, only FLAT matrices are cleared: a non-empty skill_matrix
where EVERY entry's coverage is exactly 0. That is a narrower, cheaper
sweep for the ordinary case of a genuinely stale/broken cache (e.g. the
reference embedding didn't exist yet when it was computed) without
forcing a full, costly re-embed of every job's skills.

This only ever clears a cache field that is trivially regenerable by
re-running the matrix action -- unlike the other maintenance scripts in
this repo, there is nothing here that a backup protects against, since
the "undo" is just recomputing it again.

Usage:
    python scripts/clear_stale_skill_matrices.py            # dry run, flat only
    python scripts/clear_stale_skill_matrices.py --apply    # clears flat ones
    python scripts/clear_stale_skill_matrices.py --all --apply  # clears every matrix
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jd_manager  # noqa: E402
import jd_source  # noqa: E402
import picker  # noqa: E402
import profile_paths  # noqa: E402


def _is_flat(skill_matrix: list) -> bool:
    return bool(skill_matrix) and all(
        (entry.get("coverage") or 0) == 0 for entry in skill_matrix
    )


def find_flat_matrices() -> list:
    """Returns [{"identifier", "title", "company", "skill_count"}] for every
    evaluated job (pending or completed) with a flat skill_matrix."""
    return _find_matrices(_is_flat)


def find_all_matrices() -> list:
    """Returns [{"identifier", "title", "company", "skill_count"}] for every
    evaluated job (pending or completed) with ANY cached skill_matrix."""
    return _find_matrices(bool)


def _find_matrices(predicate) -> list:
    findings = []
    for row in picker.list_all_evaluated_jds():
        skill_matrix = (row.get("evaluation") or {}).get("skill_matrix") or []
        if predicate(skill_matrix):
            findings.append(
                {
                    "identifier": row["path"],
                    "title": row.get("title") or "",
                    "company": row.get("company") or "",
                    "skill_count": len(skill_matrix),
                }
            )
    return findings


def clear_matrix(identifier: str, profile: str) -> None:
    with jd_source.resolved_jd(identifier, profile) as (path, _is_db):
        evaluation = jd_manager.read_evaluation(path)
        if not evaluation:
            return
        evaluation["skill_matrix"] = []
        jd_manager.save_evaluation(path, evaluation)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="clear the matrices found")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="clear_all",
        help="clear every cached matrix, not just flat (all-0%%) ones",
    )
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()

    findings = find_all_matrices() if args.clear_all else find_flat_matrices()
    label = "cached" if args.clear_all else "flat (all-0%)"
    if not findings:
        print(f"No {label} skill matrices found. Nothing to do.")
        return 0

    print(f"{len(findings)} job(s) with a {label} skill matrix:")
    for f in findings:
        print(f"  [{f['company']}] {f['title']} -- {f['skill_count']} skill(s)")

    if args.apply:
        for f in findings:
            clear_matrix(f["identifier"], profile)
        print(
            f"\ncleared {len(findings)} matrix cache(s). Re-run the batch skills "
            "gap matrix action (dashboard [M], or Settings & Upkeep -> Recompute "
            "Skill Gap Matrices) to regenerate them with your current skills."
        )
    else:
        print("\ndry run -- re-run with --apply to clear these.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
