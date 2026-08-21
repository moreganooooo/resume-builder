"""
location_filter.py -- the tiered location/workplace verdict for scanning.

Owns ONE question, asked once per raw posting at scan time: given this
posting's stated location, does the candidate want to see it at all?

Where this sits, and why there is only one of it:

  scan_boards._passes_location_filter()  <- the single chokepoint; both
      scan_boards.py and scan_ats.py route every raw posting through it,
      so delegating from there covers both scanners without either one
      growing its own copy of this logic.

  prefilter.evaluate_preflight_gate()    <- NOT this. That reads the JD
      *body prose* at batch-sweep time for deal-breaker phrases ("100%
      on-site"), which is a different input at a different stage. It is
      a downstream safety net, not a location resolver, and stays as-is.

  geo_distance.py                        <- pure math and point lookup.
      This module decides; that one measures.

Opt-in by design. With no `location:` block in scan_filters.yml, this
falls straight back to the historical always_allow/block keyword
behavior, byte for byte. That matters: the keyword `block:` list rejects
"Onsite"/"Hybrid" outright, so until a radius is actually configured
there is nothing to stop a nationwide flood of onsite postings from
entering the corpus. Configuring `location:` is what both relaxes the
block AND supplies the radius that replaces it -- the two can never be
out of step, because they are the same switch.
"""

from __future__ import annotations

import re

import geo_distance

REMOTE = "remote"
HYBRID = "hybrid"
ONSITE = "onsite"
UNKNOWN = "unknown"
ANY = "any"

# Ordered most-specific first: "hybrid remote" is hybrid, not remote.
_HYBRID_PATTERNS = (
    r"\bhybrid\b",
    r"\d\s*days?\s*(?:per|a)\s*week\s*(?:in|on)[- ]?(?:office|site)",
    r"\bpartially\s+remote\b",
)
_REMOTE_PATTERNS = (
    r"\bremote\b",
    r"\bwork\s+from\s+(?:home|anywhere)\b",
    r"\bwfh\b",
    r"\bwfa\b",
    r"\btele(?:work|commut)\w*\b",
    r"\bdistributed\b",
    r"\banywhere\b",
    r"\bvirtual\b",
    r"\blocation[- ]independent\b",
)
_ONSITE_PATTERNS = (
    r"\bon-?\s?site\b",
    r"\bin-?office\b",
    r"\bin[- ]person\b",
    r"\boffice-?based\b",
)

# "US Remote (Excluding CA, CO, NY)" and friends. Tier 1.
_EXCLUSION_RE = re.compile(
    r"(?:excluding|except|not\s+available\s+in|no\s+applicants?\s+from|"
    r"outside\s+of|excludes)\s*:?\s*([A-Za-z ,\.]+)",
    re.IGNORECASE,
)

# Tier 2: postings that name several hubs at once.
_COMPOUND_SPLIT_RE = re.compile(r"\s+or\s+|\s*\|\s*|\s*;\s*|\s+/\s+", re.IGNORECASE)

_STATE_CODES = {code.upper() for code in geo_distance._STATE_CODES}
_STATE_NAMES = dict(geo_distance._STATE_NAMES)


# Countries and non-US subdivision codes that show up in postings. This
# is not a world atlas -- it only needs to catch the international
# locations a US job search actually surfaces, so that they are rejected
# outright instead of falling through as "unresolvable, keep for review".
_INTERNATIONAL_TOKENS = {
    "uk",
    "u.k.",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "ireland",
    "canada",
    "ca-on",
    "ontario",
    "quebec",
    "bc",
    "british columbia",
    "alberta",
    "germany",
    "france",
    "spain",
    "portugal",
    "italy",
    "netherlands",
    "belgium",
    "poland",
    "romania",
    "sweden",
    "norway",
    "denmark",
    "finland",
    "switzerland",
    "austria",
    "czechia",
    "czech republic",
    "greece",
    "turkey",
    "ukraine",
    "india",
    "china",
    "japan",
    "singapore",
    "australia",
    "new zealand",
    "brazil",
    "mexico",
    "argentina",
    "chile",
    "colombia",
    "israel",
    "south africa",
    "nigeria",
    "kenya",
    "egypt",
    "uae",
    "united arab emirates",
    "philippines",
    "indonesia",
    "malaysia",
    "vietnam",
    "thailand",
    "pakistan",
    "emea",
    "apac",
    "latam",
}

