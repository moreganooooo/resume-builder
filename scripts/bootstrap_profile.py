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
import sys

import questionary

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

PROFILE_YML_PATH = os.path.join(KB_DIR, "profile.yml")
PORTALS_YML_PATH = os.path.join(KB_DIR, "portals.yml")
CV_MD_PATH = os.path.join(KB_DIR, "cv.md")
BACKGROUND_GUIDE_PATH = os.path.join(KB_DIR, "user-background-guide.md")
VERIFIED_METRICS_PATH = os.path.join(KB_DIR, "verified_metrics.json")
VERIFIED_TOOLS_PATH = os.path.join(KB_DIR, "verified_tools.json")
VERIFIED_PROJECTS_PATH = os.path.join(KB_DIR, "verified_projects.json")
VERIFIED_FACTS_PATH = os.path.join(KB_DIR, "verified_facts.json")
VERIFIED_CLAIMS_PATH = os.path.join(KB_DIR, "verified-claims.csv")
EVIDENCE_GRAPH_PATH = os.path.join(KB_DIR, "evidence_graph.json")
EVIDENCE_GUIDE_PATH = os.path.join(KB_DIR, "evidence-guide.csv")
SCREENSHOT_METRICS_PATH = os.path.join(KB_DIR, "extracted-screenshot-metrics.csv")
RECRUITER_PATTERNS_PATH = os.path.join(KB_DIR, "recruiter_memory_patterns.json")

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402
import cli_art  # noqa: E402


