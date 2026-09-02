"""content_settings.py -- the Settings editor for the non-location filters.

The counterpart to location_settings.py, for the three gates that are
neither title nor location: the languages the candidate can work in and
the ceiling on a posting's stated travel requirement (both in
content_filters.py, both inferred from body text), plus the accepted
employment types (employment_type.py, read from a structured field the
provider published).

Those two kinds of gate are implemented separately and on purpose -- see
employment_type.py's own docstring -- but they are ONE question to the
person answering it, so they share an editor rather than making someone
hunt through Settings for which menu holds which constraint.

These are personal constraints -- a travel ceiling exists because of
someone's back, not because of a tuning experiment -- so they belong in
Settings where the person they describe can change them, not in a
constant somebody has to open an editor to find.

All three keys live at the TOP LEVEL of scan_filters.yml rather than
inside the `location:` block. Travel is not a location question: a fully
remote role can still require three weeks a month on the road, which is
exactly the case the ceiling exists to catch. Neither is employment type.
"""

from __future__ import annotations

import os
import re

import cli_art
import compensation
import profile_paths
import work_hours
import yaml

# Each key is rewritten in place, so surrounding comments survive an edit.
_LANGUAGES_RE = re.compile(
    r"^languages:[ \t]*\n(?:[ \t]*-[^\n]*\n)*|^languages:[^\n]*\n", re.MULTILINE
)
_TRAVEL_RE = re.compile(r"^max_travel_percent:[^\n]*\n", re.MULTILINE)
_EMPLOYMENT_RE = re.compile(
    r"^employment_type:[ \t]*\n(?:[ \t]*-[^\n]*\n)*|^employment_type:[^\n]*\n",
    re.MULTILINE,
)

# A nested mapping rather than a scalar or a list, so this consumes the
# indented lines under the key. Pay and hours share one block because
# they answer one question -- "what does this role have to be worth?" --
# and splitting them would put the two halves of a part-time decision in
# separate menus.
_COMPENSATION_RE = re.compile(
    r"^compensation:[ \t]*\n(?:[ \t]+[^\n]*\n|[ \t]*\n(?=[ \t]+\S))*",
    re.MULTILINE,
)

_SCORING_WEIGHTS_RE = re.compile(
    r"^scoring_weights:[ \t]*\n(?:[ \t]+[^\n]*\n|[ \t]*\n(?=[ \t]+\S))*",
    re.MULTILINE,
)

# Ordered so the written block reads top to bottom the way someone would
# describe the constraint. Keys are the ones compensation.py and
# work_hours.py read; a key here that neither reads is a setting that
# silently does nothing, which is what the test asserts against.
_COMPENSATION_KEYS = (
    "annual_floor",
    "hourly_floor",
    "require_stated",
    "min_hours_per_week",
    "max_hours_per_week",
)

# Offered in the picker. Deliberately the languages content_filters can
# actually DETECT -- offering a language the detector cannot recognize
# would produce a setting that silently does nothing.
LANGUAGE_LABELS = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
}

# The canonical vocabulary, with labels a person recognizes. Keys must
# match employment_type.CANONICAL exactly -- a type present there but
# missing here is a type the gate can reject and the editor cannot offer,
# which is unfixable from the UI. test_content_settings asserts the two
# agree rather than trusting anyone to remember.
EMPLOYMENT_LABELS = {
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract": "Contract / freelance",
    "contract_to_hire": "Contract-to-hire",
    "temporary": "Temporary / seasonal",
    "internship": "Internship / apprenticeship",
}

TRAVEL_CHOICES = [
    (0, "None -- only postings that say no travel"),
    (10, "Up to 10% -- occasional, a few trips a year"),
    (25, "Up to 25% -- about one week a month"),
    (50, "Up to 50% -- half your time on the road"),
]

