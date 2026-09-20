"""
location_enricher.py -- Resolves physical facility addresses and precise
coordinates for employers listed under generic metropolitan hub names (e.g.
"Buffalo, NY", "Kansas City, MO"), enabling accurate door-to-door commute
filtering.

Architectural boundaries:
1. geo_distance.py remains 100% offline, local-only math.
2. location_enricher.py is the I/O enrichment layer that queries OSM, scrapes
   contact pages, extracts contextual JD text addresses, and falls back to
   grounded Gemini search when needed.
3. Fail-closed under unit tests via RESUME_ALLOW_TEST_NETWORK guard.
4. Dynamic configuration: derived from location_settings.read_settings(),
   never hardcoding personal or regional constants.
"""

import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import geo_distance
import location_filter
import location_settings
import profile_paths

logger = logging.getLogger(__name__)

# Test network isolation guard matching websearch_ddg.py / scan_ats.py
_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"

# Rate-limiting guard for OpenStreetMap Nominatim (terms of use: <= 1 req/sec)
_LAST_OSM_CALL_TIME = 0.0
_OSM_MIN_INTERVAL_SECONDS = 1.0

# Known staffing and recruiting agencies where company HQ != job work site
_STAFFING_AGENCIES = {
    "actionlink",
    "addison group",
    "aerotek",
    "apex systems",
    "beacon hill",
    "creative circle",
    "insight global",
    "jobot",
    "judge group",
    "kelly services",
    "kforce",
    "randstad",
    "robert half",
    "russell tobin",
    "teksystems",
}

_STAFFING_CLUES = (
    "our client",
    "on behalf of our client",
    "client is seeking",
    "client in",
    "confidential client",
    "direct hire for our client",
)

_STATE_NAMES_REVERSE = {
    code.upper(): name.title() for name, code in geo_distance._STATE_NAMES.items()
}


def _blocked_under_tests() -> bool:
    """True when a test run would otherwise make real outbound network calls.
    Tests that intend to test network methods set RESUME_ALLOW_TEST_NETWORK=1
    and mock the network transport."""
    return "unittest" in sys.modules and not os.environ.get(_TEST_NETWORK_ENV)


def is_staffing_agency(company: str, jd_text: str = "") -> bool:
    """Identifies third-party staffing agencies where corporate HQ searches
    would resolve the recruiter's office rather than the candidate's work site."""
    if not company:
        return False
    clean = re.sub(r"[^\w\s]", "", company).strip().lower()
    if clean in _STAFFING_AGENCIES:
        return True
    for agency in _STAFFING_AGENCIES:
        if agency in clean:
            return True
    if jd_text:
        lower_text = jd_text[:2000].lower()
        for clue in _STAFFING_CLUES:
            if clue in lower_text:
                return True
    return False


def _build_contextual_zip_regex(state_code: str) -> re.Pattern:
    """Builds a context-aware ZIP code regex anchored to the candidate's target state.
    Requires state prefix or city prefix to prevent false-positive collisions with
    salary figures ($140,000), requisition IDs, timestamps, or statutory codes."""
    code_upper = (state_code or "").strip().upper()
    state_full = _STATE_NAMES_REVERSE.get(code_upper, code_upper)
    return re.compile(
        rf"(?:(?:{re.escape(code_upper)}|{re.escape(state_full)})[,\s]+)"
        r"\b(\d{5})\b",
        re.IGNORECASE,
    )


_STREET_TYPE_PATTERN = (
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Parkway|Pkwy|"
    r"Drive|Dr|Way|Lane|Ln|Court|Ct|Circle|Cir|Place|Pl|Trail|Trl)"
)

_GENERIC_STREET_RE = re.compile(
    rf"\b\d{{1,5}}\s+[A-Za-z0-9\.\s]{{2,30}}\s+{_STREET_TYPE_PATTERN}"
    r"(?:[,\.\s]+[A-Za-z\s]+)?[,\.\s]+[A-Z]{2}[,\.\s]+\b(\d{5})\b",
    re.IGNORECASE,
)


