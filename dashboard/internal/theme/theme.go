// Package theme provides the visual theme system for the dashboard.
package theme

import (
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// Theme holds all color definitions for the pipeline dashboard.
type Theme struct {
	// Base colors
	Base    lipgloss.Color
	Surface lipgloss.Color
	Overlay lipgloss.Color
	Text    lipgloss.Color
	Subtext lipgloss.Color

	// Accent colors
	Blue   lipgloss.Color
	Mauve  lipgloss.Color
	Green  lipgloss.Color
	Yellow lipgloss.Color
	Sky    lipgloss.Color
	Peach  lipgloss.Color
	Red    lipgloss.Color
	Pink   lipgloss.Color

	// Token grouping for UI components
	Token struct {
		Text    lipgloss.Color
		Subtext lipgloss.Color
		Mauve   lipgloss.Color
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
		Source   string
		Path     string
		Magic    string
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

// HuhTheme converts the internal Theme into a *huh.Theme that matches the
// current colour palette. huh.Theme has no flat Base/Secondary/Accent
// fields (that was never a real huh API) -- it's a full FieldStyles tree,
// so this starts from huh's own Charm preset and recolors just the
// pieces our palette actually differs on. Returns a pointer since that's
// what Form.WithTheme (the only real setter -- there is no Form.Theme
// method) expects.
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
func (t Theme) HuhTheme() *huh.Theme {
	ht := huh.ThemeCharm()
	ht.Focused.Title = ht.Focused.Title.Foreground(t.Token.Mauve)
	ht.Focused.SelectSelector = ht.Focused.SelectSelector.Foreground(t.Token.Mauve)
	ht.Blurred.Title = ht.Blurred.Title.Foreground(t.Token.Subtext)
	return ht
}
