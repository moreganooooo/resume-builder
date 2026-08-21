"""
location_settings.py -- read/write the `location:` block in a profile's
scan_filters.yml, and the interactive editor behind Settings & Upkeep.

Writes are surgical text edits, NOT a yaml round-trip. scan_filters.yml
carries a lot of load-bearing prose -- the vendored-from-career-ops
history at the top, the note about the block: list standing down when a
radius exists -- and yaml.safe_dump() would silently delete all of it
(see menu._handle_delete_custom_board, which does exactly that). So the
`location:` block is located and replaced in the raw text, and every
other byte of the file is left untouched.

Radius is offered from 5 to 25 miles. Nothing here is specific to one
person's town: the origin is whatever the profile's owner enters, and
every profile gets its own scan_filters.yml.
"""

from __future__ import annotations

import os
import re

import cli_art
import geo_distance
import profile_paths
import yaml

# 5 to 25 miles. A radius is straight-line, so the practical drive is
# roughly 1.2-1.4x these numbers in a US metro.
RADIUS_CHOICES = (5, 10, 15, 20, 25)

REMOTE_MODE, HYBRID_MODE, ONSITE_MODE = "remote", "hybrid", "onsite"

# The three real modes, for the multi-select. "any" is not listed: it is
# what selecting all three (or none) means, rather than a fourth option
# that could be checked alongside them and contradict them.
SELECTABLE_WORKPLACES = (
    (REMOTE_MODE, "Remote"),
    (HYBRID_MODE, "Hybrid"),
    (ONSITE_MODE, "On-site (within the radius)"),
)

WORKPLACE_CHOICES = (
    ("any", "Any -- remote, hybrid, and on-site within the radius"),
    ("remote", "Remote only"),
    ("hybrid", "Hybrid only"),
    ("onsite", "On-site only"),
)

_BLOCK_RE = re.compile(
    r"^location:[ \t]*\n(?:(?:[ \t]+[^\n]*|[ \t]*)\n)*", re.MULTILINE
)


def scan_filters_path(profile: str = None) -> str:
    """The active profile's scan_filters.yml."""
    root = profile_paths.profile_root(profile or profile_paths.active_profile())
    return os.path.join(root, "board_scanner", "scan_filters.yml")


def read_settings(path: str = None) -> dict:
    """Returns the `location:` block, or {} when unconfigured."""
    path = path or scan_filters_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    block = data.get("location")
    return block if isinstance(block, dict) else {}


def render_block(settings: dict) -> str:
    """Serializes a settings dict as the YAML text we write."""
    lines = ["location:"]
    for key in ("city", "state", "zip"):
        value = str(settings.get(key) or "").strip()
        if value:
            # Quote the ZIP so a leading zero survives YAML parsing --
            # 01002 would otherwise load as the integer 1002.
            lines.append(f'  {key}: "{value}"' if key == "zip" else f"  {key}: {value}")
    lines.append(f"  radius_miles: {int(settings.get('radius_miles') or 25)}")
    mode = settings.get("workplace_mode") or "any"
    if isinstance(mode, (list, tuple, set)):
        modes = [str(m).strip().lower() for m in mode if str(m).strip()]
        if len(modes) == 1:
            lines.append(f"  workplace_mode: {modes[0]}")
        elif modes:
            # Inline list: readable, and yaml.safe_load reads it back as
            # the list location_filter.wanted_workplaces() expects.
            lines.append(f"  workplace_mode: [{', '.join(sorted(modes))}]")
        else:
            lines.append("  workplace_mode: any")
    else:
        lines.append(f"  workplace_mode: {mode}")
    return "\n".join(lines) + "\n"


def write_settings(settings: dict, path: str = None) -> None:
    """Replaces (or inserts) the `location:` block, preserving comments."""
    path = path or scan_filters_path()
    with open(path, "r", encoding="utf-8") as handle:
        original = handle.read()

    block = render_block(settings)
    if _BLOCK_RE.search(original):
        updated = _BLOCK_RE.sub(block, original, count=1)
    elif "\nlocation_filter:" in original:
        # Sits directly above the keyword lists it supersedes, where a
        # reader looking for location behavior will find both together.
        updated = original.replace(
            "\nlocation_filter:", f"\n{block}\nlocation_filter:", 1
        )
    else:
        updated = original.rstrip("\n") + "\n\n" + block

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(updated)


def clear_settings(path: str = None) -> None:
    """Removes the block entirely, returning to keyword-only filtering."""
    path = path or scan_filters_path()
    with open(path, "r", encoding="utf-8") as handle:
        original = handle.read()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_BLOCK_RE.sub("", original, count=1))


def describe(settings: dict) -> str:
    """One-line human summary for menu labels and confirmations."""
    if not settings:
        return "not configured (keyword filtering only)"
    origin = settings.get("zip") or ", ".join(
        p for p in (settings.get("city"), settings.get("state")) if p
    )
    raw = settings.get("workplace_mode") or "any"
    modes = raw if isinstance(raw, (list, tuple, set)) else [raw]
    modes = sorted(str(m).strip().lower() for m in modes if str(m).strip())
    label = "any" if (not modes or "any" in modes) else "+".join(modes)

    # Radius is only meaningful when something commutable is wanted.
    if label == "remote":
        return f"{origin or 'no origin'} -- remote only"
    return f"{origin or 'no origin'} -- {settings.get('radius_miles', 25)} mi, {label}"


