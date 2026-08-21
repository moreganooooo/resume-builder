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
		Location string

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
		// isDark is huh's own guess, set from an async OSC background-color
		// query (tea.BackgroundColorMsg) that huh's Bubbletea Program sends
		// and waits on. Through this binary's Python-subprocess/pty
		// invocation that round trip is unreliable -- the response often
		// never arrives before first render, leaving isDark at Go's false
		// zero-value and producing light-theme colors (incl. black text)
		// against this app's actual dark terminal. This app never ships a
		// light theme regardless (see NewTheme's hardcoded "resume-builder"
		// case, never "auto"), so the incoming isDark is ignored in favor
		// of a hardcoded true.
		//
		// ThemeCatppuccin, not ThemeCharm: it's huh's built-in Catppuccin
		// theme, sourced from the same canonical Mocha palette this app's
		// own hex values already match (see catppuccin.go's Mauve
		// #cba6f7) -- so it styles every field (options, descriptions,
		// errors, buttons, text-input cursor/placeholder...), not just the
		// 3 this function overrides, and stays palette-consistent doing
		// it.
		ht := huh.ThemeCatppuccin(true)
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

// FormatTrackedHeader formats a header title with wide letter tracking and diamond accents.
// Example: "PIPELINE" -> "✦  P I P E L I N E  ✧"
func FormatTrackedHeader(title string) string {
	if len(title) == 0 {
		return "✦  ✧"
	}
	runes := []rune(title)
	var sb strings.Builder
	for i, r := range runes {
		if i > 0 {
			sb.WriteRune(' ')
		}
		sb.WriteRune(r)
	}
	return "✦  " + sb.String() + "  ✧"
}

func linearizeColorComponent(val float64) float64 {
	if val <= 0.04045 {
		return val / 12.92
	}
	return math.Pow((val+0.055)/1.055, 2.4)
}

// RelativeLuminance calculates the WCAG relative luminance of a color.
func RelativeLuminance(c color.Color) float64 {
	if c == nil {
		return 0
	}
	r, g, b, _ := c.RGBA()
	rs := float64(uint8(r>>8)) / 255.0
	gs := float64(uint8(g>>8)) / 255.0
	bs := float64(uint8(b>>8)) / 255.0

	rLin := linearizeColorComponent(rs)
	gLin := linearizeColorComponent(gs)
	bLin := linearizeColorComponent(bs)

	return 0.2126*rLin + 0.7152*gLin + 0.0722*bLin
}

// ContrastRatio calculates the WCAG 2.0 contrast ratio between two colors (ranging from 1.0 to 21.0).
func ContrastRatio(c1, c2 color.Color) float64 {
	l1 := RelativeLuminance(c1)
	l2 := RelativeLuminance(c2)

	lighter := math.Max(l1, l2)
	darker := math.Min(l1, l2)

	return (lighter + 0.05) / (darker + 0.05)
}
