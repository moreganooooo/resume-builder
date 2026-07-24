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

import jd_manager
import theme

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIVENESS_INPUT_PATH = os.path.join(jd_manager.PROJECT_ROOT, "output", "liveness_input_tmp.json")

# How recently a JD needs to have been checked (or scanned -- see
# scan.py's seeding of _liveness at write time) to skip re-checking it by
# default. Unlike evaluate's skip (permanent -- a JD either has been
# evaluated or hasn't), this is time-windowed since a posting can genuinely
# go stale between runs.
RECENCY_HOURS = 24


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
        print(f"({len(recently_checked)} JD(s) checked within the last {RECENCY_HOURS}h will be skipped -- use --refresh to re-check everything.)")

    if not candidates:
        print(f"Nothing to check -- {len(to_check)} pending JD(s) (of {len(pending_paths)} total), none with a source_url.")
        return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "recently_checked": len(recently_checked), "moved": 0}

    os.makedirs(os.path.dirname(LIVENESS_INPUT_PATH), exist_ok=True)
    with open(LIVENESS_INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f)

    print(f"\n{'─'*60}")
    print(f"Checking {len(candidates)} JD(s) via headless browser...")
    print(f"{'─'*60}")
    print()

    try:
        script = os.path.join(SCRIPT_DIR, "check-liveness.mjs")
        proc = subprocess.run(
            ["node", script, "--json-file", LIVENESS_INPUT_PATH],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if proc.returncode != 0:
            print(f"\n  ⚠️  Liveness check failed:\n{proc.stderr}")
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "recently_checked": len(recently_checked), "moved": 0, "error": True}

        # Print incremental progress from stderr as it arrives
        if proc.stderr.strip():
            for line in proc.stderr.strip().split('\n'):
                print(f"  {line}")

        try:
            results = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"\n  ⚠️  Liveness check produced unparseable output:\n{proc.stdout[:500]}")
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "recently_checked": len(recently_checked), "moved": 0, "error": True}
    finally:
        if os.path.exists(LIVENESS_INPUT_PATH):
            os.remove(LIVENESS_INPUT_PATH)

    counts = {}
    moved = 0
    os.makedirs(jd_manager.EXPIRED_DIR, exist_ok=True)

    # Group results by outcome for better visual organization
    results_by_status = {"active": [], "likely_active": [], "expired": [], "uncertain": []}
    for r in results:
        outcome = r.get("result", "uncertain")
        counts[outcome] = counts.get(outcome, 0) + 1
        results_by_status.setdefault(outcome, []).append(r)

    print()

    # Process and display by status group
    status_order = ["active", "likely_active", "expired", "uncertain"]
    icon_map = {
        "active": theme.colorize_icon_ansi('success'),
        "likely_active": theme.colorize_icon_ansi('warning'),
        "expired": theme.colorize_icon_ansi('error'),
        "uncertain": theme.colorize_icon_ansi('warning'),
    }

    for status in status_order:
        status_results = results_by_status.get(status, [])
        if status_results:
            status_label = status.replace("_", " ").title()
            print(f"{icon_map.get(status, '?')} {status_label}:")
            for r in status_results:
                print(f"  • {r.get('source_file')}")
                if status not in ("active", "likely_active"):
                    reason = r.get('reason', '')
                    if reason:
                        print(f"    → {reason}")
            print()

    # Save liveness status for all results
    for r in results:
        source_file = r.get("source_file")
        outcome = r.get("result", "uncertain")
        if source_file and os.path.exists(source_file):
            jd_manager.save_liveness(source_file, outcome, r.get("reason", ""))

    # Move expired JDs to expired/ folder
    for r in results_by_status.get("expired", []):
        source_file = r.get("source_file")
        if source_file and os.path.exists(source_file):
            dest = os.path.join(jd_manager.EXPIRED_DIR, os.path.basename(source_file))
            shutil.move(source_file, dest)
            moved += 1

    print(f"{'─'*60}")
    print("Liveness Summary:")
    print(f"{'─'*60}")
    print(f"  {theme.colorize_icon_ansi('success')} Active:                 {counts.get('active', 0)}")
    print(f"  {theme.colorize_icon_ansi('warning')} Likely active:          {counts.get('likely_active', 0)}")
    print(f"  {theme.colorize_icon_ansi('error')} Expired (moved):         {counts.get('expired', 0)}")
    print(f"  {theme.colorize_icon_ansi('warning')} Uncertain (left):       {counts.get('uncertain', 0)}")
    print(f"  {theme.colorize_icon_ansi('skip')} Skipped (no URL):       {skipped}")
    print(f"  {theme.colorize_icon_ansi('skip')} Recently checked:       {len(recently_checked)}")
    print()

    return {
        "active": counts.get("active", 0),
        "likely_active": counts.get("likely_active", 0),
        "expired": counts.get("expired", 0),
        "uncertain": counts.get("uncertain", 0),
        "recently_checked": len(recently_checked),
        "skipped": skipped,
        "moved": moved,
    }
