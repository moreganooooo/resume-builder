package screens

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/progress"
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

// scoreIcon returns the tier icon matching scoreStyle's own color banding,
// so a colorblind user isn't relying on color alone to read a composite/
// interview-probability score's tier -- previously scoreStyle encoded the
// tier purely by color, with no redundant cue, unlike colorize_icon()
// (scripts/theme.py), which pairs every semantic color in this codebase
// with a distinct icon. Reuses the CLI's own established icon vocabulary
// (success/gem/hint/skip -- see icons.go's MenuIcons.Score* fields) rather
// than inventing new glyphs, and honors RESUME_BUILDER_ICONS=unicode the
// same way every other glyph in this package already does, since it's
// read from theme.Theme.Icons rather than hardcoded here.
func scoreIcon(t theme.Theme, score float64) string {
	switch {
	case score >= 4.2:
		return t.Icons.ScoreStrong
	case score >= 3.8:
		return t.Icons.ScoreGood
	case score >= 3.0:
		return t.Icons.ScoreFair
	default:
		return t.Icons.ScoreWeak
	}
}

// renderSidebarRow renders the shared two-line sidebar row shape: a score
// prefix plus a company/primary name (bold when selected), then a Blue
// subtitle (job title / role) on the line below, hover-highlighted when
// selected. jobs.go's renderSidebarLine and pipeline.go's
// renderSidebarAppLine were identical apart from field names.
func renderSidebarRow(t theme.Theme, score float64, company, subtitle string, width int, selected bool) string {
	scoreText := scoreStyle(t, score).Render(scoreIcon(t, score) + " " + fmt.Sprintf("%.1f", score))

	// compWidth: total minus score glyph+space+number (≈ 6) minus 1 guard
	// for the PadHorizontal outer padding, so company text doesn't wrap or
	// ellipsize a char too early on narrow sidebars.
	compWidth := width - 7
	if compWidth < 8 {
		compWidth = 8
	}
	companyText := truncateRunes(company, compWidth)
	companyStyle := lipgloss.NewStyle().Foreground(t.Text)
	if selected {
		companyStyle = companyStyle.Bold(true)
	}
	line1 := fmt.Sprintf("%s %s", scoreText, companyStyle.Render(companyText))

	// subtitleWidth: full available width minus 1 for the outer PadHorizontal
	subtitleWidth := width - 3
	if subtitleWidth < 8 {
		subtitleWidth = 8
	}
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

// -- Help overlay --
//
// Each major screen has 12-14 single-letter keybindings living only in its
// dense bottom help bar -- discoverable only by reading a single packed
// line, in whatever order the bar happens to list them. helpBinding/
// helpCategory/renderHelpOverlay give every screen a `?`-triggered,
// categorized reference (Navigation/Actions/View/Exit) instead, dismissed
// the same way (`?`, Esc, or q) everywhere it appears.

// helpBinding is one key -> description pair shown in a screen's `?` help
// overlay.
type helpBinding struct {
	key  string
	desc string
}

// helpCategory groups related bindings under a heading -- Navigation,
// Actions, View, or Exit, matching how the design critique asked for these
// to be organized rather than dumped as one flat list.
type helpCategory struct {
	label    string
	bindings []helpBinding
}

// renderHelpOverlay renders title's full keybinding reference as a
// bordered, categorized box that replaces the screen's normal body for as
// long as help is open -- simpler and more robust on a narrow terminal
// than trying to compose it alongside the split-pane content the way
// fitBar composes header/help bars, since the overlay owns the whole
// frame and can just wrap/clip its own lines to width/height directly.
func renderHelpOverlay(t theme.Theme, title string, categories []helpCategory, width, height int) string {
	headerStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(t.Text).
		Background(t.Surface).
		Width(width).
		Padding(0, 2)
	header := headerStyle.Render(title + " Help")

	footerStyle := lipgloss.NewStyle().
		Foreground(t.Subtext).
		Background(t.Surface).
		Width(width).
		Padding(0, 1)
	footer := footerStyle.Render(
		lipgloss.NewStyle().Bold(true).Foreground(t.Text).Background(t.Surface).Render("? / Esc / q") +
			lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface).Render(" close help"))

	catStyle := lipgloss.NewStyle().Bold(true).Foreground(t.Mauve)
	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(t.Blue).Width(14)
	descStyle := lipgloss.NewStyle().Foreground(t.Text)

	innerWidth := width - 6 // border (2) + PadHorizontal-equivalent (2+2)
	if innerWidth < 10 {
		innerWidth = 10
	}

	var lines []string
	for _, cat := range categories {
		if len(lines) > 0 {
			lines = append(lines, "")
		}
		lines = append(lines, catStyle.Render(cat.label))
		for _, b := range cat.bindings {
			line := "  " + keyStyle.Render(b.key) + descStyle.Render(b.desc)
			if lipgloss.Width(line) > innerWidth {
				line = ansi.Truncate(line, innerWidth, "…")
			}
			lines = append(lines, line)
		}
	}

	// bodyBudget mirrors fitBar/renderTabs's own narrow-terminal discipline:
	// degrade (here, clip with a dimmed notice) rather than let the overlay
	// overflow the terminal on a short window.
	bodyBudget := height - 4 // header + footer + border top/bottom
	if bodyBudget < 3 {
		bodyBudget = 3
	}
	if len(lines) > bodyBudget {
		lines = lines[:bodyBudget-1]
		lines = append(lines, lipgloss.NewStyle().Foreground(t.Subtext).Render("  … grow the terminal to see the rest"))
	}

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Mauve).
		Width(width-2).
		Padding(1, 2)

	body := borderStyle.Render(strings.Join(lines, "\n"))
	return lipgloss.JoinVertical(lipgloss.Left, header, body, footer)
}

