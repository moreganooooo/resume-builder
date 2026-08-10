package theme

import (
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/glamour/ansi"
)

// MarkdownStyle returns a Glamour terminal renderer configured with the dashboard's colour palette.
func MarkdownStyle() *glamour.TermRenderer {
	// Start from a dark base style and then customize colours using the theme tokens.
	// Glamour's style config mirrors CSS properties.
	//
	// Only BaseColor/AccentColor are used below, never PrintColor -- that
	// token is DESIGN.md's print-only "absolute black" (the PDF output's
	// text color), and DESIGN.md's own No-Bleed Rule states print colors
	// must never bleed into the TUI. BlockQuote/CodeBlock previously used
	// PrintColor for their foreground, which also happened to collide
	// with CodeBlock's BaseColor background (foreground == background,
	// invisible text) once BaseColor/AccentColor/PrintColor stopped all
	// being stuck on the same fallback value (see tokens.go).
	custom := ansi.StyleConfig{
		Document: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color: func() *string { s := BaseColor; return &s }(),
			},
		},
		Heading: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color: func() *string { s := AccentColor; return &s }(),
				Bold:  func() *bool { b := true; return &b }(),
			},
		},
		BlockQuote: ansi.StyleBlock{
			StylePrimitive: ansi.StylePrimitive{
				Color:  func() *string { s := AccentColor; return &s }(),
				Italic: func() *bool { b := true; return &b }(),
			},
		},
		CodeBlock: ansi.StyleCodeBlock{
			StyleBlock: ansi.StyleBlock{
				StylePrimitive: ansi.StylePrimitive{
					Color:           func() *string { s := AccentColor; return &s }(),
					BackgroundColor: func() *string { s := BaseColor; return &s }(),
				},
			},
		},
		List: ansi.StyleList{
			StyleBlock: ansi.StyleBlock{
				StylePrimitive: ansi.StylePrimitive{
					Color: func() *string { s := AccentColor; return &s }(),
				},
			},
		},
		Link: ansi.StylePrimitive{
			Color:     func() *string { s := AccentColor; return &s }(),
			Underline: func() *bool { b := true; return &b }(),
		},
	}

	// Create the renderer with a dark base and apply our custom style.
	r, err := glamour.NewTermRenderer(
		glamour.WithStandardStyle("dark"),
		glamour.WithStyles(custom),
	)
	if err != nil {
		panic(err)
	}
	// Fallback colour handling for undefined elements might need to be done differently
	// depending on how glamour v1.0.0 exposes styles. But with custom styles above,
	// Document color is set.
	return r
}
