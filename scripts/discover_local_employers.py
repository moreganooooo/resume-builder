"""
discover_local_employers.py -- turn the aggregators into a discovery feed
for full-text ATS scraping.

The problem this closes. Every free aggregator reachable from here is
teaser-only by design, because their business is the click-through:
jooble returns ~275 characters, adzuna exactly 500, and neither posting
page can be fetched (both 403). Meanwhile the richest job text in this
profile's whole corpus comes from ATS providers scraped directly --
greenhouse a median of 8,898 characters, workday 8,427 -- because those
are the employer's own boards with nothing to gain from truncating.

So the aggregators are used for what they are actually good at, which is
telling you WHICH employers are hiring near you, and the ATS providers
already vendored here are used for the text. This script is the bridge:
it reads local postings, extracts the employer names, probes each one for
a public ATS board, and appends the confirmed hits to
tracked_companies.yml, where scan_ats.py picks them up on the next run
with no further wiring.

Detection requires a non-empty posting list, not merely HTTP 200.
SmartRecruiters answers 200 with totalFound 0 for company slugs that do
not exist at all, so a status-code check alone would claim every employer
on earth uses SmartRecruiters.

Dry run by default, matching reconcile_jd_status.py and
purge_terminal_jobs.py: it prints what it would add and changes nothing
until --apply. Existing entries are never modified or duplicated, and the
YAML is backed up before it is touched.
"""

import argparse
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import cli_art
import location_settings
import profile_paths
import requests
import yaml

# Public, unauthenticated board endpoints. Each returns JSON listing the
# employer's open roles; the counter below knows each one's shape.
ATS_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "recruitee": "https://{slug}.recruitee.com/api/offers/",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
}

# The human-facing board, for the entry's careers_url.
ATS_CAREERS_URL = {
    "greenhouse": "https://boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "recruitee": "https://{slug}.recruitee.com/",
    "smartrecruiters": "https://careers.smartrecruiters.com/{slug}",
}

REQUEST_TIMEOUT_SECONDS = 12
PROBE_WORKERS = 8
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; resume-builder/1.0)"}

# Suffixes that are part of a legal name but never part of a board slug.
_LEGAL_SUFFIXES = (
    "inc",
    "llc",
    "ltd",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "lp",
    "llp",
    "gmbh",
    "holdings",
    "group",
    "the",
)

# Staffing agencies and job-board middlemen post on behalf of employers,
# so their name on a listing is not the hiring company. Tracking them
# would fill the list with recruiters rather than employers.
_NOT_EMPLOYERS = (
    "staffing",
    "recruit",
    "talent",
    "consultants",
    "consulting group",
    "solutions group",
    "placement",
    "temp",
    "employment agency",
    "jobs",
    "careers",
    "hiring",
    "confidential",
    "undisclosed",
)


def _normalize_company_key(name: str) -> str:
    """Comparison key for 'do we already track this employer'."""
    lowered = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    words = [w for w in lowered.split() if w and w not in _LEGAL_SUFFIXES]
    return " ".join(words)


def slug_candidates(name: str) -> list:
    """Board slugs an employer plausibly uses, most likely first.

    Boards are keyed by a slug the employer chose, which is usually the
    company name with the legal suffix dropped and the spaces removed or
    hyphenated. Guessing a couple of forms is what makes this work
    without a directory lookup.
    """
    key = _normalize_company_key(name)
    if not key:
        return []
    compact = key.replace(" ", "")
    hyphenated = key.replace(" ", "-")
    # Deliberately NO first-word guess. "Stellar Roofing" -> "stellar"
    # matched a completely unrelated company's board, as did "barnes",
    # "dave", "ino" and "evolution": 5 of 6 hits in the first live run
    # were this fallback, every one of them wrong. A local employer
    # silently mapped onto a national company's board would pour dozens
    # of irrelevant postings into the pipeline labeled as local.
    seen, out = set(), []
    for candidate in (compact, hyphenated):
        if candidate and candidate not in seen and len(candidate) >= 3:
            seen.add(candidate)
            out.append(candidate)
    return out


def looks_like_employer(name: str) -> bool:
    """False for staffing agencies and placeholder company names."""
    lowered = (name or "").strip().lower()
    if len(lowered) < 2:
        return False
    return not any(token in lowered for token in _NOT_EMPLOYERS)