# Unlike everything above, these don't decide which postings survive
# scanning -- they tune how already-surviving postings get RANKED by
# orchestrator.fit_composite_score()/evaluate_fit()'s prestige/funnel
# calibration. Kept in this file because scan_filters.yml is the one
# place per-profile filtering config lives, but exposed through its own
# Settings entry (run_scoring_weights_settings(), not folded into
# run_content_settings()) since "how stress signals affect ranking" is a
# different kind of decision than "what postings to admit at all".
_SCORING_WEIGHTS_KEYS = (
    "stress_signal_penalty_per_category",
    "stress_signal_max_penalty",
    "low_stress_bonus",
    "stretch_gap_penalty_per_item",
    "stretch_gap_max_penalty",
    "funnel_friction_nudge",
)

# Mirrors orchestrator.py's hardcoded module constants exactly, so an
# unedited scan_filters.yml produces identical scoring to before this
# setting existed.
DEFAULT_SCORING_WEIGHTS = {
    "stress_signal_penalty_per_category": 0.25,
    "stress_signal_max_penalty": 0.75,
    "low_stress_bonus": 0.40,
    "stretch_gap_penalty_per_item": 0.20,
    "stretch_gap_max_penalty": 0.80,
    "funnel_friction_nudge": 1,
}

SCORING_WEIGHT_LABELS = {
    "stress_signal_penalty_per_category": "Penalty per detected stress-signal category",
    "stress_signal_max_penalty": "Max total stress-signal penalty",
    "low_stress_bonus": "Bonus for zero detected stress signals",
    "stretch_gap_penalty_per_item": "Penalty per capability gap",
    "stretch_gap_max_penalty": "Max total capability-gap penalty",
    "funnel_friction_nudge": "Remote/onsite funnel-friction nudge (+/-)",
}


def scan_filters_path(profile: str | None = None) -> str:
    root = profile_paths.profile_root(profile or profile_paths.active_profile())
    return os.path.join(root, "board_scanner", "scan_filters.yml")


def read_settings(path: str | None = None) -> dict:
    """Returns {"languages": [...], "max_travel_percent": N}, keys absent when unset."""
    path = path or scan_filters_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    settings = {}
    languages = data.get("languages")
    if isinstance(languages, list) and languages:
        settings["languages"] = [str(code).strip().lower() for code in languages]
    ceiling = data.get("max_travel_percent")
    if isinstance(ceiling, int):
        settings["max_travel_percent"] = ceiling
    employment = data.get("employment_type")
    if isinstance(employment, list) and employment:
        settings["employment_type"] = [
            str(value).strip().lower() for value in employment
        ]
    pay = data.get("compensation")
    if isinstance(pay, dict):
        # Only the keys the gates actually read, so a stray key in the
        # file cannot round-trip through the editor and look supported.
        kept = {k: pay[k] for k in _COMPENSATION_KEYS if pay.get(k) not in (None, "")}
        if kept:
            settings["compensation"] = kept
    weights = data.get("scoring_weights")
    if isinstance(weights, dict):
        kept = {
            k: weights[k]
            for k in _SCORING_WEIGHTS_KEYS
            if weights.get(k) not in (None, "")
        }
        if kept:
            settings["scoring_weights"] = kept
    return settings


def read_scoring_weights(path: str | None = None) -> dict:
    """DEFAULT_SCORING_WEIGHTS merged with any profile override -- what
    orchestrator.py actually reads. Always returns all six keys, so a
    caller never has to fall back itself."""
    overrides = read_settings(path).get("scoring_weights") or {}
    merged = dict(DEFAULT_SCORING_WEIGHTS)
    merged.update(overrides)
    return merged


def describe_scoring_weights(weights: dict | None) -> str:
    """One line for the menu header -- only mentions keys that differ
    from the default, since the common case is "unedited"."""
    weights = weights or {}
    changed = [
        f"{key}={weights[key]}"
        for key in _SCORING_WEIGHTS_KEYS
        if key in weights and weights[key] != DEFAULT_SCORING_WEIGHTS[key]
    ]
    return ", ".join(changed) if changed else "defaults (unedited)"


