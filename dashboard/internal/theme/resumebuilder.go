package theme

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
func newResumeBuilder() Theme {
	return Theme{
		// Structural neutrals -- Catppuccin Mocha, untouched.
		Base:    lipgloss.Color("#1e1e2e"),
		Surface: lipgloss.Color("#313244"),
		Overlay: lipgloss.Color("#45475a"),
		Text:    lipgloss.Color("#cdd6f4"),
		Subtext: lipgloss.Color("#a6adc8"),

		// Accents -- resume-builder's scripts/theme.py tokens.
		Blue:   lipgloss.Color("#2196f3"), // INFO
		Mauve:  lipgloss.Color("#b39ddb"), // BRAND_ACCENT
		Green:  lipgloss.Color("#4caf50"), // SUCCESS
		Yellow: lipgloss.Color("#f5c542"), // WARNING
		Sky:    lipgloss.Color("#4dabf7"), // BRAND
		Peach:  lipgloss.Color("#f5c542"), // WARNING (reused, see above)
		Red:    lipgloss.Color("#c96a6a"), // ERROR
		Pink:   lipgloss.Color("#b39ddb"), // BRAND_ACCENT (reused, unused field)
	}
}
