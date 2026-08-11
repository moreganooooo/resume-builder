"""
liveness.py — the `liveness` command: checks every pending JD's source_url
via a Node/Playwright subprocess, moving confirmed-expired postings out of
the active queue into jds/expired/.

No MongoDB, no LLM calls -- pure Playwright + deterministic classification,
ported from career-ops's already-proven liveness-core.mjs/liveness-browser.mjs.
See docs/superpowers/specs/2026-07-05-liveness-checker-design.md.
"""

import datetime
import json
import os
import shutil
import subprocess

import cli_art
import jd_manager
import profile_paths
import theme

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
# Profile-scoped: this used to land at the repo root's output/, outside
# profile_paths.sync_roots(). It's cleaned up in a finally block, so it only
# persisted when the process was killed mid-check -- but a stray temp file
# from one profile sitting in a shared path is still the wrong shape.
LIVENESS_INPUT_PATH = os.path.join(profile_paths.output_dir(), "liveness_input_tmp.json")
# check-liveness.mjs's results JSON goes to a real file, not a pipe --
# see _verify_candidates()'s Popen call for why (B21).
LIVENESS_OUTPUT_PATH = os.path.join(profile_paths.output_dir(), "liveness_output_tmp.json")

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
    return (datetime.datetime.now() - checked_at) < datetime.timedelta(hours=RECENCY_HOURS)


def split_recently_checked(pending_paths: list) -> tuple:
    """Splits pending_paths into (recently_checked, to_check), based on
    whether each JD's persisted _liveness.checked_at is within
    RECENCY_HOURS. Mirrors batch_evaluate.split_evaluated()'s shape so a
    caller can show an accurate confirmation count before proceeding."""
    recently_checked = [p for p in pending_paths if _is_recently_checked(p)]
    to_check = [p for p in pending_paths if not _is_recently_checked(p)]
    return recently_checked, to_check


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
        candidates.append({
            "job_key": jd_manager.compute_job_key(path),
            "source_file": path,
            "url": url,
        })
    return candidates


def _jd_label(source_file: str | None) -> str:
    """Company — Title for a JD's results listing, matching every other
    list view in this app (none of which identify a JD by raw file path).
    Falls back to the filename when metadata can't be read, rather than
    showing nothing."""
    if not source_file:
        return "(unknown)"
    title, company = jd_manager.extract_job_meta(source_file)
    if title or company:
        return f"{company or '?'} — {title or '?'}"
    return os.path.basename(source_file)


