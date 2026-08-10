package theme

import "github.com/charmbracelet/lipgloss"

func newCatppuccinLatte() Theme {
	t := Theme{
		// Catppuccin Latte palette
		Base:    lipgloss.Color("#eff1f5"),
		Surface: lipgloss.Color("#dce0e8"),
		Overlay: lipgloss.Color("#9ca0b0"),
		Text:    lipgloss.Color("#4c4f69"),
		Subtext: lipgloss.Color("#5c5f77"),

		// Accents
		Blue:   lipgloss.Color("#1e66f5"),
		Mauve:  lipgloss.Color("#8839ef"),
		Green:  lipgloss.Color("#40a02b"),
		Yellow: lipgloss.Color("#df8e1d"),
		Sky:    lipgloss.Color("#04a5e5"),
		Peach:  lipgloss.Color("#fe640b"),
		Red:    lipgloss.Color("#d20f39"),
		Pink:   lipgloss.Color("#ea76cb"),
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
