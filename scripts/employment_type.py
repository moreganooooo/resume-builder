"""employment_type.py -- normalize the provider field, then gate on it.

WHY THIS IS A SEPARATE MODULE FROM content_filters.py

content_filters.py reads the posting's BODY and infers. This reads a
STRUCTURED field the provider already published and does not infer at
all. That is the whole reason employment type can be gated at scan time
with confidence while role track cannot: measured across 24 boards per
provider, employment-type coverage has near-zero variance
(greenhouse 0/0/0%, lever 94/100/100%, ashby 100/100/100%) because it is
a property of the provider's SCHEMA. Salary, by contrast, spans 0-100%
on every provider -- it is a property of the employer's disclosure
habit -- which is why no equivalent salary gate lives here.

THE VOCABULARY IS UNBOUNDED, SO MATCHING IS SUBSTRING, NOT EQUALITY

Seven mutually incompatible spellings of "full time" were observed:
`FullTime` (ashby), `Full-time` (lever, workable), `Full Time`
(himalayas), `full_time` (remotive), `Full-time, Contract` (jobright,
comma-joined), `['Full-Time']` (jobicy, list-wrapped), `Full time`
(workday). And lever's `commitment` is employer-authored FREE TEXT, not
an enum -- `Full Time - Union`, `Full Time - Non-Union`, `Full Time / On
Site` are things employers typed into a box. No fixed mapping can ever
be complete, so:

  * normalize case, separators and container shape BEFORE matching;
  * match on substrings of the normalized form;
  * LOG any value that maps to nothing, so a new variant announces
    itself instead of silently becoming "unknown" and passing the gate.

`Full Time / On Site` also carries a WORKPLACE MODE inside the
employment field. Parsing it as employment type alone would discard that
signal, and handing the whole string to a workplace classifier would
mis-set it. Values are therefore split on separators and each token is
routed to the classifier that understands it -- see
`split_mixed_value()`.

EXCLUSION-ONLY, AND UNKNOWN IS KEPT

Same contract as the location and body gates. A posting whose type
cannot be determined passes: greenhouse publishes the field 0% of the
time, so treating absence as a rejection would silently drop an entire
provider.
"""

from __future__ import annotations

import logging
import re

# The canonical set. Deliberately small and about SCHEDULE/DURATION only;
# workplace mode and seniority are different axes with their own filters.
CANONICAL = (
    "full_time",
    "part_time",
    "contract",
    "contract_to_hire",
    "temporary",
    "internship",
)

# Ordered longest-intent first: "contract to hire" must be tested before
# "contract", and "part time" before "time", or the shorter pattern wins
# and silently mislabels. Each entry is (canonical, patterns...).
_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "contract_to_hire",
        ("contracttohire", "contracttoperm", "temptohire", "temptoperm"),
    ),
    ("internship", ("intern", "internship", "coop", "apprentice", "trainee")),
    ("part_time", ("parttime", "halftime", "partial")),
    (
        "temporary",
        ("temporary", "temp", "fixedterm", "fixedtermcontract", "seasonal", "casual"),
    ),
    (
        "contract",
        ("contract", "contractor", "freelance", "consultant", "b2b", "c2c", "1099"),
    ),
    ("full_time", ("fulltime", "permanent", "regular", "perm")),
)

# Tokens that are NOT an employment type even though providers put them
# in the employment field. Recognized so they are neither mapped nor
# logged as unknown -- an unmapped-value log that cries wolf on "On Site"
# every scan is a log nobody reads.
_WORKPLACE_TOKENS = (
    "onsite",
    "on site",
    "remote",
    "hybrid",
    "inperson",
    "in person",
    "wfh",
    "telecommute",
)

# Employer-authored qualifiers on lever's free-text commitment field.
# "Full Time - Union" is full_time; the union clause is not a type.
_IGNORABLE_QUALIFIERS = (
    "union",
    "nonunion",
    "non union",
    "exempt",
    "nonexempt",
    "salaried",
    "hourly",
    "w2",
    "benefited",
    "eligible",
)

_SPLIT_RE = re.compile(r"[,;/|]| and | or ", re.I)
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")

# Values already logged this process, so a 600-posting scan reports a new
# provider spelling ONCE rather than six hundred times.
_seen_unmapped: set[tuple[str, str]] = set()


def _normalize(text: str) -> str:
    """Case, separators and punctuation out; letters and digits only."""
    return _NORMALIZE_RE.sub("", (text or "").lower())


def split_mixed_value(raw: str) -> list[str]:
    """Split a provider value into tokens, each routable to one classifier.

    `Full Time / On Site` is two facts in one field. Splitting keeps the
    employment half usable without letting the workplace half be parsed
    as a type (or vice versa).
    """
    return [part.strip() for part in _SPLIT_RE.split(raw or "") if part.strip()]


def _flatten(value) -> list[str]:
    """Unwrap the container shapes providers actually use.

    jobicy list-wraps (`['Full-Time']`), jobright comma-joins
    (`Full-time, Contract`), smartrecruiters nests under a label
    (`typeOfEmployment.label`). All three arrive here.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return split_mixed_value(value)
    if isinstance(value, dict):
        # smartrecruiters: {"typeOfEmployment": {"label": "Full-time"}}
        for key in ("label", "name", "text", "value", "commitment"):
            if value.get(key):
                return _flatten(value[key])
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return _flatten(str(value))


def normalize_employment_type(value, provider: str = "") -> list[str]:
    """Provider value -> canonical types. Empty list means "not stated".

    Multi-valued by design: `Full-time, Contract` is a posting offering
    BOTH, and collapsing it to one would misrepresent the posting to a
    filter that accepts only one of them.
    """
    found: list[str] = []
    for token in _flatten(value):
        norm = _normalize(token)
        if not norm:
            continue
        if any(_normalize(w) in norm for w in _WORKPLACE_TOKENS):
            continue  # a workplace mode, handled by location_filter
        if norm in (_normalize(q) for q in _IGNORABLE_QUALIFIERS):
            continue
        matched = None
        for canonical, patterns in _PATTERNS:
            if any(pattern in norm for pattern in patterns):
                matched = canonical
                break
        if matched:
            if matched not in found:
                found.append(matched)
        elif not any(_normalize(q) in norm for q in _IGNORABLE_QUALIFIERS):
            key = (provider or "?", token)
            if key not in _seen_unmapped:
                _seen_unmapped.add(key)
                # Once per distinct value per process. A silent miss here
                # becomes an "unknown" that passes the gate, so the filter
                # would quietly stop filtering as a provider's vocabulary
                # drifts.
                logging.warning(
                    "employment_type: unmapped value %r from provider %r "
                    "-- posting will be treated as unstated and KEPT",
                    token,
                    provider or "unknown",
                )
    return found


def passes_employment_filter(value, config, provider: str = "") -> tuple[bool, str]:
    """Returns (passes, reason). Inert unless `employment_type` is configured.

    Rejects only when the posting states its type AND none of the stated
    types is accepted. A posting offering `Full-time, Contract` passes a
    `[contract]` filter: it really is available as a contract.
    """
    accepted = [str(v).strip().lower() for v in (config or []) if str(v).strip()]
    if not accepted:
        return True, ""
    types = normalize_employment_type(value, provider)
    if not types:
        return True, "employment type not stated; kept for review"
    if any(t in accepted for t in types):
        return True, "/".join(types)
    return False, f"employment type {'/'.join(types)} not in {accepted}"


__all__ = [
    "CANONICAL",
    "normalize_employment_type",
    "passes_employment_filter",
    "split_mixed_value",
]
