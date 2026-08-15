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

THE USER_ERROR CONTRACT
-----------------------
Because that stderr goes through verbatim, a raw traceback or a terse
developer string used to land unfiltered in front of the least technical
part of the product. So on failure this module emits, as its VERY LAST
non-empty stderr line:

    USER_ERROR: <one plain-language sentence>

jobs.go's parseActionError() reads only the last non-empty line looking
for that prefix. When it finds one, the sentence becomes the error the
user sees and the full raw stderr moves behind the "d for details"
affordance -- nothing is lost, only deprioritized. When it finds none, it
falls back to showing raw stderr exactly as before.

Two rules follow from "last non-empty line", and breaking either silently
disables the contract:
  1. _user_error() must be the final thing written to stderr on any
     failing path.
  2. Nothing may print to stderr after it.

The plain sentence is produced by cli_art.describe_error(), the same
classifier the CLI's own friendly_error() uses, so a given failure reads
identically whether the user hit it from the terminal or the dashboard.
Importing cli_art here is safe despite the no-markup rule above:
describe_error() only returns strings, it never touches the Rich console.
"""

import argparse
import sys
import traceback

import cli_art
import dashboard
import jd_manager
import liveness
import orchestrator


def _user_error(message: str) -> None:
    """Emit the plain-language line jobs.go promotes into its error panel.

    Must be the last thing written to stderr on a failing path -- see the
    module docstring's contract."""
    print(f"USER_ERROR: {message}", file=sys.stderr)


def _user_error_from_exception(exc: BaseException, context: str) -> None:
    """Classify an unexpected exception into the same plain sentence the
    CLI would show for it, appending the suggested fix when there is one."""
    explanation, fix = cli_art.describe_error(exc, context)
    message = f"Couldn't finish {context}. {explanation}"
    if fix:
        message = f"{message} {fix}"
    _user_error(message)


def _liveness(jd_path: str, jobs_path: str) -> int:
    result = liveness.verify_jd_paths([jd_path])
    if result.get("error"):
        # Raw detail first, plain sentence last -- see the contract above.
        print(f"liveness check failed for {jd_path}: {result['error']}", file=sys.stderr)
        _user_error(
            "Couldn't check whether this posting is still live. "
            "The job board may be unreachable right now -- try again in a moment."
        )
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _tailor(jd_path: str, jobs_path: str) -> int:
    completed, _failed = orchestrator.run_pipeline(jd_path=jd_path)
    if completed == 0:
        print(f"tailoring failed for {jd_path}", file=sys.stderr)
        _user_error(
            "Couldn't build a tailored resume for this job. "
            "Run `resume doctor` to check your setup, then try again."
        )
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _status(jd_path: str, new_status: str, jobs_path: str) -> int:
    if new_status not in jd_manager.APPLICATION_STATUSES:
        print(
            f"invalid status {new_status!r} -- must be one of {jd_manager.APPLICATION_STATUSES}",
            file=sys.stderr,
        )
        # This one is a programming error on the Go side, not something the
        # user did -- but it still reaches their screen, so it still gets a
        # sentence rather than a schema dump.
        _user_error(f"\"{new_status}\" isn't a status this app recognizes, so nothing was changed.")
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


# What each subcommand was trying to do, phrased as the noun phrase
# describe_error()/friendly_error() expect after "Couldn't finish ...".
_ACTION_CONTEXTS = {
    "liveness": "checking whether this posting is still live",
    "tailor": "building a tailored resume for this job",
    "status": "updating this job's application status",
}


def _run() -> int:
    """main() with a catch-all so an unexpected exception still honors the
    USER_ERROR contract.

    Without this, any bug below this line printed a raw Python traceback,
    and jobs.go -- which forwards this subprocess's stderr verbatim by
    design -- rendered that traceback into the dashboard's error panel.
    A traceback is the single worst thing to show a job seeker, and it was
    the one failure mode the contract couldn't cover from the call sites
    alone, since it happens precisely where no call site is looking.

    The traceback is still written first, so `d for details` keeps the full
    diagnostic; only its position changes, from headline to detail."""
    try:
        return main()
    except SystemExit:
        # argparse's own --help/usage exits. Not a failure, and argparse
        # has already written its message -- appending a USER_ERROR line
        # would corrupt clean --help output.
        raise
    except KeyboardInterrupt:
        _user_error("Cancelled.")
        return 130
    except BaseException as exc:
        traceback.print_exc()
        context = _ACTION_CONTEXTS.get(
            sys.argv[1] if len(sys.argv) > 1 else "", "this action"
        )
        _user_error_from_exception(exc, context)
        return 1


if __name__ == "__main__":
    sys.exit(_run())
