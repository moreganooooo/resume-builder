"""
sync_dashboard_theme.py -- Regenerates Go TUI theme files from Python theme tokens and synchronizes user theme preferences.

Regenerates dashboard/internal/theme/resumebuilder.go from theme.py's color
constants, so the two can never drift apart again (B23/P2F9). Also
regenerates dashboard/internal/theme/subscore_labels.go from
cli_art.py's own _FIT_DIMENSION_GROUPS, so the Jobs screen's subscore
labels can never drift from the CLI's own render_comparison_table() labels.

Also provides helpers for getting and persisting the active UI theme preference.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import cli_art
import profile_paths
import theme

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_THEME_PATH = os.path.join(
    PROJECT_ROOT, "dashboard", "internal", "theme", "resumebuilder.go"
)
SUBSCORE_LABELS_PATH = os.path.join(
    PROJECT_ROOT, "dashboard", "internal", "theme", "subscore_labels.go"
)

SUPPORTED_THEMES = [
    "modern",
    "classic",
    "minimal",
    "cyberpunk",
    "monochrome",
    "dracula",
]


def get_active_theme(profile: Optional[str] = None) -> str:
    """Gets the active UI theme for the given profile or globally."""
    config_path = os.path.join(profile_paths.profile_root(profile), "theme.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                theme_name = data.get("theme", "modern").lower()
                if theme_name in SUPPORTED_THEMES:
                    return theme_name
        except Exception:
            pass
    return "modern"


def set_active_theme(theme_name: str, profile: Optional[str] = None) -> bool:
    """Sets and persists the active theme configuration."""
    theme_clean = theme_name.strip().lower()
    if theme_clean not in SUPPORTED_THEMES:
        return False

    config_path = os.path.join(profile_paths.profile_root(profile), "theme.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(
                {"theme": theme_clean, "updated_at": os.getenv("CURRENT_TIME", "")},
                f,
                indent=2,
            )
        return True
    except Exception:
        return False


# (Go struct field, theme.py constant name, source token)
_ACCENT_FIELDS = [
    ("Blue", "INFO", theme.INFO),
    ("Mauve", "BRAND_ACCENT", theme.BRAND_ACCENT),
    ("Green", "SUCCESS", theme.SUCCESS),
    ("Yellow", "WARNING", theme.WARNING),
    ("Sky", "BRAND", theme.BRAND),
    ("Peach", "PEACH", theme.PEACH),
    ("Red", "ERROR", theme.ERROR),
    ("Pink", "PINK", theme.PINK),
]

_HEADER = """package theme

import "github.com/charmbracelet/lipgloss"

// newResumeBuilder mirrors resume-builder's own CLI palette
// (scripts/theme.py) so the dashboard reads as the same product, not a
// different tool bolted on. Only the accent colors are ported -- the
// structural neutrals (Base/Surface/Overlay/Text/Subtext) stay Catppuccin
// Mocha's, since resume-builder's own CLI never defines a background/
// foreground pair of its own (it prints plain-color text onto whatever
// terminal theme is active) and Mocha's neutrals are already tuned for
// exactly this kind of dark-terminal TUI.
//
// Colors are Charmtone (github.com/charmbracelet/x/exp/charmtone), the
// Charm ecosystem's own branded palette -- six carry semantic meaning on
// the CLI side too (INFO/BRAND_ACCENT/SUCCESS/WARNING/BRAND/ERROR); Peach
// and Pink are dashboard-only decorative accents (theme.py's PEACH/PINK)
// with no CLI role of their own, added so this struct's 8 Catppuccin-
// shaped accent slots are 8 actually-distinct colors instead of 6 real
// ones plus 2 reused placeholders.
//
// GENERATED from scripts/theme.py by scripts/sync_dashboard_theme.py --
// do not hand-edit the accent block below. Re-run that script after
// changing any of theme.py's INFO/BRAND_ACCENT/SUCCESS/WARNING/BRAND/
// ERROR/PEACH/PINK constants; doctor.py's check_dashboard_theme_sync()
// flags it if this file ever falls out of sync.
// newCatppuccinMocha moved to catppuccin.go