def extract_jd_address(
    raw_text: str, state_code: str = "NY"
) -> Optional[Dict[str, Any]]:
    """Step 2: Scans JD body text with context-bound regex for street addresses
    and postal codes within the target state. Returns structured point or None."""
    if not raw_text or not str(raw_text).strip():
        return None

    text = str(raw_text)

    # 1. Full street address match (Highest confidence within text)
    street_match = _GENERIC_STREET_RE.search(text)
    if street_match:
        zip_code = street_match.group(1)
        point = geo_distance.get_zip_centroid(zip_code)
        if point:
            matched_str = street_match.group(0).strip()
            return {
                "address": matched_str,
                "zip": zip_code,
                "lat": point[0],
                "lon": point[1],
                "source": "jd_text",
            }

    # 2. Contextual state + ZIP match
    zip_re = _build_contextual_zip_regex(state_code)
    zip_match = zip_re.search(text)
    if zip_match:
        zip_code = zip_match.group(1)
        point = geo_distance.get_zip_centroid(zip_code)
        if point:
            return {
                "address": f"{state_code.upper()} {zip_code}",
                "zip": zip_code,
                "lat": point[0],
                "lon": point[1],
                "source": "jd_text",
            }

    return None


def lookup_osm_nominatim(
    company: str, city: str, state: str
) -> Optional[Dict[str, Any]]:
    """Step 1a: Free OpenStreetMap Nominatim POI search.
    Enforces <= 1.0s pacing and custom User-Agent."""
    if _blocked_under_tests():
        return None

    if not company or company.lower() in {"confidential", "unknown company", "stealth"}:
        return None

    global _LAST_OSM_CALL_TIME
    now = time.time()
    elapsed = now - _LAST_OSM_CALL_TIME
    if elapsed < _OSM_MIN_INTERVAL_SECONDS:
        time.sleep(_OSM_MIN_INTERVAL_SECONDS - elapsed)
    _LAST_OSM_CALL_TIME = time.time()

    query = f"{company}, {city}, {state}".strip(", ")
    params = urllib.parse.urlencode(
        {"q": query, "format": "json", "addressdetails": "1", "limit": "1"}
    )
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    headers = {"User-Agent": "resume-builder-app/1.0 (contact: local-candidate-search)"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list):
                item = data[0]
                lat = float(item["lat"])
                lon = float(item["lon"])
                addr = item.get("address", {})
                postcode = addr.get("postcode", "")
                # Clean 5-digit zip if formatted as 14202-1234
                if postcode and len(postcode) >= 5:
                    postcode = postcode[:5]
                return {
                    "address": item.get("display_name", query),
                    "zip": postcode,
                    "lat": lat,
                    "lon": lon,
                    "source": "osm_nominatim",
                }
    except Exception as exc:
        logger.debug("OSM Nominatim lookup error for %s: %s", company, exc)

    return None


def lookup_website_via_search(company: str) -> Optional[str]:
    """Step 1c: Free fallback for a missing company_website, using the same
    no-key DuckDuckGo backend the board-scan sweeps already rely on
    (websearch_ddg.py) rather than spending a Gemini call just to find a
    homepage URL. Tried between OSM and the paid Gemini search backup so
    scrape_company_locations() has something to scrape on far more jobs
    without touching the search-call quota.

    Reuses company_research._REJECTED_DOMAINS so a job board or review site
    ranking above the real homepage (a real, observed DDG result shape) is
    never handed to the scraper as if it were the company's own site.
    Returns None on no query, no results, or an unresolved/rejected match --
    never raises, matching every other lookup_* in this module."""
    if not company or company.lower() in {"confidential", "unknown company", "stealth"}:
        return None

    # The same strict matcher company research uses. Taking the first result
    # that merely wasn't a known job board matched the wrong company in live
    # runs (G.Skill for "Skill", a tour operator for "Sona") -- and scraping
    # a stranger's contact page yields a confidently wrong office address.
    from company_research import _find_website_via_search_engine

    return _find_website_via_search_engine(company)


