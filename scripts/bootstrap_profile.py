#!/usr/bin/env python3
"""
bootstrap_profile.py

Phase 0.5 of the bootstrap flow: guesses and confirms profile.yml,
portals.yml, drafts cv.md and user-background-guide.md, and derives the
verified_* ledger -- all from documents Phase 0 (bootstrap_bullet_bank.py)
already ingested. See run_profile_setup() for the single entry point.
"""

import csv
import json
import os
import re
import sys
from typing import Any, Callable, cast

import questionary
import yaml
from dotenv import dotenv_values, set_key

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

KB_DIR = profile_paths.kb_dir()

PROFILE_YML_PATH = os.path.join(KB_DIR, "profile.yml")
PORTALS_YML_PATH = os.path.join(KB_DIR, "portals.yml")
SITUATIONAL_ROLES_PATH = profile_paths.situational_roles_path()
CV_MD_PATH = os.path.join(KB_DIR, "cv.md")
BACKGROUND_GUIDE_PATH = os.path.join(KB_DIR, "user-background-guide.md")
VOICE_ANCHORS_PATH = os.path.join(KB_DIR, "voice-anchors.md")
VERIFIED_METRICS_PATH = os.path.join(KB_DIR, "verified_metrics.json")
VERIFIED_TOOLS_PATH = os.path.join(KB_DIR, "verified_tools.json")
VERIFIED_PROJECTS_PATH = os.path.join(KB_DIR, "verified_projects.json")
VERIFIED_FACTS_PATH = os.path.join(KB_DIR, "verified_facts.json")
VERIFIED_CLAIMS_PATH = os.path.join(KB_DIR, "verified-claims.csv")
EVIDENCE_GRAPH_PATH = os.path.join(KB_DIR, "evidence_graph.json")
EVIDENCE_GUIDE_PATH = os.path.join(KB_DIR, "evidence-guide.csv")
SCREENSHOT_METRICS_PATH = os.path.join(KB_DIR, "extracted-screenshot-metrics.csv")
RECRUITER_PATTERNS_PATH = os.path.join(KB_DIR, "recruiter_memory_patterns.json")
CV_DRAFT_CHECKPOINT_PATH = os.path.join(KB_DIR, "bootstrap", "cv_draft_checkpoint.json")

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402
import cli_art  # noqa: E402
import content_settings  # noqa: E402
import theme  # noqa: E402
from rewrite_bullets import (  # noqa: E402
    RULES_DIR,
    KnowledgeBase,
    RulesBundle,
    build_system_prompts,
    process_bullet,
)


def _load_checkpoint() -> dict:
    if not os.path.exists(bootstrap_bullet_bank.CHECKPOINT_PATH):
        return {}
    with open(bootstrap_bullet_bank.CHECKPOINT_PATH, encoding="utf-8") as f:
        return cast("dict", json.load(f))


def _load_timeline() -> list:
    if not os.path.exists(bootstrap_bullet_bank.TIMELINE_PATH):
        return []
    with open(bootstrap_bullet_bank.TIMELINE_PATH, encoding="utf-8") as f:
        return cast("list", json.load(f))


def _achievements_summary_text() -> str:
    """Bullet text only, joined for prompts that don't need per-bullet
    employer attribution (e.g. secondary-role suggestion)."""
    if not os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH):
        return ""
    with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return "\n".join(row.get("Bullet Point", "") for row in rows)


def _bullet_source_path() -> str | None:
    """The CSV to read achievement bullets from, or None if neither exists.

    bullet-bank-draft.csv is a *bootstrap-only* artifact: it exists while
    a profile is being onboarded and not afterwards. An established
    profile keeps its bullets in bullet-bank-clean.csv, which shares the
    "Role / Company" + "Bullet Point" columns this module needs.

    Reading only the draft meant write_verified_ledger() saw an empty
    achievements string on any established profile, extracted nothing,
    and then wrote total_entries: 0 over verified_metrics/tools/projects
    -- turning a routine bootstrap re-run into silent KB data loss.
    """
    for path in (
        bootstrap_bullet_bank.DRAFT_CSV_PATH,
        bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH,
    ):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None


def _achievements_summary_text_by_employer() -> str:
    """Same bullets as _achievements_summary_text(), but each line prefixed
    with its "Role / Company" in brackets -- required by extract_ledger_entries()
    so extracted metrics/tools/projects can be attributed to the right employer
    (see _LEDGER_PROMPT in bootstrap_extractors.py). Without this, a fresh
    profile's verified_metrics/tools/projects.json would have no "employer"
    field, silently disabling filter_projects_by_employer()'s protection
    against cross-company content leaking into a rewritten bullet."""
    path = _bullet_source_path()
    if path is None:
        return ""
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return "\n".join(
        f"[{row.get('Role / Company', '')}] {row.get('Bullet Point', '')}"
        for row in rows
    )


def _resolve_text_or_upload(path: str) -> tuple:
    """Re-derives a document's text-or-upload_path split for a second
    extraction pass over it (contact info / recommendation quotes) without
    modifying Phase 0's _process_one_file."""
    kind = bootstrap_extractors.detect_file_kind(path)
    if kind == "doc":
        converted = bootstrap_extractors.convert_legacy_doc_to_pdf(path)
        if converted is None:
            return None, None
        path, kind = converted, "pdf"
    if kind in ("pdf", "image"):
        return None, path
    if kind == "unsupported":
        return None, None
    return bootstrap_extractors.extract_local_text(path, kind), None


def _guess_contact_info(
    checkpoint: dict, dry_run: bool = False
) -> bootstrap_extractors.ContactInfo:
    for filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done" or result.get("doc_type") not in (
            "resume",
            "linkedin_export",
        ):
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, upload_path = _resolve_text_or_upload(path)
        if text is None and upload_path is None:
            continue
        info = bootstrap_extractors.extract_contact_info(
            text=text, upload_path=upload_path, dry_run=dry_run
        )
        if any(v for v in info.model_dump().values()):
            return info
    return bootstrap_extractors.ContactInfo()


def _guess_primary_roles(timeline: list) -> list:
    seen = []
    for entry in sorted(timeline, key=lambda e: e.get("end_date") or "", reverse=True):
        title = entry.get("title")
        if title and title not in seen:
            seen.append(title)
    return seen[:3]


def _guess_recommendations(checkpoint: dict, dry_run: bool = False) -> list:
    quotes = []
    for filename, result in sorted(checkpoint.items()):
        if (
            result.get("status") != "done"
            or result.get("doc_type") != "recommendation_letter"
        ):
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, upload_path = _resolve_text_or_upload(path)
        if text is None and upload_path is None:
            continue
        quote = bootstrap_extractors.extract_recommendation_quote(
            text=text, upload_path=upload_path, dry_run=dry_run
        )
        if quote is not None:
            quotes.append(quote)
    return quotes


