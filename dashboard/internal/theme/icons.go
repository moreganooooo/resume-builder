package theme

import "os"

// MenuIcons holds every glyph the dashboard renders -- Main Menu rows and
// screen-header decorations alike. Mirrors resume-builder's own
// Nerd-Font-by-default, RESUME_BUILDER_ICONS=unicode-fallback convention
// (scripts/theme.py) so a terminal already configured for the interactive
// menu renders these the same way, with no separate setup. Only the
// explicit-override tier of scripts/theme.py's icon-set resolution is
// replicated here -- its other tiers (a persisted first-launch answer, an
// isatty-based default) read Python-side profile state (ui_config.py) this
// package has no access to, so RESUME_BUILDER_ICONS=unicode is the one
// signal the dashboard can act on; everything else defaults to Nerd Font,
// matching the CLI's own isatty default for an interactive terminal.
//
// Field order/names mirror Theme.Icons's anonymous struct exactly (see
// theme.go) so `t.Icons = NewMenuIcons()` type-checks as a single
// assignment -- Go allows this between a named and an unnamed struct type
// when the underlying shape is identical. Pipeline/Progress double as the
// Pipeline/Progress screen headers' own decoration glyphs (nf-fa-cog /
// nf-fa-bar_chart), not just their Main Menu row icons -- this used to be
// a second, separately-constructed `Icons` type with `Utility`/`Evaluate`
// fields carrying the identical glyphs, read fresh via a free-standing
// theme.NewIcons() call on every header render instead of the theme
// instance already sitting on the model; folded into this single type to
// remove that duplication.
type MenuIcons struct {
	Pipeline string // nf-fa-cog
	Progress string // nf-fa-bar_chart
	Report   string // nf-fa-file_text_o
	Quit     string // nf-fa-sign_out
	Menu     string // nf-fa-bars
	Jobs     string // nf-fa-briefcase
	Profile  string // nf-fa-user
	Source   string // nf-fa-folder_open
	Path     string // nf-fa-file_o
	Magic    string // nf-fa-magic

	// Score* give a composite/interview-probability score's color tier
	// (see screens/bars.go's scoreStyle) a redundant shape cue too, so a
	// colorblind user isn't reading tier from color alone -- the one place
	// in the dashboard that previously encoded meaning purely by hue, unlike
	// scripts/theme.py's colorize_icon(), which pairs every semantic color
	// with a distinct icon everywhere else in this codebase. These reuse
	// that same module's success/gem/hint/skip glyphs (U+F00C/F219/F0EB/
	// F05E, "✓"/"*"/"!"/"-" in the Unicode fallback) rather than inventing
	// a new vocabulary -- gem ("quality/priority") and skip ("excluded/
	// rejection") already carry almost exactly the right connotation for
	// the "good" and "weak" tiers respectively.
	ScoreStrong string // nf-fa-check (theme.py's "success")
	ScoreGood   string // nf-fa-diamond (theme.py's "gem")
	ScoreFair   string // nf-fa-lightbulb_o (theme.py's "hint")
	ScoreWeak   string // nf-fa-ban (theme.py's "skip")
}

func NewMenuIcons() MenuIcons {
	if os.Getenv("RESUME_BUILDER_ICONS") == "unicode" {
		return MenuIcons{
			Pipeline: "⚙",
			Progress: "%",
			Report:   "▤",
			Quit:     "x",
			Menu:     "☰",
			Jobs:     "▣",
			Profile:  "@",
			// "#" previously here didn't evoke "folder"/"source" the way
			// every other fallback in this set reads as a recognizable
			// pictogram for its Nerd Font original -- ⊔ (open container/
			// tray shape) is a closer visual match for nf-fa-folder_open,
			// same narrow-width geometric-symbol style as Pipeline/Report/
			// Jobs above (Neutral East Asian width, single terminal column,
			// unlike an emoji folder glyph would be).
			Source: "⊔",
			Path:   "/",
			Magic:  "*",

			// Exact ASCII fallbacks scripts/theme.py's _UNICODE_ICONS uses
			// for "success"/"gem"/"hint"/"skip" -- single-width, colorless-
			// by-default in every terminal/font, same reasoning as that
			// module's own B22/P1F7 fix.
			ScoreStrong: "✓",
			ScoreGood:   "*",
			ScoreFair:   "!",
			ScoreWeak:   "-",
		}
	}
	return MenuIcons{
		Pipeline: "", // nf-fa-cog
		Progress: "", // nf-fa-bar_chart
		Report:   "", // nf-fa-file_text_o
		Quit:     "", // nf-fa-sign_out
		Menu:     "", // nf-fa-bars
		Jobs:     "", // nf-fa-briefcase
		Profile:  "", // nf-fa-user
		Source:   "", // nf-fa-folder_open
		Path:     "", // nf-fa-file_o
		Magic:    "", // nf-fa-magic

		// Use Unicode fallbacks instead of Nerd Font glyphs (U+F00C/F219/F0EB/F05E)
		// which don't render reliably across all terminal configurations
		ScoreStrong: "✓",
		ScoreGood:   "",
		ScoreFair:   "",
		ScoreWeak:   "",
	}
}