# Canadian province codes look exactly like US state codes, so without
# this "Toronto, ON" parses as an ordinary "City, XX" and sails through
# as merely unresolvable. Checked against the US list: none of these
# collide with a real state code, so matching them is unambiguous.
_INTERNATIONAL_TOKENS |= {
    "on",
    "qc",
    "bc",
    "ab",
    "mb",
    "sk",
    "ns",
    "nb",
    "nl",
    "pe",
    "yt",
    "nt",
    "nu",
}

# Workplace words are not part of a place name. "Hybrid - Kansas City, MO"
# must resolve to Kansas City, or every hybrid posting looks unresolvable
# and silently survives the radius check.
_WORKPLACE_TOKEN_RE = re.compile(
    r"\b(?:hybrid|remote|on-?\s?site|in-?office|in[- ]person|office-?based|"
    r"flexible|wfh)\b",
    re.IGNORECASE,
)


def strip_workplace_tokens(location: str) -> str:
    """Removes workplace-mode words and leftover separators from a location."""
    cleaned = _WORKPLACE_TOKEN_RE.sub(" ", location or "")
    cleaned = re.sub(r"\s*[-–—:]\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ,-")


def looks_international(location: str) -> bool:
    """True when a location names a country/region outside the US.

    Checked before the radius test so an unreachable posting is rejected
    on what it says, rather than passing as merely unresolvable.
    """
    if not location:
        return False
    stripped = re.sub(r"\([^)]*\)", " ", location)
    for part in re.split(r"[,/|;]", stripped):
        token = part.strip().strip(".").lower()
        if token in _INTERNATIONAL_TOKENS:
            return True
    return False


class LocationVerdict:
    """Why a posting passed or failed, not just whether.

    `distance_miles` is None whenever the location could not be resolved
    to a point -- never a sentinel like -1 or a very large number, so a
    caller can never accidentally sort or threshold "unknown" as if it
    were a real measurement.
    """

    def __init__(
        self,
        passes: bool,
        workplace: str = UNKNOWN,
        distance_miles: float | None = None,
        reason: str = "",
    ):
        self.passes = passes
        self.workplace = workplace
        self.distance_miles = distance_miles
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        miles = "?" if self.distance_miles is None else f"{self.distance_miles:.1f}mi"
        return (
            f"<LocationVerdict {'pass' if self.passes else 'reject'} "
            f"{self.workplace} {miles} {self.reason!r}>"
        )


def classify_workplace(
    location: str, is_remote: bool | None = None, work_model: str = ""
) -> str:
    """Returns REMOTE / HYBRID / ONSITE / UNKNOWN for a posting.

    Structured provider fields (`is_remote`, `work_model`) are trusted
    over the free-text location string when present -- a provider that
    tells us outright beats guessing from prose. Hybrid is checked before
    remote because "hybrid remote" and "remote/hybrid" are both common
    and mean hybrid.
    """
    model = (work_model or "").strip().lower()
    if model:
        if any(re.search(p, model) for p in _HYBRID_PATTERNS):
            return HYBRID
        if any(re.search(p, model) for p in _ONSITE_PATTERNS):
            return ONSITE
        if any(re.search(p, model) for p in _REMOTE_PATTERNS):
            return REMOTE

    text = (location or "").strip().lower()
    if any(re.search(p, text) for p in _HYBRID_PATTERNS):
        return HYBRID
    if any(re.search(p, text) for p in _ONSITE_PATTERNS):
        return ONSITE
    if any(re.search(p, text) for p in _REMOTE_PATTERNS):
        return REMOTE

    # Only consulted after the text, which can say "hybrid" on a posting
    # whose provider flagged it remote.
    if is_remote is True:
        return REMOTE
    if is_remote is False and text:
        return ONSITE
    return UNKNOWN


def _normalize_state(token: str) -> str | None:
    """Maps 'CA' / 'California' to an uppercase state code."""
    cleaned = token.strip().strip(".").lower()
    if not cleaned:
        return None
    if cleaned in _STATE_NAMES:
        return _STATE_NAMES[cleaned].upper()
    if cleaned.upper() in _STATE_CODES:
        return cleaned.upper()
    return None


def excluded_states(location: str) -> set:
    """Tier 1 -- states a posting explicitly rules out.

    "US Remote (Excluding CA, CO, NY)" is a real and common shape, and
    silently ignoring it means surfacing roles the candidate cannot
    legally be hired into.
    """
    match = _EXCLUSION_RE.search(location or "")
    if not match:
        return set()
    states = set()
    for token in re.split(r"[,/&]|\band\b", match.group(1)):
        code = _normalize_state(token)
        if code:
            states.add(code)
    return states


