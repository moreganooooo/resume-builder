"""content_settings.py -- the Settings editor for the body-text filters.

The counterpart to location_settings.py, for the two gates in
content_filters.py: the languages the candidate can work in, and the
ceiling on a posting's stated travel requirement.

These are personal constraints -- a travel ceiling exists because of
someone's back, not because of a tuning experiment -- so they belong in
Settings where the person they describe can change them, not in a
constant somebody has to open an editor to find.

Both keys live at the TOP LEVEL of scan_filters.yml rather than inside
the `location:` block. Travel is not a location question: a fully remote
role can still require three weeks a month on the road, which is exactly
the case the ceiling exists to catch.
"""

from __future__ import annotations

import os
import re

import cli_art
import profile_paths
import yaml

# Each key is rewritten in place, so surrounding comments survive an edit.
_LANGUAGES_RE = re.compile(
    r"^languages:[ \t]*\n(?:[ \t]*-[^\n]*\n)*|^languages:[^\n]*\n", re.MULTILINE
)
_TRAVEL_RE = re.compile(r"^max_travel_percent:[^\n]*\n", re.MULTILINE)

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

TRAVEL_CHOICES = [
    (0, "None -- only postings that say no travel"),
    (10, "Up to 10% -- occasional, a few trips a year"),
    (25, "Up to 25% -- about one week a month"),
    (50, "Up to 50% -- half your time on the road"),
]


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
    return settings


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
    return "; ".join(parts)


def _replace_or_append(original: str, pattern: re.Pattern, block: str) -> str:
    """Rewrite a key in place, or append it when absent.

    In place matters: scan_filters.yml carries explanatory comments above
    these keys, and regenerating the file would discard them.
    """
    if pattern.search(original):
        return pattern.sub(block, original, count=1)
    return original.rstrip("\n") + "\n" + block


def write_settings(settings: dict, path: str | None = None) -> None:
    """Writes both keys, removing either one whose value is None."""
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
            questionary.Choice("Turn off language filtering", value="clear_languages"),
            questionary.Choice("Turn off travel filtering", value="clear_travel"),
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

    elif action == "clear_languages":
        current.pop("languages", None)

    elif action == "clear_travel":
        current.pop("max_travel_percent", None)

    write_settings(current, path)
    cli_art.console.print(
        f"{cli_art.SUCCESS} Content filters: {describe(read_settings(path))}",
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


__all__ = [
    "LANGUAGE_LABELS",
    "TRAVEL_CHOICES",
    "describe",
    "read_settings",
    "run_content_settings",
    "scan_filters_path",
    "write_settings",
]
