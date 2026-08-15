package theme

import (
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/glamour/ansi"
)

// GlamourConfig returns a *glamour.TermRendererOption set that renders
// markdown through Glamour using this project's color palette instead of
// Glamour's stock Tokyo Night / Dark / Light defaults. Every token resolves
// through Theme fields, so switching from resume-builder to Catppuccin Mocha
// or Latte carries over automatically — no second set of hex values to drift
// out of sync, which is exactly the bug lint_colors.go exists to prevent in
// the LipGloss rendering paths.
//
// Key adaptations from Glamour's stock styles:
//   - Code blocks use the theme's Surface as background and Text as foreground,
//     matching viewer.go's fenced-code styling (the custom renderer's one
//     non-delegatable job remains hard-wrapping unbreakable tokens inside code
//     blocks — Glamour has no per-line wrap config, so renderCodeBlock still
//     post-processes the Glamour output for that).
//   - No document-level margin (WithWordWrap only controls text wrapping, not
//     the 3-column left indent Glamour's default Document style adds).
//   - No emoji by default: resume reports are technical/professional -- emoji
//     render inconsistently across terminals and have no semantic role here,
//     unlike Crush's conversational tone where they land naturally.
//   - Inline links are rendered as styled spans rather than footnote-style
//     references — a resume report's inline links are always meaningful (a
//     posting URL, a source reference), and the footnote list would consume
//     prime viewport height.
func GlamourConfig(t Theme) []glamour.TermRendererOption {
	return []glamour.TermRendererOption{
		glamour.WithStyles(glamourStyle(t)),
		glamour.WithWordWrap(0), // viewer.go wraps manually to its known width
		glamour.WithInlineTableLinks(true),
	}
}

// glamourStyle builds an ansi.StyleConfig whose colors all resolve through
// Theme fields. Every helper that needs a *string (Glamour's StylePrimitive
// uses pointers, nil means "inherit") gets its own closure; stringPtr is
// Glamour's own helper from styles/styles.go.
func glamourStyle(t Theme) ansi.StyleConfig {
	return ansi.StyleConfig{
		Document: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color:           strPtr(string(t.Text)),
				BackgroundColor: strPtr(string(t.Base)),
			},
		},

		Heading: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Blue)),
			},
		},
		H1: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Blue)),
			},
		},
		H2: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Mauve)),
			},
		},
		H3: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Sky)),
			},
		},
		H4: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Text)),
			},
		},
		H5: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Subtext)),
			},
		},
		H6: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(string(t.Subtext)),
			},
		},

		Paragraph: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color: strPtr(string(t.Text)),
			},
		},

		BlockQuote: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color: strPtr(string(t.Text)),
			},
			Indent:       uintPtr(0),
			IndentToken:  strPtr(""),
		},

		Text: ansi.StylePrimitive{
			Color: strPtr(string(t.Text)),
		},

		Strong: ansi.StylePrimitive{
			Bold: boolPtr(true),
		},
		Emph: ansi.StylePrimitive{
			Italic: boolPtr(true),
		},
		Strikethrough: ansi.StylePrimitive{
			CrossedOut: boolPtr(true),
		},

		HorizontalRule: ansi.StylePrimitive{
			Color: strPtr(string(t.Overlay)),
		},

		Item: ansi.StylePrimitive{
			Color: strPtr(string(t.Blue)),
		},
		Enumeration: ansi.StylePrimitive{
			Color: strPtr(string(t.Blue)),
		},

		Link: ansi.StylePrimitive{
			Color:     strPtr(string(t.Token.Mauve)),
			Underline: boolPtr(true),
		},
		LinkText: ansi.StylePrimitive{
			Color:     strPtr(string(t.Token.Mauve)),
			Underline: boolPtr(true),
		},

		Code: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color:           strPtr(string(t.Text)),
				BackgroundColor: strPtr(string(t.Surface)),
			},
		},

		CodeBlock: ansi.StyleCodeBlock{
			StyleBlock: ansi.StyleBlock{
				StylePrimitive: ansi.StylePrimitive{
					Color:           strPtr(string(t.Text)),
					BackgroundColor: strPtr(string(t.Surface)),
				},
				Indent:      uintPtr(1),
				IndentToken: strPtr("  "),
			},
		},

		Table: ansi.StyleTable{
			StyleBlock: ansi.StyleBlock{},
			CenterSeparator: strPtr("─"),
			ColumnSeparator: strPtr("│"),
			RowSeparator:    strPtr("─"),
		},
	}
}

func strPtr(s string) *string { return &s }
func boolPtr(b bool) *bool    { return &b }
func uintPtr(u uint) *uint    { return &u }