def split_hubs(location: str) -> list:
    """Tier 2 -- 'Austin, TX OR Sunnyvale, CA' -> both hubs.

    Splits only on separators that join whole locations. A comma is NOT
    a separator here: it is the city/state delimiter inside one location,
    and splitting on it would shred every ordinary "Austin, TX".
    """
    if not location:
        return []
    # Drop parentheticals so "(Excluding CA, CO)" cannot be read as a hub.
    stripped = re.sub(r"\([^)]*\)", " ", location)
    parts = [p.strip(" ,-") for p in _COMPOUND_SPLIT_RE.split(stripped)]
    return [p for p in parts if p]


def nearest_hub_distance(location: str, origin: str) -> tuple:
    """Returns (miles, hub_text) for the closest resolvable hub, else (None, '').

    A posting listing several offices is as close as its nearest one --
    scoring it by the first or the farthest would hide genuinely
    commutable roles.
    """
    best_miles, best_hub = None, ""
    for hub in split_hubs(location):
        hub_text = strip_workplace_tokens(hub)
        point = geo_distance.resolve_location(hub_text)
        if not point:
            continue
        origin_point = geo_distance.resolve_location(origin)
        if not origin_point:
            return None, ""
        miles = geo_distance.haversine_distance_miles(
            origin_point[0], origin_point[1], point[0], point[1]
        )
        if best_miles is None or miles < best_miles:
            best_miles, best_hub = miles, hub_text
    return best_miles, best_hub


def origin_from_config(config: dict) -> str:
    """Builds a resolvable origin string from a scan_filters `location:` block.

    A ZIP is preferred when given -- it is unambiguous, where a city name
    needs its state to mean anything.
    """
    if not config:
        return ""
    zip_code = str(config.get("zip") or "").strip()
    if zip_code:
        return zip_code
    city = str(config.get("city") or "").strip()
    state = str(config.get("state") or "").strip()
    if city and state:
        return f"{city}, {state}"
    return ""


def evaluate_location(location: str, config: dict, **posting) -> LocationVerdict:
    """The tiered verdict. `config` is scan_filters.yml's `location:` block.

    Callers pass provider-supplied structured hints through **posting
    (`is_remote`, `work_model`) when they have them.
    """
    config = config or {}
    mode = str(config.get("workplace_mode") or ANY).strip().lower()
    radius = config.get("radius_miles")
    origin = origin_from_config(config)

    workplace = classify_workplace(
        location,
        is_remote=posting.get("is_remote"),
        work_model=posting.get("work_model", ""),
    )

    # An empty location has always passed; keep that. Providers routinely
    # omit it at the list-page level, and rejecting those would discard
    # good remote roles for a missing field.
    if not location or not location.strip():
        return LocationVerdict(True, workplace, None, "no location stated")

    # Tier 1: explicit exclusions beat everything, including a remote
    # posting the candidate would otherwise qualify for.
    home_state = _normalize_state(str(config.get("state") or ""))
    if home_state and home_state in excluded_states(location):
        return LocationVerdict(False, workplace, None, f"posting excludes {home_state}")

    if mode not in (ANY, REMOTE, HYBRID, ONSITE):
        mode = ANY

    if mode != ANY and workplace != UNKNOWN and workplace != mode:
        return LocationVerdict(
            False, workplace, None, f"workplace is {workplace}, wanted {mode}"
        )

    if workplace == REMOTE:
        return LocationVerdict(True, REMOTE, None, "remote")

    # A named foreign country is a definite no for an on-site or hybrid
    # role, unlike a merely unparseable string.
    if looks_international(location):
        return LocationVerdict(False, workplace, None, "international location")

    # On-site and hybrid roles are worth seeing only within commuting
    # range, which is the whole point of configuring an origin.
    if origin and radius:
        miles, hub = nearest_hub_distance(location, origin)
        if miles is None:
            # Unresolvable is NOT far. Surfacing an unknown location is a
            # cheap mistake for a human to spot; silently dropping a
            # commutable role is not.
            return LocationVerdict(
                True, workplace, None, "location not resolvable; kept for review"
            )
        if miles > float(radius):
            return LocationVerdict(
                False, workplace, miles, f"{miles:.0f} mi exceeds {radius} mi radius"
            )
        label = f"{miles:.1f} mi" + (f" ({hub})" if hub else "")
        return LocationVerdict(True, workplace, miles, label)

    return LocationVerdict(True, workplace, None, "no radius configured")
