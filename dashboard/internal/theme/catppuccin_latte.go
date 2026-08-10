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

		// Accents. Every one of these is darkened from stock Catppuccin
		// Latte -- this dashboard renders them at body-text size (scoreStyle,
		// statusColorMap, rateColor, and the funnel/score-distribution bar
		// labels all use these directly as foreground text, not just as
		// decorative fills), and stock Latte's pastel accents are tuned for
		// large-surface use, not 4.5:1 text contrast on Base (#eff1f5) or
		// Surface (#dce0e8) -- stock Green measured 2.96:1 on Base and
		// 2.53:1 on Surface, Yellow 2.31/1.98, Sky 2.47/2.11, Peach
		// 2.64/2.25, Pink 2.34/2.00, and Mauve/Red each cleared Base but
		// still failed on Surface (4.09/4.10). Blue was the first of these
		// fixed (originally #1e66f5, 4.35:1 on Base); the rest follow the
		// same approach: same hue held constant, lightness walked down
		// until contrast against the tighter of the two backgrounds
		// (Surface, since it's darker than Base) clears ~5:1 for a real
		// margin rather than sitting right on the AA line. Yellow and Peach
		// necessarily read as a darker amber/rust at this lightness --
		// a true yellow or orange hue cannot reach 4.5:1 on a near-white
		// background without doing that; this is the actual color, not a
		// rendering bug.
		Blue:   lipgloss.Color("#1a56db"),
		Mauve:  lipgloss.Color("#761aed"),
		Green:  lipgloss.Color("#29681c"),
		Yellow: lipgloss.Color("#805211"),
		Sky:    lipgloss.Color("#026288"),
		Peach:  lipgloss.Color("#a03b01"),
		Red:    lipgloss.Color("#b80d32"),
		Pink:   lipgloss.Color("#a81a82"),
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
