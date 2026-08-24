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
import os
import sys
import traceback

import cli_art
import jd_manager
import jd_source
import liveness
import orchestrator

import dashboard


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
    with jd_source.resolved_jd(jd_path) as (path, _is_db):
        return _liveness_at(path, jd_path, jobs_path)


def _liveness_at(path: str, jd_path: str, jobs_path: str) -> int:
    result = liveness.verify_jd_paths([path])
    if result.get("error"):
        # Raw detail first, plain sentence last -- see the contract above.
        print(
            f"liveness check failed for {jd_path}: {result['error']}", file=sys.stderr
        )
        _user_error(
            "Couldn't check whether this posting is still live. "
            "The job board may be unreachable right now -- try again in a moment."
        )
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _tailor(jd_path: str, jobs_path: str) -> int:
    # Tailoring is the one action that materializes a real file. The
    # pipeline moves the JD into completed/ on success, which a temp file
    # cannot support -- and a job being tailored is one actually being
    # pursued, so it has earned the disk.
    if not os.path.exists(jd_path):
        try:
            jd_path = jd_source.materialize_permanently(jd_path)
        except LookupError as exc:
            print(f"tailor failed: {exc}", file=sys.stderr)
            _user_error("Couldn't find this job's details, so no resume was built.")
            return 1

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
        _user_error(
            f'"{new_status}" isn\'t a status this app recognizes, so nothing was changed.'
        )
        return 1
    with jd_source.resolved_jd(jd_path) as (path, _is_db):
        jd_manager.save_application_status(path, new_status)
    dashboard._export_jobs_to(jobs_path)
    return 0


def _archive(jd_path: str, jobs_path: str) -> int:
    try:
        if not os.path.exists(jd_path):
            # Database-only job: flip the status rather than moving a file.
            # Routing this through archive_jd would deposit a stray JD in
            # jds/archived/ -- the on-disk clutter jd_source exists to avoid.
            jd_source.set_status(jd_path, "archived")
            print(f"Archived job {jd_path} (database-only, no file moved)")
            dashboard._export_jobs_to(jobs_path)
            return 0

        archived_path = jd_manager.archive_jd(jd_path)
        print(f"Archived to: {archived_path}")
    except Exception as exc:
        print(f"archive failed for {jd_path}: {exc}", file=sys.stderr)
        _user_error(
            "Couldn't archive this job posting. "
            "Check that the file still exists and try again."
        )
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _export(jobs_path: str) -> int:
    """Writes the JD evaluation export to jobs_path. Delegates to
    dashboard._export_jobs_to so there is exactly one implementation of
    "what the export contains" -- the Python menu's launch path and the
    dashboard's own startup fallback must not drift apart."""
    import dashboard

    dashboard._export_jobs_to(jobs_path)
    return 0


def _scan(jobs_path: str) -> int:
    try:
        import scan

        scan.run_scan()
        dashboard._export_jobs_to(jobs_path)
        return 0
    except Exception as exc:
        print(f"scan failed: {exc}", file=sys.stderr)
        _user_error_from_exception(exc, "scanning job postings")
        return 1


def _batch_evaluate(jobs_path: str) -> int:
    try:
        import batch_evaluate

        batch_evaluate.evaluate_all_pending()
        dashboard._export_jobs_to(jobs_path)
        return 0
    except Exception as exc:
        print(f"batch evaluate failed: {exc}", file=sys.stderr)
        _user_error_from_exception(exc, "batch evaluating job postings")
        return 1


def _sweep_stale(jobs_path: str) -> int:
    try:
        import liveness

        liveness.run_liveness_check()
        dashboard._export_jobs_to(jobs_path)
        return 0
    except Exception as exc:
        print(f"liveness sweep failed: {exc}", file=sys.stderr)
        _user_error_from_exception(exc, "sweeping stale postings")
        return 1


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

    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("jd_path")
    archive_parser.add_argument("--jobs-path", required=True)

    matrix_parser = subparsers.add_parser("matrix")
    matrix_parser.add_argument("jd_path")
    matrix_parser.add_argument("--jobs-path", required=True)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--jobs-path", required=True)

    batch_eval_parser = subparsers.add_parser("batch_evaluate")
    batch_eval_parser.add_argument("--jobs-path", required=True)

    sweep_parser = subparsers.add_parser("sweep_stale")
    sweep_parser.add_argument("--jobs-path", required=True)

    # Unlike the actions above, "export" takes no jd_path: it writes the
    # whole evaluation export. The Go dashboard calls this at startup when
    # it was launched without -jobs-path (a bare `dashboard -profile X`
    # rather than via the Python menu), which used to leave Browse & Manage
    # Jobs silently empty -- LoadJobs was simply never called.
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--jobs-path", required=True)

    args = parser.parse_args()

    if args.command == "liveness":
        return _liveness(args.jd_path, args.jobs_path)
    if args.command == "tailor":
        return _tailor(args.jd_path, args.jobs_path)
    if args.command == "status":
        return _status(args.jd_path, args.new_status, args.jobs_path)
    if args.command == "archive":
        return _archive(args.jd_path, args.jobs_path)
    if args.command == "matrix":
        return _matrix(args.jd_path, args.jobs_path)
    if args.command == "scan":
        return _scan(args.jobs_path)
    if args.command == "batch_evaluate":
        return _batch_evaluate(args.jobs_path)
    if args.command == "sweep_stale":
        return _sweep_stale(args.jobs_path)
    if args.command == "export":
        return _export(args.jobs_path)
    return 1


