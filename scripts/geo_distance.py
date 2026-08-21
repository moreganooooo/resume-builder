"""
geo_distance.py -- offline distance math for the location/radius filter.

Answers one question: how far is a job posting's stated location from the
place the candidate is willing to commute to. Everything is local -- the
centroid indexes in assets/geodata/ are bundled (see build_geodata.py), so
this never makes a network call and costs nothing per lookup.

The hard part is not the arithmetic, it is that postings state a location
as free text written by a human for other humans: "Austin, TX",
"Austin, Texas", "78701", "Greater Austin Area", "Remote (US)",
"London, UK". resolve_location() handles the forms that map to a single
point and returns None for everything else, so callers can distinguish
"this is 8 miles away" from "we could not tell" -- which are very
different answers and must never be conflated into a number.

Layered above this, scripts/prefilter.py implements the multi-tier parse
(exclusion fencing, compound "A OR B" splitting) that turns a messy
string into one or more candidates to hand here.
"""

import functools
import gzip
import json
import math
import os
import re

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "geodata"
)

EARTH_RADIUS_MILES = 3958.7613

# Full state names appear in postings at least as often as codes
# ("Austin, Texas"), and the bundled city index is keyed by code.
_STATE_NAMES = {
    "alabama": "al",
    "alaska": "ak",
    "arizona": "az",
    "arkansas": "ar",
    "california": "ca",
    "colorado": "co",
    "connecticut": "ct",
    "delaware": "de",
    "district of columbia": "dc",
    "florida": "fl",
    "georgia": "ga",
    "hawaii": "hi",
    "idaho": "id",
    "illinois": "il",
    "indiana": "in",
    "iowa": "ia",
    "kansas": "ks",
    "kentucky": "ky",
    "louisiana": "la",
    "maine": "me",
    "maryland": "md",
    "massachusetts": "ma",
    "michigan": "mi",
    "minnesota": "mn",
    "mississippi": "ms",
    "missouri": "mo",
    "montana": "mt",
    "nebraska": "ne",
    "nevada": "nv",
    "new hampshire": "nh",
    "new jersey": "nj",
    "new mexico": "nm",
    "new york": "ny",
    "north carolina": "nc",
    "north dakota": "nd",
    "ohio": "oh",
    "oklahoma": "ok",
    "oregon": "or",
    "pennsylvania": "pa",
    "puerto rico": "pr",
    "rhode island": "ri",
    "south carolina": "sc",
    "south dakota": "sd",
    "tennessee": "tn",
    "texas": "tx",
    "utah": "ut",
    "vermont": "vt",
    "virginia": "va",
    "washington": "wa",
    "west virginia": "wv",
    "wisconsin": "wi",
    "wyoming": "wy",
}
_STATE_CODES = set(_STATE_NAMES.values())

_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")

# Metro shorthand a posting uses instead of a city name. Deliberately
# short: these are the abbreviations that appear as a WHOLE location
# field ("Onsite - NYC"), where the alternative is resolving nothing and
# waving the posting through as unknown. This is not a general metro
# gazetteer -- regional phrases like "Greater Austin Area" or "Tri-State"
# still return None, since their real extent is a bounding box rather
# than a point.
_METRO_ALIASES = {
    "nyc": "New York, NY",
    "new york city": "New York, NY",
    "la": "Los Angeles, CA",
    "sf": "San Francisco, CA",
    "sfo": "San Francisco, CA",
    "bay area": "San Francisco, CA",
    "sf bay area": "San Francisco, CA",
    "dc": "Washington, DC",
    "washington dc": "Washington, DC",
    "d.c.": "Washington, DC",
    "philly": "Philadelphia, PA",
    "atx": "Austin, TX",
    "chi": "Chicago, IL",
    "atl": "Atlanta, GA",
    "bos": "Boston, MA",
    "sea": "Seattle, WA",
    "pdx": "Portland, OR",
    "phx": "Phoenix, AZ",
    "dfw": "Dallas, TX",
    "nola": "New Orleans, LA",
}


