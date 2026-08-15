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

// HoverStyle applies a subtle border to indicate hover/selection, using the
// active theme's own Mauve accent rather than the fixed AccentColor
// constant -- that constant is the same hex value in every theme, so a
// selected Pipeline/Jobs row previously kept a dark-theme-tuned border
// color even under Catppuccin Latte's light palette.
func HoverStyle(style lipgloss.Style, t Theme) lipgloss.Style {
    return style.Border(lipgloss.NormalBorder()).BorderForeground(t.Token.Mauve)
}