def scrape_company_locations(
    company_website: str, state_code: str = "NY"
) -> List[Dict[str, Any]]:
    """Step 1b: Scrapes /contact, /locations, /about pages for employer addresses."""
    if _blocked_under_tests():
        return []

    if not company_website or not str(company_website).strip():
        return []

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    base = company_website.strip().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"

    candidate_paths = [
        "/contact",
        "/contact-us",
        "/locations",
        "/about",
        "/about-us",
    ]
    results = []
    seen_zips = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    zip_re = _build_contextual_zip_regex(state_code)

    for path in candidate_paths:
        target_url = f"{base}{path}"
        try:
            resp = requests.get(target_url, headers=headers, timeout=5)
            if resp.status_code != 200 or not resp.text:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator=" ")

            # Look for full street addresses
            for match in _GENERIC_STREET_RE.finditer(text):
                zip_code = match.group(1)
                if zip_code not in seen_zips:
                    point = geo_distance.get_zip_centroid(zip_code)
                    if point:
                        seen_zips.add(zip_code)
                        results.append(
                            {
                                "address": match.group(0).strip(),
                                "zip": zip_code,
                                "lat": point[0],
                                "lon": point[1],
                                "source": "website_contact",
                            }
                        )

            # Look for state-anchored ZIP codes
            for match in zip_re.finditer(text):
                zip_code = match.group(1)
                if zip_code not in seen_zips:
                    point = geo_distance.get_zip_centroid(zip_code)
                    if point:
                        seen_zips.add(zip_code)
                        results.append(
                            {
                                "address": f"{state_code.upper()} {zip_code}",
                                "zip": zip_code,
                                "lat": point[0],
                                "lon": point[1],
                                "source": "website_contact",
                            }
                        )

            if results:
                break
        except Exception:
            continue

    return results


def select_closest_branch(
    branches: List[Dict[str, Any]], origin: str
) -> Optional[Dict[str, Any]]:
    """Selects the closest facility to the candidate's home origin from a list of branches."""
    if not branches:
        return None
    if len(branches) == 1:
        return branches[0]

    origin_point = geo_distance.resolve_location(origin)
    if not origin_point:
        return branches[0]

    best_branch = None
    best_distance = float("inf")
    for b in branches:
        lat, lon = b.get("lat"), b.get("lon")
        if lat is not None and lon is not None:
            dist = geo_distance.haversine_distance_miles(
                origin_point[0], origin_point[1], lat, lon
            )
            if dist < best_distance:
                best_distance = dist
                best_branch = b

    return best_branch or branches[0]


def reconcile_address(
    discovery_result: Optional[Dict[str, Any]],
    jd_text_result: Optional[Dict[str, Any]],
    is_agency: bool = False,
) -> Tuple[Optional[Dict[str, Any]], str, Dict[str, Any]]:
    """Reconciles discovery vs. JD body text. Defer to JD text on conflict."""
    corroboration = {
        "discovery_source": (
            discovery_result.get("source") if discovery_result else None
        ),
        "discovery_zip": discovery_result.get("zip") if discovery_result else None,
        "jd_text_zip": jd_text_result.get("zip") if jd_text_result else None,
        "match": False,
    }

    if is_agency:
        if jd_text_result:
            winning = dict(jd_text_result)
            winning["source"] = "jd_text"
            return winning, "resolved", corroboration
        else:
            return None, "unresolved_agency", corroboration

    if discovery_result and jd_text_result:
        d_zip = discovery_result.get("zip")
        j_zip = jd_text_result.get("zip")
        if d_zip and j_zip and d_zip == j_zip:
            corroboration["match"] = True
            winning = dict(discovery_result)
            winning["source"] = "corroborated"
            return winning, "resolved", corroboration
        else:
            # JD body text takes precedence on conflict
            winning = dict(jd_text_result)
            winning["source"] = "jd_text_override"
            corroboration["override_reason"] = "JD text specified work facility"
            return winning, "resolved", corroboration

    if jd_text_result:
        winning = dict(jd_text_result)
        winning["source"] = "jd_text"
        return winning, "resolved", corroboration

    if discovery_result:
        winning = dict(discovery_result)
        winning["source"] = discovery_result.get("source", "discovery")
        return winning, "resolved", corroboration

    return None, "unresolved", corroboration


# Google Maps Platform terms: a Maps-sourced address may be cached for at
# most 30 days, then must be fetched again; the place reference (the maps_uri,
# which carries the place's CID) may be kept. Coordinates stored here come
# from the bundled ZIP gazetteer, never from Google.
MAPS_CACHE_DAYS = 30
# 500 map-grounded requests/day on the free tier (Search grounding is ZERO
# for every Gemini 3 model, which is why the old backup could never work).
MAPS_BACKUP_MODEL = "gemini-3.5-flash-lite"
_MAPS_ADDRESS_RE = re.compile(r"\*\*Address:\*\*\s*(.+)")
_MAPS_WEBSITE_RE = re.compile(r"\*\*Website:\*\*\s*(\S+)")
_US_ADDRESS_TAIL_RE = re.compile(
    r",\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?(?:,\s*(?:USA|United States))?\s*$"
)


