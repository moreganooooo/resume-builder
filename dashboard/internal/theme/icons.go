package theme

import "os"

// Icons holds the header-decoration glyphs used alongside the
// resume-builder theme. Mirrors resume-builder's own Nerd-Font-by-default,
// RESUME_BUILDER_ICONS=unicode-fallback convention (scripts/theme.py) so a
// terminal already configured for the interactive menu renders these the
// same way, with no separate setup. Only the explicit-override tier of
// scripts/theme.py's icon-set resolution is replicated here -- its other
// tiers (a persisted first-launch answer, an isatty-based default) read
// Python-side profile state (ui_config.py) this package has no access to,
// so RESUME_BUILDER_ICONS=unicode is the one signal the dashboard can act
// on; everything else defaults to Nerd Font, matching the CLI's own
// isatty default for an interactive terminal.
type Icons struct {
	Evaluate string // nf-fa-bar_chart / % -- analytics/progress screens
	Utility  string // nf-fa-cog / ⚙ -- pipeline/management screens
}

func NewIcons() Icons {
	if os.Getenv("RESUME_BUILDER_ICONS") == "unicode" {
		// Matches scripts/theme.py's _UNICODE_ICONS -- plain, narrow
		// glyphs, not emoji: theme.py replaced Evaluate's original 📊
		// with "%" for exactly this reason (double-width emoji glyphs
		// break single-width column math and ignore ANSI color).
		return Icons{Evaluate: "%", Utility: "⚙"}
	}
	// Nerd Font Font Awesome glyphs, matching scripts/theme.py's
	// _NERD_ICONS (nf-fa-bar_chart / nf-fa-cog).
	return Icons{Evaluate: "\uf080", Utility: "\uf013"}
}

// MenuIcons holds the Main Menu's row glyphs. Field order/names mirror
// Theme.Icons's anonymous struct exactly (see theme.go) so `t.Icons =
// NewMenuIcons()` type-checks as a single assignment -- Go allows this
// between a named and an unnamed struct type when the underlying shape
// is identical. Pipeline/Progress reuse Icons' existing Utility/Evaluate
// glyphs (same nf-fa-cog / nf-fa-bar_chart concepts, already the
// established pipeline/analytics icons); Report/Quit/Jobs/Menu are new
// but follow the same nf-fa-* sourcing and narrow-Unicode-fallback
// discipline documented on Icons above.
type MenuIcons struct {
	Pipeline string // nf-fa-cog / same glyph as Icons.Utility
	Progress string // nf-fa-bar_chart / same glyph as Icons.Evaluate
	Report   string // nf-fa-file_text_o
	Quit     string // nf-fa-sign_out
	Menu     string // nf-fa-bars
	Jobs     string // nf-fa-briefcase
}

func NewMenuIcons() MenuIcons {
	if os.Getenv("RESUME_BUILDER_ICONS") == "unicode" {
		return MenuIcons{
			Pipeline: "\u2699", // matches Icons.Utility's unicode fallback
			Progress: "%",      // matches Icons.Evaluate's unicode fallback
			Report:   "\u25a4",
			Quit:     "x",
			Menu:     "\u2630",
			Jobs:     "\u25a3",
		}
	}
	return MenuIcons{
		Pipeline: "\uf013", // nf-fa-cog, matches Icons.Utility
		Progress: "\uf080", // nf-fa-bar_chart, matches Icons.Evaluate
		Report:   "\uf0f6", // nf-fa-file_text_o
		Quit:     "\uf08b", // nf-fa-sign_out
		Menu:     "\uf0c9", // nf-fa-bars
		Jobs:     "\uf0b1", // nf-fa-briefcase
	}
}
