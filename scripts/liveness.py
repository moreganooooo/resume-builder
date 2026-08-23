"""
liveness.py — the `liveness` command: checks every pending JD's source_url
via a Node/Playwright subprocess, moving confirmed-expired postings out of
the active queue into jds/expired/.

No MongoDB, no LLM calls -- pure Playwright + deterministic classification,
ported from career-ops's already-proven liveness-core.mjs/liveness-browser.mjs.
See docs/superpowers/specs/2026-07-05-liveness-checker-design.md.
"""

import contextlib
import datetime
import json
import logging
import os
import shutil
import subprocess
import uuid

import cli_art
import jd_manager
import profile_paths
import theme
from atomic_write import atomic_write

# Vars this repo's own subprocess children (Chromium via check-liveness.mjs
# here, every board/ATS provider via scan_boards.py's own copy of this
# list) have no legitimate need for, so they're stripped rather than
# inherited by default -- neither the liveness check nor any scan provider
# calls Gemini or JobRight, so there's no reason for a Chromium process
# navigating to arbitrary employer sites to be carrying Morgan's API key
# or JobRight session cookie in its environment (B41).
_SUBPROCESS_ENV_STRIP = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "JOBRIGHT_COOKIE_STRING")


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _SUBPROCESS_ENV_STRIP}


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Maps check-liveness.mjs's structured progress-event `result` field to
# this codebase's existing theme.py icon keys (success/warning/error --
# there's no "likely_active"-specific icon, so it shares "warning" with
# "uncertain"). "blocked" takes "skip": an anti-bot interstitial or login
# wall means the page was never shown to us, which is closer to "not
# checked" than to a verdict we reached.
_LIVENESS_ICON_BY_RESULT = {
    "active": "success",
    "likely_active": "warning",
    "expired": "error",
    "blocked": "skip",
    "uncertain": "warning",
}


@contextlib.contextmanager
def _resolve_activity(activity):
    """Reuses a shared activity when the caller (scan.py's run_scan())
    already has one open; otherwise opens a fresh, self-contained one so
    the standalone `resume liveness` entry point (run_liveness_check(),
    with no scan preceding it) also gets the themed step-log rather than
    only benefiting when chained after a scan."""
    if activity is not None:
        yield activity
    else:
        with cli_art.new_scan_activity() as local_activity:
            yield local_activity


# Profile-scoped: these used to land at the repo root's output/, outside
# profile_paths.sync_roots(). A stray temp file from one profile sitting in
# a shared path is the wrong shape even though the finally block removes it
# on every path except an outright kill.
_LIVENESS_TMP_GLOB = "liveness_*_tmp_*.json"


def leftover_temp_files() -> list:
    """Any liveness temp files still on disk for the active profile.

    Every run removes its own pair in a finally block, so a non-empty
    result means some run was killed outright. Exposed so the cleanup
    tests can assert on "no temp residue" without knowing the per-run
    names _run_temp_paths() generates.
    """
    import glob

    return sorted(
        glob.glob(os.path.join(profile_paths.output_dir(), _LIVENESS_TMP_GLOB))
    )


def _run_temp_paths() -> tuple[str, str]:
    """Per-run input/output temp paths for one `check-liveness.mjs` spawn.

    These used to be two fixed module-level constants shared by every
    sweep of a profile. `open(path, "w")` truncates, so any second writer
    destroyed the first one's data:

    * two sweeps of the same profile overlapping, or
    * far more likely, an orphaned Node child from a run that was killed
      mid-check -- see leftover_temp_files() for why those survive --
      still holding the old fd and writing its final blob at
      its own (large) offset into the file a new run had just truncated.

    Demonstrated, not theorised: two runs sharing the path, one destroys
    the other's results while both children exit 0.

    Whether this was the trigger for the unexplained 812-candidate loss on
    2026-08-21 (docs/to_do/HANDOFF-2026-08-21.md -- child exited 0, output
    file unreadable) is NOT proven; that exact ordering was not reproduced.
    It is a mechanism that can produce that signature, and it is a real
    data-loss bug either way. If the symptom recurs after this, the shared
    path was not the cause and the next place to look is the child's
    `finally` in check-liveness.mjs, where the final blob is printed after
    `await browser.close()`.

    A unique suffix per spawn means a stale writer can only ever corrupt
    its own dead run's file.
    """
    unique = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    out_dir = profile_paths.output_dir()
    return (
        os.path.join(out_dir, f"liveness_input_tmp_{unique}.json"),
        os.path.join(out_dir, f"liveness_output_tmp_{unique}.json"),
    )