def maps_data_expired(entry: Optional[Dict[str, Any]]) -> bool:
    """True for a Google-Maps-sourced record older than MAPS_CACHE_DAYS, or
    carrying no readable timestamp. Records from any other source never
    expire here."""
    if not isinstance(entry, dict) or entry.get("source") != "google_maps":
        return False
    stamp = entry.get("fetched_at") or entry.get("resolved_at") or ""
    try:
        fetched = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return True
    return (datetime.utcnow() - fetched).total_seconds() / 86400 >= MAPS_CACHE_DAYS


def lookup_google_maps_backup(
    company: str,
    city: str,
    state: str,
    client: Any | None = None,
    company_site: str = "",
) -> Optional[Dict[str, Any]]:
    """Step 3: a Google-Maps-grounded lookup of the employer's office in or
    nearest the candidate's configured city.

    Replaces a Search-grounded backup that never produced an address: it
    called GeminiClient.generate_content_with_search(), which does not exist
    (the AttributeError was swallowed by its broad except, and the tests
    mocked the method into existence), and Search grounding has a ZERO
    free-tier quota on Gemini 3 anyway. Map grounding on gemini-3.1-flash-
    lite was verified live 2026-09-13.

    Trusts only what Google Maps returned (see _parse_maps_grounding): the
    same live test's UNgrounded answer gave a different, wrong address.
    `client` is unused, kept for call-site compatibility. Fails closed under
    tests unless RESUME_ALLOW_TEST_NETWORK=1."""
    if _blocked_under_tests():
        return None
    if not company or company.lower() in {"confidential", "unknown company", "stealth"}:
        return None

    # A Maps place is trusted only when its Website is on the company's own
    # domain (see _parse_maps_grounding), so with no known site there is
    # nothing to verify against: find one for free first, and skip the
    # Maps call entirely if that fails.
    from company_research import is_usable_company_site

    if not (company_site and is_usable_company_site(company_site)):
        company_site = lookup_website_via_search(company) or ""
    if not company_site:
        return None

    # Biases Maps toward the office near the candidate, not the HQ.
    center = geo_distance.resolve_location(f"{city}, {state}")
    tool_config = (
        {"retrievalConfig": {"latLng": {"latitude": center[0], "longitude": center[1]}}}
        if center
        else None
    )
    prompt = (
        f"Using Google Maps, find the office of '{company}' in or nearest to "
        f"{city}, {state}, and give its street address."
    )
    try:
        import gemini_client

        _text, grounding = gemini_client.generate_grounded(
            MAPS_BACKUP_MODEL,
            prompt,
            tools=[{"google_maps": {}}],
            tool_config=tool_config,
        )
    except Exception as exc:
        logger.debug("Google Maps backup error for %s: %s", company, exc)
        return None
    return _parse_maps_grounding(grounding, company, company_site)


def _maps_search_url(query: str) -> str:
    """A Google Maps URLs search link (keyless and documented by Google for
    linking into Maps)."""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(
        query.strip()
    )


