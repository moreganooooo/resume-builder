"""dashboard_actions.py -- CLI the Go dashboard shells out to mid-session
to trigger real work (Liveness Check, Tailor Resume, Update Status) on a
single JD, from inside the Jobs screen (dashboard/internal/ui/screens/
jobs.go). Each subcommand does its real work via the existing Python
functions, then refreshes the same --jobs-path file the dashboard is
reading from (via dashboard._export_jobs_to()) so the Go side can reload
fresh state after the subprocess returns.

See docs/superpowers/specs/2026-08-08-jobs-screen-actions-design.md.

Deliberately plain stderr, not cli_art/theme: jobs.go captures this
subprocess's stderr verbatim into its own error panel (see
runAction()/jobsActionCompleteMsg in dashboard/internal/ui/screens/jobs.go)
and styles it there -- Rich markup or ANSI codes emitted here would leak
into that Go-rendered panel as garbage rather than styled text.
"""

import argparse
import sys

import dashboard
import jd_manager
import liveness
import orchestrator


def _liveness(jd_path: str, jobs_path: str) -> int:
    result = liveness.verify_jd_paths([jd_path])
    if result.get("error"):
        print(f"liveness check failed for {jd_path}", file=sys.stderr)
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _tailor(jd_path: str, jobs_path: str) -> int:
    completed, _failed = orchestrator.run_pipeline(jd_path=jd_path)
    if completed == 0:
        print(f"tailoring failed for {jd_path}", file=sys.stderr)
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _status(jd_path: str, new_status: str, jobs_path: str) -> int:
    if new_status not in jd_manager.APPLICATION_STATUSES:
        print(
            f"invalid status {new_status!r} -- must be one of {jd_manager.APPLICATION_STATUSES}",
            file=sys.stderr,
        )
        return 1
    jd_manager.save_application_status(jd_path, new_status)
    dashboard._export_jobs_to(jobs_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    liveness_parser = subparsers.add_parser("liveness")
    liveness_parser.add_argument("jd_path")
    liveness_parser.add_argument("--jobs-path", required=True)

    tailor_parser = subparsers.add_parser("tailor")
    tailor_parser.add_argument("jd_path")
    tailor_parser.add_argument("--jobs-path", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("jd_path")
    status_parser.add_argument("new_status")
    status_parser.add_argument("--jobs-path", required=True)

    args = parser.parse_args()

    if args.command == "liveness":
        return _liveness(args.jd_path, args.jobs_path)
    if args.command == "tailor":
        return _tailor(args.jd_path, args.jobs_path)
    if args.command == "status":
        return _status(args.jd_path, args.new_status, args.jobs_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
