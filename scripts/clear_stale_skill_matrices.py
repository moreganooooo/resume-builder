"""clear_stale_skill_matrices.py -- clears a cached evaluation["skill_matrix"]
for any pending/completed evaluated job whose matrix is FLAT (every skill
scored 0% coverage), so a later `resume` batch-matrix run treats it as
missing and recomputes it.

Why this exists: dashboard_actions._batch_matrix() (the "[M]" bulk action
in Browse & Manage Jobs) only computes a matrix for jobs that don't have
one yet -- `if not (jd.get("evaluation") or {}).get("skill_matrix")`. That
means updating verified_tools.json (adding skills via the Skills Bank
Builder) and re-running scripts/embed_verified_skills.py never refreshes a
job that was already scored once, even if every entry in its cached matrix
reads 0% because it was computed before those skills existed. This script
is the missing "make it eligible again" step -- it only clears the cache,
it never recomputes anything itself (re-run the batch/single-job matrix
action afterward for that).

"Flat" is deliberately narrow: a non-empty skill_matrix where EVERY entry's
coverage is exactly 0. A real matrix can legitimately contain individual
0% entries for a skill with no bullet-bank support at all, but every entry
landing at exactly the bottom percentile is the known symptom of a stale
reference embedding, not a real result.

This only ever clears a cache field that is trivially regenerable by
re-running the matrix action -- unlike the other maintenance scripts in
this repo, there is nothing here that a backup protects against, since
the "undo" is just recomputing it again.

Usage:
    python scripts/clear_stale_skill_matrices.py            # dry run
    python scripts/clear_stale_skill_matrices.py --apply    # clears them
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
    findings = []
    for row in picker.list_all_evaluated_jds():
        skill_matrix = (row.get("evaluation") or {}).get("skill_matrix") or []
        if _is_flat(skill_matrix):
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
    parser.add_argument(
        "--apply", action="store_true", help="clear the flat matrices found"
    )
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()

    findings = find_flat_matrices()
    if not findings:
        print("No flat (all-0%) skill matrices found. Nothing to do.")
        return 0

    print(f"{len(findings)} job(s) with a flat skill matrix:")
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