def _parse_maps_grounding(
    grounding: Dict[str, Any], company: str, company_site: str = ""
) -> Optional[Dict[str, Any]]:
    """The first Maps source that is THIS company and has a US street
    address we can place by ZIP, else None. The address is read from the
    Maps source itself, never the model's prose; a response with no Maps
    source at all (an ungrounded answer) yields nothing.

    Identity is proven by WEBSITE, not name: the place's own listed Website
    must sit on the company's registrable domain. A name check alone
    accepted local businesses that merely share a word with a remote
    employer -- live, "Fingerprint" near Buffalo returned IdentoGO and a
    UPS Store, and "Boulevard" returned Boulevard Suites. With no company
    site to compare, nothing is accepted: an unknown address is kept for
    review, while a wrong one makes a remote role look local."""
    from company_research import _compact_name, _registrable_labels

    want_domain = ".".join(_registrable_labels(company_site)) if company_site else ""
    if not want_domain:
        return None
    want = _compact_name(company)
    for chunk in (grounding or {}).get("groundingChunks") or []:
        maps = chunk.get("maps") if isinstance(chunk, dict) else None
        if not isinstance(maps, dict):
            continue
        title = re.sub(r"\s*-\s*Google Maps\s*$", "", maps.get("title") or "")
        have = _compact_name(title)
        # Maps biases toward the search center, so a nearby DIFFERENT
        # business is a real possibility -- require the place's own name.
        if len(want) < 3 or len(have) < 4 or (want not in have and have not in want):
            continue
        listed = _MAPS_WEBSITE_RE.search(maps.get("text") or "")
        if not listed or ".".join(_registrable_labels(listed.group(1))) != want_domain:
            continue
        match = _MAPS_ADDRESS_RE.search(maps.get("text") or "")
        if not match:
            continue
        address = match.group(1).strip()
        tail = _US_ADDRESS_TAIL_RE.search(address)
        if not tail:
            continue  # non-US, or no ZIP to place it by
        point = geo_distance.get_zip_centroid(tail.group(2))
        if not point:
            continue
        return {
            "address": address,
            "zip": tail.group(2),
            "lat": point[0],
            "lon": point[1],
            "source": "google_maps",
            # The API's own source link when it sends one -- it sometimes
            # returns uri: "" (seen live for Sunrun). Otherwise Google's
            # documented Maps URLs search link, so every Maps address keeps
            # its source one interaction away, as the terms require.
            "maps_uri": maps.get("uri") or _maps_search_url(f"{title} {address}"),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    return None


# Statuses that will never change on a re-run and so should never be
# re-queued: a remote job stays remote and a real address was found. Everything
# else ("unresolved", "unresolved_agency") is retried on future runs, since
# discovery sources that were down or rate-limited today may succeed later.
_TERMINAL_ENRICHMENT_STATUSES = {"resolved", "bypassed_remote"}


# A failed discovery is re-tried after this many days rather than never --
# a real, permanently-unfindable company should stop costing repeat OSM/DDG
# calls, but a transient failure (DDG timeout, OSM briefly down) must not
# get stuck reporting "unresolved" forever just because it landed in the
# cache on a bad day.
_NEGATIVE_CACHE_COOLDOWN_DAYS = 14


def _negative_cache_expired(entry: Dict[str, Any]) -> bool:
    checked_at = entry.get("checked_at")
    if not checked_at:
        return True
    try:
        checked = datetime.strptime(checked_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return True
    age_days = (datetime.utcnow() - checked).total_seconds() / 86400
    return age_days >= _NEGATIVE_CACHE_COOLDOWN_DAYS


def load_locations_cache(profile: str | None = None) -> Dict[str, Any]:
    """Loads cached company locations from profiles/<profile>/company_locations.json."""
    path = profile_paths.company_locations_cache_path(profile)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}
    return {}


def save_locations_cache(cache: Dict[str, Any], profile: str | None = None) -> None:
    """Saves company locations cache to profiles/<profile>/company_locations.json."""
    path = profile_paths.company_locations_cache_path(profile)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, indent=2, sort_keys=True)
    except Exception as exc:
        logger.debug("Failed to write company locations cache: %s", exc)


