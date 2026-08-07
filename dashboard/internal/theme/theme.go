// Package theme provides the visual theme system for the dashboard.
package theme

import (
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/huh"
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

	// Gradients
	GradientStart lipgloss.Color
	GradientEnd   lipgloss.Color

	// Token grouping for UI components
	Token struct {
		Text          lipgloss.Color
		Subtext       lipgloss.Color
		GradientStart lipgloss.Color
		GradientEnd   lipgloss.Color
		Mauve         lipgloss.Color
	}

	// Icon set for UI elements
	Icons struct {
		Pipeline string
		Progress string
		Report   string
		Quit     string
		Menu     string
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
