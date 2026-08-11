package screens

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
)

// fitBar composes left and right content on a single line within width
// columns. Every header/help/footer bar in this package already floors its
// gap at 1 to avoid a negative repeat count, but flooring the gap alone
// doesn't stop left+right from overflowing width when the terminal is
// narrower than both pieces combined -- the composed line just wraps onto
// a second row, breaking the bar's single-line layout. fitBar truncates
// right first (it's given priority room up to the full available budget),
// then truncates left with whatever's left over, using ansi.Truncate --
// ANSI-escape-aware, so it can safely shorten an already-styled/rendered
// string -- so the composed line fits at any width down to 0, not just
// down to whatever width right alone happens to need.
//
// bg is the bar's own panel background (every caller wraps the returned
// three pieces in an outer style with this same Background). The caller's
// left/right strings arrive already-rendered (each ending in its own SGR
// reset), so the gap returned here is pre-rendered with bg too -- otherwise
// that reset clears the outer style's background for every column after
// the first rendered fragment, and the plain-string gap (and anything
// concatenated after it) falls back to the terminal's default background
// instead of bg. Confirmed by dumping the raw ANSI bytes of the composed
// line: only the segment before the first embedded reset ever carried the
// outer background. Callers still need their own left/right sub-styles
// (title, keyStyle, descStyle, etc.) to set Background(bg) themselves --
// fitBar only owns the gap, since it never sees those styles, only their
// rendered output.
func fitBar(left, right string, width, reserved int, bg lipgloss.Color) (string, string, string) {
	avail := width - reserved
	if avail < 0 {
		avail = 0
	}
	if lipgloss.Width(right) > avail {
		right = ansi.Truncate(right, avail, "…")
	}
	availForLeft := avail - lipgloss.Width(right)
	if availForLeft < 0 {
		availForLeft = 0
	}
	if lipgloss.Width(left) > availForLeft {
		left = ansi.Truncate(left, availForLeft, "…")
	}
	gap := avail - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 1 {
		gap = 1
	}
	gapStr := lipgloss.NewStyle().Background(bg).Render(strings.Repeat(" ", gap))
	return left, right, gapStr
}
