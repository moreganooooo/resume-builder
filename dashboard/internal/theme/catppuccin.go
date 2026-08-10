package theme

import "github.com/charmbracelet/lipgloss"

func newCatppuccinMocha() Theme {
	t := Theme{
		// Catppuccin Mocha palette
		Base:    lipgloss.Color("#1e1e2e"),
		Surface: lipgloss.Color("#313244"),
		Overlay: lipgloss.Color("#45475a"),
		Text:    lipgloss.Color("#cdd6f4"),
		Subtext: lipgloss.Color("#a6adc8"),

		// Accents
		Blue:   lipgloss.Color("#89b4fa"),
		Mauve:  lipgloss.Color("#cba6f7"),
		Green:  lipgloss.Color("#a6e3a1"),
		Yellow: lipgloss.Color("#f9e2af"),
		Sky:    lipgloss.Color("#89dceb"),
		Peach:  lipgloss.Color("#fab387"),
		Red:    lipgloss.Color("#f38ba8"),
		Pink:   lipgloss.Color("#f5c2e7"),
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