def _count_postings(provider_id: str, payload) -> int:
    """Open roles in a board response, per that provider's own shape."""
    try:
        if provider_id == "lever":
            return len(payload) if isinstance(payload, list) else 0
        if not isinstance(payload, dict):
            return 0
        if provider_id == "greenhouse":
            return len(payload.get("jobs") or [])
        if provider_id == "ashby":
            return len(payload.get("jobs") or [])
        if provider_id == "recruitee":
            return len(payload.get("offers") or [])
        if provider_id == "smartrecruiters":
            return int(payload.get("totalFound") or 0)
    except (TypeError, ValueError):
        return 0
    return 0


def board_owner_name(provider_id: str, slug: str, payload) -> str:
    """The board owner's real name, when the API discloses it.

    Returns "" when the provider exposes no name -- Ashby and Lever do
    not -- which means those can only be trusted as far as the slug
    itself is, hence the strict slug forms above.
    """
    try:
        if provider_id == "smartrecruiters" and isinstance(payload, dict):
            first = (payload.get("content") or [{}])[0]
            return str((first.get("company") or {}).get("name") or "")
        if provider_id == "recruitee" and isinstance(payload, dict):
            first = (payload.get("offers") or [{}])[0]
            return str(first.get("company_name") or "")
        if provider_id == "greenhouse":
            # The jobs endpoint carries no owner name; the board itself
            # does, and it is one extra cheap request on a confirmed hit.
            response = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}",
                headers=_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                return str(response.json().get("name") or "")
    except (requests.RequestException, ValueError, IndexError, AttributeError):
        return ""
    return ""


def owner_matches(employer: str, owner: str) -> bool:
    """Whether a board's disclosed owner is really this employer.

    Containment either way, because the two rarely agree exactly:
    a board reads "Hearst" where the posting says "The Hearst
    Corporation". What it rejects is the case that actually bit --
    "Evolution" answering for "Evolution Dental Science", where the
    board name is a strict prefix of a longer, different company.
    """
    a = _normalize_company_key(employer)
    b = _normalize_company_key(owner)
    if not a or not b:
        return False
    if a == b:
        return True
    # A single shared word is not a match ("evolution" vs "evolution
    # dental science"); require the shorter name to be a multi-word
    # prefix or the names to differ only by dropped filler.
    short, long_ = sorted((a, b), key=len)
    return len(short.split()) > 1 and long_.startswith(short)


