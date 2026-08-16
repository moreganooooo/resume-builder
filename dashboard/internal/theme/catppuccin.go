package theme

func newCatppuccinMocha() Theme {
	t := Theme{
		// Catppuccin Mocha palette
		Base:    c("0", "233", "#1e1e2e"),
		Surface: c("8", "235", "#313244"),
		Overlay: c("8", "237", "#45475a"),
		Text:    c("15", "252", "#cdd6f4"),
		Subtext: c("7", "246", "#a6adc8"),

		// Accents
		Blue:   c("4", "111", "#89b4fa"),
		Mauve:  c("5", "183", "#cba6f7"),
		Green:  c("2", "114", "#a6e3a1"),
		Yellow: c("3", "223", "#f9e2af"),
		Sky:    c("6", "116", "#89dceb"),
		Peach:  c("3", "215", "#fab387"),
		Red:    c("1", "210", "#f38ba8"),
		Pink:   c("13", "218", "#f5c2e7"),
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
