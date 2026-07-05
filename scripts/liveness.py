"""
liveness.py — the `liveness` command: checks every pending JD's source_url
via a Node/Playwright subprocess, moving confirmed-expired postings out of
the active queue into jds/expired/.

No MongoDB, no LLM calls -- pure Playwright + deterministic classification,
ported from career-ops's already-proven liveness-core.mjs/liveness-browser.mjs.
See docs/superpowers/specs/2026-07-05-liveness-checker-design.md.
"""

import json
import os
import shutil
import subprocess

import jd_manager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIVENESS_INPUT_PATH = os.path.join(jd_manager.PROJECT_ROOT, "output", "liveness_input_tmp.json")


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


def run_liveness_check() -> dict:
    """
    Checks every pending JD's source_url, moves confirmed-expired ones to
    jds/expired/. Returns a summary dict with keys: active, likely_active,
    expired, uncertain, skipped, moved (plus error=True on a failure path).
    """
    pending_paths = jd_manager.get_pending_jds()
    candidates = _gather_candidates(pending_paths)
    skipped = len(pending_paths) - len(candidates)

    if not candidates:
        print(f"Nothing to check -- {len(pending_paths)} pending JD(s), none with a source_url.")
        return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "moved": 0}

    os.makedirs(os.path.dirname(LIVENESS_INPUT_PATH), exist_ok=True)
    with open(LIVENESS_INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f)

    try:
        script = os.path.join(SCRIPT_DIR, "check-liveness.mjs")
        proc = subprocess.run(
            ["node", script, "--json-file", LIVENESS_INPUT_PATH],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"  ⚠️  Liveness check failed:\n{proc.stderr}")
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "moved": 0, "error": True}

        try:
            results = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"  ⚠️  Liveness check produced unparseable output:\n{proc.stdout[:500]}")
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "moved": 0, "error": True}
    finally:
        if os.path.exists(LIVENESS_INPUT_PATH):
            os.remove(LIVENESS_INPUT_PATH)

    counts = {}
    moved = 0
    os.makedirs(jd_manager.EXPIRED_DIR, exist_ok=True)

    for r in results:
        outcome = r.get("result", "uncertain")
        counts[outcome] = counts.get(outcome, 0) + 1
        icon = {"active": "✅", "likely_active": "🟡", "expired": "❌", "uncertain": "⚠️"}.get(outcome, "❓")
        print(f"  {icon} {outcome:<14} {r.get('source_file')}")
        if outcome not in ("active", "likely_active"):
            print(f"       {r.get('reason', '')}")

        if outcome == "expired":
            source_file = r.get("source_file")
            if source_file and os.path.exists(source_file):
                dest = os.path.join(jd_manager.EXPIRED_DIR, os.path.basename(source_file))
                shutil.move(source_file, dest)
                moved += 1

    print(
        f"\nLiveness summary: {counts.get('active', 0)} active, "
        f"{counts.get('likely_active', 0)} likely active, "
        f"{counts.get('expired', 0)} expired (moved to jds/expired/), "
        f"{counts.get('uncertain', 0)} uncertain (left in place), "
        f"{skipped} skipped (no source_url)."
    )

    return {
        "active": counts.get("active", 0),
        "likely_active": counts.get("likely_active", 0),
        "expired": counts.get("expired", 0),
        "uncertain": counts.get("uncertain", 0),
        "skipped": skipped,
        "moved": moved,
    }
