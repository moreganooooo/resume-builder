"""compensation.py -- parse stated pay, then gate on a floor.

WHY THIS IS NOT SHAPED LIKE THE EMPLOYMENT-TYPE GATE

Employment type is a PROVIDER property: coverage per provider barely
varies across boards, because it is in the schema. Salary is an EMPLOYER
property, and coverage spans the full 0-100% range on every provider --
measured on greenhouse alone, Stripe disclosed on 2.8% of postings while
Airbnb disclosed on 67.3%. A twenty-fold spread inside one provider.

That has a consequence worth stating plainly, because it is the main
thing that can mislead someone using this filter:

    With `require_stated: false` -- the safe default -- an unstated
    salary passes. So enforcing a floor does NOT filter neutrally. It
    judges only the postings that DISCLOSE. Turning on a $40k floor does
    not yield "roles paying $40k+". It yields "roles paying $40k+, plus
    every role from an employer that does not publish pay."

The filter is still worth having; it is just not the guarantee its name
suggests, and `describe_bias()` exists so the UI can say so.

WHAT THIS DELIBERATELY DOES NOT DO: DETECT UNPAID ROLES BY KEYWORD

Measured against this profile's own 2,068-posting corpus on 2026-08-31:
the words "unpaid", "volunteer", "stipend", "pro bono" and "equity only"
appear in 241 postings, and ALL 241 are false positives. "Stipend" is a
home-office or wellness BENEFIT (105 hits). "Volunteer" is the company's
volunteering program or its volunteer community (194 hits). The single
"unpaid" in the whole corpus is "paid and unpaid time away from work".

Zero true positives, 241 false positives. A keyword detector for unpaid
work is not a weak signal here, it is an inverted one, and adding it
would reject 12% of a corpus for saying it offers a home-office stipend.
An unpaid role is caught, if at all, by a stated rate below the floor.

COMPARE AGAINST THE MAX, NEVER THE MIN

A $30-95K band clears a $40K floor and is worth seeing. Rejecting on the
minimum would drop every wide range, which is most of them.
"""

from __future__ import annotations

import re

# Hours used to convert an hourly rate to an annual one and back. A
# single shared constant so the two floors cannot drift apart: a user who
# sets $40,000/yr and $20/hr has set nearly the same bar (40k / 2080 =
# $19.23), and the conversion is what makes a posting quoted in the other
# unit comparable at all.
ANNUAL_HOURS = 2080

CANONICAL_PERIODS = ("annual", "hourly", "monthly", "weekly", "daily")

# Multipliers to annualize. Weekly/daily are rare but real (agency and
# contract postings quote them), and a day rate read as an annual salary
# would reject a $600/day contract as though it paid $600 a year.
_TO_ANNUAL = {
    "annual": 1.0,
    "monthly": 12.0,
    "weekly": 52.0,
    "daily": 260.0,
    "hourly": float(ANNUAL_HOURS),
}

_PERIOD_WORDS = (
    ("hourly", r"per\s+hour|/\s*hour|/\s*hr\b|an\s+hour|hourly|\bp/?h\b"),
    ("daily", r"per\s+day|/\s*day|\bdaily\b|per\s+diem"),
    ("weekly", r"per\s+week|/\s*week|\bweekly\b"),
    ("monthly", r"per\s+month|/\s*month|\bmonthly\b|\bpcm\b"),
    (
        "annual",
        r"per\s+year|/\s*year|/\s*yr\b|annually|\bannual\b|per\s+annum|\bsalary\b",
    ),
)

# A money amount, with optional K suffix and optional decimals.
_AMOUNT = r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*([kK])?"