def _load_checkpoint() -> dict:
    if not os.path.exists(bootstrap_bullet_bank.CHECKPOINT_PATH):
        return {}
    with open(bootstrap_bullet_bank.CHECKPOINT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_timeline() -> list:
    if not os.path.exists(bootstrap_bullet_bank.TIMELINE_PATH):
        return []
    with open(bootstrap_bullet_bank.TIMELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _achievements_summary_text() -> str:
    if not os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH):
        return ""
    with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return "\n".join(row.get("Bullet Point", "") for row in rows)


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


def _guess_contact_info(checkpoint: dict, dry_run: bool = False) -> bootstrap_extractors.ContactInfo:
    for filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done" or result.get("doc_type") not in ("resume", "linkedin_export"):
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, upload_path = _resolve_text_or_upload(path)
        if text is None and upload_path is None:
            continue
        info = bootstrap_extractors.extract_contact_info(text=text, upload_path=upload_path, dry_run=dry_run)
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
        if result.get("status") != "done" or result.get("doc_type") != "recommendation_letter":
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, upload_path = _resolve_text_or_upload(path)
        if text is None and upload_path is None:
            continue
        quote = bootstrap_extractors.extract_recommendation_quote(text=text, upload_path=upload_path, dry_run=dry_run)
        if quote is not None:
            quotes.append(quote)
    return quotes


def _confirm_text(label: str, guessed) -> str:
    return questionary.text(label, default=guessed or "", style=cli_art.QUESTIONARY_STYLE).ask() or ""


def _confirm_roles(label: str, guessed: list) -> list:
    if not guessed:
        extra = questionary.text(f"{label} (comma-separated, optional)", default="", style=cli_art.QUESTIONARY_STYLE).ask() or ""
        return [r.strip() for r in extra.split(",") if r.strip()]
    choices = [questionary.Choice(title=r, value=r, checked=True) for r in guessed]
    kept = questionary.checkbox(label, choices=choices, style=cli_art.QUESTIONARY_STYLE).ask() or []
    extra = questionary.text(f"Add any more {label.lower()} (comma-separated, optional)", default="", style=cli_art.QUESTIONARY_STYLE).ask() or ""
    kept.extend(r.strip() for r in extra.split(",") if r.strip())
    return kept


def collect_identity(dry_run: bool = False) -> dict:
    checkpoint = _load_checkpoint()
    timeline = _load_timeline()
    guessed = _guess_contact_info(checkpoint, dry_run=dry_run)
    primary_guess = _guess_primary_roles(timeline)

    if dry_run:
        print("[DRY RUN] would confirm identity fields:")
        print(f"  Full name: {guessed.full_name or ''}")
        print(f"  Email: {guessed.email or ''}")
        print(f"  Phone: {guessed.phone or ''}")
        print(f"  Location: {guessed.location or ''}")
        print(f"  LinkedIn URL: {guessed.linkedin_url or ''}")
        print(f"  Primary target roles: {', '.join(primary_guess)}")
        return {
            "full_name": guessed.full_name or "", "email": guessed.email or "",
            "phone": guessed.phone or "", "location": guessed.location or "",
            "linkedin_url": guessed.linkedin_url or "", "portfolio_url": guessed.portfolio_url or "",
            "extra_link": "", "primary_roles": primary_guess, "secondary_roles": [],
            "remote_preference": False,
        }

    full_name = _confirm_text("Full name:", guessed.full_name)
    email = _confirm_text("Email:", guessed.email)
    phone = _confirm_text("Phone:", guessed.phone)
    location = _confirm_text("Location (city, state):", guessed.location)
    linkedin_url = _confirm_text("LinkedIn URL:", guessed.linkedin_url)
    portfolio_url = _confirm_text("Portfolio URL (optional, press Enter to skip):", guessed.portfolio_url)
    extra_link = _confirm_text("Any other portfolio/work-sample link? (optional, press Enter to skip):", None)

    primary_roles = _confirm_roles("Primary target roles:", primary_guess)

    achievements_text = _achievements_summary_text()
    secondary_guess = (
        bootstrap_extractors.suggest_secondary_roles(primary_roles, achievements_text, dry_run=dry_run)
        if primary_roles else []
    )
    secondary_roles = _confirm_roles("Secondary target roles:", secondary_guess)

    remote_preference = questionary.confirm(
        "Are you remote-only?", default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    return {
        "full_name": full_name, "email": email, "phone": phone, "location": location,
        "linkedin_url": linkedin_url, "portfolio_url": portfolio_url, "extra_link": extra_link,
        "primary_roles": primary_roles, "secondary_roles": secondary_roles,
        "remote_preference": bool(remote_preference),
    }


def _yaml_string_list(items: list, indent: str = "    ") -> str:
    if not items:
        return f"{indent}[]"
    return "\n".join(f'{indent}- "{item}"' for item in items)


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

target_roles:
  primary:
{primary_roles_yaml}
  secondary:
{secondary_roles_yaml}

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

background_context: >
  A paragraph on how your background came together -- the different
  tracks/experiences that combine into what you do now.

industries_of_genuine_fit:
  # Industries or company types where you'd genuinely want to work.
  - ""

companies_previously_applied: []
  # Track applications here as you go, to avoid duplicate applying.

deal_breakers:
  # Things that would make a role a bad fit, with the specific reason.
  # Example: "On-site or hybrid required -- remote-only availability"
  - ""

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
"""


def write_profile_yml(identity: dict, recommendations: list) -> None:
    content = _PROFILE_YML_TEMPLATE.format(
        full_name=identity["full_name"], email=identity["email"], phone=identity["phone"],
        location=identity["location"], linkedin_url=identity["linkedin_url"],
        portfolio_url=identity["portfolio_url"], extra_link=identity["extra_link"],
        primary_roles_yaml=_yaml_string_list(identity["primary_roles"]),
        secondary_roles_yaml=_yaml_string_list(identity["secondary_roles"]),
        key_recommendations_yaml=_yaml_key_recommendations(recommendations),
        location_flexibility="Remote only" if identity.get("remote_preference") else "",
        remote_required=str(bool(identity.get("remote_preference"))).lower(),
    )
    os.makedirs(os.path.dirname(PROFILE_YML_PATH), exist_ok=True)
    with open(PROFILE_YML_PATH, "w", encoding="utf-8") as f:
        f.write(content)