# How recently a JD needs to have been checked (or scanned -- see
# scan.py's seeding of _liveness at write time) to skip re-checking it by
# default. Unlike evaluate's skip (permanent -- a JD either has been
# evaluated or hasn't), this is time-windowed since a posting can genuinely
# go stale between runs.
RECENCY_HOURS = 24

# Sizes subprocess.run's timeout= from the candidate count instead of
# waiting unbounded -- each candidate is one real Chromium navigation
# (liveness-browser.mjs's NAV_TIMEOUT_MS=15s + RENDER_WAIT_MS=1.2s +
# evaluate() overhead), plus a floor covering Node/Chromium startup for
# even a single candidate (B21).
NODE_TIMEOUT_PER_CANDIDATE_S = 20
NODE_TIMEOUT_FLOOR_S = 60


def _is_recently_checked(jd_path: str) -> bool:
    liveness = jd_manager.read_liveness(jd_path)
    if not liveness or not liveness.get("checked_at"):
        return False
    try:
        checked_at = datetime.datetime.fromisoformat(liveness["checked_at"])
    except ValueError:
        return False
    return (datetime.datetime.now() - checked_at) < datetime.timedelta(
        hours=RECENCY_HOURS
    )


def split_recently_checked(pending_paths: list) -> tuple:
    """Splits pending_paths into (recently_checked, to_check), based on
    whether each JD's persisted _liveness.checked_at is within
    RECENCY_HOURS. Mirrors batch_evaluate.split_evaluated()'s shape so a
    caller can show an accurate confirmation count before proceeding."""
    recently_checked = [p for p in pending_paths if _is_recently_checked(p)]
    to_check = [p for p in pending_paths if not _is_recently_checked(p)]
    return recently_checked, to_check


def _liveness_is_recent(liveness: dict | None) -> bool:
    """_is_recently_checked() for an in-memory _liveness block, so a
    database row can be skipped without materializing a file for it."""
    if not liveness or not liveness.get("checked_at"):
        return False
    try:
        checked_at = datetime.datetime.fromisoformat(liveness["checked_at"])
    except (ValueError, TypeError):
        return False
    return (datetime.datetime.now() - checked_at) < datetime.timedelta(
        hours=RECENCY_HOURS
    )


def _save_liveness_to_db(job_id: str, outcome: str, reason: str) -> None:
    """Persists a liveness result onto a job row that has no JD file."""
    import jd_source

    try:
        with jd_source.resolved_jd(job_id) as (path, _is_db):
            jd_manager.save_liveness(path, outcome, reason)
    except (LookupError, OSError):
        return