// renderStatusPickerOverlay renders a status picker inline at the bottom of
// body, at up to 30 columns wide but never wider than availWidth allows.
// jobs.go's and pipeline.go's overlayStatusPicker differed only in header
// text and options list.
//
// confirmLabel, when non-empty, swaps the option list for a one-line
// inline confirm prompt instead ("Mark as Interview?") -- application-
// status changes are destructive-but-free (see scripts/cli_art.py's
// confirm_destructive, which exists for the identical bug class on the
// CLI side: "the audit found cost-gated Gemini calls confirming properly
// while destructive-but-free actions ... committed instantly"), so
// picking an option here is a proposal, not a commit, until the caller's
// own confirm sub-state accepts a second Enter/y or cancels on Esc/n. Kept
// inline rather than a heavy modal to match that same file's existing
// cost-gated confirms' lightweight tone.
func renderStatusPickerOverlay(t theme.Theme, body string, availWidth int, header string, options []string, cursor int, confirmLabel string) string {
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
	if confirmLabel != "" {
		confirmStyle := lipgloss.NewStyle().Foreground(t.Yellow).Bold(true).Width(pickerWidth)
		hintStyle := lipgloss.NewStyle().Foreground(t.Subtext).Width(pickerWidth)
		picker = append(picker, padStyle.Render(confirmStyle.Render(truncateRunes(confirmLabel, pickerWidth))))
		picker = append(picker, padStyle.Render(hintStyle.Render("Enter/y confirm  Esc/n cancel")))
	} else {
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
	}

	bodyLines = append(bodyLines, picker...)
	return strings.Join(bodyLines, "\n")
}

// renderModalOverlay renders content as a centered modal dialog over a
// dimmed background (similar to Crush IDE's modal style). background is the
// full-screen content to render behind the modal, content is the modal's body.
func renderModalOverlay(t theme.Theme, background string, content string, width, height int) string {
	// Split background and content into lines
	bgLines := strings.Split(background, "\n")
	contentLines := strings.Split(content, "\n")

	// Modal dimensions: 80% of screen width, centered
	modalWidth := int(float64(width) * 0.8)
	if modalWidth > 100 {
		modalWidth = 100 // Cap at 100 columns
	}
	if modalWidth < 40 {
		modalWidth = 40 // Minimum 40 columns
	}
	modalHeight := len(contentLines) + 4 // +4 for border/padding

	// Ensure we don't exceed screen height
	if modalHeight > height-4 {
		modalHeight = height - 4
	}

	// Calculate centered position
	startCol := (width - modalWidth) / 2
	if startCol < 0 {
		startCol = 0
	}
	startRow := (height - modalHeight) / 2
	if startRow < 0 {
		startRow = 0
	}

	// Create modal with border
	border := lipgloss.NewStyle().
		BorderStyle(lipgloss.RoundedBorder()).
		BorderForeground(t.Blue).
		Background(t.Surface).
		Foreground(t.Text).
		Width(modalWidth - 2)

	// Render modal content
	modalContent := border.Render(strings.Join(contentLines, "\n"))
	modalLines := strings.Split(modalContent, "\n")

	// Build output: overlay modal on background with dimming
	var result []string
	dimStyle := lipgloss.NewStyle().Foreground(t.Overlay)

	for i := 0; i < height; i++ {
		bgLine := ""
		if i < len(bgLines) {
			bgLine = bgLines[i]
		}

		// Strip existing ANSI colors and format to exact width
		stripped := ansi.Strip(bgLine)
		runes := []rune(stripped)
		if len(runes) > width {
			runes = runes[:width]
		} else {
			for len(runes) < width {
				runes = append(runes, ' ')
			}
		}

		// Check if this row intersects the modal
		if i >= startRow && i < startRow+len(modalLines) && i < startRow+modalHeight {
			modalIdx := i - startRow
			modalLine := ""
			if modalIdx < len(modalLines) {
				modalLine = modalLines[modalIdx]
			}
			modalW := ansi.StringWidth(modalLine)

			leftPart := dimStyle.Render(string(runes[:startCol]))
			
			rightCol := startCol + modalW
			rightPart := ""
			if rightCol < width {
				rightPart = dimStyle.Render(string(runes[rightCol:]))
			}

			result = append(result, leftPart+modalLine+rightPart)
		} else {
			// Dim the entire background line
			result = append(result, dimStyle.Render(string(runes)))
		}
	}

	return strings.Join(result, "\n")
}

// renderThickProgress renders a progress bar with multiple lines for a
// thicker/bolder appearance. The standard bubbles progress bar is a single
// line; this stacks 3 rendered lines with the same percent to create a
// visually heavier bar that matches the reference design.
func renderThickProgress(p progress.Model, theme theme.Theme, thickness int) string {
	if thickness <= 1 {
		return p.View()
	}
	var lines []string
	single := p.View()
	for i := 0; i < thickness; i++ {
		lines = append(lines, single)
	}
	return strings.Join(lines, "\n")
}