# What each subcommand was trying to do, phrased as the noun phrase
# describe_error()/friendly_error() expect after "Couldn't finish ...".
_ACTION_CONTEXTS = {
    "liveness": "checking whether this posting is still live",
    "tailor": "building a tailored resume for this job",
    "status": "updating this job's application status",
    "archive": "archiving this job posting",
    "matrix": "computing the skills gap matrix",
    "scan": "scanning job postings",
    "batch_evaluate": "batch evaluating job postings",
    "sweep_stale": "sweeping stale postings",
    "export": "loading your evaluated jobs",
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


def _matrix(jd_path: str, jobs_path: str) -> int:
    import json
    import os

    import jd_manager
    import jd_source
    import numpy as np
    import profile_paths
    from embed_bullet_bank import BATCH_SIZE, embed_batch
    from vector_store import cosine_similarity_matrix

    try:
        try:
            resolved_ctx = jd_source.resolved_jd(jd_path)
        except LookupError as exc:
            print(f"matrix lookup failed for {jd_path}: {exc}", file=sys.stderr)
            _user_error(
                "Couldn't find this job's details to compute the skills gap matrix."
            )
            return 1

        with resolved_ctx as (path, _is_db):
            evaluation = jd_manager.read_evaluation(path)
            if not evaluation:
                _user_error("JD must be evaluated first.")
                return 1

            with open(path, "r", encoding="utf-8") as f:
                jd_data = json.load(f)

            skills = jd_data.get("skills") or []
            if not skills:
                _user_error("No skills found for this JD.")
                return 1

            kb_dir = profile_paths.kb_dir()
            emb_npy = os.path.join(kb_dir, "bullet_vectors_ge2_d768.npy")
            if not os.path.exists(emb_npy):
                _user_error(
                    "Missing bullet bank embeddings. Run `resume doctor` to check your setup."
                )
                return 1

            embs = np.load(emb_npy)
            skill_names = [s.get("skill", "") for s in skills if s.get("skill")]
            if not skill_names:
                _user_error("No named skills extracted for this JD.")
                return 1

            skill_vecs = []
            for i in range(0, len(skill_names), BATCH_SIZE):
                batch = skill_names[i : i + BATCH_SIZE]
                try:
                    vecs = embed_batch(batch)
                    skill_vecs.extend(vecs)
                except Exception as e:
                    _user_error_from_exception(e, "embedding JD skills via Gemini API")
                    return 1

            reference = _coverage_reference(embs)

            skill_matrix = []
            for name, vec in zip(skill_names, skill_vecs):
                if vec:
                    scores = cosine_similarity_matrix(
                        np.array(vec, dtype=np.float32), embs
                    )
                    max_score = float(np.max(scores)) if len(scores) > 0 else 0.0
                    coverage_pct = _coverage_percentile(max_score, reference)
                    skill_matrix.append(
                        {
                            "skill": name,
                            "coverage": coverage_pct,
                        }
                    )

            skill_matrix.sort(key=lambda x: x["coverage"])
            evaluation["skill_matrix"] = skill_matrix
            jd_manager.save_evaluation(path, evaluation)
    except Exception as e:
        _user_error_from_exception(e, "computing the skills gap matrix")
        return 1

    return _export(jobs_path)


# Coverage is a RANK, not a raw cosine, and that is deliberate.
#
# Gemini text embeddings occupy a narrow cone: measured over this profile's
# own 844-bullet corpus on 2026-08-24, the similarity between two RANDOMLY
# CHOSEN bullets had a median of 0.727, and 5% of unrelated pairs already
# exceeded 0.85. Because the matrix scores a skill by its MAX similarity
# over the whole bank, an affine rescale of raw cosine is degenerate: the
# earlier (x - 0.50) / 0.35 mapping pinned 95% of queries at 100% and never
# returned less than 63.9%, so the bar could not express a gap -- the one
# thing a "Skills Gap Matrix" exists to show.
#
# Ranking against the corpus's own best-match distribution sidesteps the
# problem: it needs no hand-tuned constants, and it re-calibrates itself as
# the bullet bank grows or the embedding model changes.
def _coverage_reference(embs):
    """Distribution of best-match similarity within the bullet bank itself.

    Each bullet's similarity to its nearest OTHER bullet -- i.e. what a
    strong match looks like in this corpus. A skill is then scored by where
    its own best match falls in that distribution.
    """
    import numpy as np

    sims = embs @ embs.T
    np.fill_diagonal(sims, -1.0)
    return np.sort(sims.max(axis=1))


def _coverage_percentile(max_score: float, reference) -> float:
    """Percent of the reference distribution that max_score meets or beats."""
    import numpy as np

    if reference is None or len(reference) == 0:
        return 0.0
    rank = int(np.searchsorted(reference, max_score, side="right"))
    return round(100.0 * rank / len(reference), 1)


if __name__ == "__main__":
    sys.exit(_run())