def _gather_db_candidates() -> list:
    """Liveness candidates for evaluated roles that exist only in data.db.

    Most pending roles have no JD file, so a file-only sweep checked 157
    of 812 and reported that as the total -- which read as the app
    disagreeing with itself. Returns the same {job_key, source_file, url}
    shape, with source_file carrying the job id; the write-back paths
    branch on whether it names a real file.
    """
    import db

    # Hard stop under tests pointed at the real profile. A liveness sweep
    # is real network I/O through Playwright: when this first shipped, the
    # existing liveness tests mocked the filesystem JD list but knew
    # nothing about a database source, so the suite quietly launched
    # Chromium and began checking 643 live URLs. Failing closed here is
    # the only place that can catch it for every current and future test.
    if db._is_unisolated_test_write():
        return []

    try:
        conn = db.get_db()
    except Exception:
        return []

    try:
        rows = conn.execute(
            "SELECT id, metadata_json FROM jobs WHERE status = 'pending'"
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    # A row keyed by content hash may still have a JD file (see
    # jobs.id's two shapes), and os.path.exists() cannot see that.
    # Without hashing the pending files the sweep double-counted ~126
    # roles it had already gathered from disk.
    file_keys = set()
    for path in jd_manager.get_pending_jds():
        file_keys.add(os.path.basename(path))
        try:
            file_keys.add(jd_manager.compute_job_key(path))
        except (OSError, ValueError):
            continue

    candidates = []
    for row in rows:
        job_id = str(row["id"])
        if os.path.exists(job_id) or job_id in file_keys:
            continue  # file-backed; the filesystem sweep already has it
        if os.path.basename(job_id) in file_keys:
            continue
        try:
            data = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue

        # Only evaluated roles, matching picker.list_all_evaluated_jds().
        # Sweeping every pending row instead would check 1,411 postings
        # and report that figure, which is a third number for the user to
        # reconcile against the 812 every screen shows.
        if not data.get("_evaluation"):
            continue

        url = data.get("source_url")
        if not url:
            continue

        # Same 24-hour skip the filesystem path gets. Without it every run
        # would re-check hundreds of URLs through Playwright.
        if _liveness_is_recent(data.get("_liveness")):
            continue

        # Title and company ride along because there is no file to read
        # them back from later. Without them _styled_jd_label() falls
        # through to os.path.basename(job_id) and the sweep prints a raw
        # 64-character content hash as the row -- which is what most of
        # the list looked like, since the majority of pending roles are
        # database-only.
        candidates.append(
            {
                "job_key": job_id,
                "source_file": job_id,
                "url": url,
                "title": data.get("job_title") or data.get("title") or "",
                "company": data.get("company_name") or data.get("company") or "",
            }
        )
    return candidates


def _gather_candidates(pending_paths: list) -> list:
    """Returns [{"job_key": ..., "source_file": ..., "url": ...}, ...] for
    every path in pending_paths whose JD data has a real source_url; the
    rest are silently excluded (not flagged as anything)."""
    candidates = []
    for path in pending_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        url = data.get("source_url") if isinstance(data, dict) else None
        if not url:
            continue
        candidates.append(
            {
                "job_key": jd_manager.compute_job_key(path),
                "source_file": path,
                "url": url,
            }
        )
    return candidates


def _checkpoint_path() -> str:
    """Where an in-flight sweep records what it has already verified."""
    return os.path.join(profile_paths.checkpoints_dir(), "liveness_sweep.json")


def _load_checkpoint() -> dict:
    """Verdicts from an interrupted sweep, keyed by job_key.

    A full sweep is 30-50 minutes of Playwright. Losing it to a Ctrl-C,
    a closed laptop, or a crash means paying that again for work already
    done, so each verdict is persisted as it arrives and replayed on the
    next run.
    """
    try:
        with open(_checkpoint_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    results = data.get("results")
    return results if isinstance(results, dict) else {}


def _save_checkpoint(results_by_key: dict) -> None:
    """Best-effort. A checkpoint that cannot be written must never take
    the sweep down with it -- the sweep's own work is the valuable part."""
    try:
        os.makedirs(profile_paths.checkpoints_dir(), exist_ok=True)
        with atomic_write(_checkpoint_path(), "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "saved_at": datetime.datetime.now().isoformat(),
                    "results": results_by_key,
                },
                handle,
            )
    except (OSError, ValueError, TypeError) as e:
        logging.debug(f"liveness: could not write checkpoint -- {e}")


def _clear_checkpoint() -> None:
    """Removes the checkpoint once a sweep has finished and persisted."""
    try:
        os.remove(_checkpoint_path())
    except OSError:
        pass


def _results_from_progress(events: list, candidates: list) -> list:
    """Rebuilds the result rows from streamed progress events.

    A progress event carries the verdict (result/code/reason) and the
    source_file it belongs to, but not job_key or url -- those come from
    the candidate the caller already has in hand.
    """
    by_source = {
        c.get("source_file"): c for c in (candidates or []) if c.get("source_file")
    }
    rebuilt = []
    for event in events or []:
        candidate = by_source.get(event.get("source_file"))
        if not candidate or not event.get("result"):
            continue
        rebuilt.append(
            {
                **candidate,
                "result": event.get("result"),
                "code": event.get("code"),
                "reason": event.get("reason"),
            }
        )
    return rebuilt


def _styled_jd_label(source_file: str | None, meta: dict | None = None) -> str:
    """Styled version of _jd_label with Rich markup for terminal display.

    `meta` maps source_file -> {"title", "company"} for candidates whose
    metadata cannot be read back off disk. Database-only roles are keyed
    by a content hash rather than a path, so extract_job_meta() has
    nothing to open and the label degraded to the bare hash.
    """
    if not source_file:
        return "(unknown)"

    entry = (meta or {}).get(source_file) or {}
    title = entry.get("title") or ""
    company = entry.get("company") or ""
    if not (title or company):
        title, company = jd_manager.extract_job_meta(source_file)

    if title or company:
        company_str = company or "?"
        title_str = title or "?"
        return cli_art.format_jd_label(company_str, title_str)
    return os.path.basename(source_file)


def _verify_candidates(candidates: list, activity=None) -> dict:
    """Given exactly these {job_key, source_file, url} candidates, runs
    check-liveness.mjs, persists each result via jd_manager.save_liveness(),
    moves any 'expired' result's file to jds/expired/, prints the same
    progress/summary check_liveness_check() always has, and returns a
    dict with keys active/likely_active/expired/blocked/uncertain/moved/
    expired_source_paths (plus error=True on a failure path).
    expired_source_paths deliberately holds each moved file's pre-move
    path, not where it now lives in jds/expired/ -- that's the identity
    scan.py's run_scan() already has cached in its own written_paths dict
    (keyed the same way) and needs to look an entry back up by, not a
    location to open (B42). Candidate-gathering and recency-skip
    stay the caller's concern -- run_liveness_check() derives candidates
    from get_pending_jds() + a recency split; verify_jd_paths() (used by
    scan.py to verify freshly-scanned postings before presenting them as
    a hit, career-ops's scan.mjs --verify ported) skips recency
    entirely since these are brand new. Silently returns all-zero on an
    empty candidate list -- callers embedding this in a larger flow
    (scan.py) shouldn't get a standalone "nothing to check" message."""
    if not candidates:
        return {
            "active": 0,
            "likely_active": 0,
            "expired": 0,
            "blocked": 0,
            "uncertain": 0,
            "moved": 0,
            "expired_source_paths": [],
        }

    # Resume an interrupted sweep. A full run is 30-50 minutes of real
    # browser work, which is long enough that a Ctrl-C, a closed lid, or
    # a crash is likely -- and previously cost the entire run.
    original_candidates = list(candidates)
    resumed_results = {
        key: value
        for key, value in _load_checkpoint().items()
        if any(c.get("job_key") == key for c in candidates)
    }
    if resumed_results:
        candidates = [c for c in candidates if c.get("job_key") not in resumed_results]
        cli_art.console.print(
            f"\n  {theme.colorize_icon('success')}  Resuming: "
            f"{len(resumed_results)} JD(s) already verified in an earlier run, "
            f"{len(candidates)} left to check.",
            soft_wrap=True,
        )
    candidate_by_source = {
        c["source_file"]: c for c in candidates if c.get("source_file")
    }

    input_path, output_path = _run_temp_paths()
    os.makedirs(os.path.dirname(input_path), exist_ok=True)
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f)

    cli_art.print_literal()
    cli_art.console.rule(
        f"[bold {theme.BRAND}]Checking {len(candidates)} JD(s) via headless browser[/bold {theme.BRAND}]",
        style="dim",
    )
    cli_art.print_literal()

    script = os.path.join(SCRIPT_DIR, "check-liveness.mjs")
    timeout_s = max(
        NODE_TIMEOUT_FLOOR_S, len(candidates) * NODE_TIMEOUT_PER_CANDIDATE_S
    )
    try:
        # stdout goes to a real file, not a pipe: Node writes the final
        # JSON blob once, at exit, and it can exceed the OS pipe buffer on
        # a large scan -- piping it while also reading stderr line-by-line
        # below would risk the classic subprocess deadlock (child blocks
        # writing a full stdout pipe, parent blocks reading stderr, or
        # vice versa).
        with open(output_path, "w", encoding="utf-8") as stdout_file:
            proc = subprocess.Popen(
                ["node", script, "--json-file", input_path],
                stdout=stdout_file,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                env={**_child_env(), "RESUME_BUILDER_ICONS": theme.icon_set_name()},
            )
            try:
                # Stream progress as the Node child writes it, instead of
                # subprocess.run()'s communicate(), which buffers the
                # entire stream and only hands it back after the process
                # has already exited -- the progress "indicator" was
                # replaying a finished transcript, not showing live
                # progress (B21).
                # Every progress event carries this candidate's verdict,
                # so the run's work is already in hand by the time the
                # final blob is read. Kept so an unparseable blob costs
                # the formatting, not the results -- see the fallback
                # below.
                streamed_results = []
                # Persisted as they arrive so an interrupted sweep can
                # resume instead of re-checking work already done.
                checkpoint = dict(resumed_results)
                candidate_meta = {
                    c["source_file"]: {
                        "title": c.get("title") or "",
                        "company": c.get("company") or "",
                    }
                    for c in candidates
                    if c.get("source_file")
                }
                with _resolve_activity(activity) as resolved_activity:
                    resolved_activity.start_source(len(candidates), label="Checking")
                    for line in proc.stderr:
                        stripped = line.rstrip()
                        event = None
                        try:
                            event = json.loads(stripped)
                        except json.JSONDecodeError:
                            pass
                        if isinstance(event, dict) and event.get("type") == "progress":
                            streamed_results.append(event)
                            source = event.get("source_file")
                            if source and source in candidate_by_source:
                                checkpoint[candidate_by_source[source]["job_key"]] = {
                                    "result": event.get("result"),
                                    "code": event.get("code"),
                                    "reason": event.get("reason"),
                                    "source_file": source,
                                }
                                # Batched: a sweep is hundreds of events
                                # and the file is rewritten whole each
                                # time. Every 10 bounds a crash to at
                                # most 10 re-checks.
                                if len(checkpoint) % 10 == 0:
                                    _save_checkpoint(checkpoint)
                            icon_name = _LIVENESS_ICON_BY_RESULT.get(
                                event.get("result"), "warning"
                            )
                            message = _styled_jd_label(
                                event.get("source_file"), candidate_meta
                            )
                            resolved_activity.step(
                                icon_name, "Verify", message, preserve_markup=True
                            )
                        else:
                            cli_art.print_subprocess_output(f"  {stripped}")
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                cli_art.console.print(
                    f"\n  {theme.colorize_icon('warning')}  Liveness check timed out after {timeout_s}s.",
                    soft_wrap=True,
                )
                return {
                    "active": 0,
                    "likely_active": 0,
                    "expired": 0,
                    "blocked": 0,
                    "uncertain": 0,
                    "moved": 0,
                    "expired_source_paths": [],
                    "error": True,
                }
            finally:
                if proc.poll() is None:
                    try:
                        import signal

                        if isinstance(proc.pid, int) and proc.pid > 1:
                            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        pass
                    try:
                        proc.kill()
                    except Exception:
                        pass
                proc.wait()

        if proc.returncode != 0:
            cli_art.console.print(
                f"\n  {theme.colorize_icon('warning')}  Liveness check failed (exit code {proc.returncode}).",
                soft_wrap=True,
            )
            return {
                "active": 0,
                "likely_active": 0,
                "expired": 0,
                "blocked": 0,
                "uncertain": 0,
                "moved": 0,
                "expired_source_paths": [],
                "error": True,
            }

        with open(output_path, "r", encoding="utf-8") as f:
            stdout_data = f.read()
        try:
            results = json.loads(stdout_data)
        except json.JSONDecodeError:
            # The child prints one final JSON blob after the browser
            # closes. When that blob is missing or truncated, every
            # verdict is STILL known -- each was streamed as a progress
            # event while the sweep ran. Rebuilding from those turns a
            # total loss into a complete result set.
            #
            # This is not hypothetical: an 812-candidate sweep on
            # 2026-08-21 ran for ~50 minutes, checked every URL, and then
            # discarded all of it because stdout came back empty while
            # the child still exited 0.
            results = _results_from_progress(streamed_results, candidates)
            if results:
                cli_art.console.print(
                    f"\n  {theme.colorize_icon('warning')}  Liveness output was "
                    f"unreadable; recovered {len(results)} result(s) from the "
                    "progress stream.",
                    soft_wrap=True,
                )
            else:
                cli_art.console.print(
                    f"\n  {theme.colorize_icon('warning')}  Liveness check produced unparseable output:\n{stdout_data[:500]}",
                    soft_wrap=True,
                )
                return {
                    "active": 0,
                    "likely_active": 0,
                    "expired": 0,
                    "blocked": 0,
                    "uncertain": 0,
                    "moved": 0,
                    "expired_source_paths": [],
                    "error": True,
                }
    finally:
        for path in (input_path, output_path):
            if os.path.exists(path):
                os.remove(path)

    # Fold in anything an earlier, interrupted run already verified.
    # Those candidates were filtered out above, so the child never saw
    # them and they are absent from `results` -- without this they would
    # be silently dropped from the summary and never persisted.
    if resumed_results:
        by_key = {c.get("job_key"): c for c in original_candidates}
        for key, saved in resumed_results.items():
            candidate = by_key.get(key)
            if not candidate:
                continue
            results.append(
                {
                    **candidate,
                    "result": saved.get("result"),
                    "code": saved.get("code"),
                    "reason": saved.get("reason"),
                }
            )

    counts = {}
    moved = 0
    os.makedirs(jd_manager.EXPIRED_DIR, exist_ok=True)

    # Group results by outcome for better visual organization
    results_by_status = {
        "active": [],
        "likely_active": [],
        "expired": [],
        "blocked": [],
        "uncertain": [],
    }
    for r in results:
        outcome = r.get("result", "uncertain")
        counts[outcome] = counts.get(outcome, 0) + 1
        results_by_status.setdefault(outcome, []).append(r)

    # Save liveness status for all results
    for r in results:
        source_file = r.get("source_file")
        outcome = r.get("result", "uncertain")
        if source_file and os.path.exists(source_file):
            jd_manager.save_liveness(source_file, outcome, r.get("reason", ""))
        elif source_file:
            # A database-only role: source_file is its job id, not a path.
            # Round-trip through jd_source so the same save_liveness() call
            # applies, then the result is synced back into the row.
            _save_liveness_to_db(source_file, outcome, r.get("reason", ""))

    # Move expired JDs to expired/ folder
    expired_source_paths = []
    for r in results_by_status.get("expired", []):
        source_file = r.get("source_file")
        if source_file and os.path.exists(source_file):
            # Was a bare shutil.move to a fixed destination path, which
            # silently overwrote any JD already in expired/ under the same
            # basename -- two postings sharing a company+title (ordinary
            # when the same role is found via two sources) destroyed one of
            # them, along with its evaluation and application history, with
            # no error. move_jd_to() suffixes on collision instead.
            jd_manager.move_jd_to(source_file, jd_manager.EXPIRED_DIR)
            moved += 1
            expired_source_paths.append(source_file)
        elif source_file:
            # Nothing to move -- expiring a database-only role is a status
            # change, not a file operation.
            import jd_source

            jd_source.set_status(source_file, "expired")
            moved += 1

    # Every verdict is now persisted via save_liveness(), so the
    # checkpoint has done its job. Cleared only on this path -- an early
    # return above means the sweep did NOT finish, and that is exactly
    # when the next run needs it.
    _clear_checkpoint()

    return {
        "active": counts.get("active", 0),
        "likely_active": counts.get("likely_active", 0),
        "expired": counts.get("expired", 0),
        "blocked": counts.get("blocked", 0),
        "uncertain": counts.get("uncertain", 0),
        "moved": moved,
        "expired_source_paths": expired_source_paths,
    }


