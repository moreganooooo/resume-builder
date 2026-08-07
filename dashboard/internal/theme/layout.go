package theme

import (
    "github.com/charmbracelet/lipgloss"
)

// Layout helper functions for consistent padding and margins.

// PadHorizontal adds horizontal padding of 2 cells (left/right) and no vertical padding.
func PadHorizontal(style lipgloss.Style) lipgloss.Style {
    return style.Padding(0, 2)
}

// PadVertical adds vertical padding of 1 cell (top/bottom) and no horizontal padding.
func PadVertical(style lipgloss.Style) lipgloss.Style {
    return style.Padding(1, 0)
}

// HoverStyle applies a subtle border to indicate hover/selection.
func HoverStyle(style lipgloss.Style) lipgloss.Style {
    return style.Border(lipgloss.NormalBorder()).BorderForeground(lipgloss.Color(AccentColor))
}
