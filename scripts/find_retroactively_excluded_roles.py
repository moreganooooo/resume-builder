"""find_retroactively_excluded_roles.py -- identifies PENDING roles that
would be rejected by today's scan filters or today's scoring, even though
they were saved under an older configuration.

Two independent kinds of "would now be excluded", counted separately:

  1. Gate failures: re-runs the same deterministic scan-time gates
     scan_boards.py applies (_passes_employment_filter,
     _passes_compensation_filter, _passes_hours_filter,
     _passes_location_filter, _passes_hybrid_preference_filter) against
     the JD's own already-saved fields and the *current* scan_filters.yml.
  2. Score-based flags: recomputes composite_score/recommendation with
     the current fit_composite_score() (current content_settings
     scoring_weights, current stress/capability-gap adjustments) and
     flags roles whose recommendation now comes out "Skip". Only
     applicable to roles that already have an evaluation -- an
     unevaluated role has no score to recompute, so it's checked for
     gate failures only.

Covers the FULL pending population, not just already-evaluated rows:
picker.pending_roles() (file paths + database-only ids, no evaluation
required) is unioned with the already-evaluated pending set from
picker.list_all_evaluated_jds(). Checking gates only on the evaluated
subset would miss exactly the population this script exists to protect --
the unevaluated backlog about to be spent API calls on -- so a
scan_filters.yml change made after a role was scraped but before it's
evaluated is still caught here, before evaluation ever runs.

Restricted to PENDING/unevaluated roles only -- this never looks at, and
will never touch, anything already applied/interviewing/offer or later in
the funnel. That is a hard safety rule, not a toggle.

Run reconcile_jd_status.py first: this script keys off status (via
picker.list_all_evaluated_jds()), so a row whose status has drifted from
its file's actual directory would be judged on stale information.

The database is backed up before any --apply write. This is real, live
data -- review the dry-run report before ever passing --apply.

Usage:
    python scripts/find_retroactively_excluded_roles.py            # dry run
    python scripts/find_retroactively_excluded_roles.py --apply    # archives
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import content_settings  # noqa: E402
import jd_manager  # noqa: E402
import jd_source  # noqa: E402
import orchestrator  # noqa: E402
import picker  # noqa: E402
import profile_paths  # noqa: E402
import scan_boards  # noqa: E402


def _raw_jd_fields(identifier: str, profile: str) -> dict:
    """Loads the JD's own saved JSON, whether it's a real file or a
    database-only row -- jd_source.resolved_jd() handles both uniformly
    via a synced-back temp file for the latter."""
    with jd_source.resolved_jd(identifier, profile) as (path, _):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def check_gates(data: dict) -> list:
    """Returns the list of gate names this JD would now fail, re-run
    against the CURRENT scan_filters.yml. Exclusion-only, same as the
    gates themselves -- an unstated field never fails a gate."""
    failed = []
    description = data.get("description") or ""
    location = (data.get("location") or "").strip()

    if not scan_boards._passes_employment_filter(
        data.get("employment_type"), data.get("source_platform") or ""
    ):
        failed.append("employment_type")
    if not scan_boards._passes_compensation_filter(
        description, data.get("compensation")
    ):
        failed.append("compensation")
    if not scan_boards._passes_hours_filter(description):
        failed.append("hours")
    if not scan_boards._passes_location_filter(
        location,
        is_remote=data.get("is_remote"),
        work_model=data.get("work_model") or "",
    ):
        failed.append("location")
    if not scan_boards._passes_hybrid_preference_filter(location, description):
        failed.append("hybrid_preference")

    return failed


def check_score(evaluation: dict, description: str, scoring_weights: dict) -> bool:
    """Recomputes the recommendation with current scoring weights and
    reports whether it now comes out Skip. hard_blockers/experience_blockers
    already on the evaluation are preserved as-is -- this only re-applies
    the deterministic stress/capability-gap/composite-score math, not a
    fresh location/proximity recompute (no live distance input here)."""
    if not evaluation:
        return False
    rescored = orchestrator.rescore_evaluation_with_location(
        evaluation=evaluation,
        distance_miles=None,
        radius_miles=None,
        workplace_mode="any",
        remote_required=False,
        posting_age_days=evaluation.get("posting_age_days"),
        description=description,
        scoring_weights=scoring_weights,
    )
    return rescored.get("recommendation") == "Skip"


def find_candidates(profile: str) -> list:
    scoring_weights = content_settings.read_scoring_weights()
    findings = []
    checked = set()

    # Already-evaluated pending roles: full gate + score-based check.
    for row in picker.list_all_evaluated_jds(statuses=["Pending"]):
        identifier = row["path"]
        checked.add(identifier)
        try:
            data = _raw_jd_fields(identifier, profile)
        except (LookupError, OSError, json.JSONDecodeError):
            continue

        gate_failures = check_gates(data)
        description = data.get("description") or ""
        score_flagged = check_score(row["evaluation"], description, scoring_weights)

        if gate_failures or score_flagged:
            findings.append(
                {
                    "identifier": identifier,
                    "title": row.get("title") or "",
                    "company": row.get("company") or "",
                    "gate_failures": gate_failures,
                    "score_flagged": score_flagged,
                }
            )

    # Unevaluated backlog: no score to recompute, but still worth a gate
    # check before it burns an API call on evaluation. list_all_evaluated_jds()
    # skips these entirely (it requires an evaluation to include a row), so
    # pending_roles() is the only way to reach them.
    file_paths, db_ids = picker.pending_roles()
    for identifier in list(file_paths) + list(db_ids):
        if identifier in checked:
            continue
        try:
            data = _raw_jd_fields(identifier, profile)
        except (LookupError, OSError, json.JSONDecodeError):
            continue

        gate_failures = check_gates(data)
        if gate_failures:
            findings.append(
                {
                    "identifier": identifier,
                    "title": data.get("job_title") or "",
                    "company": data.get("company_name") or "",
                    "gate_failures": gate_failures,
                    "score_flagged": False,
                }
            )

    return findings


def apply_archive(findings: list, profile: str) -> None:
    for finding in findings:
        identifier = finding["identifier"]
        if os.path.exists(identifier):
            jd_manager.archive_jd(identifier)
        else:
            jd_source.set_status(identifier, "archived", profile)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="archive them")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()
    db_path = os.path.join(profile_paths.profile_root(profile), "data.db")

    print(
        "Reminder: this keys off status -- run scripts/reconcile_jd_status.py "
        "first if you haven't recently, or a drifted row may be judged on "
        "stale information.\n"
    )

    findings = find_candidates(profile)
    gate_only = [f for f in findings if f["gate_failures"] and not f["score_flagged"]]
    score_only = [f for f in findings if f["score_flagged"] and not f["gate_failures"]]
    both = [f for f in findings if f["gate_failures"] and f["score_flagged"]]

    print(f"Pending roles checked, {len(findings)} flagged:")
    print(f"  gate failure only:  {len(gate_only)}")
    print(f"  score-based only:   {len(score_only)}")
    print(f"  both:               {len(both)}\n")

    for finding in findings:
        reasons = []
        if finding["gate_failures"]:
            reasons.append("gates: " + ", ".join(finding["gate_failures"]))
        if finding["score_flagged"]:
            reasons.append("score: now Skip")
        print(f"  [{finding['company']}] {finding['title']} -- {'; '.join(reasons)}")

    if not findings:
        print("Nothing to do.")
        return 0

    if args.apply:
        if os.path.exists(db_path):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = f"{db_path}.backup-{stamp}"
            shutil.copy2(db_path, backup)
            print(f"\n✓ backed up to {backup}")
        apply_archive(findings, profile)
        print(f"\narchived {len(findings)} role(s).")
    else:
        print("\ndry run -- re-run with --apply to archive these after review.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