# A dollar figure in a job posting is USUALLY NOT THE SALARY. Measured on
# this profile's corpus, taking the first figure in the body rejected 99
# postings at a $40k floor and essentially every rejection was a benefit:
# "$50 monthly stipend", "$2,000 professional development stipend",
# "$4,000 annual travel stipend". Reported as pay below the floor, those
# would have dropped real jobs for describing their perks -- the same
# inverted signal that ruled out keyword-detecting unpaid work.
#
# So a figure counts only when pay language sits near it AND benefit
# language does not. Both lists are checked against the same context
# window the period is read from.
_PAY_ANCHOR = re.compile(
    r"\b(salary|salaries|compensation|pay\s*(?:range|rate|band|scale)?|base\s*pay"
    r"|base\s*salary|hourly\s*rate|wage|remuneration|earn|paid|pays"
    r"|annualized|per\s+hour|per\s+year|per\s+annum|/\s*hour|/\s*hr\b|/\s*yr\b"
    r"|an\s+hour|hourly|annually)\b",
    re.I,
)

# Checked against the SAME window. "Stipend" is the single biggest source
# of false pay in this corpus (105 hits, none of them salary).
_BENEFIT_NEAR = re.compile(
    r"\b(stipend|allowance|reimburse\w*|budget|discount|credit|donation|match\w*"
    r"|premium|deductible|tuition|401\s*\(?k\)?|hsa|fsa|referral\s+bonus"
    r"|sign(?:ing|-on)\s+bonus|per\s+diem\s+travel|professional\s+development"
    r"|home\s*office|wellness|travel\s+stipend|equipment)\b",
    re.I,
)

# Below this, an "annual" figure is not a salary -- it is a benefit
# amount that happened to sit near the word "annual" ("$4,000 annual
# travel stipend"). Kept well under any plausible full-year wage so it
# cannot reject a real low-paying role; that job belongs to the floor.
_MIN_PLAUSIBLE_ANNUAL = 12_000

# A range, or a single figure. The range form is tried first: on
# "$80,000 - $95,000" the single-figure pattern would match only the
# first number and report a $80k maximum, silently discarding the top of
# the band the max-comparison rule depends on.
_RANGE_RE = re.compile(_AMOUNT + r"\s*(?:-|–|—|to|up\s+to)\s*" + _AMOUNT, re.I)
_SINGLE_RE = re.compile(_AMOUNT)


def _to_number(digits: str, k_suffix: str | None) -> float | None:
    try:
        value = float(digits.replace(",", ""))
    except ValueError:
        return None
    if k_suffix:
        value *= 1000
    return value


def _infer_period(context: str, amount: float, anchor: int | None = None) -> str:
    """Read the period from words near the figure, else from magnitude.

    The NEAREST period word wins, not the first one in the list. The
    window is wide enough to reach a neighboring sentence, and a posting
    that says "$80,000 - $95,000 per year" a line above "20-25 hours per
    week" has both a yearly and a weekly cue in range. Taking them in
    list order read that salary as weekly and annualized it to $4.9M.
    Proximity is the only thing that distinguishes them.

    Magnitude is the fallback, not the primary signal, and the thresholds
    are deliberately far apart: nobody is paid $900/hour and no salary is
    $45/year, so the middle band is where a guess would be wrong and is
    left as "unknown" rather than guessed.
    """
    lowered = context.lower()
    if anchor is None:
        anchor = len(lowered) // 2
    best = None
    for period, pattern in _PERIOD_WORDS:
        for found in re.finditer(pattern, lowered):
            # Distance from the figure to the nearest edge of the cue, so
            # a word just after the amount is not penalized for its length.
            distance = min(abs(found.start() - anchor), abs(found.end() - anchor))
            if best is None or distance < best[0]:
                best = (distance, period)
    if best is not None:
        return best[1]
    if amount >= 1000:
        return "annual"
    if amount <= 500:
        return "hourly"
    return "unknown"