def validate_origin(city: str, state: str, zip_code: str) -> tuple:
    """Returns (ok, message). An origin that cannot be resolved offline
    is rejected at entry rather than silently disabling every distance
    check later, which would look like the filter simply not working."""
    if zip_code.strip():
        if geo_distance.get_zip_centroid(zip_code):
            return True, ""
        return False, f"ZIP {zip_code.strip()} is not in the offline index."
    if city.strip() and state.strip():
        if geo_distance.get_city_centroid(city, state):
            return True, ""
        return False, f"Could not resolve {city.strip()}, {state.strip()}."
    return False, "Enter either a ZIP code, or a city and state."


def _prompt_workplace_modes(current) -> list | None:
    """Asks which workplace types to keep, allowing a combination.

    A checkbox rather than a single select because the useful answer is
    often two of three -- happy to work remotely OR to commute in, but
    not to be on a hybrid schedule -- which no single value can say.
    Selecting all three (or none) is stored as "any".
    """
    import questionary

    raw = current if isinstance(current, (list, tuple, set)) else [current]
    selected = {str(m).strip().lower() for m in raw if str(m).strip()}
    if "any" in selected or not selected:
        selected = {REMOTE_MODE, HYBRID_MODE, ONSITE_MODE}

    choices = [
        questionary.Choice(label, value=value, checked=value in selected)
        for value, label in SELECTABLE_WORKPLACES
    ]
    picked = cli_art.checkbox(
        "Which types of roles should scans keep? (space to toggle)", choices=choices
    )
    if picked is None:
        return None
    if not picked or set(picked) == {REMOTE_MODE, HYBRID_MODE, ONSITE_MODE}:
        return ["any"]
    return sorted(picked)


def _radius_choices(current: int) -> list:
    import questionary

    return [
        questionary.Choice(
            f"{miles} miles" + ("  (current)" if miles == current else ""),
            value=miles,
        )
        for miles in RADIUS_CHOICES
    ]


def run_location_settings() -> None:
    """Interactive editor for the radius/workplace filter."""
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
        f"\n  Current location filter: [cyan]{describe(current)}[/cyan]\n",
        soft_wrap=True,
    )

    action = cli_art.select(
        "Location & commute radius:",
        choices=[
            questionary.Choice("Set or change my location", value="set"),
            questionary.Choice("Change commute radius only", value="radius"),
            questionary.Choice("Change workplace type only", value="mode"),
            questionary.Choice(
                "Turn off distance filtering (keyword only)", value="clear"
            ),
            questionary.Choice("Back", value="back"),
        ],
    )
    if action in (None, "back"):
        return

    if action == "clear":
        if cli_art.confirm_destructive(
            "Turn off", "distance filtering for this profile"
        ):
            clear_settings(path)
            cli_art.console.print(
                f"{cli_art.SUCCESS} Distance filtering off; keyword filtering resumes.",
                soft_wrap=True,
            )
        return

    if action == "radius":
        if not current:
            cli_art.console.print(
                f"{cli_art.WARNING} Set a location first.", soft_wrap=True
            )
            return
        miles = cli_art.select(
            "Commute radius (straight-line; a real drive runs ~1.2-1.4x this):",
            choices=_radius_choices(current.get("radius_miles")),
        )
        if miles is None:
            return
        current["radius_miles"] = miles
        write_settings(current, path)
        cli_art.console.print(
            f"{cli_art.SUCCESS} Radius set to {miles} miles.", soft_wrap=True
        )
        return

    if action == "mode":
        if not current:
            cli_art.console.print(
                f"{cli_art.WARNING} Set a location first.", soft_wrap=True
            )
            return
        mode = _prompt_workplace_modes(current.get("workplace_mode"))
        if mode is None:
            return
        current["workplace_mode"] = mode
        write_settings(current, path)
        cli_art.console.print(
            f"{cli_art.SUCCESS} Workplace filter: {describe(current)}.", soft_wrap=True
        )
        return

    # action == "set"
    cli_art.console.print(
        "  A ZIP code is the most precise origin. City and state also work.\n",
        soft_wrap=True,
    )
    zip_code = (
        cli_art.text(
            "ZIP code (blank to use city/state):", default=str(current.get("zip") or "")
        )
        or ""
    )
    city = state = ""
    if not zip_code.strip():
        city = cli_art.text("City:", default=str(current.get("city") or "")) or ""
        state = (
            cli_art.text("State (e.g. NY):", default=str(current.get("state") or ""))
            or ""
        )

    ok, message = validate_origin(city, state, zip_code)
    if not ok:
        cli_art.console.print(f"{cli_art.WARNING} {message}", soft_wrap=True)
        return

    miles = cli_art.select(
        "Commute radius (straight-line; a real drive runs ~1.2-1.4x this):",
        choices=_radius_choices(current.get("radius_miles")),
    )
    if miles is None:
        return
    mode = _prompt_workplace_modes(current.get("workplace_mode"))
    if mode is None:
        return

    settings = {
        "city": city.strip(),
        "state": state.strip(),
        "zip": zip_code.strip(),
        "radius_miles": miles,
        "workplace_mode": mode,
    }
    write_settings(settings, path)
    cli_art.console.print(
        f"\n{cli_art.SUCCESS} Location filter: [cyan]{describe(settings)}[/cyan]",
        soft_wrap=True,
    )
    cli_art.console.print(
        "  On-site and hybrid postings inside this radius will now be kept.\n",
        soft_wrap=True,
    )