def describe(settings: dict) -> str:
    """One line for the menu header."""
    parts = []
    languages = settings.get("languages")
    if languages:
        parts.append(
            "languages: "
            + ", ".join(LANGUAGE_LABELS.get(code) or code for code in languages)
        )
    else:
        parts.append("languages: any")
    ceiling = settings.get("max_travel_percent")
    parts.append(f"travel: up to {ceiling}%" if ceiling is not None else "travel: any")
    employment = settings.get("employment_type")
    if employment:
        parts.append(
            "types: "
            + ", ".join(EMPLOYMENT_LABELS.get(value) or value for value in employment)
        )
    else:
        parts.append("types: any")
    parts.append("pay: " + (describe_pay(settings.get("compensation")) or "any"))
    hours = work_hours.describe_range(settings.get("compensation") or {})
    if hours:
        parts.append(f"hours: {hours}")
    return "; ".join(parts)


def describe_pay(pay: dict | None) -> str:
    """The floor as a phrase, or '' when no floor is set.

    Both floors are shown when both are set, because they are two
    expressions of one bar and hiding either would make the effective
    threshold (the LOWER of them -- see compensation.floor_to_annual)
    impossible to predict from the UI.
    """
    pay = pay or {}
    bits = []
    annual = pay.get("annual_floor")
    hourly = pay.get("hourly_floor")
    if isinstance(annual, (int, float)) and annual > 0:
        bits.append(f"${annual:,.0f}/yr")
    if isinstance(hourly, (int, float)) and hourly > 0:
        bits.append(f"${hourly:g}/hr")
    if not bits:
        return ""
    phrase = " or ".join(bits) + " minimum"
    if pay.get("require_stated"):
        phrase += " (must be stated)"
    return phrase


def _replace_or_append(original: str, pattern: re.Pattern, block: str) -> str:
    """Rewrite a key in place, or append it when absent.

    In place matters: scan_filters.yml carries explanatory comments above
    these keys, and regenerating the file would discard them.
    """
    if pattern.search(original):
        return pattern.sub(block, original, count=1)
    return original.rstrip("\n") + "\n" + block


def _scalar_default(value) -> str:
    """Prefill a text prompt without showing a float's trailing '.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _parse_money(raw: str) -> float | None:
    """Read '$40,000', '40000', '40k' or '20' as a number.

    People type the dollar sign and the comma because that is how the
    amount is written everywhere else in the app; refusing those would
    make the prompt feel broken. Returns None when there is no number,
    which the caller distinguishes from a deliberately blank answer.
    """
    cleaned = re.sub(r"[\s$,]", "", raw or "")
    if not cleaned:
        return None
    multiplier = 1000.0 if cleaned[-1:].lower() == "k" else 1.0
    if multiplier != 1.0:
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _yaml_scalar(value) -> str:
    """Booleans must render as YAML's `true`, not Python's `True`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_settings(settings: dict, path: str | None = None) -> None:
    """Writes all three keys, removing any whose value is absent or empty."""
    path = path or scan_filters_path()
    with open(path, "r", encoding="utf-8") as handle:
        updated = handle.read()

    languages = settings.get("languages")
    if languages:
        block = "languages:\n" + "".join(f"- {code}\n" for code in languages)
        updated = _replace_or_append(updated, _LANGUAGES_RE, block)
    else:
        updated = _LANGUAGES_RE.sub("", updated, count=1)

    ceiling = settings.get("max_travel_percent")
    if ceiling is not None:
        updated = _replace_or_append(
            updated, _TRAVEL_RE, f"max_travel_percent: {int(ceiling)}\n"
        )
    else:
        updated = _TRAVEL_RE.sub("", updated, count=1)

    employment = settings.get("employment_type")
    if employment:
        block = "employment_type:\n" + "".join(f"- {value}\n" for value in employment)
        updated = _replace_or_append(updated, _EMPLOYMENT_RE, block)
    else:
        updated = _EMPLOYMENT_RE.sub("", updated, count=1)

    pay = settings.get("compensation") or {}
    pay = {k: pay[k] for k in _COMPENSATION_KEYS if pay.get(k) not in (None, "")}
    if pay:
        block = "compensation:\n" + "".join(
            f"  {key}: {_yaml_scalar(pay[key])}\n"
            for key in _COMPENSATION_KEYS
            if key in pay
        )
        updated = _replace_or_append(updated, _COMPENSATION_RE, block)
    else:
        updated = _COMPENSATION_RE.sub("", updated, count=1)

    weights = settings.get("scoring_weights") or {}
    weights = {
        k: weights[k] for k in _SCORING_WEIGHTS_KEYS if weights.get(k) not in (None, "")
    }
    if weights:
        block = "scoring_weights:\n" + "".join(
            f"  {key}: {_yaml_scalar(weights[key])}\n"
            for key in _SCORING_WEIGHTS_KEYS
            if key in weights
        )
        updated = _replace_or_append(updated, _SCORING_WEIGHTS_RE, block)
    else:
        updated = _SCORING_WEIGHTS_RE.sub("", updated, count=1)

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)