def enrich_job_location(
    job_data: Dict[str, Any],
    profile: str | None = None,
    settings: Optional[Dict[str, Any]] = None,
    allow_search_backup: bool = False,
    cache: Optional[Dict[str, Any]] = None,
    gemini_client: Any | None = None,
) -> Dict[str, Any]:
    """Main enrichment orchestrator for a single job posting.

    Calculates precise facility address and dynamic distance from the
    active profile's configured origin. Fully remote roles short-circuit.
    """
    if settings is None:
        settings_path = location_settings.scan_filters_path(profile)
        settings = location_settings.read_settings(settings_path)

    origin = location_filter.origin_from_config(settings)
    origin_point = geo_distance.resolve_location(origin)

    location_str = str(
        job_data.get("location") or job_data.get("job_location") or ""
    ).strip()
    company = str(job_data.get("company") or job_data.get("company_name") or "").strip()
    raw_text = str(
        job_data.get("raw_text") or job_data.get("description") or ""
    ).strip()
    website = str(job_data.get("company_website") or "").strip()

    # Pre-check: Workplace classifier. Remote jobs immediately short-circuit.
    workplace = location_filter.classify_workplace(
        location_str,
        is_remote=job_data.get("is_remote"),
        work_model=job_data.get("work_model"),
    )
    if workplace == location_filter.REMOTE:
        return {
            "status": "bypassed_remote",
            "workplace": location_filter.REMOTE,
            "original_location": location_str,
            "distance_miles": None,
        }

    target_state = str(settings.get("state") or "NY").strip().upper()
    target_city = str(settings.get("city") or "Buffalo").strip()

    clean_company_key = f"{company.lower()}::{target_state.lower()}"
    if cache is None:
        cache = load_locations_cache(profile)

    agency = is_staffing_agency(company, raw_text)

    # Step 1: Discovery (Cache -> OSM -> Website)
    discovery_result = None
    if not agency and company:
        cached_entry = cache.get(clean_company_key)
        if maps_data_expired(cached_entry):
            # Google Maps terms: a Maps address older than 30 days is
            # re-fetched, never served from cache.
            cached_entry = None
        cached_failure = (
            bool(cached_entry)
            and cached_entry is not None
            and cached_entry.get("failed") is True
        )
        if cached_entry and not cached_failure:
            discovery_result = dict(cached_entry)
        elif (
            cached_entry is not None
            and cached_failure
            and not _negative_cache_expired(cached_entry)
        ):
            # A prior run already spent an OSM + free-search + scrape
            # attempt on this exact company and came up empty -- retrying
            # it on every subsequent job posting for the same employer
            # (batches routinely carry several) was the actual source of
            # the repeated "No results found" DDG errors: one real
            # unresolvable company, retried dozens of times per run.
            discovery_result = None
        else:
            # Try OSM
            discovery_result = lookup_osm_nominatim(company, target_city, target_state)
            if not discovery_result:
                if not website:
                    # Free fallback -- finds a homepage to scrape without
                    # spending a Gemini call (see lookup_website_via_search).
                    website = lookup_website_via_search(company) or ""
                if website:
                    # Try Website Scraping
                    branches = scrape_company_locations(website, target_state)
                    if branches:
                        discovery_result = select_closest_branch(branches, origin)

            if discovery_result:
                cache[clean_company_key] = {
                    "address": discovery_result.get("address"),
                    "zip": discovery_result.get("zip"),
                    "lat": discovery_result.get("lat"),
                    "lon": discovery_result.get("lon"),
                    "source": discovery_result.get("source"),
                }
            else:
                cache[clean_company_key] = {
                    "failed": True,
                    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            save_locations_cache(cache, profile)

    # Step 2: JD Text Extraction & Precedence
    jd_result = extract_jd_address(raw_text, target_state)
    winning, status, corroboration = reconcile_address(
        discovery_result, jd_result, is_agency=agency
    )

    # Step 3: Ultra-Backup via Google Maps grounding if needed. Its negative
    # cache uses maps_failed/maps_checked_at, NOT the old gemini_* keys: the
    # old Search backup never actually ran (see lookup_google_maps_backup),
    # yet stamped gemini_failed on 108 companies -- honoring those flags kept
    # 63 of them from ever getting a real Maps attempt. Skipped when a prior
    # run already spent a search call on this exact company and it came up
    # empty within the cooldown window -- otherwise the small per-run quota
    # (max_search_calls) gets re-spent on the same unfindable companies every
    # run instead of ever reaching new ones further down the queue.
    company_cache_entry = cache.get(clean_company_key) or {}
    gemini_previously_failed = company_cache_entry.get(
        "maps_failed"
    ) is True and not _negative_cache_expired(
        {"checked_at": company_cache_entry.get("maps_checked_at")}
    )
    search_call_attempted = False
    maps_site = ""
    if (
        not winning
        and allow_search_backup
        and not agency
        and company
        and not gemini_previously_failed
    ):
        # A Maps result is only accepted when its Website matches the
        # company's domain, so resolve the site first (free) and spend --
        # and count against max_search_calls -- a Maps call only when there
        # is something to verify it against.
        from company_research import is_usable_company_site

        maps_site = (
            website
            if website and is_usable_company_site(website)
            else (lookup_website_via_search(company) or "")
        )
    if maps_site:
        search_call_attempted = True
        gemini_result = lookup_google_maps_backup(
            company,
            target_city,
            target_state,
            client=gemini_client,
            company_site=maps_site,
        )
        if gemini_result:
            winning = gemini_result
            status = "resolved"
            corroboration["discovery_source"] = "google_maps"
            corroboration["discovery_zip"] = gemini_result.get("zip")
            cache[clean_company_key] = {
                "address": gemini_result.get("address"),
                "zip": gemini_result.get("zip"),
                "lat": gemini_result.get("lat"),
                "lon": gemini_result.get("lon"),
                "source": "google_maps",
                "maps_uri": gemini_result.get("maps_uri"),
                "fetched_at": gemini_result.get("fetched_at"),
            }
        else:
            cache[clean_company_key] = {
                **company_cache_entry,
                "maps_failed": True,
                "maps_checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        save_locations_cache(cache, profile)

    # Step 4: Dynamic Distance Math
    distance_miles = None
    if winning and origin_point:
        dest_lat = winning.get("lat")
        dest_lon = winning.get("lon")
        if dest_lat is not None and dest_lon is not None:
            distance_miles = geo_distance.haversine_distance_miles(
                origin_point[0], origin_point[1], dest_lat, dest_lon
            )

    radius_miles = float(settings.get("radius_miles") or 25.0)
    is_within = (distance_miles <= radius_miles) if distance_miles is not None else None

    return {
        "status": status,
        "source": winning.get("source") if winning else None,
        "original_location": location_str,
        "company": company,
        "resolved_address": winning.get("address") if winning else None,
        "resolved_zip": winning.get("zip") if winning else None,
        "lat": winning.get("lat") if winning else None,
        "lon": winning.get("lon") if winning else None,
        # The Google Maps source link: attribution for a Maps address, and
        # the place reference kept past the 30-day address expiry.
        "maps_uri": winning.get("maps_uri") if winning else None,
        "distance_miles": distance_miles,
        "is_within_radius": is_within,
        "is_agency": agency,
        "search_call_attempted": search_call_attempted,
        "corroboration": corroboration,
        "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def enrich_profile_locations(
    profile: str | None = None,
    statuses: Optional[List[str]] = None,
    allow_search_backup: bool = False,
    max_search_calls: int = 10,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Batch enriches company locations for a profile's pending/active database jobs and file-based JDs.
    Respects Gemini search quota caps (counts all attempts, not just successes) and persists cache incrementally.
    """
    import db
    import jd_manager

    profile = profile or profile_paths.active_profile()
    settings_path = location_settings.scan_filters_path(profile)
    settings = location_settings.read_settings(settings_path)

    cache = load_locations_cache(profile)
    conn = db.get_db(profile)

    statuses = [s.lower() for s in (statuses or ["pending"])]
    placeholders = ", ".join("?" for _ in statuses)

    # 1. Collect file-based JDs
    file_items = []
    seen_paths = set()
    if "pending" in statuses:
        for path in jd_manager.get_pending_jds():
            if path not in seen_paths and os.path.isfile(path):
                seen_paths.add(path)
                file_items.append(path)
    if any(
        s in statuses for s in ("active", "applied", "interviewing", "completed", "all")
    ):
        for path in jd_manager.get_completed_jds():
            if path not in seen_paths and os.path.isfile(path):
                seen_paths.add(path)
                file_items.append(path)

    # 2. Collect database jobs
    query_sql = f"SELECT id, title, company, location, raw_text, metadata_json FROM jobs WHERE lower(status) IN ({placeholders})"  # nosec B608
    rows = conn.execute(query_sql, statuses).fetchall()

    enriched_count = 0
    resolved_count = 0
    bypassed_count = 0
    unresolved_count = 0
    search_calls_made = 0

    gemini_client = None
    if allow_search_backup:
        try:
            from gemini_client import GeminiClient

            gemini_client = GeminiClient()
        except Exception:
            gemini_client = None

    # Merge into a unified queue of tasks
    tasks = []

    # First add file-based JDs
    for path in file_items:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            if data.get("_location_enrichment", {}).get(
                "status"
            ) in _TERMINAL_ENRICHMENT_STATUSES and not maps_data_expired(
                data.get("_location_enrichment")
            ):
                # Terminal -- except a Google Maps address past its 30-day
                # cache limit, which must be re-fetched.
                continue
            tasks.append(
                {
                    "type": "file",
                    "path": path,
                    "id": data.get("id") or path,
                    "title": data.get("title") or data.get("job_title") or "",
                    "company": data.get("company") or data.get("company_name") or "",
                    "location": data.get("location") or "",
                    "raw_text": data.get("raw_text") or data.get("jd_text") or "",
                    "company_website": data.get("company_website", ""),
                    "is_remote": data.get("is_remote"),
                    "work_model": data.get("work_model"),
                    "data": data,
                }
            )
        except Exception:
            continue

    # Next add database rows that aren't already represented
    seen_db_keys = {t["id"] for t in tasks}
    seen_db_keys.update(seen_paths)

    for row in rows:
        if row["id"] in seen_db_keys:
            continue
        meta = json.loads(row["metadata_json"] or "{}")
        row_path = meta.get("path") or meta.get("jd_path")
        if row_path and row_path in seen_paths:
            continue
        if (
            meta.get("_location_enrichment")
            and meta["_location_enrichment"].get("status")
            in _TERMINAL_ENRICHMENT_STATUSES
            and not maps_data_expired(meta["_location_enrichment"])
        ):
            continue
        tasks.append(
            {
                "type": "db",
                "path": row_path,
                "id": row["id"],
                "title": row["title"],
                "company": row["company"],
                "location": row["location"],
                "raw_text": row["raw_text"],
                "company_website": meta.get("company_website", ""),
                "is_remote": meta.get("is_remote"),
                "work_model": meta.get("work_model"),
                "meta": meta,
            }
        )

    if limit is not None and limit > 0:
        tasks = tasks[:limit]

    total_to_process = len(tasks)
    print(
        f"✦ Found {total_to_process} job posting(s) to check/enrich for profile '{profile}'."
    )

    try:
        for idx, item in enumerate(tasks, 1):
            use_search = allow_search_backup and (search_calls_made < max_search_calls)
            enrichment = enrich_job_location(
                item,
                profile=profile,
                settings=settings,
                allow_search_backup=use_search,
                cache=cache,
                gemini_client=gemini_client,
            )

            if enrichment.get("search_call_attempted"):
                search_calls_made += 1

            # Persist to file if file-backed
            if item["type"] == "file" or (
                item.get("path") and os.path.isfile(item["path"])
            ):
                fpath = item.get("path")
                if fpath and os.path.isfile(fpath):
                    jd_manager.save_location_enrichment(fpath, enrichment)

            # Persist to database if db-backed
            if item["type"] == "db":
                meta = item.get("meta", {})
                meta["_location_enrichment"] = enrichment
                conn.execute(
                    "UPDATE jobs SET metadata_json = ? WHERE id = ?",
                    (json.dumps(meta), item["id"]),
                )

            enriched_count += 1

            status = enrichment.get("status", "unknown")
            source = enrichment.get("source", "none")
            resolved_office = str(enrichment.get("resolved_address") or "")
            company_display = item.get("company") or "Unknown"
            if status == "resolved":
                resolved_count += 1
                loc_display_str = f" → {resolved_office}" if resolved_office else ""
                print(
                    f"  [{idx}/{total_to_process}] ✓ {company_display}: resolved via {source}{loc_display_str}"
                )
            elif status.startswith("bypassed"):
                bypassed_count += 1
                print(
                    f"  [{idx}/{total_to_process}] ✦ {company_display}: bypassed ({enrichment.get('reason', 'remote')})"
                )
            else:
                unresolved_count += 1
                print(
                    f"  [{idx}/{total_to_process}] ▤ {company_display}: unresolved ({status})"
                )

            # Incrementally save cache and commit DB every 5 jobs
            if enriched_count % 5 == 0:
                conn.commit()
                save_locations_cache(cache, profile)

    except KeyboardInterrupt:
        print("\n⚠ Enrichment interrupted by user. Saving current progress...")
    finally:
        conn.commit()
        conn.close()
        db.checkpoint(profile)
        save_locations_cache(cache, profile)

    return {
        "profile": profile,
        "total_processed": enriched_count,
        "resolved": resolved_count,
        "bypassed_remote": bypassed_count,
        "unresolved": unresolved_count,
        "search_calls_used": search_calls_made,
    }
