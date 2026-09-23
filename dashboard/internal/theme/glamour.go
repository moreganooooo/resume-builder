package theme

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"image/color"

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
		glamour.WithStyles(styleFor(t)),
		glamour.WithWordWrap(0), // viewer.go wraps manually to its known width
		glamour.WithInlineTableLinks(true),
	}
}

// resumeBuilderGlamourJSON is the design system's own Glamour style
// (docs/DesignSystem/assets/glamour-resumebuilder.json), copied into the
// module because go:embed cannot reach outside it. TestGlamourJSONMatchesDesignSystem
// fails the moment the two copies differ, so the docs file stays the source.
//
//go:embed glamour-resumebuilder.json
var resumeBuilderGlamourJSON []byte

// styleFor uses the design system's JSON verbatim for the resume-builder
// palette -- its prefixes, block-quote bar and heading colors are choices the
// Go-built style never made -- and keeps the Go-built style for the
// Catppuccin variants, which the JSON (hex values from one palette) cannot
// describe. One deviation, deliberate: the document margin is zeroed, because
// viewer.go wraps to its exact pane width and a 2-column margin would push
// every full-width line past it.
func styleFor(t Theme) ansi.StyleConfig {
	rb := newResumeBuilder()
	if colorToHex(t.Base) != colorToHex(rb.Base) || colorToHex(t.Blue) != colorToHex(rb.Blue) {
		return glamourStyle(t)
	}
	var cfg ansi.StyleConfig
	if err := json.Unmarshal(resumeBuilderGlamourJSON, &cfg); err != nil {
		return glamourStyle(t) // unreachable while the test below parses it
	}
	var zero uint
	cfg.Document.Margin = &zero
	return cfg
}

func colorToHex(c color.Color) string {
	if c == nil {
		return ""
	}
	r, g, b, _ := c.RGBA()
	return fmt.Sprintf("#%02x%02x%02x", uint8(r>>8), uint8(g>>8), uint8(b>>8))
}

// glamourStyle builds an ansi.StyleConfig whose colors all resolve through
// Theme fields. Every helper that needs a *string (Glamour's StylePrimitive
// uses pointers, nil means "inherit") gets its own closure; stringPtr is
// Glamour's own helper from styles/styles.go.
func glamourStyle(t Theme) ansi.StyleConfig {
	return ansi.StyleConfig{
		Document: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color:           strPtr(colorToHex(t.Text)),
				BackgroundColor: strPtr(colorToHex(t.Base)),
			},
		},

		Heading: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Blue)),
			},
		},
		H1: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Blue)),
			},
		},
		H2: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Mauve)),
			},
		},
		H3: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Sky)),
			},
		},
		H4: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Text)),
			},
		},
		H5: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Subtext)),
			},
		},
		H6: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Bold:  boolPtr(true),
				Color: strPtr(colorToHex(t.Subtext)),
			},
		},

		Paragraph: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color: strPtr(colorToHex(t.Text)),
			},
		},

		BlockQuote: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color: strPtr(colorToHex(t.Text)),
			},
			Indent:      uintPtr(0),
			IndentToken: strPtr(""),
		},

		Text: ansi.StylePrimitive{
			Color: strPtr(colorToHex(t.Text)),
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
			Color: strPtr(colorToHex(t.Overlay)),
		},

		Item: ansi.StylePrimitive{
			Color: strPtr(colorToHex(t.Blue)),
		},
		Enumeration: ansi.StylePrimitive{
			Color: strPtr(colorToHex(t.Blue)),
		},

		Link: ansi.StylePrimitive{
			Color:     strPtr(colorToHex(t.Token.Mauve)),
			Underline: boolPtr(true),
		},
		LinkText: ansi.StylePrimitive{
			Color:     strPtr(colorToHex(t.Token.Mauve)),
			Underline: boolPtr(true),
		},

		Code: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color:           strPtr(colorToHex(t.Text)),
				BackgroundColor: strPtr(colorToHex(t.Surface)),
			},
		},

		CodeBlock: ansi.StyleCodeBlock{
			StyleBlock: ansi.StyleBlock{
				StylePrimitive: ansi.StylePrimitive{
					Color:           strPtr(colorToHex(t.Text)),
					BackgroundColor: strPtr(colorToHex(t.Surface)),
				},
				Indent:      uintPtr(1),
				IndentToken: strPtr("  "),
			},
		},

		Table: ansi.StyleTable{
			StyleBlock:      ansi.StyleBlock{},
			CenterSeparator: strPtr("─"),
			ColumnSeparator: strPtr("│"),
			RowSeparator:    strPtr("─"),
		},
	}
}

func strPtr(s string) *string { return &s }
func boolPtr(b bool) *bool    { return &b }
func uintPtr(u uint) *uint    { return &u }