def _load_existing_identity() -> dict:
    """Reads candidate/target_roles/location straight from an existing
    profile.yml, if one exists -- used as the fallback default when
    "Update My Knowledge" re-runs identity collection. Without this, a
    re-run only had fresh per-document extraction guesses to offer as
    defaults (empty whenever this run's new documents didn't happen to
    contain a resume/LinkedIn export), so a returning user saw their
    already-answered fields reset to blank instead of pre-filled with
    what they already told the program."""
    if not os.path.exists(PROFILE_YML_PATH):
        return {}
    with open(PROFILE_YML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    candidate = data.get("candidate") or {}
    target_roles = data.get("target_roles") or {}
    location = data.get("location") or {}
    return {
        "full_name": candidate.get("full_name") or "",
        "email": candidate.get("email") or "",
        "phone": candidate.get("phone") or "",
        "location": candidate.get("location") or "",
        "linkedin_url": candidate.get("linkedin") or "",
        "portfolio_url": candidate.get("portfolio_url") or "",
        "extra_link": candidate.get("extra_link") or "",
        "primary_roles": target_roles.get("primary") or [],
        "secondary_roles": target_roles.get("secondary") or [],
        "remote_preference": bool(location.get("remote_required")),
    }


def _confirm_text(label: str, guessed) -> str:
    return cli_art.text(label, default=guessed or "") or ""


def _confirm_roles(label: str, guessed: list) -> list:
    if not guessed:
        extra = cli_art.text(f"{label} (comma-separated, optional)", default="") or ""
        return [r.strip() for r in extra.split(",") if r.strip()]
    choices = [questionary.Choice(title=r, value=r, checked=True) for r in guessed]
    kept = (
        cli_art.checkbox(
            f"{label} we detected -- uncheck any that don't fit, or leave as-is",
            choices=choices,
        )
        or []
    )
    extra = (
        cli_art.text(
            f"Anything missing? Add more {label.lower()} (comma-separated, or "
            "press Enter to move on)",
            default="",
        )
        or ""
    )
    kept.extend(r.strip() for r in extra.split(",") if r.strip())
    return kept


def _identity_dry_run(guessed, primary_guess: list) -> dict:
    """Prints the identity fields a real run would confirm, and returns them."""
    cli_art.cli_info("[DRY RUN] would confirm identity fields:")
    cli_art.console.print()
    cli_art.cli_info(f"Full name: {guessed.full_name or ''}")
    cli_art.cli_info(f"Email: {guessed.email or ''}")
    cli_art.cli_info(f"Phone: {guessed.phone or ''}")
    cli_art.cli_info(f"Location: {guessed.location or ''}")
    cli_art.cli_info(f"LinkedIn URL: {guessed.linkedin_url or ''}")
    cli_art.cli_info(f"Primary target roles: {', '.join(primary_guess)}")
    cli_art.console.print()
    return {
        "full_name": guessed.full_name or "",
        "email": guessed.email or "",
        "phone": guessed.phone or "",
        "location": guessed.location or "",
        "linkedin_url": guessed.linkedin_url or "",
        "portfolio_url": guessed.portfolio_url or "",
        "extra_link": "",
        "primary_roles": primary_guess,
        "secondary_roles": [],
        "remote_preference": False,
    }


def _review_identity(result: dict) -> None:
    """Shows every collected identity field back for a final yes/no."""
    cli_art.console.rule("Review your answers", style="dim")
    cli_art.cli_info(f"Full name:       {result['full_name'] or '(blank)'}")
    cli_art.cli_info(f"Email:           {result['email'] or '(blank)'}")
    cli_art.cli_info(f"Phone:           {result['phone'] or '(blank)'}")
    cli_art.cli_info(f"Location:        {result['location'] or '(blank)'}")
    cli_art.cli_info(f"LinkedIn URL:    {result['linkedin_url'] or '(blank)'}")
    cli_art.cli_info(f"Portfolio URL:   {result['portfolio_url'] or '(blank)'}")
    cli_art.cli_info(f"Other link:      {result['extra_link'] or '(blank)'}")
    cli_art.cli_info(
        f"Primary roles:   {', '.join(result['primary_roles']) or '(none)'}"  # type: ignore[arg-type]
    )
    cli_art.cli_info(
        f"Secondary roles: {', '.join(result['secondary_roles']) or '(none)'}"  # type: ignore[arg-type]
    )
    cli_art.cli_info(
        f"Remote-only:     {'Yes' if result['remote_preference'] else 'No'}"
    )
    cli_art.console.print()


def collect_identity(dry_run: bool = False) -> dict:
    checkpoint = _load_checkpoint()
    timeline = _load_timeline()
    guessed = _guess_contact_info(checkpoint, dry_run=dry_run)
    primary_guess = _guess_primary_roles(timeline)
    # Fresh per-document extraction wins when it found something; an
    # already-answered field from a prior run fills in the rest, so
    # "Update My Knowledge" shows the user what they already told the
    # program instead of a blank field. See _load_existing_identity()'s
    # docstring for why this matters.
    existing = _load_existing_identity()
    for field in (
        "full_name",
        "email",
        "phone",
        "location",
        "linkedin_url",
        "portfolio_url",
    ):
        if not getattr(guessed, field, None) and existing.get(field):
            setattr(guessed, field, existing[field])
    existing_extra_link = existing.get("extra_link") or ""
    if not primary_guess and existing.get("primary_roles"):
        primary_guess = existing["primary_roles"]

    if dry_run:
        return _identity_dry_run(guessed, primary_guess)

    # This is the single densest sequential-entry point in the whole wizard
    # (9 fields/prompts in a row) with no way to correct an earlier answer
    # except finishing everything and re-running the whole step from
    # scratch. Wrapping it in a review-and-redo loop instead: collect
    # everything once, show it all back, and either accept it or go
    # through the same prompts again with what was just typed pre-filled
    # as the new defaults -- so fixing one wrong field doesn't mean
    # retyping the other eight. `defaults` starts from the guessed/existing
    # values and gets replaced with the previous pass's own answers on a
    # redo; `secondary_defaults` is tracked separately from `defaults` so a
    # redo reuses the already-typed secondary roles instead of spending a
    # second suggest_secondary_roles() API call.
    defaults = {
        "full_name": guessed.full_name,
        "email": guessed.email,
        "phone": guessed.phone,
        "location": guessed.location,
        "linkedin_url": guessed.linkedin_url,
        "portfolio_url": guessed.portfolio_url,
        "extra_link": existing_extra_link,
        "primary_roles": primary_guess,
        "remote_preference": existing.get("remote_preference", True),
    }
    secondary_defaults = None  # None means "not yet suggested this session"

    while True:
        full_name = _confirm_text("Full name:", defaults["full_name"])
        email = _confirm_text("Email (e.g. jane.doe@gmail.com):", defaults["email"])
        phone = _confirm_text("Phone (e.g. (555) 123-4567):", defaults["phone"])
        location = _confirm_text("Location (e.g. Austin, TX):", defaults["location"])
        linkedin_url = _confirm_text(
            "LinkedIn URL (e.g. linkedin.com/in/janedoe):", defaults["linkedin_url"]
        )
        portfolio_url = _confirm_text(
            "Portfolio URL (optional, press Enter to skip):",
            defaults["portfolio_url"],
        )
        extra_link = _confirm_text(
            "Any other portfolio/work-sample link? (optional, press Enter to skip):",
            defaults["extra_link"],
        )

        cli_art.console.print()
        cli_art.console.print(
            "[dim]Primary target roles are the exact job titles you'd apply to "
            'today -- e.g. "Product Marketing Manager", "Senior Copywriter." '
            "These drive job-board searches and scoring, so keep them specific "
            "and few (2-4 is typical).[/dim]"
        )
        primary_roles = _confirm_roles(
            "Primary target roles:", defaults["primary_roles"]
        )

        if secondary_defaults is None:
            achievements_text = _achievements_summary_text()
            secondary_defaults = (
                bootstrap_extractors.suggest_secondary_roles(
                    primary_roles, achievements_text, dry_run=dry_run
                )
                if primary_roles
                else []
            )
        cli_art.console.print()
        cli_art.console.print(
            "[dim]Secondary target roles are near-miss or stretch titles you'd "
            'also consider -- e.g. a step up ("Senior Marketing Manager"), a '
            'step sideways ("Content Strategist"), or a title you\'re open to '
            "but wouldn't chase first. Fine to leave empty.[/dim]"
        )
        secondary_roles = _confirm_roles("Secondary target roles:", secondary_defaults)

        cli_art.console.print()
        cli_art.console.print(
            "[dim]This only affects the location filter used when scanning for "
            "new postings -- it excludes onsite/hybrid roles outright. You can "
            "change it later in Settings & Upkeep.[/dim]"
        )
        remote_preference = cli_art.confirm(
            "Are you remote-only (no onsite/hybrid roles)?",
            default=defaults["remote_preference"],
        )

        result: dict[str, Any] = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "location": location,
            "linkedin_url": linkedin_url,
            "portfolio_url": portfolio_url,
            "extra_link": extra_link,
            "primary_roles": primary_roles,
            "secondary_roles": secondary_roles,
            "remote_preference": bool(remote_preference),
        }

        cli_art.console.print()
        _review_identity(result)

        if cli_art.confirm("Everything look right?", default=True):
            return result

        cli_art.cli_info(
            "No problem -- let's go through it again. Your previous answers are "
            "pre-filled, so press Enter to keep anything that was already right."
        )
        defaults = {**defaults, **result}
        secondary_defaults = result["secondary_roles"]


def collect_deal_breakers(dry_run: bool = False) -> list:
    """Free-text list of hard no's for a role (profile.yml's
    deal_breakers:), e.g. "On-site required", "Below $90K". Distinct from
    the structured, enforced gates in scan_filters.yml (location radius,
    travel ceiling, employment type, pay floor) -- this is prose for a
    human (or the LLM evaluator) to read, not something board_scanner
    parses, so it's fine to leave sparse or empty."""
    if dry_run:
        cli_art.cli_info("[DRY RUN] would collect deal-breakers.")
        return []
    cli_art.console.print()
    cli_art.console.print(
        "[dim]Deal-breakers are things that would make you turn down a role "
        'outright -- e.g. "On-site or hybrid required", "Below $90K", '
        '"No PTO." These are read by the fit evaluator alongside the '
        "structured filters (location radius, pay floor, travel ceiling, "
        "employment type) you can set up next. Optional.[/dim]"
    )
    return _confirm_roles("Deal-breakers:", [])


def offer_settings_screens(dry_run: bool = False) -> None:
    """Offers the existing Settings & Upkeep screens most relevant to a
    first-time profile, right after the profile.yml fields they extend
    are collected -- rather than leaving them undiscovered until someone
    stumbles into Settings later. Each is genuinely optional and already
    has its own "Back" option, so a no-op answer here costs nothing."""
    if dry_run:
        cli_art.cli_info(
            "[DRY RUN] would offer location radius, pay/travel/hours, and "
            "skills-review setup screens."
        )
        return

    cli_art.console.print()
    if cli_art.confirm(
        "Set up your commute radius and location filters now? (Settings & "
        "Upkeep > Location, can change any time)",
        default=True,
    ):
        import location_settings

        location_settings.run_location_settings()

    cli_art.console.print()
    if cli_art.confirm(
        "Set your pay floor, travel ceiling, accepted employment types, and "
        "IC-vs-manager preference now? (Settings & Upkeep > Language & "
        "travel, can change any time)",
        default=True,
    ):
        import content_settings

        content_settings.run_content_settings()

    cli_art.console.print()
    if cli_art.confirm(
        "Answer a few quick questions to tune how postings get scored "
        "(low-stress vs. stretch roles, remote-competition sensitivity)? "
        "(Settings & Upkeep > Scoring Weights, can change any time)",
        default=True,
    ):
        import content_settings

        content_settings.run_guided_scoring_weights_setup()

    cli_art.console.print()
    if cli_art.confirm(
        "Review the skills/tools pulled from your documents and add any "
        "that were missed? (Settings & Upkeep > Skills, can change any "
        "time)",
        default=True,
    ):
        import skills_menu

        skills_menu.run_skills_menu()


def report_job_board_readiness(dry_run: bool = False) -> None:
    """Prints which job-board sources will work right away vs. need extra
    setup -- read-only, no prompts. Indeed (via JobSpy) and any ATS board
    already listed in tracked_companies.yml need nothing beyond what
    bootstrap already collected. LinkedIn, Jobright, and the ATS
    Brave-search discovery sweep each need a separate secret/cookie that
    bootstrap does NOT collect today, so this exists to surface that gap
    rather than let someone discover it only when a scan silently skips
    a source."""
    env_path = os.path.join(profile_paths.profile_root(), ".env")
    env_text = ""
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_text = f.read()
    has_jobright = "JOBRIGHT_COOKIE_STRING=" in env_text and not re.search(
        r"^JOBRIGHT_COOKIE_STRING=\s*$", env_text, re.MULTILINE
    )
    has_brave = "BRAVE_API_KEY=" in env_text and not re.search(
        r"^BRAVE_API_KEY=\s*$", env_text, re.MULTILINE
    )
    has_linkedin_cookie = os.path.exists(
        os.path.join(profile_paths.profile_root(), ".linkedin_cookie")
    )
    tracked_companies_path = os.path.join(
        profile_paths.board_scanner_dir(), "tracked_companies.yml"
    )
    tracked_count = 0
    if os.path.exists(tracked_companies_path):
        with open(tracked_companies_path, "r", encoding="utf-8") as f:
            tracked = yaml.safe_load(f) or []
        tracked_count = len(tracked) if isinstance(tracked, list) else 0

    cli_art.console.print()
    cli_art.console.rule("Job board readiness", style="dim")
    cli_art.cli_info(f"{cli_art.SUCCESS} Indeed -- works now, no setup needed.")
    if tracked_count:
        cli_art.cli_info(
            f"{cli_art.SUCCESS} ATS boards -- {tracked_count} company board(s) "
            "already tracked in tracked_companies.yml."
        )
    else:
        cli_art.cli_info(
            f"{cli_art.WARNING} ATS boards -- none tracked yet. Run "
            "'Discover Local Employers' from the main menu to find and add some."
        )
    if has_linkedin_cookie:
        cli_art.cli_info(f"{cli_art.SUCCESS} LinkedIn -- cookie found, ready to scan.")
    else:
        cli_art.cli_info(
            f"{cli_art.WARNING} LinkedIn -- needs a logged-in Chrome session "
            "the scanner can read from; no cookie file set up yet."
        )
    if has_jobright:
        cli_art.cli_info(f"{cli_art.SUCCESS} Jobright -- cookie configured.")
    else:
        cli_art.cli_info(
            f"{cli_art.WARNING} Jobright -- needs JOBRIGHT_COOKIE_STRING in "
            "your .env to scan this source. Optional."
        )
    if has_brave:
        cli_art.cli_info(
            f"{cli_art.SUCCESS} ATS discovery search -- Brave API key set."
        )
    else:
        cli_art.cli_info(
            f"{cli_art.WARNING} ATS discovery search -- needs BRAVE_API_KEY in "
            "your .env to find new ATS boards by search. Optional; tracked "
            "boards above still scan without it."
        )
    cli_art.console.print()

    if tracked_count == 0 and not dry_run:
        if cli_art.confirm(
            "Search for local employers with public ATS boards now? (optional -- "
            "finds companies near you whose own careers pages can be scanned "
            "for the full job text, not just aggregator teasers)",
            default=False,
        ):
            import discover_local_employers

            hits = discover_local_employers.discover()
            if not hits:
                cli_art.cli_info(
                    f"{cli_art.WARNING} No local employers with a public ATS board found."
                )
            else:
                cli_art.cli_info(
                    f"Found {len(hits)} local employer(s) with a public board:"
                )
                for hit in hits:
                    cli_art.cli_info(
                        f"    {hit['name']}  ({hit['provider']} -- "
                        f"{hit['postings']} open role(s))"
                    )
                if cli_art.confirm(
                    f"Track these {len(hits)} employer(s)?", default=True
                ):
                    path = discover_local_employers.tracked_companies_path()
                    backup = discover_local_employers.append_entries(hits, path)
                    cli_art.cli_info(
                        f"{cli_art.SUCCESS} Added {len(hits)}. Backup: {backup}"
                    )
            cli_art.console.print()


