package screens

import (
	"fmt"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- ScrollIndicator --
//
// The design system's ScrollIndicator: a one-cell right-edge rail plus a
// top-right readout, so a long pane says where it is without spending a line
// on a "showing 12 of 28" banner. Every scrolling surface here either said
// nothing at all (Viewer, Progress) or said it in prose, which is the
// inconsistency this closes.
//
// Two rules from the spec are load-bearing and easy to lose:
//   - the rail HIDES when the content fits. A full-height thumb is not
//     information, it is furniture that reads as a scrollbar stuck at the top.
//   - percentages CLAMP to 0 and 100. Rounding a nearly-scrolled pane to 99%
//     is how a person ends up scrolling for a line that is already visible.

// ScrollState is what a screen knows about its own pane. Total is the content
// length, Visible the window height, and Offset the index of the first shown
// line -- the same three numbers every scrolling model here already keeps.
type ScrollState struct {
	Total   int
	Visible int
	Offset  int
}

// Fits reports whether the content needs no rail at all.
func (s ScrollState) Fits() bool {
	return s.Total <= s.Visible || s.Visible <= 0
}

// maxOffset is the largest Offset that still fills the window.
func (s ScrollState) maxOffset() int {
	m := s.Total - s.Visible
	if m < 0 {
		return 0
	}
	return m
}

// Percent is the scroll position as 0-100, clamped at both ends. Content that
// fits is 0: it is all visible, which is the top.
func (s ScrollState) Percent() int {
	if s.Fits() {
		return 0
	}
	off := s.Offset
	if off < 0 {
		off = 0
	}
	if off >= s.maxOffset() {
		return 100
	}
	return int(float64(off) / float64(s.maxOffset()) * 100)
}

// ScrollReadout is the top-right text: "12%" by default, or "3 of 28" when
// the unit is a row a person can point at rather than a line of wrapped prose.
// Returns "" when the content fits, so a caller can join it unconditionally.
func ScrollReadout(t theme.Theme, s ScrollState) string {
	if s.Fits() {
		return ""
	}
	return lipgloss.NewStyle().Foreground(t.Subtext).Render(fmt.Sprintf("%d%%", s.Percent()))
}

// ScrollCountReadout is the "3 of 28" form, for panes whose unit is a
// selectable item. cursor is zero-based.
func ScrollCountReadout(t theme.Theme, cursor, total int) string {
	if total <= 0 {
		return ""
	}
	return lipgloss.NewStyle().Foreground(t.Subtext).Render(fmt.Sprintf("%d of %d", cursor+1, total))
}

// ScrollRail renders the right-edge rail as `height` lines of one cell each:
// an Overlay track with a Mauve thumb sized to the visible fraction. Returns
// an empty slice when the content fits, so `for i, line := range body` can
// append rail[i] only when there is one.
func ScrollRail(t theme.Theme, s ScrollState, height int) []string {
	if height <= 0 || s.Fits() {
		return nil
	}

	track := lipgloss.NewStyle().Foreground(t.Overlay).Render("│")
	thumb := lipgloss.NewStyle().Foreground(t.Mauve).Render("█")

	// Thumb length is the visible fraction of the content, never zero (a
	// rail with no thumb cannot show a position) and never the whole rail
	// (that is what Fits() already covers).
	thumbLen := height * s.Visible / s.Total
	if thumbLen < 1 {
		thumbLen = 1
	}
	if thumbLen > height-1 {
		thumbLen = height - 1
	}

	// Place the thumb by scroll fraction, then clamp so the last line of
	// content always parks it against the bottom -- an off-by-one here reads
	// as "there is more below" on a pane that has none.
	start := 0
	if m := s.maxOffset(); m > 0 {
		start = (height - thumbLen) * s.Offset / m
	}
	if start < 0 {
		start = 0
	}
	if start > height-thumbLen {
		start = height - thumbLen
	}

	rail := make([]string, height)
	for i := range rail {
		if i >= start && i < start+thumbLen {
			rail[i] = thumb
		} else {
			rail[i] = track
		}
	}
	return rail
}

// AttachScrollRail glues a rail onto the right edge of an already-rendered
// block, one cell per line. The block is returned unchanged when the content
// fits, so callers need no conditional.
//
// Lines are padded (and over-long ones truncated) to innerWidth first: a rail
// that follows ragged text is a zigzag, not an edge, and a line left at full
// width wraps once the rail cell is appended -- which adds a line and pushes a
// screen's footer off, exactly what the Jobs and Pipeline fit tests catch.
//
// innerWidth is the space available BEFORE the rail's own cell, so callers
// pass their pane's usable width minus one. For a detail pane, that is
// width-detailPaneChrome-1: lipgloss counts the border and padding inside
// Width, and both detail panes style the box itself at width-2, so the text
// area is width-8 (see detailPaneChrome in bars.go).
func AttachScrollRail(t theme.Theme, block string, s ScrollState, innerWidth int) string {
	lines := strings.Split(block, "\n")
	rail := ScrollRail(t, s, len(lines))
	if rail == nil || innerWidth <= 0 {
		return block
	}

	target := innerWidth

	for i, line := range lines {
		w := lipgloss.Width(line)
		switch {
		case w < target:
			line += strings.Repeat(" ", target-w)
		case w > target:
			// Truncation, not overflow: the rail cell comes out of the pane's
			// own budget. A full-width line plus a rail cell wraps, which adds
			// a line and pushes the footer off -- what the Jobs and Pipeline
			// fit tests catch.
			line = ansi.Truncate(line, target, "\u2026")
		}
		lines[i] = line + rail[i]
	}
	return strings.Join(lines, "\n")
}
