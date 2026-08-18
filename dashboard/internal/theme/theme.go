// Package theme provides the visual theme system for the dashboard.
package theme

import (
	"fmt"
	"image/color"
	"math"
	"strings"

	"charm.land/huh/v2"
	lipgloss "charm.land/lipgloss/v2"
	"github.com/muesli/termenv"
)

func c(ansi, ansi256, truecolor string) color.Color {
	return lipgloss.Color(truecolor)
}

// Theme holds all color definitions for the pipeline dashboard.
type Theme struct {
	// Base colors
	Base    color.Color
	Surface color.Color
	Overlay color.Color
	Text    color.Color
	Subtext color.Color

	// Accent colors
	Blue   color.Color
	Mauve  color.Color
	Green  color.Color
	Yellow color.Color
	Sky    color.Color
	Peach  color.Color
	Red    color.Color
	Pink   color.Color

	// Token grouping for UI components
	Token struct {
		Text    color.Color
		Subtext color.Color
		Mauve   color.Color
	}

	// Icon set for UI elements
	Icons struct {
		Pipeline string
		Progress string
		Report   string
		Quit     string
		Menu     string
		Jobs     string
		Profile  string
		Search   string
		Source   string
		Path     string
		Magic    string
		Trash    string
		Edit     string
		External string
		Clock    string
		Graph    string

		// Score* -- see icons.go's MenuIcons for the doc comment; field
		// order/names must mirror that struct exactly for
		// `t.Icons = NewMenuIcons()` to type-check as a single assignment.
		ScoreStrong string
		ScoreGood   string
		ScoreFair   string
		ScoreWeak   string
	}
}

// NewTheme creates a theme by name. Use "auto" or "" to detect from terminal background.
func NewTheme(name string) Theme {
	switch name {
	case "resume-builder":
		return newResumeBuilder()
	case "catppuccin-mocha":
		return newCatppuccinMocha()
	case "catppuccin-latte":
		return newCatppuccinLatte()
	case "auto", "":
		if termenv.HasDarkBackground() {
			return newCatppuccinMocha()
		}
		return newCatppuccinLatte()
	default:
		return newCatppuccinMocha()
	}
}

// HuhTheme converts the internal Theme into a huh.Theme that matches the
// current colour palette. huh.Theme is an interface in v2, and we wrap our
// styles builder inside huh.ThemeFunc to conform to the interface cleanly.
//
// Focused.Title/SelectSelector use Token.Mauve, not the module-level
// BrandColor constant (tokens.go, formerly wired into a now-removed
// GradientStart theme field that had no real consumer) -- BrandColor is
// the same hardcoded hex in every theme, which is exactly the
// cross-theme-drift bug the Main Menu's own selected-row style was
// already rewritten to avoid (see list.go's NewMenuModel comment).
// BrandColor measures 6.63:1 against the dark themes' Base but only
// 2.19:1 against Catppuccin Latte's -- unreadable for a focused field's
// own label under the one theme that needed a real per-theme token here.
func (t Theme) HuhTheme() huh.Theme {
	return huh.ThemeFunc(func(isDark bool) *huh.Styles {
		ht := huh.ThemeCharm(isDark)
		ht.Focused.Title = ht.Focused.Title.Foreground(t.Token.Mauve)
		ht.Focused.SelectSelector = ht.Focused.SelectSelector.Foreground(t.Token.Mauve)
		ht.Blurred.Title = ht.Blurred.Title.Foreground(t.Token.Subtext)
		return ht
	})
}

func parseHex(h string) (r, g, b int) {
	if len(h) > 0 && h[0] == '#' {
		h = h[1:]
	}
	if len(h) == 3 {
		_, _ = fmt.Sscanf(h, "%1x%1x%1x", &r, &g, &b)
		r = r * 17
		g = g * 17
		b = b * 17
		return
	}
	if len(h) == 6 {
		_, _ = fmt.Sscanf(h, "%2x%2x%2x", &r, &g, &b)
	}
	return
}

// ColorToHex converts a standard image/color.Color to a "#rrggbb" hex string.
func ColorToHex(c color.Color) string {
	if c == nil {
		return "#000000"
	}
	r, g, b, _ := c.RGBA()
	return fmt.Sprintf("#%02x%02x%02x", uint8(r>>8), uint8(g>>8), uint8(b>>8))
}

// RenderColorGradient takes a string and blends it from color c1 to c2 character-by-character.
func RenderColorGradient(text string, c1, c2 color.Color) string {
	return RenderGradient(text, ColorToHex(c1), ColorToHex(c2))
}

// RenderGradient takes a string and blends it from startHex to endHex color character-by-character.
func RenderGradient(text string, startHex, endHex string) string {
	r1, g1, b1 := parseHex(startHex)
	r2, g2, b2 := parseHex(endHex)

	runes := []rune(text)
	n := len(runes)
	if n <= 1 {
		return text
	}

	var result strings.Builder
	for i, rn := range runes {
		t := float64(i) / float64(n-1)
		r := int(float64(r1) + t*float64(r2-r1))
		g := int(float64(g1) + t*float64(g2-g1))
		b := int(float64(b1) + t*float64(b2-b1))

		fmt.Fprintf(&result, "\x1b[38;2;%d;%d;%dm%c", r, g, b, rn)
	}
	result.WriteString("\x1b[0m")
	return result.String()
}

// RenderFlowingGradient renders text with an animated wave gradient that cycles between c1 and c2 based on phase.
func RenderFlowingGradient(text string, c1, c2 color.Color, phase float64) string {
	r1, g1, b1, _ := c1.RGBA()
	r2, g2, b2, _ := c2.RGBA()

	red1, green1, blue1 := int(uint8(r1>>8)), int(uint8(g1>>8)), int(uint8(b1>>8))
	red2, green2, blue2 := int(uint8(r2>>8)), int(uint8(g2>>8)), int(uint8(b2>>8))

	runes := []rune(text)
	if len(runes) == 0 {
		return text
	}

	var result strings.Builder
	for i, rn := range runes {
		// Sine wave mapped to [0, 1] range with spatial frequency and time phase
		t := (math.Sin(float64(i)*0.35+phase) + 1.0) / 2.0
		r := int(float64(red1) + t*float64(red2-red1))
		g := int(float64(green1) + t*float64(green2-green1))
		b := int(float64(blue1) + t*float64(blue2-blue1))

		fmt.Fprintf(&result, "\x1b[38;2;%d;%d;%dm%c", r, g, b, rn)
	}
	result.WriteString("\x1b[0m")
	return result.String()
}

// ShimmerColor returns an interpolated color along a sine-wave phase between c1 and c2.
func ShimmerColor(c1, c2 color.Color, phase float64) color.Color {
	if c1 == nil || c2 == nil {
		return c1
	}
	r1, g1, b1, _ := c1.RGBA()
	r2, g2, b2, _ := c2.RGBA()

	red1, green1, blue1 := int(uint8(r1>>8)), int(uint8(g1>>8)), int(uint8(b1>>8))
	red2, green2, blue2 := int(uint8(r2>>8)), int(uint8(g2>>8)), int(uint8(b2>>8))

	t := (math.Sin(phase) + 1.0) / 2.0
	r := int(float64(red1) + t*float64(red2-red1))
	g := int(float64(green1) + t*float64(green2-green1))
	b := int(float64(blue1) + t*float64(blue2-blue1))

	return lipgloss.Color(fmt.Sprintf("#%02x%02x%02x", r, g, b))
}
