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

		// Accents -- resume-builder's scripts/theme.py tokens.
		Blue:   lipgloss.Color("#00A4FF"), // INFO
		Mauve:  lipgloss.Color("#FF60FF"), // BRAND_ACCENT
		Green:  lipgloss.Color("#12C78F"), // SUCCESS
		Yellow: lipgloss.Color("#F5EF34"), // WARNING
		Sky:    lipgloss.Color("#8B75FF"), // BRAND
		Peach:  lipgloss.Color("#FF985A"), // PEACH
		Red:    lipgloss.Color("#FF7B99"), // ERROR
		Pink:   lipgloss.Color("#FF84FF"), // PINK
	}

	t.GradientStart = lipgloss.Color(BrandColor)
	t.GradientEnd = lipgloss.Color(AccentColor)

	// Populate Token shortcuts
	t.Token.Text = t.Text
	t.Token.Subtext = t.Subtext
	t.Token.GradientStart = t.GradientStart
	t.Token.GradientEnd = t.GradientEnd
	t.Token.Mauve = t.Mauve

	// Populate Icons -- see icons.go's NewMenuIcons for the Nerd-Font-
	// by-default, RESUME_BUILDER_ICONS=unicode-fallback logic this
	// replaced (was previously hardcoded emoji, identical in all 3
	// theme constructors, that ignored the env var entirely).
	t.Icons = NewMenuIcons()

	return t
}
