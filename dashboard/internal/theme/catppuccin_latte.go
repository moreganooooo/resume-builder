package theme

func newCatppuccinLatte() Theme {
	t := Theme{
		// Catppuccin Latte palette
		Base:    c("15", "255", "#eff1f5"),
		Surface: c("7", "254", "#dce0e8"),
		Overlay: c("8", "248", "#9ca0b0"),
		Text:    c("0", "239", "#4c4f69"),
		Subtext: c("8", "241", "#5c5f77"),

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
		Blue:   c("4", "26", "#1a56db"),
		Mauve:  c("5", "93", "#761aed"),
		Green:  c("2", "28", "#29681c"),
		Yellow: c("3", "94", "#805211"),
		Sky:    c("6", "31", "#026288"),
		Peach:  c("1", "130", "#a03b01"),
		Red:    c("1", "124", "#b80d32"),
		Pink:   c("13", "126", "#a81a82"),
	}

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
