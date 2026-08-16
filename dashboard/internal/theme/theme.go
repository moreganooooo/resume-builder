// Package theme provides the visual theme system for the dashboard.
package theme

import (
	"fmt"
	"image/color"
	"os"
	"strings"

	"charm.land/huh/v2"
	lipgloss "charm.land/lipgloss/v2"
	"github.com/charmbracelet/colorprofile"
	"github.com/muesli/termenv"
)

var terminalProfile = colorprofile.Detect(os.Stdout, os.Environ())

func c(ansi, ansi256, truecolor string) color.Color {
	complete := lipgloss.Complete(terminalProfile)
	return complete(
		lipgloss.Color(ansi),
		lipgloss.Color(ansi256),
		lipgloss.Color(truecolor),
	)
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
		fmt.Sscanf(h, "%1x%1x%1x", &r, &g, &b)
		r = r * 17
		g = g * 17
		b = b * 17
		return
	}
	if len(h) == 6 {
		fmt.Sscanf(h, "%2x%2x%2x", &r, &g, &b)
	}
	return
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

		colorHex := fmt.Sprintf("#%02x%02x%02x", r, g, b)
		style := lipgloss.NewStyle().Foreground(lipgloss.Color(colorHex))
		result.WriteString(style.Render(string(rn)))
	}
	return result.String()
}

