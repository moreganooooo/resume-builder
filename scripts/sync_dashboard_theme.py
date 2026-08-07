"""
sync_dashboard_theme.py -- regenerates dashboard/internal/theme/
resumebuilder.go's accent-color block from scripts/theme.py's own color
constants, so the two can never drift apart again (B23/P2F9).

Before this, the Go file's six accent hexes were hand-copied from
theme.py with comments merely *claiming* they matched -- nothing enforced
it, so a theme.py color change (like B23's own BRAND_ACCENT fix) would
silently make those comments lie. doctor.py's check_dashboard_theme_sync()
detects that drift; this script is how you fix it.

Run this after changing any of theme.py's INFO/BRAND_ACCENT/SUCCESS/
WARNING/BRAND/ERROR constants:

    python scripts/sync_dashboard_theme.py
"""

import os

import theme

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_THEME_PATH = os.path.join(
    PROJECT_ROOT, "dashboard", "internal", "theme", "resumebuilder.go"
)

# (Go struct field, theme.py constant name, source token) -- the exact
# mapping the file's own doc comment already describes, now enforced
# instead of just asserted.
_ACCENT_FIELDS = [
    ("Blue", "INFO", theme.INFO),
    ("Mauve", "BRAND_ACCENT", theme.BRAND_ACCENT),
    ("Green", "SUCCESS", theme.SUCCESS),
    ("Yellow", "WARNING", theme.WARNING),
    ("Sky", "BRAND", theme.BRAND),
    ("Peach", "WARNING (reused, see above)", theme.WARNING),
    ("Red", "ERROR", theme.ERROR),
    ("Pink", "BRAND_ACCENT (reused, unused field)", theme.BRAND_ACCENT),
]

_HEADER = '''package theme

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
// resume-builder only has six semantic tokens against this struct's eight
// accent slots, so two get reused rather than invented:
//   - Peach reuses WARNING (no distinct 5th "orange" tone exists upstream;
//     the funnel/score-bucket gradients lose one visually distinct step,
//     which is an honest trade against inventing an unbranded color).
//   - Pink reuses BRAND_ACCENT (the field is currently unread by every
//     screen -- see internal/ui/screens -- so any value is a placeholder
//     until something actually renders it).
//
// GENERATED from scripts/theme.py by scripts/sync_dashboard_theme.py --
// do not hand-edit the accent block below. Re-run that script after
// changing any of theme.py's INFO/BRAND_ACCENT/SUCCESS/WARNING/BRAND/
// ERROR constants; doctor.py's check_dashboard_theme_sync() flags it if
// this file ever falls out of sync.
// newCatppuccinMocha moved to catppuccin.go

func newResumeBuilder() Theme {
	t := Theme{
		// Structural neutrals -- Catppuccin Mocha, untouched.
		Base:    lipgloss.Color("#1e1e2e"),
		Surface: lipgloss.Color("#313244"),
		Overlay: lipgloss.Color("#45475a"),
		Text:    lipgloss.Color("#cdd6f4"),
		Subtext: lipgloss.Color("#a6adc8"),

		// Accents -- resume-builder's scripts/theme.py tokens.
'''

_FOOTER = """	}

	t.GradientStart = lipgloss.Color(BrandColor)
	t.GradientEnd = lipgloss.Color(AccentColor)

	// Populate Token shortcuts
	t.Token.Text = t.Text
	t.Token.Subtext = t.Subtext
	t.Token.GradientStart = t.GradientStart
	t.Token.GradientEnd = t.GradientEnd
	t.Token.Mauve = t.Mauve

	// Populate Icons (generic placeholders)
	t.Icons.Pipeline = "🛠"
	t.Icons.Progress = "📈"
	t.Icons.Report = "📄"
	t.Icons.Quit = "❌"
	t.Icons.Menu = "☰"

	return t
}
"""


def build_go_theme_source() -> str:
    lines = [_HEADER]
    for field, label, hexcode in _ACCENT_FIELDS:
        lines.append(f'\t\t{field}:{" " * (7 - len(field))}lipgloss.Color("{hexcode}"), // {label}\n')
    lines.append(_FOOTER)
    return "".join(lines)


def sync() -> bool:
    """Writes the regenerated file. Returns True if the file's content
    actually changed (worth mentioning), False if it was already in sync."""
    new_source = build_go_theme_source()
    old_source = None
    if os.path.exists(DASHBOARD_THEME_PATH):
        with open(DASHBOARD_THEME_PATH, "r", encoding="utf-8") as f:
            old_source = f.read()
    if old_source == new_source:
        return False
    with open(DASHBOARD_THEME_PATH, "w", encoding="utf-8") as f:
        f.write(new_source)
    return True


if __name__ == "__main__":
    changed = sync()
    print(f"{DASHBOARD_THEME_PATH}: {'updated' if changed else 'already in sync'}")
