package theme

import "os"

// Icons holds the header-decoration glyphs used alongside the
// resume-builder theme. Mirrors resume-builder's own Nerd-Font-by-default,
// RESUME_BUILDER_ICONS=unicode-fallback convention (scripts/theme.py) so a
// terminal already configured for the interactive menu renders these the
// same way, with no separate setup.
type Icons struct {
	Evaluate string // nf-fa-bar_chart / 📊 -- analytics/progress screens
	Utility  string // nf-fa-cog / ⚙ -- pipeline/management screens
}

func NewIcons() Icons {
	if os.Getenv("RESUME_BUILDER_ICONS") == "unicode" {
		return Icons{Evaluate: "\U0001F4CA", Utility: "⚙"}
	}
	return Icons{Evaluate: "", Utility: ""}
}
