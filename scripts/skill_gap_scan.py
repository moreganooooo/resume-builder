"""skill_gap_scan.py -- scans every PENDING role in the pipeline (not just
the one JD being tailored) for tools/hard_skills/core_functions, aggregates
the ones not yet recorded in verified_tools.json across the whole backlog,
and lets the user mass-confirm which they already have.

Mirrors orchestrator.confirm_jd_skill_gaps_interactively()'s per-JD
"JobRight-style" prompt, but run once across the full pending pipeline
instead of once per tailor build -- the point (per Morgan's own framing) is
to build up the skills bank AHEAD of tailoring, so later evaluations have
more of the model's own extraction to match capability_gaps/fit-scoring
against, not just whatever the currently-being-tailored JD happens to ask
for.

Keyword extraction is a real Gemini call per JD that has never been
extracted before (jd_manager.save_extracted_keywords caches the result on
the JD itself, the same cache the Skills Gap Matrix now also reads from) --
capped by --max-roles per run so a first pass against a large backlog
doesn't silently spend hundreds of API calls. Run again to keep working
through the backlog; already-extracted JDs are free on a repeat run.

Usage:
    python scripts/skill_gap_scan.py [--max-roles N]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cli_art  # noqa: E402
import jd_manager  # noqa: E402
import jd_source  # noqa: E402
import orchestrator  # noqa: E402
import profile_paths  # noqa: E402
import questionary  # noqa: E402
import skills_menu  # noqa: E402
import theme  # noqa: E402

DEFAULT_MAX_ROLES = 40

# Which extraction bucket a gap came from, used purely as a display
# category -- there's no other categorization source for JD-extracted
# candidates (unlike verified_tools.json entries, which carry a real
# `category` field). Priority mirrors find_unverified_jd_skill_gaps' own
# candidate ordering (tools, then hard_skills, then core_functions): a
# name that happens to appear in more than one bucket is labeled by
# whichever is most concrete/actionable.
_CATEGORY_BUCKETS = (
    ("tools", "Tool"),
    ("hard_skills", "Hard Skill"),
    ("core_functions", "Core Function"),
)
_CATEGORY_ORDER = {label: i for i, (_key, label) in enumerate(_CATEGORY_BUCKETS)}
_CATEGORY_ORDER["Skill"] = len(_CATEGORY_BUCKETS)


def _categorize_gaps(gaps: list, combined: dict) -> dict:
    """Maps each gap name to a display category ("Tool"/"Hard Skill"/
    "Core Function", or "Skill" as a fallback) based on which extraction
    bucket first produced it."""
    lookup = {}
    for bucket_key, label in _CATEGORY_BUCKETS:
        for name in combined.get(bucket_key) or []:
            key = name.strip().lower()
            if key and key not in lookup:
                lookup[key] = label
    return {g: lookup.get(g.lower(), "Skill") for g in gaps}


def _all_pending_jd_identifiers() -> list:
    """File paths plus database-only pending job ids -- the full pending
    pipeline, not just the never-evaluated backlog picker.pending_roles()
    walks (that function deliberately excludes anything already evaluated,
    which is most of what this scan wants to cover)."""
    file_paths = jd_manager.get_pending_jds()
    seen = {os.path.basename(p) for p in file_paths}
    for p in file_paths:
        try:
            seen.add(jd_manager.compute_job_key(p))
        except (OSError, ValueError):
            pass

    try:
        import db
    except ImportError:
        return file_paths

    # Fails closed under tests, same reasoning and same guard as
    # picker.pending_roles()/liveness._gather_db_candidates: an unguarded
    # read here would pull a developer's real pending rows into a test.
    if db._is_unisolated_test_write():
        return file_paths

    try:
        conn = db.get_db()
    except Exception:
        return file_paths

    try:
        records = conn.execute(
            "SELECT id FROM jobs WHERE status = 'pending'"
        ).fetchall()
    except Exception:
        return file_paths
    finally:
        conn.close()

    job_ids = [
        str(r["id"])
        for r in records
        if str(r["id"]) not in seen and os.path.basename(str(r["id"])) not in seen
    ]
    return file_paths + job_ids


def gather_pending_skill_gaps(max_roles: int = DEFAULT_MAX_ROLES) -> tuple:
    """Returns (sorted candidate skill names not yet verified, stats dict,
    {name: display category} map). stats records how many roles were
    served from cache vs. freshly extracted vs. left for a future run,
    for the summary printed to the user."""
    identifiers = _all_pending_jd_identifiers()

    try:
        verified_tools_data = skills_menu._load_verified_tools()
    except Exception:
        verified_tools_data = {"tools": []}
    try:
        profile_data = profile_paths.profile_yaml() or {}
    except Exception:
        profile_data = {}

    combined = {"tools": [], "hard_skills": [], "core_functions": []}
    stats = {
        "total": len(identifiers),
        "cached": 0,
        "extracted": 0,
        "failed": 0,
        "budget_skipped": 0,
    }

    for identifier in identifiers:
        try:
            with jd_source.resolved_jd(identifier) as (path, _is_db):
                cached = jd_manager.read_extracted_keywords(path)
                if cached is not None:
                    keywords = cached
                    stats["cached"] += 1
                elif stats["extracted"] < max_roles:
                    keywords = orchestrator.extract_jd_keywords_via_gemini(
                        jd_manager.read_jd_text(path)
                    )
                    if keywords is None:
                        stats["failed"] += 1
                        continue
                    jd_manager.save_extracted_keywords(path, keywords)
                    stats["extracted"] += 1
                else:
                    stats["budget_skipped"] += 1
                    continue
        except Exception:
            stats["failed"] += 1
            continue

        for key in ("tools", "hard_skills", "core_functions"):
            combined[key].extend(keywords.get(key) or [])

    gaps = orchestrator.find_unverified_jd_skill_gaps(
        combined, verified_tools_data, profile_data
    )
    sorted_gaps = sorted(gaps, key=str.lower)
    categories = _categorize_gaps(sorted_gaps, combined)
    return sorted_gaps, stats, categories


def run(max_roles: int = DEFAULT_MAX_ROLES) -> int:
    # Same test/headless guard as confirm_jd_skill_gaps_interactively --
    # never prompt or mutate verified_tools.json under unittest/non-tty.
    if "unittest" in sys.modules or not sys.stdin.isatty():
        return 0

    cli_art.console.rule(
        "Skills Bank Builder -- Pending Pipeline Scan", style=theme.BRAND
    )
    cli_art.detail(
        "Scanning your pending pipeline for tools/skills not yet in your "
        "verified profile...",
        level=cli_art.NORMAL,
    )

    gaps, stats, categories = gather_pending_skill_gaps(max_roles=max_roles)

    if stats["extracted"] or stats["failed"] or stats["budget_skipped"]:
        note = f"Extracted {stats['extracted']} new role(s), {stats['cached']} already cached"
        if stats["failed"]:
            note += f", {stats['failed']} failed"
        if stats["budget_skipped"]:
            note += f", {stats['budget_skipped']} left for a future run (raise --max-roles or re-run)"
        cli_art.detail(note + ".", level=cli_art.NORMAL)

    if not gaps:
        cli_art.detail(
            "No new skill gaps found across your pending pipeline.",
            level=cli_art.NORMAL,
        )
        return 0

    cli_art.detail(
        f"Found {len(gaps)} tool(s)/skill(s) across your pending pipeline not "
        "yet in your verified profile, grouped by category below. Check any "
        "you have legitimate experience with to add them to your verified "
        "tools ledger. Tip: press ctrl+a to select/deselect everything at "
        "once, or start typing to filter the list.",
        level=cli_art.NORMAL,
    )

    ordered_gaps = sorted(
        gaps,
        key=lambda g: (_CATEGORY_ORDER.get(categories.get(g, "Skill"), 3), g.lower()),
    )
    choices = [
        questionary.Choice(title=f"[{categories.get(g, 'Skill')}] {g}", value=g)
        for g in ordered_gaps
    ]
    selected = cli_art.checkbox(
        "Select verified skills/tools to add to your profile:", choices=choices
    )
    if not selected:
        cli_art.detail("No additional skills added.", level=cli_art.NORMAL)
        return 0

    try:
        verified_tools_data = skills_menu._load_verified_tools()
    except Exception:
        verified_tools_data = {"tools": []}

    tools = verified_tools_data.setdefault("tools", [])
    for skill_name in selected:
        new_id = skills_menu._generate_next_id(tools)
        tools.append(
            {
                "id": new_id,
                "name": skill_name,
                "category": "Candidate Verified",
                "confidence": "Proficient",
                "employer": "Self / Profile",
                "use_notes": "Added via Pending Pipeline Skill Gap Scan",
                "tr_references": ["profile.yml"],
            }
        )

    saved = skills_menu._save_verified_tools(verified_tools_data)
    if saved:
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Added [bold green]{len(selected)}[/bold green] "
            f"tool(s) to verified_tools.json: {', '.join(selected)}"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-roles",
        type=int,
        default=DEFAULT_MAX_ROLES,
        help="Max number of never-before-extracted roles to spend a Gemini call on this run.",
    )
    args = parser.parse_args()
    raise SystemExit(run(max_roles=args.max_roles))
