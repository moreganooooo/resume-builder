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


def lookup_gemini_search_backup(
    company: str,
    city: str,
    state: str,
    client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Step 3: Ultra-backup using Gemini Flash-Lite with Google Search Grounding.
    Fails closed under tests unless mocked or RESUME_ALLOW_TEST_NETWORK=1."""
    if _blocked_under_tests():
        return None

    if not company or company.lower() in {"confidential", "unknown company", "stealth"}:
        return None

    try:
        from gemini_client import GeminiClient

        client = client or GeminiClient()
        prompt = (
            f"What is the office or physical work facility address of '{company}' in or near {city}, {state}?\n"
            "Return a clean JSON object with fields:\n"
            '{"found": true|false, "address": "...", "zip": "12345", "city": "...", "state": "..."}'
        )
        response = client.generate_content_with_search(
            prompt=prompt,
            model="gemini-3.1-flash-lite",
        )
        text = response.text if hasattr(response, "text") else str(response)
        # Parse JSON from response text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if data.get("found") and data.get("zip"):
                zip_code = str(data.get("zip")).strip()
                point = geo_distance.get_zip_centroid(zip_code)
                if point:
                    return {
                        "address": data.get("address") or f"{city}, {state} {zip_code}",
                        "zip": zip_code,
                        "lat": point[0],
                        "lon": point[1],
                        "source": "gemini_search",
                    }
    except Exception as exc:
        logger.debug("Gemini Search backup error for %s: %s", company, exc)

    return None


def load_locations_cache(profile: str = None) -> Dict[str, Any]:
    """Loads cached company locations from profiles/<profile>/company_locations.json."""
    path = profile_paths.company_locations_cache_path(profile)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}
    return {}


def save_locations_cache(cache: Dict[str, Any], profile: str = None) -> None:
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
    profile: str = None,
    settings: Optional[Dict[str, Any]] = None,
    allow_search_backup: bool = False,
    cache: Optional[Dict[str, Any]] = None,
    gemini_client: Any = None,
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
        if clean_company_key in cache:
            discovery_result = dict(cache[clean_company_key])
        else:
            # Try OSM
            discovery_result = lookup_osm_nominatim(company, target_city, target_state)
            if not discovery_result and website:
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
                save_locations_cache(cache, profile)

    # Step 2: JD Text Extraction & Precedence
    jd_result = extract_jd_address(raw_text, target_state)
    winning, status, corroboration = reconcile_address(
        discovery_result, jd_result, is_agency=agency
    )

    # Step 3: Ultra-Backup via Gemini Search if needed
    search_call_attempted = False
    if not winning and allow_search_backup and not agency and company:
        search_call_attempted = True
        gemini_result = lookup_gemini_search_backup(
            company, target_city, target_state, client=gemini_client
        )
        if gemini_result:
            winning = gemini_result
            status = "resolved"
            corroboration["discovery_source"] = "gemini_search"
            corroboration["discovery_zip"] = gemini_result.get("zip")
            cache[clean_company_key] = {
                "address": gemini_result.get("address"),
                "zip": gemini_result.get("zip"),
                "lat": gemini_result.get("lat"),
                "lon": gemini_result.get("lon"),
                "source": "gemini_search",
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
        "distance_miles": distance_miles,
        "is_within_radius": is_within,
        "is_agency": agency,
        "search_call_attempted": search_call_attempted,
        "corroboration": corroboration,
        "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def enrich_profile_locations(
    profile: str = None,
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
            if data.get("_location_enrichment", {}).get("status") == "resolved":
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
            and meta["_location_enrichment"].get("status") == "resolved"
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
            addr = enrichment.get("resolved_address", "")
            company_display = item.get("company") or "Unknown"
            if status == "resolved":
                resolved_count += 1
                addr_str = f" → {addr}" if addr else ""
                print(
                    f"  [{idx}/{total_to_process}] ✓ {company_display}: resolved via {source}{addr_str}"
                )
            elif status.startswith("bypassed"):
                print(
                    f"  [{idx}/{total_to_process}] ✦ {company_display}: bypassed ({enrichment.get('reason', 'remote')})"
                )
            else:
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
        "search_calls_used": search_calls_made,
    }