def run_content_settings() -> None:
    """Interactive editor for the language and travel filters."""
    import questionary

    path = scan_filters_path()
    if not os.path.exists(path):
        cli_art.console.print(
            f"{cli_art.WARNING} No scan_filters.yml for this profile yet.",
            soft_wrap=True,
        )
        return

    current = read_settings(path)
    cli_art.console.print(
        f"\n  Current content filters: [cyan]{describe(current)}[/cyan]\n",
        soft_wrap=True,
    )

    action = cli_art.select(
        "Language & travel:",
        choices=[
            questionary.Choice("Set the languages I can work in", value="languages"),
            questionary.Choice("Set my maximum travel percentage", value="travel"),
            questionary.Choice(
                "Set the employment types I'll accept", value="employment"
            ),
            questionary.Choice("Set my minimum pay", value="pay"),
            questionary.Choice("Set my weekly hours range", value="hours"),
            questionary.Choice("Turn off language filtering", value="clear_languages"),
            questionary.Choice("Turn off travel filtering", value="clear_travel"),
            questionary.Choice(
                "Turn off employment-type filtering", value="clear_employment"
            ),
            questionary.Choice("Turn off pay filtering", value="clear_pay"),
            questionary.Choice("Turn off hours filtering", value="clear_hours"),
            questionary.Choice("Back", value="back"),
        ],
    )
    if action in (None, "back"):
        return

    if action == "languages":
        selected = current.get("languages") or ["en"]
        picked = cli_art.checkbox(
            "Which languages can you work in?",
            choices=[
                questionary.Choice(label, value=code, checked=code in selected)
                for code, label in LANGUAGE_LABELS.items()
            ],
        )
        if not picked:
            # An empty list would read as "no languages", which would
            # reject everything. Refuse rather than write it.
            cli_art.console.print(
                f"{cli_art.WARNING} Pick at least one language, or use "
                "'Turn off language filtering'.",
                soft_wrap=True,
            )
            return
        current["languages"] = list(picked)

    elif action == "travel":
        picked = cli_art.select(
            "How much travel are you willing to do?",
            choices=[
                questionary.Choice(label, value=value)
                for value, label in TRAVEL_CHOICES
            ],
        )
        if picked is None:
            return
        current["max_travel_percent"] = picked

    elif action == "employment":
        selected = current.get("employment_type") or list(EMPLOYMENT_LABELS)
        picked = cli_art.checkbox(
            "Which kinds of work will you accept?",
            choices=[
                questionary.Choice(label, value=value, checked=value in selected)
                for value, label in EMPLOYMENT_LABELS.items()
            ],
        )
        if not picked:
            # Same reasoning as languages: an empty list reads as "no
            # types accepted", which would reject every posting that
            # states one.
            cli_art.console.print(
                f"{cli_art.WARNING} Pick at least one type, or use "
                "'Turn off employment-type filtering'.",
                soft_wrap=True,
            )
            return
        current["employment_type"] = list(picked)

    elif action == "pay":
        pay = dict(current.get("compensation") or {})
        annual = cli_art.text(
            "Minimum yearly salary (blank for none):",
            default=_scalar_default(pay.get("annual_floor")),
        )
        if annual is None:
            return
        hourly = cli_art.text(
            "Minimum hourly rate (blank for none):",
            default=_scalar_default(pay.get("hourly_floor")),
        )
        if hourly is None:
            return
        parsed_annual = _parse_money(annual)
        parsed_hourly = _parse_money(hourly)
        if annual.strip() and parsed_annual is None:
            cli_art.console.print(
                f"{cli_art.WARNING} Couldn't read {annual!r} as an amount.",
                soft_wrap=True,
            )
            return
        if hourly.strip() and parsed_hourly is None:
            cli_art.console.print(
                f"{cli_art.WARNING} Couldn't read {hourly!r} as an amount.",
                soft_wrap=True,
            )
            return
        pay.pop("annual_floor", None)
        pay.pop("hourly_floor", None)
        if parsed_annual:
            pay["annual_floor"] = parsed_annual
        if parsed_hourly:
            pay["hourly_floor"] = parsed_hourly
        current["compensation"] = pay

    elif action == "hours":
        pay = dict(current.get("compensation") or {})
        low = cli_art.text(
            "Fewest hours per week you'd accept (blank for none):",
            default=_scalar_default(pay.get("min_hours_per_week")),
        )
        if low is None:
            return
        high = cli_art.text(
            "Most hours per week you'd accept (blank for none):",
            default=_scalar_default(pay.get("max_hours_per_week")),
        )
        if high is None:
            return
        parsed_low = _parse_money(low)
        parsed_high = _parse_money(high)
        if parsed_low and parsed_high and parsed_low > parsed_high:
            cli_art.console.print(
                f"{cli_art.WARNING} {parsed_low:g} is more than {parsed_high:g} -- "
                "the fewest hours has to be the smaller number.",
                soft_wrap=True,
            )
            return
        pay.pop("min_hours_per_week", None)
        pay.pop("max_hours_per_week", None)
        if parsed_low:
            pay["min_hours_per_week"] = parsed_low
        if parsed_high:
            pay["max_hours_per_week"] = parsed_high
        current["compensation"] = pay

    elif action == "clear_pay":
        pay = dict(current.get("compensation") or {})
        pay.pop("annual_floor", None)
        pay.pop("hourly_floor", None)
        pay.pop("require_stated", None)
        current["compensation"] = pay

    elif action == "clear_hours":
        pay = dict(current.get("compensation") or {})
        pay.pop("min_hours_per_week", None)
        pay.pop("max_hours_per_week", None)
        current["compensation"] = pay

    elif action == "clear_languages":
        current.pop("languages", None)

    elif action == "clear_travel":
        current.pop("max_travel_percent", None)

    elif action == "clear_employment":
        current.pop("employment_type", None)

    write_settings(current, path)
    cli_art.console.print(
        f"{cli_art.SUCCESS} Content filters: {describe(read_settings(path))}",
        soft_wrap=True,
    )

    if current.get("employment_type"):
        # The same honesty as the travel note below. Greenhouse -- the
        # largest ATS source in this corpus -- publishes no employment
        # field at all, so this gate is silent on those postings by
        # design rather than by accident.
        cli_art.console.print(
            "  [dim]Note: postings that don't state an employment type are "
            "always kept. Some sources (Greenhouse especially) never publish "
            "one, so this only drops postings that name a type you excluded."
            "[/dim]",
            soft_wrap=True,
        )

    pay = current.get("compensation") or {}
    if pay.get("annual_floor") or pay.get("hourly_floor"):
        # The most important note of the three, because this filter's
        # name overpromises hardest -- see compensation.describe_bias.
        # A floor narrows the disclosing minority, not the whole list.
        cli_art.console.print(
            f"  [dim]Note: {compensation.describe_bias(0.27)}[/dim]",
            soft_wrap=True,
        )

    if pay.get("min_hours_per_week") or pay.get("max_hours_per_week"):
        # Stated even more plainly than the pay note: 2% is low enough
        # that someone could reasonably think the setting is broken.
        cli_art.console.print(
            "  [dim]Note: only about 2% of postings state weekly hours -- but "
            "about a quarter of PART-TIME ones do, which is where this "
            "actually earns its keep. Postings that state none are kept.[/dim]",
            soft_wrap=True,
        )

    ceiling = current.get("max_travel_percent")
    if ceiling is not None:
        # State the limit of the thing they just turned on. Only ~5% of
        # postings state a travel figure, and a filter silently doing
        # nothing on the other 95% is worth saying out loud once.
        cli_art.console.print(
            "  [dim]Note: postings that state no travel requirement are always "
            "kept -- about 95% of them. This only drops postings that name a "
            "figure above your ceiling.[/dim]",
            soft_wrap=True,
        )


