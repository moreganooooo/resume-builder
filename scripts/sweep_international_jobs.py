"""sweep_international_jobs.py -- archives pending JDs that are actually
international/non-US roles, using the location logic in location_filter.py
(the same logic scan_ats.py/scan_boards.py now apply at discovery time --
see 2026-08-27's Ashby/Greenhouse/Lever location-richness fixes).

This exists because that fix only prevents NEW international postings from
being scanned in -- it does nothing for JDs already sitting in the pending
queue from before the fix, which the user had been archiving by hand as
they noticed them (ad hoc, easy to miss one).

Two checks per JD, either one is enough to archive it:
  1. location_filter.evaluate_location() against the JD's own `location`
     field (and `is_remote`/`work_model` hints), using the profile's
     scan_filters.yml `location:` block -- the same tiered verdict used at
     scan time.
  2. location_filter.looks_international_in_text() against the JD's
     description, for a "Remote"-only location field whose body text names
     an international-only eligibility list (the gap the structured check
     alone can't see).

Only ever touches pending JDs (jds/<profile>/ root) -- completed/expired/
already-archived JDs are left alone; a resume already built for one is not
this script's business to undo.

Usage:
    python scripts/sweep_international_jobs.py            # dry run
    python scripts/sweep_international_jobs.py --apply    # archives matches
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jd_manager  # noqa: E402
import location_filter  # noqa: E402
import profile_paths  # noqa: E402
import yaml  # noqa: E402


def _location_config() -> dict:
    profile = profile_paths.active_profile()
    path = os.path.join(profile_paths.board_scanner_dir(profile), "scan_filters.yml")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("location") or {}


def find_international_jds(paths: list, config: dict) -> list:
    """Returns [(path, reason)] for pending JDs that read as international."""
    hits = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue

        location = data.get("location") or ""
        verdict = location_filter.evaluate_location(
            location,
            config,
            is_remote=data.get("is_remote"),
            work_model=data.get("work_model") or "",
        )
        if not verdict.passes:
            hits.append((path, verdict.reason))
            continue

        if verdict.workplace == location_filter.REMOTE:
            description = data.get("description") or ""
            if location_filter.looks_international_in_text(description):
                hits.append((path, "description names international-only eligibility"))

    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="archive the matches")
    args = parser.parse_args()

    config = _location_config()
    if not config:
        print(
            "✗ no location: block in scan_filters.yml -- nothing to evaluate against."
        )
        return 1

    pending = jd_manager.get_pending_jds()
    hits = find_international_jds(pending, config)

    verb = "archived" if args.apply else "would archive"
    print(f"  pending JDs scanned  {len(pending)}")
    print(f"  {verb:<19} {len(hits)}")
    for path, reason in hits:
        print(f"      {os.path.basename(path):<70} {reason}")
        if args.apply:
            jd_manager.archive_jd(path)

    if not args.apply and hits:
        print("\n  dry run -- re-run with --apply to archive these.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