def probe_slug(slug: str) -> dict | None:
    """Returns the first ATS board that actually lists open roles.

    A board with zero postings is not evidence of anything -- see the
    SmartRecruiters note in the module docstring -- so an empty response
    is treated as no match.
    """
    for provider_id, template in ATS_ENDPOINTS.items():
        url = template.format(slug=slug)
        try:
            response = requests.get(
                url, headers=_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        try:
            payload = response.json()
        except ValueError:
            continue
        count = _count_postings(provider_id, payload)
        if count > 0:
            return {
                "provider": provider_id,
                "slug": slug,
                "api": url,
                "careers_url": ATS_CAREERS_URL[provider_id].format(slug=slug),
                "postings": count,
                "payload": payload,
            }
    return None


def find_ats_board(name: str) -> dict | None:
    """Tries each plausible slug for one employer, and verifies the hit.

    A board is accepted only if the provider either discloses an owner
    name that matches, or discloses none at all -- in which case the
    strict slug is the only evidence available and has to carry it.
    """
    for slug in slug_candidates(name):
        hit = probe_slug(slug)
        if not hit:
            continue
        owner = board_owner_name(hit["provider"], slug, hit.pop("payload", None))
        if owner and not owner_matches(name, owner):
            # A different company owns this slug. Silently tracking it
            # would attribute their postings to a local employer.
            continue
        return dict(hit, name=name, owner=owner)
    return None


def tracked_companies_path(profile: str = None) -> str:
    return os.path.join(
        profile_paths.board_scanner_dir(profile or profile_paths.active_profile()),
        "tracked_companies.yml",
    )


def existing_company_keys(path: str) -> set:
    """Normalized names already tracked, so nothing is added twice."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return set()
    keys = set()
    for entry in data.get("tracked_companies") or []:
        if isinstance(entry, dict) and entry.get("name"):
            keys.add(_normalize_company_key(entry["name"]))
    return keys


def gather_local_employers(limit: int = 60, search_term: str = None) -> list:
    """Employer names from local postings, best source first.

    Indeed carries by far the most local employers, so it leads; the
    teaser-only aggregators still contribute names, which is exactly the
    role they are good for.
    """
    settings = location_settings.read_settings()
    if not settings:
        cli_art.cli_error(
            "No location configured -- set one under Settings & Upkeep "
            "-> Location & Commute Radius first."
        )
        return []

    names, seen = [], set()

    def add(raw_name: str) -> None:
        name = (raw_name or "").strip()
        if not name or not looks_like_employer(name):
            return
        key = _normalize_company_key(name)
        if not key or key in seen:
            return
        seen.add(key)
        names.append(name)

    try:
        import scan_indeed

        for job in scan_indeed.fetch_indeed_jobs(search_term=search_term):
            add(job.get("company_name"))
    except Exception as e:  # pragma: no cover - network path
        cli_art.cli_error(f"Indeed discovery failed ({type(e).__name__}); continuing.")

    try:
        import scan_boards

        for provider_id in ("adzuna", "jooble"):
            for job in scan_boards.fetch_board_jobs(
                sources=[provider_id], search_term=search_term
            ):
                add(job.get("company_name"))
    except Exception as e:  # pragma: no cover - network path
        cli_art.cli_error(f"Board discovery failed ({type(e).__name__}); continuing.")

    return names[:limit]


def discover(limit: int = 60, search_term: str = None, profile: str = None) -> list:
    """Local employers that have a public ATS board and are not tracked."""
    path = tracked_companies_path(profile)
    known = existing_company_keys(path)

    candidates = [
        name
        for name in gather_local_employers(limit=limit, search_term=search_term)
        if _normalize_company_key(name) not in known
    ]
    if not candidates:
        return []

    cli_art.console.print(
        f"  Probing {len(candidates)} local employer(s) for public ATS boards...",
        soft_wrap=True,
    )

    found = []
    with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as executor:
        futures = {executor.submit(find_ats_board, n): n for n in candidates}
        for future in as_completed(futures):
            try:
                hit = future.result()
            except Exception:
                hit = None
            if hit:
                found.append(hit)
    found.sort(key=lambda h: -h["postings"])
    return found


def render_entries(hits: list) -> str:
    """The YAML block appended to tracked_companies.yml."""
    lines = []
    for hit in hits:
        lines.append(f"- name: {hit['name']}")
        lines.append(f"  careers_url: {hit['careers_url']}")
        lines.append(f"  api: {hit['api']}")
        lines.append("  enabled: true")
    return "\n".join(lines) + "\n"


def append_entries(hits: list, path: str) -> str:
    """Appends new entries, preserving every existing comment.

    Text append rather than a yaml round-trip: this file opens with
    load-bearing prose about how provider resolution works, and
    yaml.safe_dump would delete all of it (the same trap
    location_settings.py documents).
    """
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)

    with open(path, "r", encoding="utf-8") as handle:
        original = handle.read()
    updated = original.rstrip("\n") + "\n" + render_entries(hits)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Find local employers with public ATS boards and track them, "
            "so their full job descriptions get scraped directly."
        )
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the entries (default: dry run)"
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--limit", type=int, default=60, help="max employers to probe (default: 60)"
    )
    parser.add_argument(
        "--search-term",
        default=None,
        help="what to search locally (default: the scanner's own term)",
    )
    args = parser.parse_args()

    if args.profile:
        profile_paths.set_active_profile(args.profile)

    path = tracked_companies_path(args.profile)
    if not os.path.exists(path):
        cli_art.cli_error(f"No tracked_companies.yml at {path}")
        sys.exit(1)

    hits = discover(
        limit=args.limit, search_term=args.search_term, profile=args.profile
    )
    if not hits:
        cli_art.console.print(
            "\n  No new local employers with public ATS boards found.\n",
            soft_wrap=True,
        )
        return

    cli_art.console.print(
        f"\n  Found [cyan]{len(hits)}[/cyan] local employer(s) with a public board:\n",
        soft_wrap=True,
    )
    for hit in hits:
        cli_art.console.print(
            f"    {hit['name']}  [dim]{hit['provider']} · "
            f"{hit['postings']} open role(s)[/dim]",
            soft_wrap=True,
        )

    if not args.apply:
        cli_art.console.print(
            "\n  Dry run -- nothing written. Re-run with --apply to track these.\n",
            soft_wrap=True,
        )
        return

    backup = append_entries(hits, path)
    cli_art.console.print(
        f"\n  {cli_art.SUCCESS} Added {len(hits)} employer(s). Backup: {backup}\n"
        "  They will be scanned on the next run.\n",
        soft_wrap=True,
    )


if __name__ == "__main__":
    main()