def haversine_distance_miles(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance between two points, in miles.

    Straight-line distance, not driving distance -- deliberately. Driving
    distance needs a routing service (network, API key, rate limits) to
    refine a number that only ever feeds a coarse "within N miles"
    question. Real road mileage runs roughly 1.2-1.4x this in US metros,
    so treat a 25-mile radius as "about a 30-mile drive".
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(min(1.0, a)))


@functools.lru_cache(maxsize=1)
def _zip_index() -> dict:
    """ZIP -> [lat, lon]. Decompressed once per process, on first use."""
    return _load_index("us_zipcodes.json.gz")


@functools.lru_cache(maxsize=1)
def _city_index() -> dict:
    """ "city,st" -> [lat, lon]. Loaded separately from the ZIP index so a
    ZIP-only lookup never pays to decompress cities it will not read."""
    return _load_index("us_cities.json.gz")


def _load_index(filename: str) -> dict:
    path = os.path.join(ASSETS_DIR, filename)
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        # Missing or corrupt bundled data degrades to "cannot resolve"
        # rather than crashing a scan. Callers already handle None, and a
        # location filter that cannot answer must not take the pipeline
        # down with it.
        return {}


def get_zip_centroid(zip_code: str) -> list | None:
    """Returns [lat, lon] for a 5-digit US ZIP, or None if unknown."""
    if not zip_code:
        return None
    match = _ZIP_RE.search(str(zip_code).strip())
    if not match:
        return None
    return _zip_index().get(match.group(1))


def get_city_centroid(city: str, state: str) -> list | None:
    """Returns [lat, lon] for a US city, or None if unknown.

    `state` accepts either a postal code ("TX") or a full name ("Texas").
    """
    if not city or not state:
        return None
    state_key = state.strip().lower()
    state_key = _STATE_NAMES.get(state_key, state_key)
    if state_key not in _STATE_CODES:
        return None
    return _city_index().get(f"{city.strip().lower()},{state_key}")


def resolve_location(text: str) -> list | None:
    """Best-effort single-point resolution of one location string.

    Returns [lat, lon], or None when the string does not name exactly one
    resolvable US place. None is a real answer meaning "unknown", never
    "far away" -- callers must not treat it as a large distance.

    Handles, in order of confidence:
      "78701"                 -> ZIP centroid
      "Austin, TX 78701"      -> ZIP centroid (most precise token wins)
      "Austin, TX"            -> city centroid
      "Austin, Texas"         -> city centroid
    Anything else -- bare city names with no state, metro phrases, and
    non-US locations -- returns None by design.
    """
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()

    alias = _METRO_ALIASES.get(raw.lower().strip(" .,"))
    if alias:
        raw = alias

    # A ZIP is unambiguous, so prefer it wherever it appears.
    centroid = get_zip_centroid(raw)
    if centroid:
        return centroid

    # "City, ST" -- take the last two comma-separated parts so a leading
    # qualifier ("Downtown, Austin, TX") does not defeat the match.
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2:
        city, state = parts[-2], parts[-1]
        # Trailing country tokens are common: "Austin, TX, USA".
        if state.lower() in {"usa", "us", "u.s.", "u.s.a.", "united states"}:
            if len(parts) >= 3:
                city, state = parts[-3], parts[-2]
            else:
                return None
        # A state field can carry a trailing ZIP: "Austin, TX 78701".
        state = re.sub(r"\s*\d{5}(?:-\d{4})?$", "", state).strip()
        return get_city_centroid(city, state)

    return None


def distance_between(origin: str, destination: str) -> float | None:
    """Miles between two location strings, or None if either is unresolvable."""
    a = resolve_location(origin)
    b = resolve_location(destination)
    if not a or not b:
        return None
    return haversine_distance_miles(a[0], a[1], b[0], b[1])
