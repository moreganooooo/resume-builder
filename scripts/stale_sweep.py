"""stale_sweep.py -- shrinks an over-grown Pending JD queue by moving
postings past a staleness threshold into jd_manager.EXPIRED_DIR.

Scoring alone (orchestrator.STALE_POSTING_*) can only rank old postings
lower; it can't shrink a backlog that's already 1,000+ files deep. This
module is what actually removes stale postings from the active queue.

LOGIC ONLY -- no prompts, no confirmations, no menu code. run_sweep()
and backfill_discovery_dates() both assume the caller already confirmed
with the user; menu._handle_stale_sweep() is that caller.
"""

import os
import shutil

import cli_art
import jd_manager
import picker

DEFAULT_STALE_ARCHIVE_DAYS = 30


def _is_already_applied(application: dict | None) -> bool:
    """True if this JD carries any persisted _application record at all
    (see jd_manager.save_application_status()/read_application_status()).
    Presence of a record -- regardless of which APPLICATION_STATUSES
    value it holds (even "Rejected"/"Withdrawn") -- means a real
    application exists somewhere out in the world; losing track of it by
    archiving the JD out from under it would be the worst possible bug
    this module could have, so presence alone is the gate, not a
    specific status value."""
    return bool(application)


def _classify(row: dict, threshold_days: int) -> tuple:
    """Returns ("archive" | "keep" | "skip", age_days) for one
    picker.list_all_evaluated_jds() row. age_days is None only for
    "skip" (compute_posting_age_days() found no age signal at all).
    Boundary is inclusive: a posting exactly at threshold_days old is
    "archive", matching the everyday reading of "archive postings 30+
    days old" -- a strict "> threshold" reading (like
    orchestrator.fit_composite_score()'s penalty threshold) would leave
    a posting sitting at exactly the number the user configured."""
    age_days = jd_manager.compute_posting_age_days(row["path"])
    if age_days is None:
        return "skip", None
    if _is_already_applied(row.get("application")):
        return "keep", age_days
    if age_days >= threshold_days:
        return "archive", age_days
    return "keep", age_days


def preview_sweep(threshold_days: int = DEFAULT_STALE_ARCHIVE_DAYS) -> dict:
    """Pure: computes what WOULD move. Never writes anything.

    Only Pending postings are eligible -- a Completed one has already
    been acted on -- sourced via picker.list_all_evaluated_jds(), the
    same listing the menu's browse views already use. A posting whose
    age can't be determined at all is never archived (see
    jd_manager.compute_posting_age_days()'s own docstring: guessing
    staleness from missing data would silently delete real leads, the
    same choice orchestrator.fit_composite_score() makes for scoring
    penalties). A posting already applied to is never archived either,
    regardless of age -- see _is_already_applied().
    """
    to_archive = []
    to_keep_count = 0
    oldest_kept_days = None
    newest_moved_days = None
    skipped_no_age_count = 0

    for row in picker.list_all_evaluated_jds(statuses=["Pending"]):
        outcome, age_days = _classify(row, threshold_days)
        if outcome == "skip":
            skipped_no_age_count += 1
            continue
        if outcome == "archive":
            to_archive.append(
                {
                    "path": row["path"],
                    "company": row["company"],
                    "title": row["title"],
                    "age_days": age_days,
                }
            )
            if newest_moved_days is None or age_days < newest_moved_days:
                newest_moved_days = age_days
        else:
            to_keep_count += 1
            if oldest_kept_days is None or age_days > oldest_kept_days:
                oldest_kept_days = age_days

    return {
        "to_archive": to_archive,
        "to_keep_count": to_keep_count,
        "oldest_kept_days": oldest_kept_days,
        "newest_moved_days": newest_moved_days,
        "skipped_no_age_count": skipped_no_age_count,
    }