def parse_compensation(
    text: str, window: int = 60, require_anchor: bool = True
) -> dict | None:
    """Extract the first stated pay figure from prose.

    Returns {"min", "max", "period", "annualized_max", "text"} or None
    when nothing is stated. `min`/`max` are `None`-free floats in the
    posting's OWN period; `annualized_max` is what the gate compares, and
    is None when the period could not be determined.

    Only figures with pay language nearby and no benefit language nearby
    are considered, and the first such figure wins. A posting's body
    routinely quotes other money -- a $2,000 professional-development
    stipend, a $4,000 travel allowance -- and taking the first dollar
    amount in the body found a benefit far more often than a salary.

    `require_anchor=False` turns that off, and is for parsing a
    provider's own SALARY FIELD rather than prose. A field whose whole
    purpose is to state pay needs no nearby word proving it is pay --
    ashby's "$100K - $130K" tier summary carries no sentence at all, so
    demanding an anchor would reject every structured free-text field.
    """
    if not text:
        return None

    # Ranges first across the whole body, then singles. On
    # "$80,000 - $95,000" the single-figure pattern matches only the first
    # number and reports an $80k maximum, discarding the top of the band
    # the max-comparison rule depends on.
    for pattern in (_RANGE_RE, _SINGLE_RE):
        for match in pattern.finditer(text):
            start = max(0, match.start() - window)
            context = text[start : match.end() + window]
            if require_anchor and (
                not _PAY_ANCHOR.search(context) or _BENEFIT_NEAR.search(context)
            ):
                continue

            low = _to_number(match.group(1), match.group(2))
            if low is None:
                continue
            if pattern is _RANGE_RE:
                high = _to_number(match.group(3), match.group(4))
                if high is None:
                    continue
                # "$80 - $95K" states the suffix once, on the second
                # figure. Read literally that is an $80/hr-to-$95k range,
                # which is nonsense; the employer meant both in thousands.
                if match.group(4) and not match.group(2) and low < high / 100:
                    low *= 1000
            else:
                high = low
            if high < low:
                low, high = high, low

            period = _infer_period(context, high, anchor=match.start() - start)
            annualized = high * _TO_ANNUAL[period] if period in _TO_ANNUAL else None
            # A figure that annualizes below any plausible wage is a
            # benefit amount that happened to sit near pay language.
            if annualized is not None and annualized < _MIN_PLAUSIBLE_ANNUAL:
                continue

            return {
                "min": low,
                "max": high,
                "period": period,
                "annualized_max": annualized,
                "text": " ".join(match.group(0).split()),
            }
    return None