def collect_voice_calibration_example(dry_run: bool = False) -> str:
    """A short, real quote in the candidate's own voice, used only by
    evaluate_recruiter.md's role-rules block for tone calibration --
    distinct from and much smaller than voice-anchors.md (the full
    writing-sample corpus drafted from source_documents/, see
    write_voice_anchors()). Optional: an empty string is a fully
    supported "not set" state (build_role_rules_block() falls back to
    general judgment)."""
    if dry_run:
        cli_art.cli_info(
            "[DRY RUN] would prompt for an optional voice-calibration example quote."
        )
        return ""
    return (
        _confirm_text(
            "A short, real sentence or two in your own voice (optional -- used "
            "to calibrate tone during resume critique; press Enter to skip). "
            "This is just a quick quote typed here -- if you'd rather have a "
            "fuller writing sample drawn from a document, drop it in your "
            "source documents folder and this wizard's later 'Writing Voice "
            "& Samples' step will draft from it instead:",
            None,
        )
        or ""
    )


_VOICE_CALIBRATION_LINE_RE = re.compile(
    r'^voice_calibration_example:\s*".*"\s*$', re.MULTILINE
)


def get_voice_calibration_example() -> str:
    """Reads the current value straight from profile.yml, if any -- used
    by the Settings & Upkeep editor to show what's already set before
    offering to replace it."""
    if not os.path.exists(PROFILE_YML_PATH):
        return ""
    with open(PROFILE_YML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("voice_calibration_example") or ""


def set_voice_calibration_example(value: str) -> None:
    """Adds or replaces profile.yml's voice_calibration_example line via
    targeted text substitution rather than a full yaml.safe_load/dump
    round-trip -- profile.yml is a hand-annotated template full of prose
    comments (see _PROFILE_YML_TEMPLATE), and a real yaml.dump would
    silently strip every one of them. A profile.yml written before this
    field existed has no line to replace, so a missing match appends a
    fresh section instead, mirroring the template's own comment block."""
    if not os.path.exists(PROFILE_YML_PATH):
        raise FileNotFoundError(f"No profile.yml at {PROFILE_YML_PATH} yet.")
    with open(PROFILE_YML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    escaped = json.dumps(value or "")
    new_line = f"voice_calibration_example: {escaped}"
    if _VOICE_CALIBRATION_LINE_RE.search(content):
        content = _VOICE_CALIBRATION_LINE_RE.sub(new_line, content, count=1)
    else:
        content = content.rstrip("\n") + (
            "\n\n# A short, real quote in your own voice -- used only to calibrate "
            "tone\n# during resume critique (evaluate_recruiter.md's role-rules "
            "block), not\n# your full writing-sample corpus (that's "
            "voice-anchors.md, drawn from\n# whatever you dropped into "
            "source_documents/ during bootstrap). Optional\n# -- leave blank and "
            f"this is skipped entirely.\n{new_line}\n"
        )

    with atomic_write(PROFILE_YML_PATH, encoding="utf-8") as f:
        f.write(content)


# --- Personal narrative fields (Settings & Upkeep -> Personal Narrative
# & Story) -----------------------------------------------------------
# These are the profile.yml fields that are deliberately never
# auto-generated -- narrative.headline/exit_story, superpowers,
# background_context, deal_breakers, industries_of_genuine_fit all read
# "often come from your own self-reflection or feedback you've
# received" in the bootstrap scaffold itself. But they aren't just
# resume flavor text: background_context/narrative/superpowers/
# deal_breakers are part of AUDIT_PROFILE_KEEP (orchestrator.py), so a
# real per-JD evaluation call sees them too. Get/set pairs here mirror
# get_/set_voice_calibration_example()'s targeted-substitution approach
# (never a yaml.safe_load/dump round-trip, which would silently strip
# every one of profile.yml's hand-written comments).


def _get_profile_scalar(field: str, parent: str | None = None) -> str:
    if not os.path.exists(PROFILE_YML_PATH):
        return ""
    with open(PROFILE_YML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    node = data
    if parent:
        node = data.get(parent)
        if not isinstance(node, dict):
            node = {}
    return node.get(field) or ""


def _set_profile_scalar(field: str, value: str, indent: str = "") -> None:
    """Replaces a scalar field's `field: "..."` YAML line in place. A
    field with no existing line to replace (an old profile.yml predating
    it) gets one appended instead -- `indent` reproduces its nesting
    depth for that case; an existing line's own indent is always reused
    when one is found, regardless of what's passed."""
    if not os.path.exists(PROFILE_YML_PATH):
        raise FileNotFoundError(f"No profile.yml at {PROFILE_YML_PATH} yet.")
    with open(PROFILE_YML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    escaped = json.dumps(value or "")
    pattern = re.compile(rf'^([ \t]*){re.escape(field)}:\s*".*"\s*$', re.MULTILINE)
    match = pattern.search(content)
    if match:
        content = pattern.sub(f"{match.group(1)}{field}: {escaped}", content, count=1)
    else:
        content = content.rstrip("\n") + f"\n{indent}{field}: {escaped}\n"

    with atomic_write(PROFILE_YML_PATH, encoding="utf-8") as f:
        f.write(content)


def _get_profile_list(field: str) -> list:
    if not os.path.exists(PROFILE_YML_PATH):
        return []
    with open(PROFILE_YML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get(field) or []
    return [i.strip() for i in items if isinstance(i, str) and i.strip()]


def _set_profile_list(field: str, items: list) -> None:
    """Replaces a top-level YAML list field via block substitution,
    same reasoning as _set_profile_scalar. An empty list is still
    written as one blank entry (`- ""`), matching the bootstrap
    scaffold's own convention for an unfilled list field."""
    if not os.path.exists(PROFILE_YML_PATH):
        raise FileNotFoundError(f"No profile.yml at {PROFILE_YML_PATH} yet.")
    with open(PROFILE_YML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    cleaned = [i.strip() for i in items if i and i.strip()] or [""]
    rendered = "\n".join(f"  - {json.dumps(i)}" for i in cleaned)
    new_block = f"{field}:\n{rendered}\n"

    pattern = re.compile(
        rf"^{re.escape(field)}:[ \t]*\n(?:(?:[ \t]+[^\n]*|[ \t]*)\n)*", re.MULTILINE
    )
    if pattern.search(content):
        content = pattern.sub(new_block, content, count=1)
    else:
        content = content.rstrip("\n") + f"\n\n{new_block}"

    with atomic_write(PROFILE_YML_PATH, encoding="utf-8") as f:
        f.write(content)


def get_narrative_headline() -> str:
    return _get_profile_scalar("headline", parent="narrative")


def set_narrative_headline(value: str) -> None:
    _set_profile_scalar("headline", value, indent="  ")


def get_narrative_exit_story() -> str:
    return _get_profile_scalar("exit_story", parent="narrative")


def set_narrative_exit_story(value: str) -> None:
    _set_profile_scalar("exit_story", value, indent="  ")


def get_background_context() -> str:
    return _get_profile_scalar("background_context")


def set_background_context(value: str) -> None:
    _set_profile_scalar("background_context", value)


def get_superpowers() -> list:
    return _get_profile_list("superpowers")


def set_superpowers(items: list) -> None:
    _set_profile_list("superpowers", items)


def get_deal_breakers() -> list:
    return _get_profile_list("deal_breakers")


def set_deal_breakers(items: list) -> None:
    _set_profile_list("deal_breakers", items)


def get_industries_of_genuine_fit() -> list:
    return _get_profile_list("industries_of_genuine_fit")


def set_industries_of_genuine_fit(items: list) -> None:
    _set_profile_list("industries_of_genuine_fit", items)


# Every human-only field surfaced by the banner reminder and editable
# from the Personal Narrative & Story settings menu -- one list so the
# two stay in sync by construction rather than by remembering to update
# both places whenever a field is added.
PERSONAL_NARRATIVE_FIELDS: list[
    tuple[str, Callable[[], Any], Callable[[Any], None], str]
] = [
    ("Headline", get_narrative_headline, set_narrative_headline, "scalar"),
    ("Exit story", get_narrative_exit_story, set_narrative_exit_story, "scalar"),
    ("Background context", get_background_context, set_background_context, "scalar"),
    ("Superpowers", get_superpowers, set_superpowers, "list"),
    ("Deal breakers", get_deal_breakers, set_deal_breakers, "list"),
    (
        "Industries of genuine fit",
        get_industries_of_genuine_fit,
        set_industries_of_genuine_fit,
        "list",
    ),
]


def blank_personal_narrative_fields() -> list:
    """Names of PERSONAL_NARRATIVE_FIELDS entries that are still empty --
    used by the main banner to remind a returning user these are worth
    filling in, without ever fabricating content on their behalf."""
    return [label for label, getter, _, _ in PERSONAL_NARRATIVE_FIELDS if not getter()]


def _yaml_string_list(items: list, indent: str = "    ") -> str:
    if not items:
        return f"{indent}[]"
    return "\n".join(f'{indent}- "{item}"' for item in items)


def _yaml_linkedin_queries(items: list, indent: str = "  ") -> str:
    """Renders linkedin_search_queries: entries -- each is either a plain
    string (the common case) or a dict with query/workplace_mode/location
    overrides (scan_linkedin._build_queries() already parses both shapes;
    see that module's docstring)."""
    if not items:
        return f"{indent}[]"
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f'{indent}- query: "{item["query"]}"')
            modes = item.get("workplace_mode")
            if modes:
                lines.append(f"{indent}  workplace_mode:")
                lines.extend(f'{indent}    - "{mode}"' for mode in modes)
            location = item.get("location")
            if location:
                lines.append(f'{indent}  location: "{location}"')
        else:
            lines.append(f'{indent}- "{item}"')
    return "\n".join(lines)


def _yaml_tags(taxonomy) -> str:
    if not taxonomy.tags:
        return (
            "  # Generated from your target roles + real achievement text during\n"
            "  # bootstrap. Each bullet in your bullet bank gets auto-tagged with\n"
            "  # one of these (tag_bullet_bank.py), and the audit/rewrite steps use\n"
            "  # persona_description + keywords to pull in the right context per\n"
            '  # bullet. Add/edit any time -- an empty keywords: list means "matches\n'
            '  # everything" (the catch-all tag), not "matches nothing."\n'
            "  []"
        )
    lines = []
    for tag in taxonomy.tags:
        lines.append(f'  - name: "{tag.name}"')
        lines.append(f'    persona_description: "{tag.persona_description}"')
        keywords_json = ", ".join(json.dumps(k) for k in tag.keywords)
        lines.append(f"    keywords: [{keywords_json}]")
    return "\n".join(lines)


def _yaml_key_recommendations(quotes: list) -> str:
    if not quotes:
        return (
            "  # If you upload recommendation letters and re-run bootstrap, we'll\n"
            "  # pull real quotes + attribution from them here automatically.\n"
            "  []"
        )
    lines = []
    for q in quotes:
        lines.append(f'  - name: "{q.name or ""}"')
        lines.append(f'    title: "{q.title or ""}"')
        lines.append(f'    quote: "{q.quote or ""}"')
    return "\n".join(lines)


_PROFILE_YML_TEMPLATE = """# Career-Ops Profile Configuration
# Generated by bootstrap -- review and expand the sections below any time.

candidate:
  full_name: "{full_name}"
  email: "{email}"
  phone: "{phone}"
  location: "{location}"
  linkedin: "{linkedin_url}"
  portfolio_url: "{portfolio_url}"
  extra_link: "{extra_link}"

# Optional, deterministic answers for sensitive application questions. Leave
# these blank to require the candidate to answer work-authorization questions
# manually rather than guessing.
application_answers:
  work_authorization: null
  requires_sponsorship: null

target_roles:
  primary:
{primary_roles_yaml}
  secondary:
{secondary_roles_yaml}

# Hand-tuned boolean search strings for scan_linkedin.py's saved searches.
# Leave empty (the default) to fall back to one query per target_roles.primary
# entry instead -- fine to start with, but a real boolean query (e.g.
# "Email OR Campaign") usually finds better matches than a bare job title.
linkedin_search_queries:
{linkedin_search_queries_yaml}

tags:
{tags_yaml}

archetypes:
  # For each role you're targeting, a short note on what specifically
  # you'd bring to it. Example:
  #   - name: "Customer Marketing Manager"
  #     level: "Mid-Senior"
  #     fit: "primary"
  #     notes: "Customer engagement, onboarding, retention campaigns..."
  archetypes: []

narrative:
  # A 1-2 sentence headline summarizing your professional identity.
  # Example: "Marketing leader who writes campaigns that perform..."
  headline: ""

  # Optional: why you're job-searching now / your story if there's a
  # gap or transition. Leave blank if not applicable.
  exit_story: ""

superpowers:
  # 3-5 things you're uniquely good at, each with a real example. These
  # often come from your own self-reflection or feedback you've received.
  - ""

# A paragraph on how your background came together -- the different
# tracks/experiences that combine into what you do now.
background_context: ""

industries_of_genuine_fit:
  # Industries or company types where you'd genuinely want to work.
  - ""

companies_previously_applied: []
  # Track applications here as you go, to avoid duplicate applying.

deal_breakers:
  # Things that would make a role a bad fit, with the specific reason.
  # Example: "On-site or hybrid required -- remote-only availability"
{deal_breakers_yaml}

proof_points: []
  # Your single best, most specific hero metric per major achievement.
  # Example:
  #   - name: "PTA Council Campaign"
  #     context: "Hardest-to-reach audience in the portfolio"
  #     hero_metric: "74% open rate / 22% reply rate / 0 opt-outs"

key_recommendations:
{key_recommendations_yaml}

management_evidence: []
  # Direct quotes from real coworkers/managers confirming leadership or
  # de facto management responsibility, if you have any on record.

compensation:
  target_range: ""
  currency: "USD"
  minimum: ""
  location_flexibility: "{location_flexibility}"
  notes: ""

location:
  country: "United States"
  city: "{location}"
  timezone: ""
  visa_status: ""
  remote_required: {remote_required}
  notes: ""

cv:
  output_format: "html"

# A short, real quote in your own voice -- used only to calibrate tone
# during resume critique (evaluate_recruiter.md's role-rules block), not
# your full writing-sample corpus (that's voice-anchors.md, drawn from
# whatever you dropped into source_documents/ during bootstrap). Optional
# -- leave blank and this is skipped entirely.
voice_calibration_example: "{voice_calibration_example}"
"""


def write_profile_yml(
    identity: dict,
    recommendations: list,
    taxonomy,
    linkedin_search_queries: list | None = None,
    voice_calibration_example: str = "",
    deal_breakers: list | None = None,
) -> bool:
    """Writes profile.yml. Unlike write_cv_md()/write_background_guide()/
    write_voice_anchors(), this has no accept/regenerate/skip preview loop
    -- it's a deterministic template fill, not an LLM draft. That's fine
    on a first-time cold start (nothing to lose), but re-running this on
    an existing, possibly hand-edited profile.yml (the "Update My
    Knowledge" flow) needs a real confirm gate first, or a manual tweak
    made since onboarding gets silently clobbered. Returns False (does
    NOT write) if an existing file's overwrite is declined; True
    otherwise."""
    if os.path.exists(PROFILE_YML_PATH):
        overwrite = cli_art.confirm(
            f"{PROFILE_YML_PATH} already exists -- overwrite it with a freshly regenerated version? "
            "(Any manual edits you've made since onboarding will be lost.)",
            default=False,
        )
        if not overwrite:
            cli_art.cli_info("Keeping the existing profile.yml unchanged.")
            return False

    content = _PROFILE_YML_TEMPLATE.format(
        full_name=identity["full_name"],
        email=identity["email"],
        phone=identity["phone"],
        location=identity["location"],
        linkedin_url=identity["linkedin_url"],
        portfolio_url=identity["portfolio_url"],
        extra_link=identity["extra_link"],
        primary_roles_yaml=_yaml_string_list(identity["primary_roles"]),
        secondary_roles_yaml=_yaml_string_list(identity["secondary_roles"]),
        linkedin_search_queries_yaml=_yaml_linkedin_queries(
            linkedin_search_queries or [], indent="  "
        ),
        tags_yaml=_yaml_tags(taxonomy),
        key_recommendations_yaml=_yaml_key_recommendations(recommendations),
        location_flexibility="Remote only" if identity.get("remote_preference") else "",
        remote_required=str(bool(identity.get("remote_preference"))).lower(),
        voice_calibration_example=voice_calibration_example or "",
        deal_breakers_yaml=_yaml_string_list(deal_breakers or [""]),
    )
    os.makedirs(os.path.dirname(PROFILE_YML_PATH), exist_ok=True)
    with atomic_write(PROFILE_YML_PATH, encoding="utf-8") as f:
        f.write(content)
    return True


_PORTALS_YML_TEMPLATE = """# Portal Scanner Configuration
# Generated by bootstrap -- refine title_filter/block/seniority_boost over
# time as you see real postings come through.

location_filter:
  # Words in a job posting's location field that mean "yes, apply."
  always_allow:
{always_allow_yaml}

block:
  # Words that mean "no, this isn't remote" -- e.g. on-site/hybrid signals.
  # Starts with common defaults; add more as you see them in real postings.
  - "Onsite"
  - "On-Site"
  - "Hybrid"
  - "In-office"

title_filter:
  positive:
    # Job titles worth evaluating. Seeded from your target roles --
    # add near-miss titles you keep seeing as you scan real postings.
{title_filter_yaml}
  negative: []
    # Titles that mean "skip this one," even if it matched something above.

seniority_boost: []
  # Keywords that bump a posting's priority (e.g. "Senior", "Lead").
  # Leave as-is until you have a preference.
"""


def write_portals_yml(identity: dict) -> None:
    always_allow = (
        ["Remote", "Work from home", "Fully Remote"]
        if identity.get("remote_preference")
        else ["Remote", "Hybrid"]
    )
    title_seed = identity["primary_roles"] + identity["secondary_roles"]
    content = _PORTALS_YML_TEMPLATE.format(
        always_allow_yaml=_yaml_string_list(always_allow),
        title_filter_yaml=_yaml_string_list(title_seed),
    )
    os.makedirs(os.path.dirname(PORTALS_YML_PATH), exist_ok=True)
    with atomic_write(PORTALS_YML_PATH, encoding="utf-8") as f:
        f.write(content)


# Same nested-mapping block convention content_settings.py's own
# _SCORING_WEIGHTS_RE/_COMPENSATION_RE use: consumes every further-indented
# line under the key, stopping at the next top-level (column-0) key.
_TITLE_FILTER_RE = re.compile(
    r"^title_filter:[ \t]*\n(?:[ \t]+[^\n]*\n|[ \t]*\n(?=[ \t]+\S))*",
    re.MULTILINE,
)


def _render_title_filter_block(positive: list) -> str:
    return (
        "title_filter:\n  positive:\n"
        + _yaml_string_list(positive)
        + "\n  negative: []\n"
    )


def seed_scan_filters_from_target_roles(identity: dict) -> bool:
    """Seeds this profile's board_scanner/scan_filters.yml title_filter.positive
    from the same target-roles identity data profile.yml's target_roles.primary
    is built from (write_profile_yml() uses this same identity dict). A fresh
    profile's scaffold (bootstrap_bullet_bank._SCAN_FILTERS_SCAFFOLD) ships
    with positive: [], which is permissive by design -- meaning a stranger's
    first scan pulls every posting from every configured source with no
    title gate at all, then runs a real-browser liveness check on all of
    them (B34). Only touches the file while it's still at that untouched
    default (title_filter.positive and .negative both empty) -- never
    overwrites a profile that already has its own curated filters. Distinct
    from write_portals_yml()/knowledge_base/portals.yml, which is a
    separate, deliberately-kept artifact stitched into the tailoring
    prompt via orchestrator.KB_ALLOWLIST, not the file scan_boards.py
    actually reads for gating (profile_paths.board_scanner_dir()/
    scan_filters.yml). Returns whether it actually wrote anything, mostly
    for tests -- callers don't need to check it.

    Edits ONLY the title_filter: block in place, the same
    replace-in-place-not-whole-file convention content_settings.py/
    location_settings.py already use for this exact file -- this used to
    rebuild the entire file from a title_filter/location_filter-only
    template via a full atomic_write, silently discarding any OTHER
    top-level key already present (location:, scoring_weights:,
    languages:, any comments) the moment this ran. On a truly fresh
    profile that's a no-op (nothing else is there yet), but on "Update My
    Knowledge" for an established profile whose target roles were left
    empty (title_filter never got seeded, so this keeps firing on every
    later run), it would have silently erased Settings & Upkeep
    configuration -- commute radius, pay/travel/scoring settings -- set up
    in between runs."""
    path = os.path.join(profile_paths.board_scanner_dir(), "scan_filters.yml")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()
        existing = yaml.safe_load(original) or {}
    title_filter = existing.get("title_filter") or {}
    if title_filter.get("positive") or title_filter.get("negative"):
        return False

    title_seed = identity["primary_roles"] + identity["secondary_roles"]
    block = _render_title_filter_block(title_seed)
    if _TITLE_FILTER_RE.search(original):
        updated = _TITLE_FILTER_RE.sub(block, original, count=1)
    else:
        updated = original.rstrip("\n") + "\n" + block
    with atomic_write(path, encoding="utf-8") as f:
        f.write(updated)
    return True


def _seed_only_if_absent(path: str) -> bool:
    """True when `path` should be written with its blank starter content.

    Everything below the metrics/tools/projects block seeds a NEW
    profile: an empty facts ledger, an empty evidence graph, and
    header-only verified-claims / evidence-guide / screenshot-metrics
    CSVs. Those writes were unconditional, so calling this function on an
    established profile blanked real work -- a 97 KB verified-claims.csv
    and a curated facts ledger among them -- with no prompt and no error.

    A seed is starter content by definition, so it is only correct to
    write when there is nothing there yet.
    """
    return not os.path.exists(path) or os.path.getsize(path) == 0


def write_verified_ledger(dry_run: bool = False) -> None:
    achievements_text = _achievements_summary_text_by_employer()
    extraction = (
        bootstrap_extractors.extract_ledger_entries_chunked(
            achievements_text, dry_run=dry_run
        )
        if achievements_text
        else bootstrap_extractors.LedgerExtraction()
    )

    # Never overwrite a populated ledger with an empty extraction.
    #
    # Every write below is unconditional, so an extraction that returned
    # nothing -- no bullet source on disk, an API failure, a dry run --
    # used to replace curated verified_metrics/tools/projects.json with
    # total_entries: 0. That is pure data loss with no error and no
    # prompt, and it is silent precisely when something else already went
    # wrong. Bailing out leaves the existing files untouched.
    if not (extraction.metrics or extraction.tools or extraction.projects):
        if os.path.exists(VERIFIED_METRICS_PATH) or os.path.exists(VERIFIED_TOOLS_PATH):
            cli_art.cli_warning(
                "Skipped rewriting the verified ledger: extraction returned no "
                "entries, and overwriting would erase the existing "
                "metrics/tools/projects files."
            )
            return

    os.makedirs(os.path.dirname(VERIFIED_METRICS_PATH), exist_ok=True)

    metrics_json = {
        "_meta": {
            "source": "bootstrap ingestion",
            "total_entries": len(extraction.metrics),
        },
        "metrics": [
            {
                "id": f"metric_{i + 1:03d}",
                "label": m.label,
                "value": m.value,
                "employer": m.employer,
            }
            for i, m in enumerate(extraction.metrics)
        ],
    }
    with atomic_write(VERIFIED_METRICS_PATH, encoding="utf-8") as f:
        json.dump(metrics_json, f, indent=2)

    tools_json = {
        "_meta": {
            "source": "bootstrap ingestion",
            "total_entries": len(extraction.tools),
        },
        "tools": [
            {"id": f"tool_{i + 1:03d}", "name": t.name, "employer": t.employer}
            for i, t in enumerate(extraction.tools)
        ],
    }
    with atomic_write(VERIFIED_TOOLS_PATH, encoding="utf-8") as f:
        json.dump(tools_json, f, indent=2)

    projects_json = {
        "_meta": {
            "source": "bootstrap ingestion",
            "total_entries": len(extraction.projects),
        },
        "projects": [
            {"id": f"proj_{i + 1:03d}", "name": p.name, "employer": p.employer}
            for i, p in enumerate(extraction.projects)
        ],
    }
    with atomic_write(VERIFIED_PROJECTS_PATH, encoding="utf-8") as f:
        json.dump(projects_json, f, indent=2)

    empty_facts = {
        "_meta": {
            "source": "",
            "total_entries": 0,
            "note": "Add facts here as you cross-reference multiple sources over time.",
        },
        "facts": [],
    }
    if _seed_only_if_absent(VERIFIED_FACTS_PATH):
        with atomic_write(VERIFIED_FACTS_PATH, encoding="utf-8") as f:
            json.dump(empty_facts, f, indent=2)

    empty_graph = {
        "_meta": {
            "source": "",
            "description": "Relationship graph connecting metrics, facts, projects, tools. Build this up as your evidence grows.",
            "node_types": ["metric", "fact", "project", "tool"],
        },
        "nodes": [],
        "edges": [],
    }
    if _seed_only_if_absent(EVIDENCE_GRAPH_PATH):
        with atomic_write(EVIDENCE_GRAPH_PATH, encoding="utf-8") as f:
            json.dump(empty_graph, f, indent=2)

    if _seed_only_if_absent(VERIFIED_CLAIMS_PATH):
        with atomic_write(VERIFIED_CLAIMS_PATH, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Claim / Finding",
                    "Verification Status",
                    "Source File",
                    "Evidence / Detail",
                    "Metric(s)",
                    "Confidence",
                    "Use in Resume?",
                    "Use in Portfolio?",
                    "Next Follow-Up",
                ]
            )

    if _seed_only_if_absent(EVIDENCE_GUIDE_PATH):
        with atomic_write(EVIDENCE_GUIDE_PATH, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Evidence Cluster",
                    "Finding",
                    "Source File(s)",
                    "Best Detail / Quote",
                    "Best Metric",
                    "What This Proves About You",
                    "Where to Use It",
                    "Confidence",
                    "Source URL / Notes",
                ]
            )

    if _seed_only_if_absent(SCREENSHOT_METRICS_PATH):
        with atomic_write(SCREENSHOT_METRICS_PATH, newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Source Batch",
                    "Campaign / Screenshot Title",
                    "Screenshot File(s)",
                    "Contacted",
                    "Reached",
                    "Reached %",
                    "Opened",
                    "Open %",
                    "Replied",
                    "Reply %",
                    "Clicked %",
                    "Bounced",
                    "Bounce %",
                    "Opted Out",
                    "Opt-Out %",
                    "Best Detail / Notes",
                    "Confidence",
                    "Reviewed",
                ]
            )

    empty_recruiter_patterns = {
        "_meta": {
            "note": "Builds up over real recruiter feedback and application outcomes."
        },
        "patterns": [],
    }
    if _seed_only_if_absent(RECRUITER_PATTERNS_PATH):
        with atomic_write(RECRUITER_PATTERNS_PATH, encoding="utf-8") as f:
            json.dump(empty_recruiter_patterns, f, indent=2)


def stage_candidate_facts(dry_run: bool = False) -> int:
    """Runs the D10 fact-staging extraction (bootstrap_extractors.
    extract_and_stage_facts_chunked) over the same attributed achievements
    text write_verified_ledger() already builds, and returns how many new
    facts landed in staged_facts.json.

    This step existed in bootstrap_extractors.py (extract_and_stage_facts)
    but was never actually called from anywhere in the bootstrap flow --
    every new profile's "Review Staged Career Facts (D10 Gate)" screen in
    Settings & Upkeep > Skills showed 0 entries regardless of how much
    source material was ingested, because nothing had ever populated
    staged_facts.json in the first place. Called from run_profile_setup()
    right after write_verified_ledger(), which already guarantees
    verified_facts.json exists (empty) by this point -- staging never
    writes there directly; a human still has to promote each fact via
    facts_manager.review_staged_facts_interactive()."""
    if dry_run:
        cli_art.cli_info("[DRY RUN] would extract and stage candidate career facts.")
        return 0
    achievements_text = _achievements_summary_text_by_employer()
    if not achievements_text:
        return 0
    return bootstrap_extractors.extract_and_stage_facts_chunked(achievements_text)


def _build_cv_draft_rows() -> list:
    timeline = _load_timeline()
    if not os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH):
        return []
    with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_company: dict[str, list[str]] = {}
    for row in rows:
        by_company.setdefault(row["Role / Company"], []).append(row["Bullet Point"])

    ordered = sorted(timeline, key=lambda e: e.get("end_date") or "", reverse=True)
    result = []
    seen_companies = set()
    bullets_assigned = set()
    for entry in ordered:
        company = entry["company"]
        seen_companies.add(company)
        # A company can legitimately have more than one timeline entry --
        # two separate stints at the same employer (e.g. Data Scientist
        # 2018-2019, then Lead Data Scientist 2021-2022). Bullets are only
        # tagged with a company, not which stint they belong to, so there
        # is no reliable way to split the pool between entries -- but
        # attaching the WHOLE pool to every entry for that company used to
        # render the same achievements twice on cv.md, once per stint.
        # Attach the full pool to only the most recent entry (`ordered` is
        # sorted by end_date descending); an earlier stint's header still
        # appears, just without a duplicate copy of every bullet under it.
        if company in bullets_assigned:
            bullets = []
        else:
            bullets = by_company.get(company, [])
            bullets_assigned.add(company)
        result.append(
            {
                "company": company,
                "title": entry.get("title") or "",
                "start_date": entry.get("start_date") or "",
                "end_date": entry.get("end_date") or "",
                "bullets": bullets,
            }
        )
    for company, bullets in by_company.items():
        if company not in seen_companies and company != "Misc. / Unassigned":
            result.append(
                {
                    "company": company,
                    "title": "",
                    "start_date": "",
                    "end_date": "",
                    "bullets": bullets,
                }
            )
    return result


def _load_cv_draft_checkpoint() -> dict:
    if not os.path.exists(CV_DRAFT_CHECKPOINT_PATH):
        return {}
    with open(CV_DRAFT_CHECKPOINT_PATH, encoding="utf-8") as f:
        return cast("dict", json.load(f))


def _save_cv_draft_checkpoint(state: dict) -> None:
    os.makedirs(os.path.dirname(CV_DRAFT_CHECKPOINT_PATH), exist_ok=True)
    with atomic_write(CV_DRAFT_CHECKPOINT_PATH, encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _clear_cv_draft_checkpoint() -> None:
    if os.path.exists(CV_DRAFT_CHECKPOINT_PATH):
        os.remove(CV_DRAFT_CHECKPOINT_PATH)


def _cv_draft_checkpoint_key(role_company: str, bullet: str) -> str:
    return f"{role_company}::{bullet}"


def _polish_bullet(
    bullet: str,
    role_company: str,
    kb,
    rewrite_system: str,
    rewrite_system_gemma: str,
    score_system: str,
    dry_run: bool = False,
    checkpoint: dict | None = None,
) -> dict:
    """Returns {"final_bullet": ..., "rewrite_status": "KEEP"|"MANUAL"}.
    Reuses a prior run's result from checkpoint (keyed by company+bullet
    text) instead of re-calling the API when one's already there -- makes
    write_cv_md() resumable: an interrupted run just picks up where it
    left off on the next call, rather than losing every polish already
    paid for."""
    # Lazy pandas -- Lite Mode omits it; see requirements-lite.txt (F20).
    import pandas as pd

    checkpoint = checkpoint if checkpoint is not None else {}
    key = _cv_draft_checkpoint_key(role_company, bullet)
    if key in checkpoint:
        return cast("dict", checkpoint[key])

    row = pd.Series(
        {
            "Bullet Point": bullet,
            "Tags": "",
            "Role / Company": role_company,
            "weaknesses": "",
        }
    )
    result = process_bullet(
        row, kb, rewrite_system, rewrite_system_gemma, score_system, dry_run
    )
    polished = {
        "final_bullet": result.get("final_bullet", bullet),
        "rewrite_status": result.get("rewrite_status", "MANUAL"),
    }
    checkpoint[key] = polished
    if dry_run:
        # A dry run makes zero real API calls and must make zero real
        # filesystem changes either -- writing a checkpoint entry (even a
        # placeholder "[DRY RUN] ..." one) would violate that, and could
        # poison a *real* subsequent non-dry-run call into treating a
        # never-actually-polished bullet as already done.
        return polished
    _save_cv_draft_checkpoint(checkpoint)
    return polished


def _assemble_cv_draft(
    identity: dict,
    rows: list,
    kb,
    rewrite_system: str,
    rewrite_system_gemma: str,
    score_system: str,
    dry_run: bool,
) -> str:
    total = sum(len(role["bullets"]) for role in rows)
    cli_art.cli_info(f"Polishing {total} bullet(s) for your cv.md draft...")

    checkpoint = _load_cv_draft_checkpoint()
    already_done = sum(
        1
        for role in rows
        for bullet in role["bullets"]
        if _cv_draft_checkpoint_key(role["company"], bullet) in checkpoint
    )
    if already_done:
        cli_art.console.print(
            f"   {theme.colorize_icon('resume')} Resuming: {already_done}/{total} already polished in a prior run.",
            soft_wrap=True,
        )

    lines = [f"# {identity['full_name']}", ""]
    contact_parts = [
        p
        for p in (
            identity.get("email"),
            identity.get("phone"),
            identity.get("location"),
            identity.get("linkedin_url"),
        )
        if p
    ]
    if contact_parts:
        lines.append(" | ".join(contact_parts))
        lines.append("")

    i = 0
    for role in rows:
        header = (
            f"## {role['title']} — {role['company']}"
            if role["title"]
            else f"## {role['company']}"
        )
        date_range = (
            f" ({role['start_date']} - {role['end_date']})"
            if role["start_date"]
            else ""
        )
        lines.append(header + date_range)
        for bullet in role["bullets"]:
            i += 1
            cli_art.console.rule(style="dim")
            cli_art.cli_info(f"[{i}/{total}] {bullet[:60]}...")
            cli_art.detail(f"Company: {role['company']}", level=cli_art.NORMAL)
            polished = _polish_bullet(
                bullet,
                role["company"],
                kb,
                rewrite_system,
                rewrite_system_gemma,
                score_system,
                dry_run,
                checkpoint,
            )
            status_icon = (
                theme.colorize_icon("success")
                if polished["rewrite_status"] == "KEEP"
                else theme.colorize_icon("warning")
            )
            if polished["rewrite_status"] == "KEEP":
                cli_art.cli_success(polished["rewrite_status"])
            else:
                cli_art.cli_warning(polished["rewrite_status"])
            cli_art.console.print()
            lines.append(f"- {polished['final_bullet']}")
        lines.append("")

    return "\n".join(lines)


def write_cv_md(identity: dict, dry_run: bool = False) -> None:
    rows = _build_cv_draft_rows()
    rules = RulesBundle(RULES_DIR)
    kb = KnowledgeBase()
    rewrite_system, rewrite_system_gemma, score_system = build_system_prompts(rules, kb)

    if dry_run:
        cli_art.cli_info(
            "[DRY RUN] would draft cv.md and preview it for accept/regenerate/skip."
        )
        content = _assemble_cv_draft(
            identity,
            rows,
            kb,
            rewrite_system,
            rewrite_system_gemma,
            score_system,
            dry_run,
        )
        os.makedirs(os.path.dirname(CV_MD_PATH), exist_ok=True)
        with atomic_write(CV_MD_PATH, encoding="utf-8") as f:
            f.write(content)
        return

    content = _assemble_cv_draft(
        identity, rows, kb, rewrite_system, rewrite_system_gemma, score_system, dry_run
    )
    choice = "skip"
    while True:
        cli_art.console.print("\n--- Draft cv.md ---\n")
        cli_art.console.print(content)
        cli_art.console.print("\n--- End draft ---\n")
        choice = cli_art.select(
            "What would you like to do with this draft?",
            choices=[
                questionary.Choice(title="Accept it as-is", value="accept"),
                questionary.Choice(title="Regenerate", value="regenerate"),
                questionary.Choice(
                    title="Skip -- I'll write my own later", value="skip"
                ),
            ],
        )
        if choice == "regenerate":
            # A real regenerate request -- start every bullet over rather
            # than replaying cached results from the draft just rejected.
            _clear_cv_draft_checkpoint()
            content = _assemble_cv_draft(
                identity,
                rows,
                kb,
                rewrite_system,
                rewrite_system_gemma,
                score_system,
                dry_run,
            )
            continue
        break

    os.makedirs(os.path.dirname(CV_MD_PATH), exist_ok=True)
    with atomic_write(CV_MD_PATH, encoding="utf-8") as f:
        f.write(content if choice == "accept" else "")


def _checkpoint_entry_text(result: dict) -> str:
    """Renders one already-ingested document's extracted content as plain
    text, drawn from the structured data Phase 0 (classify_document_type /
    extract_resume_timeline_and_achievements / extract_achievements) already
    produced for it -- never by re-reading the source file. A PDF or image
    document has no local text to re-read (_resolve_text_or_upload returns
    text=None for those, upload_path instead), so gathering source texts by
    re-resolving each path silently dropped every PDF/image-derived document
    from the background guide and voice anchors: an all-PDF source set (a
    resume plus a few scanned notes, a common real case) produced an empty
    source_texts list and "no usable source text found" even though
    extraction itself had succeeded and populated the checkpoint. Reusing the
    checkpoint sidesteps that entirely, since it's already extracted plain
    text regardless of the original file format."""
    doc_type = result.get("doc_type")
    if doc_type in ("resume", "linkedin_export"):
        lines = []
        for entry in result.get("work_experience", []):
            header = (
                f"{entry.get('title') or ''} at {entry.get('company') or ''} "
                f"({entry.get('start_date') or '?'} - {entry.get('end_date') or '?'})"
            ).strip()
            lines.append(header)
            lines.extend(f"- {b}" for b in entry.get("achievements", []))
        return "\n".join(lines)
    return "\n".join(a.get("raw_text", "") for a in result.get("achievements", []))


def _gather_background_source_texts(checkpoint: dict) -> list:
    texts = []
    for _filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done":
            continue
        if result.get("doc_type") not in (
            "resume",
            "linkedin_export",
            "recommendation_letter",
            "achievement_notes",
        ):
            continue
        text = _checkpoint_entry_text(result)
        if text:
            texts.append(text)
    return texts


def write_background_guide(checkpoint: dict, dry_run: bool = False) -> None:
    source_texts = _gather_background_source_texts(checkpoint)

    if dry_run:
        cli_art.cli_info(
            "[DRY RUN] would draft user-background-guide.md and preview it for accept/regenerate/skip."
        )
        draft = bootstrap_extractors.draft_background_guide(
            source_texts, dry_run=dry_run
        )
        os.makedirs(os.path.dirname(BACKGROUND_GUIDE_PATH), exist_ok=True)
        with atomic_write(BACKGROUND_GUIDE_PATH, encoding="utf-8") as f:
            f.write(draft)
        return

    draft = (
        bootstrap_extractors.draft_background_guide(source_texts)
        if source_texts
        else ""
    )
    choice = "skip"
    while True:
        cli_art.console.print("\n--- Draft background guide ---\n")
        cli_art.console.print(
            draft or "(nothing drafted -- no usable source text found)"
        )
        cli_art.console.print("\n--- End draft ---\n")
        choice = cli_art.select(
            "What would you like to do with this draft?",
            choices=[
                questionary.Choice(title="Accept it as-is", value="accept"),
                questionary.Choice(title="Regenerate", value="regenerate"),
                questionary.Choice(
                    title="Skip -- I'll write my own later", value="skip"
                ),
            ],
        )
        if choice == "regenerate":
            draft = bootstrap_extractors.draft_background_guide(source_texts)
            continue
        break

    os.makedirs(os.path.dirname(BACKGROUND_GUIDE_PATH), exist_ok=True)
    with atomic_write(BACKGROUND_GUIDE_PATH, encoding="utf-8") as f:
        f.write(draft if choice == "accept" else "")


def _gather_voice_anchor_source_texts(checkpoint: dict) -> list:
    """Same doc-type set _gather_background_source_texts() uses, plus
    "other" -- a genuine writing sample (cover letter, essay, forum post,
    etc.) has no dedicated doc_type in DocumentClassification and most
    often lands in "other", which the background-guide gatherer
    deliberately excludes since it's not reliably career-narrative content
    there -- but it's exactly the kind of first-person writing voice
    anchors need."""
    texts = []
    for _filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done":
            continue
        if result.get("doc_type") not in (
            "resume",
            "linkedin_export",
            "recommendation_letter",
            "achievement_notes",
            "other",
        ):
            continue
        text = _checkpoint_entry_text(result)
        if text:
            texts.append(text)
    return texts


def write_voice_anchors(checkpoint: dict, dry_run: bool = False) -> None:
    """Optional -- unlike profile.yml/cv.md/background guide, voice-anchors.md
    has no fallback derived from other data, and every consumer
    (orchestrator.py, rewrite_bullets.py) already checks os.path.exists()
    before reading it, so skipping this entirely (no writing-sample
    documents provided, or explicitly skipped) is a fully supported
    "no signal yet" state, not a gap that blocks anything else."""
    source_texts = _gather_voice_anchor_source_texts(checkpoint)

    if dry_run:
        cli_art.cli_info(
            "[DRY RUN] would draft voice-anchors.md and preview it for accept/regenerate/skip."
        )
        draft = bootstrap_extractors.draft_voice_anchors(source_texts, dry_run=dry_run)
        os.makedirs(os.path.dirname(VOICE_ANCHORS_PATH), exist_ok=True)
        with atomic_write(VOICE_ANCHORS_PATH, encoding="utf-8") as f:
            f.write(draft)
        return

    draft = (
        bootstrap_extractors.draft_voice_anchors(source_texts) if source_texts else ""
    )
    choice = "skip"
    while True:
        cli_art.console.print("\n--- Draft voice anchors ---\n")
        cli_art.console.print(
            draft
            or "(nothing drafted -- no usable writing-sample text found; this is optional, skip freely)"
        )
        cli_art.console.print("\n--- End draft ---\n")
        choice = cli_art.select(
            "What would you like to do with this draft?",
            choices=[
                questionary.Choice(title="Accept it as-is", value="accept"),
                questionary.Choice(title="Regenerate", value="regenerate"),
                questionary.Choice(
                    title="Skip -- optional, I'll add my own later", value="skip"
                ),
            ],
        )
        if choice == "regenerate":
            draft = bootstrap_extractors.draft_voice_anchors(source_texts)
            continue
        break

    os.makedirs(os.path.dirname(VOICE_ANCHORS_PATH), exist_ok=True)
    with atomic_write(VOICE_ANCHORS_PATH, encoding="utf-8") as f:
        f.write(draft if choice == "accept" else "")


def _collect_secret_now_or_later(
    var_name: str,
    prompt_label: str,
    instructions: str,
    env_file: str,
    shell_default: str | None = None,
) -> bool:
    """Walks the user through one .env var: shows instructions, offers to
    enter it right now (written straight to this profile's own .env via
    python-dotenv's set_key(), which creates the file if it doesn't exist
    yet and updates the line in place if it does) or defer it, printing
    exactly which file to edit and what line to add later. Returns True
    if a value was actually collected and written.

    shell_default, when given, means var_name is already exported in the
    shell but this profile's own .env doesn't have it yet -- offered as a
    one-confirm default (not assumed) so bootstrapping a second profile on
    a machine that already has GEMINI_API_KEY exported doesn't silently
    ride on whoever's shell that happens to be, defeating this function's
    whole point of giving every profile its own credentials (B41)."""
    cli_art.console.print(f"\n{instructions}")
    if shell_default:
        cli_art.console.print(
            f"  ({var_name} is already set in your shell environment, but this profile's own "
            f"{env_file} doesn't have its own copy yet -- each profile needs one so credentials "
            f"aren't silently shared across profiles.)"
        )
        use_shell_value = cli_art.confirm(
            f"Use the {prompt_label} already in your shell for this profile too?",
            default=True,
        )
        if use_shell_value:
            os.makedirs(os.path.dirname(env_file), exist_ok=True)
            set_key(env_file, var_name, shell_default)
            cli_art.cli_success(f"Saved {var_name} to {env_file}.")
            return True
        cli_art.cli_info(
            "Okay -- you'll be asked for a value for this profile instead."
        )

    set_now = cli_art.confirm(f"Enter your {prompt_label} now?", default=True)
    if not set_now:
        cli_art.cli_info(
            f"No problem -- add it later by editing {env_file} (create it if it doesn't exist) and adding a line:"
        )
        cli_art.console.print(f"    {var_name}=your-value-here")
        return False

    value = cli_art.password(f"Paste your {prompt_label}:")
    if not value or not value.strip():
        cli_art.cli_info(
            "No value entered -- add it later the same way (see instructions above)."
        )
        return False

    # Some API-key pages (and copy/paste habits) wrap the value in quotes.
    # set_key() wraps whatever it's given in ITS OWN quotes, so a pasted
    # '"AIzaSy..."' becomes a value that still has the inner quotes once
    # dotenv strips the outer pair -- a key that looks right in the file
    # and fails every API call. Strip one matching pair before saving.
    clean_value = value.strip()
    if (
        len(clean_value) >= 2
        and clean_value[0] == clean_value[-1]
        and clean_value[0] in "\"'"
    ):
        clean_value = clean_value[1:-1].strip()

    os.makedirs(os.path.dirname(env_file), exist_ok=True)
    set_key(env_file, var_name, clean_value)
    cli_art.console.print(
        f"  {theme.colorize_icon('success')} Saved {var_name} to {env_file}.",
        soft_wrap=True,
    )
    return True


def collect_secrets(dry_run: bool = False) -> dict:
    """Walks a new profile through its own .env setup -- GEMINI_API_KEY
    (needed for every real build) and JOBRIGHT_COOKIE_STRING (optional,
    only needed for `resume scan --source jobright`). Each profile gets
    its own profiles/<name>/.env (profile_paths.env_path()), so two
    people sharing this checkout never share credentials. Returns
    {"gemini_key_set": bool, "jobright_cookie_set": bool}."""
    if dry_run:
        cli_art.cli_info(
            "[DRY RUN] would walk through .env setup (GEMINI_API_KEY, JOBRIGHT_COOKIE_STRING)."
        )
        return {"gemini_key_set": False, "jobright_cookie_set": False}

    env_file = profile_paths.env_path()
    # This profile's own .env, not the merged os.environ -- GEMINI_API_KEY
    # being exported in the shell (or set by a sibling profile's .env,
    # already loaded by the time this runs) is not the same thing as this
    # profile having its own copy. Checking os.environ here used to mean a
    # profile bootstrapped on a machine that already has the shell var set
    # skipped writing anything to its own .env and silently rode on
    # whoever's shell that was -- exactly what this function's own
    # docstring says it prevents (B41).
    profile_env = dotenv_values(env_file) if os.path.exists(env_file) else {}

    # This can run again on a profile that's already configured (bootstrap
    # is re-runnable to ingest more documents later, not strictly one-time)
    # -- skip re-prompting for a var this profile's own .env already has.
    already_configured = bool(
        profile_env.get("GEMINI_API_KEY") or profile_env.get("GOOGLE_API_KEY")
    )
    if already_configured:
        gemini_set = True
    else:
        cli_art.console.print()
        cli_art.console.rule("API key & cookie setup", style="dim")
        gemini_set = _collect_secret_now_or_later(
            "GEMINI_API_KEY",
            "Gemini API key",
            "Every resume build calls Google's Gemini API, so you'll need your own "
            "API key (a free tier is available -- get one from Google AI Studio if "
            "you don't already have one).",
            env_file,
            shell_default=os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY"),
        )

    jobright_set = bool(profile_env.get("JOBRIGHT_COOKIE_STRING"))
    if not jobright_set:
        wants_jobright = cli_art.confirm(
            "\nOptional: set up JobRight scanning now? (only needed for "
            "`resume scan --source jobright` -- skip this if you'll only use "
            "LinkedIn scanning, or aren't scanning for jobs yet)",
            default=False,
        )
        if wants_jobright:
            jobright_set = _collect_secret_now_or_later(
                "JOBRIGHT_COOKIE_STRING",
                "JobRight cookie string",
                "Grab it like this:\n"
                "  1. Log into jobright.ai in Chrome.\n"
                "  2. Open DevTools (F12 / Cmd+Option+I) -> Network tab, then reload the page.\n"
                "  3. Right-click the first request at the top of the list -> Copy -> Copy as cURL.\n"
                "  4. Paste that into a text editor and find the -H 'cookie: ...' piece --\n"
                "     everything inside the quotes after 'cookie: ' is your JOBRIGHT_COOKIE_STRING.\n"
                "  This cookie goes stale over time -- repeat these steps whenever JobRight\n"
                "  scanning starts failing with an auth error.",
                env_file,
                shell_default=os.environ.get("JOBRIGHT_COOKIE_STRING"),
            )
        else:
            cli_art.cli_info(
                f"Skipped -- add it later by editing {env_file} (create it if it doesn't exist) and adding a line:"
            )
            cli_art.console.print(
                "    JOBRIGHT_COOKIE_STRING=g_state=...; SESSION_ID=...; ..."
            )

    if not already_configured or not jobright_set:
        cli_art.cli_info(
            "Note: LinkedIn scanning needs no .env value at all -- it reads your live, already-logged-in Chrome session automatically, every time."
        )

    return {"gemini_key_set": gemini_set, "jobright_cookie_set": jobright_set}


def collect_linkedin_search_queries(primary_roles: list, dry_run: bool = False) -> list:
    """Confirms/collects this profile's own LinkedIn boolean search
    strings (profile.yml's linkedin_search_queries:). A good boolean query
    needs real per-person tuning, so this asks rather than deriving one
    automatically -- an empty answer here is a fully supported choice,
    since scan_linkedin.py already falls back to one query per
    target_roles.primary entry when linkedin_search_queries: is empty."""
    if dry_run:
        cli_art.cli_info("[DRY RUN] would confirm LinkedIn search terms.")
        return []

    cli_art.cli_info("")
    cli_art.console.rule("LinkedIn search terms", style="dim")
    cli_art.console.print()
    cli_art.cli_info(
        "LinkedIn scanning needs no cookie or login setup -- it reads your live, already-logged-in Chrome session automatically. It does need to know what to search for, though."
    )
    cli_art.console.print()
    if primary_roles:
        cli_art.cli_info(
            f"Without anything set here, it'll search for each of your primary target roles one at a time: {', '.join(primary_roles)}."
        )
        cli_art.console.print()

    wants_custom = cli_art.confirm(
        "Set up your own custom search terms now instead? (optional, and not permanent -- "
        "you can always add/edit these later)",
        default=False,
    )
    if not wants_custom:
        cli_art.cli_info(
            f'Using your target roles as-is for now. To fine-tune later, edit {PROFILE_YML_PATH}\'s linkedin_search_queries: field (boolean strings like "Email OR Campaign").'
        )
        return []

    cli_art.cli_info(
        'Enter one search term per line (e.g. "Email OR Campaign"). Leave blank when done.'
    )
    queries: list[Any] = []
    while True:
        q = cli_art.text(f"Search term {len(queries) + 1} (blank to finish):")
        if not q or not q.strip():
            break
        entry = q.strip()
        wants_override = cli_art.confirm(
            f'Restrict "{entry}" to specific workplace modes or a location, instead of '
            "the nationwide remote default? (optional)",
            default=False,
        )
        if wants_override:
            modes = (
                cli_art.checkbox(
                    "Workplace modes to search (leave all unchecked for remote-only):",
                    choices=[
                        questionary.Choice(title="Remote", value="remote"),
                        questionary.Choice(title="Onsite", value="onsite"),
                        questionary.Choice(title="Hybrid", value="hybrid"),
                    ],
                )
                or []
            )
            location = cli_art.text(
                "Location for this search (blank for nationwide 'United States'):",
                default="",
            )
            entry_dict: dict[str, Any] = {"query": entry}
            if modes:
                entry_dict["workplace_mode"] = modes
            if location and location.strip():
                entry_dict["location"] = location.strip()
            queries.append(entry_dict if len(entry_dict) > 1 else entry)
        else:
            queries.append(entry)
    if not queries:
        cli_art.cli_info("No terms entered -- falling back to target roles.")
        return queries

    experience_choices = [
        questionary.Choice(
            title=label,
            value=key,
            checked=key in content_settings.DEFAULT_LINKEDIN_EXPERIENCE_LEVELS,
        )
        for key, label in content_settings.LINKEDIN_EXPERIENCE_LABELS.items()
    ]
    selected_levels = (
        cli_art.checkbox(
            "Seniority levels to include across every LinkedIn search "
            "(default: Entry level, Associate, Mid-Senior):",
            choices=experience_choices,
        )
        or []
    )
    if selected_levels and set(selected_levels) != set(
        content_settings.DEFAULT_LINKEDIN_EXPERIENCE_LEVELS
    ):
        current = content_settings.read_settings()
        current["linkedin_experience_levels"] = selected_levels
        content_settings.write_settings(current)
        cli_art.cli_info(
            "Saved LinkedIn seniority filter: "
            + ", ".join(
                content_settings.LINKEDIN_EXPERIENCE_LABELS.get(level) or level
                for level in selected_levels
            )
        )
    return queries


def collect_excluded_roles(dry_run: bool = False) -> list:
    """Asks which discovered "roles" aren't real employers at all -- e.g. a
    "Seeking new opportunities, here's how I stayed busy" placeholder entry
    someone added to their old resume to cover a gap, not an actual job.
    Runs BEFORE collect_situational_roles() so an excluded entry is already
    gone from the timeline by the time that step re-reads the same company
    list (_build_cv_draft_rows()) and never shows up as a checkbox choice
    there either -- without this ordering the wizard would happily let
    someone configure keyword triggers for a fake employer.

    Selecting a role here doesn't delete its bullets: apply_excluded_roles()
    re-tags them onto the existing 'Misc. / Unassigned' catch-all bucket
    (the same one bootstrap_timeline.match_to_timeline() already falls back
    to for a bullet it can't attribute to any real company) so the content
    is kept as general material rather than lost or left attached to a
    company that never existed."""
    if dry_run:
        cli_art.cli_info("[DRY RUN] would confirm which past roles to exclude.")
        return []

    companies = [row["company"] for row in _build_cv_draft_rows() if row["company"]]
    if not companies:
        return []

    cli_art.cli_info("")
    cli_art.console.rule("Not actually a role?", style="dim")
    cli_art.console.print()
    cli_art.cli_info(
        "Sometimes an old resume has an entry that isn't really a job -- e.g. "
        'a "Seeking new opportunities" placeholder covering a gap. Pick any '
        "of these that should be dropped as an employer; their bullets are "
        "kept (re-tagged as general material, not tied to a fake company) "
        "rather than lost."
    )
    cli_art.console.print()

    selected = cli_art.checkbox(
        "Any of these that aren't real roles/employers? (click or space to "
        "toggle, a for all shown, / to filter; leave blank for none)",
        choices=[questionary.Choice(title=c, value=c) for c in companies],
        grid=True,
    )
    return list(selected) if selected else []


def _write_timeline_json(timeline: list) -> None:
    os.makedirs(os.path.dirname(bootstrap_bullet_bank.TIMELINE_PATH), exist_ok=True)
    with atomic_write(bootstrap_bullet_bank.TIMELINE_PATH, encoding="utf-8") as f:
        json.dump(timeline, f, indent=2)


def _retag_bullet_bank_companies(excluded: list) -> None:
    """Re-tags every bullet-bank row whose 'Role / Company' is in `excluded`
    to 'Misc. / Unassigned' rather than deleting the rows -- a role that
    turns out not to be a real employer still has genuine bullets worth
    keeping, just not attributed to a company that never existed. Touches
    both the Phase 0 draft CSV and the downstream bullet-bank-clean.csv, so
    a role excluded after Phase 0 already promoted rows into the clean bank
    doesn't leave stale company names behind there."""
    if not excluded:
        return
    excluded_set = set(excluded)
    for csv_path in (
        bootstrap_bullet_bank.DRAFT_CSV_PATH,
        bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH,
    ):
        if not os.path.exists(csv_path):
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        if not fieldnames:
            continue
        changed = False
        for row in rows:
            if row.get("Role / Company") in excluded_set:
                row["Role / Company"] = "Misc. / Unassigned"
                changed = True
        if changed:
            with atomic_write(csv_path, newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)


def apply_excluded_roles(excluded: list, dry_run: bool = False) -> None:
    """Removes each excluded company's timeline entry (so it stops rendering
    as a fake employer on cv.md/profile.yml) and re-tags its bullet-bank
    rows onto 'Misc. / Unassigned' instead of dropping them."""
    if not excluded:
        return
    if dry_run:
        cli_art.cli_info(
            f"[DRY RUN] would exclude {len(excluded)} role(s) from the timeline "
            "and re-tag their bullets to 'Misc. / Unassigned'."
        )
        return
    excluded_set = set(excluded)
    timeline = [e for e in _load_timeline() if e.get("company") not in excluded_set]
    _write_timeline_json(timeline)
    _retag_bullet_bank_companies(excluded)


def collect_situational_roles(dry_run: bool = False) -> list:
    """Confirms/collects "situational" roles -- past jobs specific enough
    that they should only show up on a tailored resume when the JD
    actually calls for them (e.g. animal-welfare work for an
    animal-welfare posting, journalism experience for a communications
    role), rather than on every resume regardless of relevance.

    Backed by situational_roles.py's keyword-triggered inclusion gate:
    each selection here becomes one entry in situational_roles.yaml, and
    bank_tag is set to the company string verbatim so it matches that
    profile's bullet-bank "Role / Company" column exactly (see that
    module's docstring). An empty answer is fully supported -- the file
    stays empty and every past role shows on every resume, same as
    before this step existed."""
    if dry_run:
        cli_art.cli_info("[DRY RUN] would confirm situational roles.")
        return []

    cli_art.cli_info("")
    cli_art.console.rule("Situational roles", style="dim")
    cli_art.console.print()
    cli_art.cli_info(
        "Some past roles are worth including only for certain kinds of jobs -- "
        "niche enough to look out of place on every resume, but genuinely "
        "strong for the right one (e.g. animal-welfare work for an "
        "animal-welfare posting, or journalism experience for a "
        "communications role)."
    )
    cli_art.console.print()

    companies = [row["company"] for row in _build_cv_draft_rows() if row["company"]]
    if not companies:
        cli_art.cli_info(
            "No employers found yet to choose from -- you can still set this "
            f"up later by editing {SITUATIONAL_ROLES_PATH}."
        )
        return []

    selected = cli_art.checkbox(
        "Any of these past roles you'd only want to show up for specific kinds "
        "of jobs? (click or space to toggle, a for all shown, / to filter; "
        "leave blank for none)",
        choices=[questionary.Choice(title=c, value=c) for c in companies],
        grid=True,
    )
    if not selected:
        cli_art.cli_info("None selected -- every past role will show on every resume.")
        return []

    roles = []
    for company in selected:
        # Per-role confirm-and-redo: each role's two fields (display name +
        # keywords) loop until confirmed, instead of committing immediately
        # -- a typo on role 2 of 4 used to mean finishing the whole wizard
        # and re-running this entire step (re-picking every checkbox, and
        # re-typing every OTHER role's answers too) just to fix it.
        display_name_default = company
        keywords_default = ""
        while True:
            cli_art.console.print()
            display_name = (
                cli_art.text(
                    f'Display name for "{company}" (blank to keep as-is):',
                    default=display_name_default,
                )
                or company
            )
            kw_raw = (
                cli_art.text(
                    f'Trigger keywords for "{company}" -- comma-separated words/phrases '
                    "a job description would need to mention for this role to be "
                    'considered (e.g. "animal welfare, animal shelter, veterinary"):',
                    default=keywords_default,
                )
                or ""
            )
            trigger_keywords = [kw.strip() for kw in kw_raw.split(",") if kw.strip()]

            cli_art.cli_info(f'  Display name: "{display_name}"')
            cli_art.cli_info(
                "  Trigger keywords: "
                + (
                    ", ".join(trigger_keywords)
                    or "(none -- this role will show on every resume)"
                )
            )
            if cli_art.confirm("Look right?", default=True):
                break
            cli_art.cli_info("No problem -- let's redo this one.")
            display_name_default, keywords_default = display_name, kw_raw

        if not trigger_keywords:
            cli_art.cli_info(
                f'No keywords entered for "{company}" -- skipping it (it will '
                "show on every resume, same as if you hadn't selected it)."
            )
            continue
        roles.append(
            {
                "display_name": display_name,
                "bank_tag": company,
                "trigger_keywords": trigger_keywords,
            }
        )
    return roles


def _yaml_situational_roles(roles: list) -> str:
    if not roles:
        return "[]"
    lines = []
    for role in roles:
        lines.append(f'  - display_name: "{role["display_name"]}"')
        lines.append(f'    bank_tag: "{role["bank_tag"]}"')
        keywords_yaml = ", ".join(f'"{kw}"' for kw in role["trigger_keywords"])
        lines.append(f"    trigger_keywords: [{keywords_yaml}]")
    return "\n".join(lines)


def write_situational_roles(roles: list, dry_run: bool = False) -> None:
    """Writes situational_roles.yaml. bootstrap_bullet_bank.create_new_profile()
    already scaffolds an empty-but-valid version of this file, so an
    onboarding run with no selections is a same-shape no-op overwrite, not
    a missing file. A re-run (Update My Knowledge) that would clobber
    roles a user already has configured gets a confirm gate first, same
    reasoning as write_profile_yml()'s overwrite guard."""
    if dry_run:
        cli_art.cli_info(
            f"[DRY RUN] would write {len(roles)} situational role(s) to "
            f"{SITUATIONAL_ROLES_PATH}."
        )
        return

    path = SITUATIONAL_ROLES_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            existing = {}
        if existing.get("roles"):
            overwrite = cli_art.confirm(
                f"{path} already has situational roles configured -- overwrite "
                "with what you just entered? (Any existing entries not "
                "re-entered here will be lost.)",
                default=False,
            )
            if not overwrite:
                cli_art.cli_info(
                    "Keeping the existing situational_roles.yaml unchanged."
                )
                return

    content = (
        f"situational_min_bullets: 2\nroles:\n{_yaml_situational_roles(roles)}\n"
        if roles
        else "situational_min_bullets: 2\nroles: []\n"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with atomic_write(path, encoding="utf-8") as f:
        f.write(content)


# The three independently-selectable outputs "Update My Knowledge" can
# target -- kept as an explicit allowlist (not e.g. free-form filenames)
# so menu.py's checkbox choices and this function's dispatch can never
# drift apart. PROFILE_YML_TARGETS is what each target actually writes,
# surfaced to the menu so the checkbox descriptions stay accurate without
# hand-duplicating the list.
PROFILE_TARGET_PROFILE_YML = "profile_yml"
PROFILE_TARGET_CV_MD = "cv_md"
PROFILE_TARGET_BACKGROUND_GUIDE = "background_guide"
ALL_PROFILE_TARGETS = (
    PROFILE_TARGET_PROFILE_YML,
    PROFILE_TARGET_CV_MD,
    PROFILE_TARGET_BACKGROUND_GUIDE,
)


def run_profile_setup(dry_run: bool = False, targets: set | None = None) -> dict:
    """Runs the identity/profile collection steps and writes whichever of
    profile.yml, cv.md, and the background/voice guide are in `targets`
    (default: all three, i.e. the original monolithic behavior). Identity
    (name/contact/target roles) is always collected since both profile.yml
    and cv.md need it, but the profile.yml-only inputs (recommendations,
    tag taxonomy, situational roles, LinkedIn search queries, voice
    calibration example) are only collected when profile.yml is actually
    a target -- no sense asking those questions if the user only wants to
    refresh cv.md."""
    if targets is None:
        targets = set(ALL_PROFILE_TARGETS)

    checkpoint = _load_checkpoint()
    identity = collect_identity(dry_run=dry_run)

    result = {
        "full_name": identity["full_name"],
        "primary_roles": len(identity["primary_roles"]),
        "secondary_roles": len(identity["secondary_roles"]),
        "recommendations_found": 0,
        "tags_generated": 0,
        "linkedin_search_queries": 0,
        "situational_roles": 0,
        "excluded_roles": 0,
        "deal_breakers": 0,
        "staged_facts": 0,
    }

    if PROFILE_TARGET_PROFILE_YML in targets:
        linkedin_search_queries = collect_linkedin_search_queries(
            identity["primary_roles"], dry_run=dry_run
        )
        recommendations = _guess_recommendations(checkpoint, dry_run=dry_run)
        achievements_text = _achievements_summary_text()
        taxonomy = bootstrap_extractors.generate_tag_taxonomy(
            identity["primary_roles"],
            identity["secondary_roles"],
            achievements_text,
            dry_run=dry_run,
        )
        excluded_roles = collect_excluded_roles(dry_run=dry_run)
        apply_excluded_roles(excluded_roles, dry_run=dry_run)
        situational_roles = collect_situational_roles(dry_run=dry_run)
        voice_calibration_example = collect_voice_calibration_example(dry_run=dry_run)
        deal_breakers = collect_deal_breakers(dry_run=dry_run)
        write_profile_yml(
            identity,
            recommendations,
            taxonomy,
            linkedin_search_queries,
            voice_calibration_example=voice_calibration_example,
            deal_breakers=deal_breakers,
        )
        write_portals_yml(identity)
        write_situational_roles(situational_roles, dry_run=dry_run)
        seed_scan_filters_from_target_roles(identity)
        write_verified_ledger(dry_run=dry_run)
        staged_facts_count = stage_candidate_facts(dry_run=dry_run)
        result.update(
            {
                "recommendations_found": len(recommendations),
                "tags_generated": len(taxonomy.tags),
                "linkedin_search_queries": len(linkedin_search_queries),
                "situational_roles": len(situational_roles),
                "excluded_roles": len(excluded_roles),
                "deal_breakers": len(deal_breakers),
                "staged_facts": staged_facts_count,
            }
        )
        if staged_facts_count and not dry_run:
            cli_art.cli_info(
                f"{cli_art.SUCCESS} Staged {staged_facts_count} candidate fact(s) for "
                "review -- Settings & Upkeep > Skills > Review Staged Career Facts "
                "(D10 Gate)."
            )
        offer_settings_screens(dry_run=dry_run)
        report_job_board_readiness(dry_run=dry_run)

    # background guide + voice anchors before cv.md, not after:
    # rewrite_bullets.KnowledgeBase (which write_cv_md()'s bullet-polishing
    # loop uses) loads both user-background-guide.md and voice-anchors.md
    # at __init__ time -- voice-anchors.md is actually injected into every
    # rewrite prompt too (unlike the background guide, which is currently
    # loaded but not yet wired into one) -- if cv.md is drafted first,
    # every bullet gets polished with neither available yet, since neither
    # file exists until these steps run. This ordering must hold even when
    # cv.md and the background guide are selected independently, so a
    # cv.md-only re-run still benefits from whatever background guide
    # already exists on disk (write_background_guide's own preview loop
    # is skipped, not the file).
    if PROFILE_TARGET_BACKGROUND_GUIDE in targets:
        write_background_guide(checkpoint, dry_run=dry_run)
        write_voice_anchors(checkpoint, dry_run=dry_run)

    if PROFILE_TARGET_CV_MD in targets:
        write_cv_md(identity, dry_run=dry_run)

    return result
