package theme

import (
	"charm.land/lipgloss/v2"
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

// HoverStyle applies a sleek, left-only vertical border line (┃) to indicate
// hover/selection, matching Crush's precise active sidebar indicators.
// Left padding is adjusted to 1, which combines with the 1-character left
// border to align content perfectly with unselected rows (which have a flat left padding of 2).
func HoverStyle(style lipgloss.Style, t Theme) lipgloss.Style {
	return style.
		Border(lipgloss.Border{Left: "┃"}, false, false, false, true).
		BorderForeground(t.Token.Mauve).
		PaddingLeft(1)
}
