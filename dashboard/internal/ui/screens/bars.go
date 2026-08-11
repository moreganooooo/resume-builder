package screens

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
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
	// left+right is guaranteed <= avail by the truncation above, so gap can
	// only be 0 or positive here -- never negative. Flooring at 1 (the
	// previous behavior) fired on the exact-fill case (gap == 0) too,
	// forcing the composed left+gap+right to be avail+1 columns wide,
	// contradicting this function's own "fits at any width" doc comment
	// above. 0 is a valid gap (left glued directly to right) and still
	// fits within avail, so only guard against the actually-impossible
	// negative case.
	gap := avail - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 0 {
		gap = 0
	}
	gapStr := lipgloss.NewStyle().Background(bg).Render(strings.Repeat(" ", gap))
	return left, right, gapStr
}

// -- Shared split-pane helpers --
//
// jobs.go and pipeline.go both implement a two-pane "sidebar list + detail
// pane" screen over different row types (JobRow vs CareerApplication).
// Everything below was previously duplicated near-verbatim between the two
// files (a prior audit's own finding); factored here once both screens
// converged on the identical rendering shape, so a future fix to one
// applies to both instead of risking the kind of drift where one screen
// gets a fix (e.g. a scroll/overflow guard) the other never receives.

// scoreStyle colors a composite/interview-probability score by tier --
// shared by jobs.go's CompositeScore and pipeline.go's Score, which use the
// identical thresholds.
func scoreStyle(t theme.Theme, score float64) lipgloss.Style {
	switch {
	case score >= 4.2:
		return lipgloss.NewStyle().Foreground(t.Green).Bold(true)
	case score >= 3.8:
		return lipgloss.NewStyle().Foreground(t.Yellow)
	case score >= 3.0:
		return lipgloss.NewStyle().Foreground(t.Text)
	default:
		return lipgloss.NewStyle().Foreground(t.Red)
	}
}

// renderSidebarRow renders the shared two-line sidebar row shape: a score
// prefix plus a company/primary name (bold when selected), then a Blue
// subtitle (job title / role) on the line below, hover-highlighted when
// selected. jobs.go's renderSidebarLine and pipeline.go's
// renderSidebarAppLine were identical apart from field names.
func renderSidebarRow(t theme.Theme, score float64, company, subtitle string, width int, selected bool) string {
	scoreText := scoreStyle(t, score).Render(fmt.Sprintf("%.1f", score))

	compWidth := width - 6
	companyText := truncateRunes(company, compWidth)
	companyStyle := lipgloss.NewStyle().Foreground(t.Text)
	if selected {
		companyStyle = companyStyle.Bold(true)
	}
	line1 := fmt.Sprintf("%s %s", scoreText, companyStyle.Render(companyText))

	subtitleWidth := width - 2
	subtitleText := truncateRunes(subtitle, subtitleWidth)
	subtitleStyle := lipgloss.NewStyle().Foreground(t.Blue)
	line2 := subtitleStyle.Render(subtitleText)

	block := line1 + "\n" + line2
	base := theme.PadHorizontal(lipgloss.NewStyle())
	if selected {
		base = theme.HoverStyle(base, t)
	}
	return base.Render(block)
}

// renderEmptyDetailPane renders the "nothing selected" state of the detail
// pane -- byte-for-byte identical between jobs.go and pipeline.go.
func renderEmptyDetailPane(t theme.Theme, width, height int) string {
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Overlay).
		Width(width-2).
		Height(height-2).
		Padding(1, 2)
	return borderStyle.Render(lipgloss.NewStyle().Foreground(t.Subtext).Render("Select a job to view details"))
}

// detailPaneStyles bundles the border + text styles shared by every detail
// pane -- jobs.go's renderJobDetailPane and pipeline.go's own built the
// exact same four styles from theme alone before diverging on content.
type detailPaneStyles struct {
	Border  lipgloss.Style
	Title   lipgloss.Style
	Subtext lipgloss.Style
	Value   lipgloss.Style
}

func newDetailPaneStyles(t theme.Theme, width, height int) detailPaneStyles {
	return detailPaneStyles{
		Border: lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(t.Overlay).
			Width(width-2).
			Height(height-2).
			Padding(1, 2),
		Title:   lipgloss.NewStyle().Bold(true).Foreground(t.Blue),
		Subtext: lipgloss.NewStyle().Foreground(t.Subtext),
		Value:   lipgloss.NewStyle().Foreground(t.Text),
	}
}

// renderStatusPickerOverlay renders a status picker inline at the bottom of
// body, at up to 30 columns wide but never wider than availWidth allows.
// jobs.go's and pipeline.go's overlayStatusPicker differed only in header
// text and options list.
func renderStatusPickerOverlay(t theme.Theme, body string, availWidth int, header string, options []string, cursor int) string {
	bodyLines := strings.Split(body, "\n")

	pickerWidth := availWidth - 4 // PadHorizontal's own 2+2 columns
	if pickerWidth > 30 {
		pickerWidth = 30
	}
	if pickerWidth < 10 {
		pickerWidth = 10
	}
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	headerStyle := lipgloss.NewStyle().Foreground(t.Blue).Bold(true)

	var picker []string
	picker = append(picker, padStyle.Render(headerStyle.Render(header)))
	for i, opt := range options {
		style := lipgloss.NewStyle().Foreground(t.Blue).Width(pickerWidth)
		if i == cursor {
			style = style.Background(t.Overlay).Bold(true)
		}
		prefix := "  "
		if i == cursor {
			prefix = "> "
		}
		picker = append(picker, padStyle.Render(style.Render(prefix+opt)))
	}

	bodyLines = append(bodyLines, picker...)
	return strings.Join(bodyLines, "\n")
}