def normalize_structured(value, period_hint: str = "") -> dict | None:
    """Parse a provider's structured compensation field.

    Providers publish this in incompatible shapes -- a dict with
    min/max/interval (ashby, lever), separate min/max keys (himalayas,
    jobicy), or free text (remotive). Free text falls through to the prose
    parser rather than getting its own half-parser.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        # No anchor required: this IS the pay field.
        return parse_compensation(value, require_anchor=False)
    if isinstance(value, (int, float)):
        amount = float(value)
        period = period_hint if period_hint in _TO_ANNUAL else _infer_period("", amount)
        return {
            "min": amount,
            "max": amount,
            "period": period,
            "annualized_max": (
                amount * _TO_ANNUAL[period] if period in _TO_ANNUAL else None
            ),
            "text": str(value),
        }
    if isinstance(value, dict):
        low = _first_number(
            value, ("minValue", "min", "salaryMin", "minSalary", "from")
        )
        high = _first_number(value, ("maxValue", "max", "salaryMax", "maxSalary", "to"))
        if low is None and high is None:
            return None
        if low is None:
            low = high
        if high is None:
            high = low
        raw_period = ""
        for key in ("interval", "period", "unit", "frequency", "payPeriod"):
            if value.get(key):
                raw_period = str(value[key])
                break
        period = _canonical_period(raw_period) or period_hint or _infer_period("", high)
        return {
            "min": low,
            "max": high,
            "period": period,
            "annualized_max": (
                high * _TO_ANNUAL[period] if period in _TO_ANNUAL else None
            ),
            "text": _format_range(low, high, period),
        }
    return None


def _format_range(low: float, high: float, period: str) -> str:
    """Render a structured range the way a posting would write it.

    The raw numbers are floats, so a naive f-string produces
    "100000.0-130000.0 year", which is not something anyone would
    recognize as a salary in a rejection reason or a dashboard cell.
    """
    suffix = {
        "hourly": "/hr",
        "daily": "/day",
        "weekly": "/wk",
        "monthly": "/mo",
        "annual": "/yr",
    }.get(period, "")
    left, right = f"${low:,.0f}", f"${high:,.0f}"
    return (left if low == high else f"{left}-{right}") + suffix


def _first_number(data: dict, keys) -> float | None:
    for key in keys:
        if data.get(key) not in (None, "", 0):
            try:
                return float(data[key])
            except (TypeError, ValueError):
                continue
    return None


def _canonical_period(raw: str) -> str:
    """Provider period vocabularies, normalized. Same substring approach
    as employment_type, and for the same reason: "YEAR", "yearly",
    "per_year" and "ANNUM" all appear."""
    lowered = re.sub(r"[^a-z]", "", (raw or "").lower())
    if not lowered:
        return ""
    for period, keys in (
        ("hourly", ("hour", "hourly")),
        ("daily", ("day", "daily", "diem")),
        ("weekly", ("week", "weekly")),
        ("monthly", ("month", "monthly")),
        ("annual", ("year", "yearly", "annual", "annum")),
    ):
        if any(key in lowered for key in keys):
            return period
    return ""


def floor_to_annual(config: dict) -> float | None:
    """The single annual number both configured floors reduce to.

    Taking the LOWER of the two is deliberate. A user who sets $40,000/yr
    and $20/hr has set two expressions of one bar, and if they disagree
    slightly the stricter reading would reject postings that satisfy the
    looser floor they also wrote down -- rejecting on a rounding
    difference between two numbers the user considers equivalent.
    """
    candidates = []
    annual = config.get("annual_floor")
    hourly = config.get("hourly_floor")
    if isinstance(annual, (int, float)) and annual > 0:
        candidates.append(float(annual))
    if isinstance(hourly, (int, float)) and hourly > 0:
        candidates.append(float(hourly) * ANNUAL_HOURS)
    return min(candidates) if candidates else None


def evaluate_compensation(text: str, config: dict, structured=None) -> tuple[bool, str]:
    """Returns (passes, reason). Inert unless a floor is configured.

    Structured provider data wins over prose when both exist: the
    employer entered it into a field, rather than it being recovered from
    a sentence that might have been describing a benefit.
    """
    config = config or {}
    floor = floor_to_annual(config)
    if floor is None:
        return True, ""

    parsed = normalize_structured(structured) or parse_compensation(text)
    if not parsed:
        if config.get("require_stated"):
            return False, "no pay stated and require_stated is on"
        return True, "pay not stated; kept for review"

    # An estimated range (Indeed publishes these beside employer-stated
    # ones) must never hard-reject -- it is the aggregator's guess, not a
    # claim by the employer.
    if parsed.get("is_estimated"):
        return True, f"estimated pay {parsed['text']}; not enforced"

    annualized = parsed.get("annualized_max")
    if annualized is None:
        return True, f"pay period unclear in {parsed['text']!r}; kept for review"
    if annualized < floor:
        return False, (
            f"stated pay {parsed['text']} annualizes to ${annualized:,.0f}, "
            f"below the ${floor:,.0f} floor"
        )
    return True, f"stated pay {parsed['text']} clears the floor"


def describe_bias(stated_fraction: float) -> str:
    """One sentence the UI can show beside the setting.

    Exists because the filter's name overpromises. Someone who turns on a
    floor and sees their corpus shrink should know WHICH postings it
    could act on, rather than assuming the survivors all clear the bar.
    """
    return (
        f"Only about {stated_fraction:.0%} of postings state pay at all. "
        "The rest are always kept, so this narrows the disclosing "
        "minority rather than the whole list."
    )


__all__ = [
    "ANNUAL_HOURS",
    "CANONICAL_PERIODS",
    "describe_bias",
    "evaluate_compensation",
    "floor_to_annual",
    "normalize_structured",
    "parse_compensation",
]
