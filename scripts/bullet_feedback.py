"""
bullet_feedback.py — Feeds per-JD-run accepted bullet rewrites back into the
persistent bullet bank's review pipeline.

orchestrator.py's audit_and_refine_bullets() rewrites bullets live during a
single resume build, but until now an accepted rewrite only ever went into
that one resume -- nothing was written back to the bank, so a genuinely
better bullet had to be copied into bullet-bank-clean.csv by hand to survive
past the current JD run.

queue_accepted_rewrite() closes that gap by appending qualifying rewrites to
needs-review.csv, in its existing schema plus the hidden_gem_* columns
triage_needs_review.py's KEEP_FIELDS already expects (but that nothing has
ever populated). triage_needs_review.py itself needs no changes -- it
already knows how to route needs-review.csv rows into bullet-bank-keepers.csv
on its next run.

Only rewrites that clear the bank's actual keeper bar (decide_action() ==
KEEP, reused from rewrite_bullets.py -- the same bar every other path into
the bank uses) are queued; a rewrite that merely improved on a bad original
without reaching that bar is dropped rather than adding review noise.
"""

import csv
import os
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

KB_DIR = profile_paths.kb_dir()

NEEDS_REVIEW = os.path.join(KB_DIR, "needs-review.csv")
KEEPERS = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")

# needs-review.csv's existing 19 columns, plus hidden_gem_score/flag/reason --
# already present in triage_needs_review.py's KEEP_FIELDS allowlist for the
# eventual copy into bullet-bank-keepers.csv, just never populated before.
FIELDNAMES = [
    "cluster_id",
    "cluster_size",
    "is_representative",
    "next_action",
    "Bullet Point",
    "Role / Company",
    "Tags",
    "accuracy_score",
    "believability_score",
    "clarity_score",
    "ats_value",
    "manager_test",
    "weaknesses",
    "hidden_gem_score",
    "hidden_gem_flag",
    "hidden_gem_reason",
    "final_bullet",
    "rewrite_status",
    "rewrite_attempts",
    "rewrite_reasoning",
    "context_gaps",
    "rewrite_date",
]

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from rewrite_bullets import decide_action  # reuse the bank's one keeper bar

_seen_bullets = None  # lazily loaded, module-level cache for this process


def _ensure_schema(path: str = NEEDS_REVIEW) -> None:
    """
    Make sure needs-review.csv's header includes FIELDNAMES, migrating any
    existing rows forward in place (new columns come back blank) if it
    doesn't. No-ops once the header already matches. Safe to call repeatedly.
    """
    if not os.path.exists(path):
        return
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        current_header = reader.fieldnames or []
        rows = list(reader)
    if current_header == FIELDNAMES:
        return
    with atomic_write(path, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_known_bullets(path: str = NEEDS_REVIEW) -> set:
    """Bullet text already present in the keeper CSVs or the queue itself,
    so the same rewrite mined across many JD runs isn't queued repeatedly."""
    seen = set()
    for p in (KEEPERS, KEEPERS_AUDITED, path):
        if not os.path.exists(p):
            continue
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                text = (row.get("Bullet Point") or "").strip()
                if text:
                    seen.add(text)
                final = (row.get("final_bullet") or "").strip()
                if final:
                    seen.add(final)
    return seen


def queue_accepted_rewrite(
    original_bullet: str,
    rewritten_bullet: str,
    company: str,
    tags: str,
    critique: dict,
    path: str = NEEDS_REVIEW,
) -> bool:
    """
    Appends `rewritten_bullet` to needs-review.csv if it clears the bank's
    keeper bar and isn't already known there or in the keeper CSVs. Returns
    True if it was queued.

    `critique` is the rescore already computed for `rewritten_bullet` itself
    (the same dict orchestrator.py used to decide whether to accept the
    rewrite) -- this makes no additional API calls.
    """
    global _seen_bullets
    if _seen_bullets is None:
        _ensure_schema(path)
        _seen_bullets = _load_known_bullets(path)

    passes_keeper_bar = (
        decide_action(critique) == "KEEP"
        and str(critique.get("manager_test", "")).strip().upper() == "PASS"
    )
    if not passes_keeper_bar:
        return False

    final_text = rewritten_bullet.strip()
    if not final_text or final_text in _seen_bullets:
        return False

    row = {
        "Bullet Point": original_bullet,
        "Role / Company": company,
        "Tags": tags,
        "accuracy_score": critique.get("accuracy_score", ""),
        "believability_score": critique.get("believability_score", ""),
        "clarity_score": critique.get("clarity_score", ""),
        "ats_value": critique.get("ats_value", ""),
        "manager_test": critique.get("manager_test", ""),
        "weaknesses": critique.get("weaknesses", ""),
        "hidden_gem_score": critique.get("hidden_gem_score", ""),
        "hidden_gem_flag": critique.get("hidden_gem_flag", ""),
        "hidden_gem_reason": critique.get("hidden_gem_reason", ""),
        "final_bullet": final_text,
        "rewrite_status": "",  # blank so triage_needs_review.py routes it fresh
        "rewrite_attempts": 1,
        "rewrite_date": str(date.today()),
    }

    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    _seen_bullets.add(final_text)
    return True