def run_scoring_weights_settings() -> None:
    """Interactive editor for the composite-score tuning constants.

    Separate menu from run_content_settings() on purpose -- these don't
    gate which postings survive scanning, they tune how already-
    surviving postings get ranked, which is a different kind of decision.
    """
    path = scan_filters_path()
    if not os.path.exists(path):
        cli_art.console.print(
            f"{cli_art.WARNING} No scan_filters.yml for this profile yet.",
            soft_wrap=True,
        )
        return

    current = read_settings(path)
    weights = dict(current.get("scoring_weights") or {})
    cli_art.console.print(
        f"\n  Current scoring weights: [cyan]{describe_scoring_weights(weights)}[/cyan]\n",
        soft_wrap=True,
    )

    import questionary

    action = cli_art.select(
        "Scoring weights & preferences:",
        choices=[
            questionary.Choice(
                f"Edit: {SCORING_WEIGHT_LABELS[key]} "
                f"(currently {weights.get(key, DEFAULT_SCORING_WEIGHTS[key])})",
                value=key,
            )
            for key in _SCORING_WEIGHTS_KEYS
        ]
        + [
            questionary.Choice("Reset all to defaults", value="reset"),
            questionary.Choice("Back", value="back"),
        ],
    )
    if action in (None, "back"):
        return

    if action == "reset":
        current.pop("scoring_weights", None)
        write_settings(current, path)
        cli_art.console.print(
            f"{cli_art.SUCCESS} Scoring weights reset to defaults.", soft_wrap=True
        )
        return

    key = action
    default = DEFAULT_SCORING_WEIGHTS[key]
    raw = cli_art.text(
        f"{SCORING_WEIGHT_LABELS[key]} (blank for default {default}):",
        default=_scalar_default(weights.get(key)),
    )
    if raw is None:
        return
    if not raw.strip():
        weights.pop(key, None)
    else:
        try:
            parsed = float(raw)
        except ValueError:
            cli_art.console.print(
                f"{cli_art.WARNING} Couldn't read {raw!r} as a number.",
                soft_wrap=True,
            )
            return
        weights[key] = parsed

    current["scoring_weights"] = weights
    write_settings(current, path)
    cli_art.console.print(
        f"{cli_art.SUCCESS} Scoring weights: "
        f"{describe_scoring_weights(read_settings(path).get('scoring_weights'))}",
        soft_wrap=True,
    )


__all__ = [
    "DEFAULT_SCORING_WEIGHTS",
    "EMPLOYMENT_LABELS",
    "SCORING_WEIGHT_LABELS",
    "describe_pay",
    "describe_scoring_weights",
    "LANGUAGE_LABELS",
    "TRAVEL_CHOICES",
    "describe",
    "read_scoring_weights",
    "read_settings",
    "run_content_settings",
    "run_scoring_weights_settings",
    "scan_filters_path",
    "write_settings",
]