def verify_jd_paths(paths: list, activity=None) -> dict:
    """Runs a real Playwright liveness check on exactly `paths` -- no
    recency skip, since these are freshly-written JDs from a scan and
    always worth checking once for real rather than trusting the API/RSS
    feed's optimistic "confirmed to exist by scan" seed (scan.py writes
    that seed at write time; a feed can list a posting that's already
    gone by the time we look, same as the TheMuse 404 seen on a live
    scan run 2026-07-26). Ported from career-ops's default-on
    `scan.mjs --verify` pass, which runs immediately after the API
    scan, before a posting is presented as a hit. `activity` (a
    cli_art.ScanActivity) is optional -- when given (scan.py's run_scan()
    passes its own), reuses it instead of opening a second one."""
    return _verify_candidates(_gather_candidates(paths), activity=activity)


def run_liveness_check(refresh: bool = False) -> dict:
    """
    Checks every pending JD's source_url, moves confirmed-expired ones to
    jds/expired/. Skips any JD checked (or scanned -- see scan.py) within
    RECENCY_HOURS unless refresh=True. Returns a summary dict with keys:
    active, likely_active, expired, uncertain, skipped, recently_checked,
    moved (plus error=True on a failure path).
    """
    pending_paths = jd_manager.get_pending_jds()

    if refresh:
        recently_checked, to_check = [], pending_paths
    else:
        recently_checked, to_check = split_recently_checked(pending_paths)

    candidates = _gather_candidates(to_check)
    skipped = len(to_check) - len(candidates)

    # Include roles that live only in the database. Without these the
    # sweep covered 157 of 812 pending roles while every other screen
    # counted all 812.
    candidates.extend(_gather_db_candidates())

    if recently_checked:
        cli_art.print_literal(
            f"({len(recently_checked)} JD(s) checked within the last {RECENCY_HOURS}h will be skipped -- use --refresh to re-check everything.)"
        )

    if not candidates:
        cli_art.print_literal(
            f"Nothing to check -- {len(to_check)} pending JD(s) (of {len(pending_paths)} total), none with a source_url."
        )
        return {
            "active": 0,
            "likely_active": 0,
            "expired": 0,
            "blocked": 0,
            "uncertain": 0,
            "skipped": skipped,
            "recently_checked": len(recently_checked),
            "moved": 0,
        }

    result = _verify_candidates(candidates)
    result["skipped"] = skipped
    result["recently_checked"] = len(recently_checked)

    if not result.get("error"):
        cli_art.console.rule(
            f"[bold {theme.BRAND}]Liveness Summary[/bold {theme.BRAND}]", style="dim"
        )
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Active:                 {result['active']}",
            soft_wrap=True,
        )
        cli_art.console.print(
            f"  {theme.colorize_icon('warning')} Likely active:          {result['likely_active']}",
            soft_wrap=True,
        )
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} Expired (moved):         {result['expired']}",
            soft_wrap=True,
        )
        cli_art.console.print(
            f"  {theme.colorize_icon('warning')} Uncertain (left):       {result['uncertain']}",
            soft_wrap=True,
        )
        # Reported separately from Uncertain on purpose: a blocked page is
        # one we were never shown (bot wall, login wall), not one we read
        # and could not judge. Folding the two together made the checker
        # look 23% indecisive when much of it was simply denied access.
        cli_art.console.print(
            f"  {theme.colorize_icon('skip')} Blocked (bot/login wall): {result.get('blocked', 0)}",
            soft_wrap=True,
        )
        cli_art.console.print(
            f"  {theme.colorize_icon('skip')} Skipped (no URL):       {skipped}",
            soft_wrap=True,
        )
        cli_art.console.print(
            f"  {theme.colorize_icon('skip')} Recently checked:       {len(recently_checked)}",
            soft_wrap=True,
        )
        cli_art.print_literal()

    return result