def _move_to_expired(jd_path: str) -> str:
    """Moves jd_path into jd_manager.EXPIRED_DIR, suffixing on collision.

    Delegates to jd_manager.move_jd_to(), which is where this function's
    original collision-avoidance loop now lives -- liveness.py writes into
    the same directory and had the clobbering bug this loop was written to
    avoid, so the safe version belongs in one shared place rather than
    being correct here and wrong there."""
    return jd_manager.move_jd_to(jd_path, jd_manager.EXPIRED_DIR)


def run_sweep(threshold_days: int = DEFAULT_STALE_ARCHIVE_DAYS) -> dict:
    """Performs the moves preview_sweep() at the same threshold_days
    would report. Returns the same shape plus "archived_count" and
    "errors" ([{"path", "error"}, ...]).

    Assumes the caller already confirmed with the user -- this module
    owns no prompts of its own. One file failing to move (permissions, a
    file that's since vanished, a sync conflict) is collected into
    "errors" and does not stop the rest of the sweep -- with a backlog
    in the thousands, aborting the whole sweep on the first bad file
    would be the most damaging possible failure mode here.
    """
    result = preview_sweep(threshold_days)
    archived_count = 0
    errors = []

    for item in result["to_archive"]:
        try:
            _move_to_expired(item["path"])
            archived_count += 1
        except OSError as e:
            cli_art.friendly_warning(
                e,
                f"archiving stale posting ({item['company'] or item['path']})",
                "it stays in your active queue -- re-run the sweep once the underlying issue is fixed",
            )
            errors.append({"path": item["path"], "error": str(e)})

    result["archived_count"] = archived_count
    result["errors"] = errors
    return result


def backfill_discovery_dates(dry_run: bool = True) -> dict:
    """Stamps _discovered_at on pending postings that have no age signal
    at all, using the JD file's own modification time as the first-seen
    date.

    Why this is needed: a posting with neither a published posted date nor
    a discovery stamp is permanently un-ageable -- the staleness curve
    never devalues it and the sweep never touches it, so it sits in the
    queue forever. On a real queue that was 297 of 872 postings, i.e. the
    single biggest obstacle to the queue ever shrinking. scan.py now
    stamps every new posting it writes, but that does nothing for the ones
    already on disk; this is the one-time catch-up for those.

    mtime is a genuine lower bound rather than a guess: the file cannot
    have existed before it was written, so "first seen" is at worst
    conservative -- it may under-state a posting's true age, never
    over-state it. Under-stating is the safe direction, since the cost is
    keeping something slightly too long rather than archiving a live lead.
    The stamp records source="backfill-mtime" so an inferred date stays
    distinguishable from one a scan actually observed.

    dry_run=True (the default) reports what would be stamped and writes
    nothing -- same preview-before-you-act shape as preview_sweep(), and
    the default is the safe one because this rewrites JD files in place.
    """
    import datetime

    candidates = []
    errors = []
    stamped = 0

    for row in picker.list_all_evaluated_jds(statuses=["Pending"]):
        path = row["path"]
        # Only postings with NO age signal whatsoever. A posting that
        # already resolves an age -- from a real posted date or an earlier
        # stamp -- must never be re-dated, or it would be made younger than
        # it is and quietly escape the sweep.
        if jd_manager.compute_posting_age_days(path) is not None:
            continue

        candidates.append(
            {
                "path": path,
                "company": row.get("company") or "?",
                "title": row.get("title") or "?",
            }
        )
        if dry_run:
            continue

        try:
            mtime = os.path.getmtime(path)
            when = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
            jd_manager.save_discovered_at(path, when=when, source="backfill-mtime")
            stamped += 1
        except OSError as e:
            cli_art.friendly_warning(
                e,
                f"dating {os.path.basename(path)}",
                "leaving it undated, so it stays in the queue",
            )
            errors.append({"path": path, "error": str(e)})

    return {
        "candidates": candidates,
        "candidate_count": len(candidates),
        "stamped_count": stamped,
        "errors": errors,
    }