def _verify_candidates(candidates: list) -> dict:
    """Given exactly these {job_key, source_file, url} candidates, runs
    check-liveness.mjs, persists each result via jd_manager.save_liveness(),
    moves any 'expired' result's file to jds/expired/, prints the same
    progress/summary check_liveness_check() always has, and returns a
    dict with keys active/likely_active/expired/uncertain/moved/
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
        return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0, "expired_source_paths": []}

    os.makedirs(os.path.dirname(LIVENESS_INPUT_PATH), exist_ok=True)
    with open(LIVENESS_INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f)

    cli_art.console.print(markup=False, soft_wrap=True)
    cli_art.console.rule(f"[bold {theme.BRAND}]Checking {len(candidates)} JD(s) via headless browser[/bold {theme.BRAND}]", style="dim")
    cli_art.console.print(markup=False, soft_wrap=True)

    script = os.path.join(SCRIPT_DIR, "check-liveness.mjs")
    timeout_s = max(NODE_TIMEOUT_FLOOR_S, len(candidates) * NODE_TIMEOUT_PER_CANDIDATE_S)
    try:
        # stdout goes to a real file, not a pipe: Node writes the final
        # JSON blob once, at exit, and it can exceed the OS pipe buffer on
        # a large scan -- piping it while also reading stderr line-by-line
        # below would risk the classic subprocess deadlock (child blocks
        # writing a full stdout pipe, parent blocks reading stderr, or
        # vice versa).
        with open(LIVENESS_OUTPUT_PATH, "w", encoding="utf-8") as stdout_file:
            proc = subprocess.Popen(
                ["node", script, "--json-file", LIVENESS_INPUT_PATH],
                stdout=stdout_file, stderr=subprocess.PIPE, text=True, bufsize=1,
                # RESUME_BUILDER_ICONS: check-liveness.mjs's stderr progress
                # lines are streamed straight to the terminal below (B21),
                # raw icons and all -- there's no shared theming layer
                # across the JS/Python boundary, so without this the child
                # only ever sees an explicit shell-level override, never
                # this process's resolved preference (B45).
                env={**_child_env(), "RESUME_BUILDER_ICONS": theme.icon_set_name()},
            )
            try:
                # Stream progress as the Node child writes it, instead of
                # subprocess.run()'s communicate(), which buffers the
                # entire stream and only hands it back after the process
                # has already exited -- the progress "indicator" was
                # replaying a finished transcript, not showing live
                # progress (B21).
                for line in proc.stderr:
                    cli_art.print_subprocess_output(f"  {line.rstrip()}")
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                cli_art.console.print(f"\n  {theme.colorize_icon('warning')}  Liveness check timed out after {timeout_s}s.", soft_wrap=True)
                return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0, "expired_source_paths": [], "error": True}
            finally:
                # subprocess.run() deliberately does not kill the child on
                # KeyboardInterrupt (bpo-25942), assuming process-group
                # delivery that doesn't happen here -- verified live: Ctrl-C
                # on the Python process left the Node child running,
                # still making outbound requests to employer sites.
                # Explicit kill()+wait() means an interrupted or timed-out
                # run never orphans it (B21).
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

        if proc.returncode != 0:
            cli_art.console.print(f"\n  {theme.colorize_icon('warning')}  Liveness check failed (exit code {proc.returncode}).", soft_wrap=True)
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0, "expired_source_paths": [], "error": True}

        with open(LIVENESS_OUTPUT_PATH, "r", encoding="utf-8") as f:
            stdout_data = f.read()
        try:
            results = json.loads(stdout_data)
        except json.JSONDecodeError:
            cli_art.console.print(f"\n  {theme.colorize_icon('warning')}  Liveness check produced unparseable output:\n{stdout_data[:500]}", soft_wrap=True)
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0, "expired_source_paths": [], "error": True}
    finally:
        for path in (LIVENESS_INPUT_PATH, LIVENESS_OUTPUT_PATH):
            if os.path.exists(path):
                os.remove(path)

    counts = {}
    moved = 0
    os.makedirs(jd_manager.EXPIRED_DIR, exist_ok=True)

    # Group results by outcome for better visual organization
    results_by_status = {"active": [], "likely_active": [], "expired": [], "uncertain": []}
    for r in results:
        outcome = r.get("result", "uncertain")
        counts[outcome] = counts.get(outcome, 0) + 1
        results_by_status.setdefault(outcome, []).append(r)

    cli_art.console.print(markup=False, soft_wrap=True)

    # Process and display by status group
    status_order = ["active", "likely_active", "expired", "uncertain"]
    icon_map = {
        "active": theme.colorize_icon('success'),
        "likely_active": theme.colorize_icon('warning'),
        "expired": theme.colorize_icon('error'),
        "uncertain": theme.colorize_icon('warning'),
    }

    for status in status_order:
        status_results = results_by_status.get(status, [])
        if status_results:
            status_label = status.replace("_", " ").title()
            cli_art.console.print(f"{icon_map.get(status, '?')} {status_label}:", markup=False, soft_wrap=True)
            for r in status_results:
                cli_art.console.print(f"  • {_jd_label(r.get('source_file'))}", markup=False, soft_wrap=True)
                if status not in ("active", "likely_active"):
                    reason = r.get('reason', '')
                    if reason:
                        cli_art.console.print(f"    → {reason}", markup=False, soft_wrap=True)
            cli_art.console.print(markup=False, soft_wrap=True)

    # Save liveness status for all results
    for r in results:
        source_file = r.get("source_file")
        outcome = r.get("result", "uncertain")
        if source_file and os.path.exists(source_file):
            jd_manager.save_liveness(source_file, outcome, r.get("reason", ""))

    # Move expired JDs to expired/ folder
    expired_source_paths = []
    for r in results_by_status.get("expired", []):
        source_file = r.get("source_file")
        if source_file and os.path.exists(source_file):
            dest = os.path.join(jd_manager.EXPIRED_DIR, os.path.basename(source_file))
            shutil.move(source_file, dest)
            moved += 1
            expired_source_paths.append(source_file)

    return {
        "active": counts.get("active", 0),
        "likely_active": counts.get("likely_active", 0),
        "expired": counts.get("expired", 0),
        "uncertain": counts.get("uncertain", 0),
        "moved": moved,
        "expired_source_paths": expired_source_paths,
    }


def verify_jd_paths(paths: list) -> dict:
    """Runs a real Playwright liveness check on exactly `paths` -- no
    recency skip, since these are freshly-written JDs from a scan and
    always worth checking once for real rather than trusting the API/RSS
    feed's optimistic "confirmed to exist by scan" seed (scan.py writes
    that seed at write time; a feed can list a posting that's already
    gone by the time we look, same as the TheMuse 404 seen on a live
    scan run 2026-07-26). Ported from career-ops's default-on
    `scan.mjs --verify` pass, which runs immediately after the API
    scan, before a posting is presented as a hit."""
    return _verify_candidates(_gather_candidates(paths))


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

    if recently_checked:
        cli_art.console.print(f"({len(recently_checked)} JD(s) checked within the last {RECENCY_HOURS}h will be skipped -- use --refresh to re-check everything.)", markup=False, soft_wrap=True)

    if not candidates:
        cli_art.console.print(f"Nothing to check -- {len(to_check)} pending JD(s) (of {len(pending_paths)} total), none with a source_url.", markup=False, soft_wrap=True)
        return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "recently_checked": len(recently_checked), "moved": 0}

    result = _verify_candidates(candidates)
    result["skipped"] = skipped
    result["recently_checked"] = len(recently_checked)

    if not result.get("error"):
        cli_art.console.rule(f"[bold {theme.BRAND}]Liveness Summary[/bold {theme.BRAND}]", style="dim")
        cli_art.console.print(f"  {theme.colorize_icon('success')} Active:                 {result['active']}", soft_wrap=True)
        cli_art.console.print(f"  {theme.colorize_icon('warning')} Likely active:          {result['likely_active']}", soft_wrap=True)
        cli_art.console.print(f"  {theme.colorize_icon('error')} Expired (moved):         {result['expired']}", soft_wrap=True)
        cli_art.console.print(f"  {theme.colorize_icon('warning')} Uncertain (left):       {result['uncertain']}", soft_wrap=True)
        cli_art.console.print(f"  {theme.colorize_icon('skip')} Skipped (no URL):       {skipped}", soft_wrap=True)
        cli_art.console.print(f"  {theme.colorize_icon('skip')} Recently checked:       {len(recently_checked)}", soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)

    return result