func newResumeBuilder() Theme {
	t := Theme{
		// Structural neutrals -- Catppuccin Mocha, untouched.
		Base:    lipgloss.Color("#1e1e2e"),
		Surface: lipgloss.Color("#313244"),
		Overlay: lipgloss.Color("#45475a"),
		Text:    lipgloss.Color("#cdd6f4"),
		Subtext: lipgloss.Color("#a6adc8"),

		// Accents -- resume-builder's scripts/theme.py tokens. Sky
		// (#8B75FF, BRAND) clears Base (#1e1e2e) at 4.75:1 -- AA text
		// contrast, but with little margin -- and fails outright against
		// Surface (#313244) at 3.64:1. It's currently only ever
		// composited against Base (progress.go/viewer.go section
		// titles), which is why this isn't visibly broken today; don't
		// pair it with Background(Surface) without re-measuring, unlike
		// catppuccin_latte.go's accents (see that file's own contrast
		// comment), which were deliberately tuned against the tighter of
		// the two backgrounds.
"""

_FOOTER = """	}

	// Populate Token shortcuts
	t.Token.Text = t.Text
	t.Token.Subtext = t.Subtext
	t.Token.Mauve = t.Mauve

	// Populate Icons -- see icons.go's NewMenuIcons for the Nerd-Font-
	// by-default, RESUME_BUILDER_ICONS=unicode-fallback logic this
	// replaced (was previously hardcoded emoji, identical in all 3
	// theme constructors, that ignored the env var entirely).
	t.Icons = NewMenuIcons()

	return t
}
"""


def build_go_theme_source() -> str:
    lines = [_HEADER]
    for field, label, hexcode in _ACCENT_FIELDS:
        lines.append(
            f'\t\t{field}:{" " * (7 - len(field))}lipgloss.Color("{hexcode}"), // {label}\n'
        )
    lines.append(_FOOTER)
    return "".join(lines)


_SUBSCORE_LABELS_HEADER = """package theme

// SubscoreLabels maps each fit/interview-odds/practical-pursue subscore
// schema key -- as persisted verbatim in a JD's `_evaluation` JSON (see
// jd_manager.save_evaluation) -- to the human-readable label a job seeker
// should see. Without this, the Jobs screen's subscore line rendered raw
// snake_case schema keys (e.g. "functional_alignment: 4") straight from
// the evaluation JSON, which is internal-jargon leakage the same class of
// bug this project's own CLI never allows onto the screen.
//
// Ported from scripts/cli_art.py's _FIT_DIMENSION_GROUPS, the CLI's own
// source of truth for these labels (render_comparison_table's grouped
// subscore table) -- flattened into one map since formatSubscores()
// (internal/ui/screens/jobs.go) renders one dict at a time with no need
// for _FIT_DIMENSION_GROUPS's own layer grouping, and every key across
// all three layers is already unique.
//
// GENERATED from scripts/cli_art.py by scripts/sync_dashboard_theme.py --
// do not hand-edit. Re-run that script after changing
// _FIT_DIMENSION_GROUPS.
var SubscoreLabels = map[string]string{
"""

_SUBSCORE_LABELS_FOOTER = "}\n"


def _flat_subscore_labels() -> dict:
    """Flattens cli_art._FIT_DIMENSION_GROUPS's (layer_label, dict_key,
    {schema_key: display_label}) triples into one schema_key -> display_label
    map."""
    flat = {}
    for _layer_label, _dict_key, mapping in cli_art._FIT_DIMENSION_GROUPS:
        flat.update(mapping)
    return flat


def build_subscore_labels_source() -> str:
    flat = _flat_subscore_labels()
    lines = [_SUBSCORE_LABELS_HEADER]
    for key in sorted(flat):
        lines.append(f'\t"{key}": "{flat[key]}",\n')
    lines.append(_SUBSCORE_LABELS_FOOTER)
    return "".join(lines)


def _write_if_changed(path: str, new_source: str) -> bool:
    """Writes new_source to path. Returns True if the file's content
    actually changed (worth mentioning), False if it was already in sync."""
    old_source = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            old_source = f.read()
    if old_source == new_source:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_source)
    return True


def sync() -> bool:
    """Writes both regenerated files. Returns True if either file's
    content actually changed (worth mentioning), False if both were
    already in sync."""
    theme_changed = _write_if_changed(DASHBOARD_THEME_PATH, build_go_theme_source())
    labels_changed = _write_if_changed(
        SUBSCORE_LABELS_PATH, build_subscore_labels_source()
    )
    return theme_changed or labels_changed


if __name__ == "__main__":
    theme_changed = _write_if_changed(DASHBOARD_THEME_PATH, build_go_theme_source())
    labels_changed = _write_if_changed(
        SUBSCORE_LABELS_PATH, build_subscore_labels_source()
    )
    cli_art.print_literal(
        f"{cli_art._escape_markup(DASHBOARD_THEME_PATH)}: {'updated' if theme_changed else 'already in sync'}"
    )
    cli_art.print_literal(
        f"{cli_art._escape_markup(SUBSCORE_LABELS_PATH)}: {'updated' if labels_changed else 'already in sync'}"
    )
