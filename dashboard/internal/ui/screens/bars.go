package screens

import (
	"encoding/base64"
	"fmt"
	"image/color"
	"math"
	"strings"
	"time"

	"charm.land/bubbles/v2/progress"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/anim"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// fitBar composes left and right content on a single line within width
// columns. Every header/help/footer bar in this package already floors its
// gap at 1 to avoid a negative repeat count, but flooring the gap alone
// doesn't stop left+right from overflowing width when the terminal is
// narrower than both pieces combined -- the composed line just wraps onto
// a second row, breaking the bar's single-line layout. fitBar truncates
// right first (it's given priority room up to the full available budget),
// left second, and pads the remaining space with a background-colored gap
// of exact width.
//
// Background styling: fitBar returns (left, right, gap) rather than a
// pre-concatenated string. If it rendered the full line itself, any Reset
// sequence inside right (automatically appended by LipGloss when rendering
// a style) would strip the bar-level background color for the gap. That
// reset clears the outer style's background for every column after
// the first rendered fragment, and the plain-string gap (and anything
// concatenated after it) falls back to the terminal's default background
// instead of bg. Confirmed by dumping the raw ANSI bytes of the composed
// line: only the segment before the first embedded reset ever carried the
// outer background. Callers still need their own left/right sub-styles
// (title, keyStyle, descStyle, etc.) to set Background(bg) themselves --
// fitBar only owns the gap, since it never sees those styles, only their
// rendered output.
func fitBar(left, right string, width, reserved int, bg color.Color) (string, string, string) {
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
// pane, shared by jobs.go and pipeline.go.
//
// hintLines carries the actionable body of the card and MUST come from the
// calling screen: the two screens bind different keys to the same letters
// (on Pipeline "s" cycles the sort mode, while on Jobs it starts a scan),
// so a hardcoded shortcut here is wrong on one screen by construction --
// which is exactly how this card once told Jobs users to press "a" to add
// a role when "a" archives one. Pass nil for a bare card with no hints.
func renderEmptyDetailPane(t theme.Theme, width, height int, hintLines []string) string {
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Overlay).
		Width(width-2).
		Height(height-2).
		Padding(0, 0)

	innerWidth := width - 4
	innerHeight := height - 4
	if innerWidth < 10 || innerHeight < 3 {
		return borderStyle.Render("Select an item to view details")
	}

	// Build a 2D grid
	nowMs := float64(time.Now().UnixNano() / 1e6)

	grid := make([][]string, innerHeight)
	for y := 0; y < innerHeight; y++ {
		grid[y] = make([]string, innerWidth)
		for x := 0; x < innerWidth; x++ {
			// Deterministic pseudo-random generation of stars using a 2D coordinate hash
			hash := math.Sin(float64(x)*12.9898+float64(y)*78.233) * 43758.5453123
			hash = hash - math.Floor(hash)

			// Sparse distribution: ~6.5% density
			if hash < 0.065 {
				starType := int(hash*100) % 3
				twinkleFreq := 1.5 + (hash * 3.0) // 1.5 to 4.5 rad/s
				phase := hash * 10.0

				// Twinkle amplitude function
				brightness := 0.5 + 0.5*math.Sin(nowMs*0.001*twinkleFreq+phase)

				var char string
				switch starType {
				case 0:
					char = "✦"
				case 1:
					char = "✧"
				default:
					char = "·"
				}

				// Select gradient foreground based on dynamic brightness
				var col color.Color
				if brightness > 0.85 {
					col = t.Mauve
				} else if brightness > 0.6 {
					col = t.Sky
				} else if brightness > 0.35 {
					col = t.Blue
				} else {
					col = t.Overlay
				}

				grid[y][x] = lipgloss.NewStyle().Foreground(col).Render(char)
			} else {
				grid[y][x] = " "
			}
		}
	}

	// Centered multiline card block
	cardLines := append([]string{"✦ No active selection ✧", ""}, hintLines...)

	cardHeight := len(cardLines)
	if innerWidth > 40 && innerHeight > cardHeight+2 {
		midY := (innerHeight - cardHeight) / 2
		cardWidth := 40
		startX := (innerWidth - cardWidth) / 2

		titleStyle := lipgloss.NewStyle().Bold(true).Foreground(t.Mauve).Background(t.Surface)
		textStyle := lipgloss.NewStyle().Foreground(t.Text).Background(t.Surface)
		keyStyle := lipgloss.NewStyle().Foreground(t.Peach).Background(t.Surface)
		mutedStyle := lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface)

		for i, line := range cardLines {
			y := midY + i
			var renderedLine string

			// Center align each line text
			padLen := cardWidth - lipgloss.Width(line)
			if padLen < 0 {
				padLen = 0
			}
			padding := padLen / 2
			rightPad := padLen - padding
			paddedLine := strings.Repeat(" ", padding) + line + strings.Repeat(" ", rightPad)

			if i == 0 {
				renderedLine = titleStyle.Render(paddedLine)
			} else if strings.Contains(line, "[") && strings.Contains(line, "]") {
				parts := strings.SplitN(paddedLine, "[", 2)
				if len(parts) == 2 {
					subParts := strings.SplitN(parts[1], "]", 2)
					if len(subParts) == 2 {
						renderedLine = textStyle.Render(parts[0]) + keyStyle.Render("["+subParts[0]+"]") + textStyle.Render(subParts[1])
					} else {
						renderedLine = textStyle.Render(paddedLine)
					}
				} else {
					renderedLine = textStyle.Render(paddedLine)
				}
			} else if i == cardHeight-1 {
				renderedLine = mutedStyle.Render(paddedLine)
			} else {
				renderedLine = textStyle.Render(paddedLine)
			}

			// Replace grid row segment
			var rowText strings.Builder
			for x := 0; x < innerWidth; x++ {
				if x >= startX && x < startX+cardWidth {
					if x == startX {
						rowText.WriteString(renderedLine)
					}
				} else {
					rowText.WriteString(grid[y][x])
				}
			}
			grid[y] = []string{rowText.String()}
		}
	}

	// Flatten grid rows
	var lines []string
	for y := 0; y < innerHeight; y++ {
		if len(grid[y]) == 1 {
			lines = append(lines, grid[y][0])
		} else {
			lines = append(lines, strings.Join(grid[y], ""))
		}
	}

	return borderStyle.Render(strings.Join(lines, "\n"))
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

// HelpBinding is one key -> description pair shown in a screen's `?` help
// overlay.
type HelpBinding struct {
	Key  string
	Desc string
}

type helpBinding struct {
	key  string
	desc string
}

// HelpCategory groups related bindings under a heading -- Navigation,
// Actions, View, or Exit, matching how the design critique asked for these
// to be organized rather than dumped as one flat list.
type HelpCategory struct {
	Label    string
	Bindings []HelpBinding
}

type helpCategory struct {
	label    string
	bindings []helpBinding
}

// RenderHelpOverlay renders title's full keybinding reference as a
// bordered, categorized box that replaces the screen's normal body for as
// long as help is open -- simpler and more robust on a narrow terminal
// than trying to compose it alongside the split-pane content the way
// fitBar composes header/help bars, since the overlay owns the whole
// frame and can just wrap/clip its own lines to width/height directly.
func RenderHelpOverlay(t theme.Theme, title string, categories []HelpCategory, width, height int) string {
	var internalCats []helpCategory
	for _, c := range categories {
		var internalBindings []helpBinding
		for _, b := range c.Bindings {
			internalBindings = append(internalBindings, helpBinding{key: b.Key, desc: b.Desc})
		}
		internalCats = append(internalCats, helpCategory{label: c.Label, bindings: internalBindings})
	}
	return renderHelpOverlay(t, title, internalCats, width, height)
}

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

// ToastNotification manages brief popup feedback for user actions.
type ToastNotification struct {
	icon      string
	message   string
	visible   bool
	seconds   int
	particles *anim.ConfettiEngine
}

// NewToastNotification creates a new toast notification component.
func NewToastNotification() *ToastNotification {
	return &ToastNotification{
		particles: anim.NewConfettiEngine(80, 24),
	}
}

// Visible returns whether the toast is actively being displayed.
func (t *ToastNotification) Visible() bool {
	return t.visible
}

// Show activates the toast message with an icon and duration in seconds.
func (t *ToastNotification) Show(icon, msg string, seconds int) {
	t.icon = icon
	t.message = msg
	t.visible = true
	t.seconds = seconds
	if t.particles != nil {
		t.particles.Emit(40, 10, 25)
	}
}

// Hide clears the toast message immediately.
func (t *ToastNotification) Hide() {
	t.visible = false
	t.seconds = 0
	if t.particles != nil {
		t.particles.Clear()
	}
}

// TickSecond decreases the remaining display time by one second.
func (t *ToastNotification) TickSecond() {
	if !t.visible {
		return
	}
	t.seconds--
	if t.seconds <= 0 {
		t.Hide()
	}
}

// Update advances the particle physics of any associated confetti.
func (t *ToastNotification) Update() bool {
	if t.particles != nil && t.particles.Active() {
		return t.particles.Update()
	}
	return false
}

// Render formats the toast box centered in the available width.
func (t *ToastNotification) Render(th theme.Theme, width int) string {
	if !t.visible {
		return ""
	}
	style := lipgloss.NewStyle().
		Bold(true).
		Foreground(th.Base).
		Background(th.Mauve).
		Padding(0, 2).
		Border(lipgloss.RoundedBorder()).
		BorderForeground(th.Pink)

	text := fmt.Sprintf("%s %s", t.icon, t.message)
	return lipgloss.PlaceHorizontal(width, lipgloss.Center, style.Render(text))
}

// Truncate truncates string s to width columns using a single Unicode ellipsis ('…').
func Truncate(s string, width int) string {
	return ansi.Truncate(s, width, "…")
}

// RenderWindowResizeGuidance renders a user-friendly notice when the terminal is below minimum dimensions.
func RenderWindowResizeGuidance(currentW, currentH, minW, minH int, t theme.Theme) string {
	boxStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Peach).
		Padding(1, 2).
		Align(lipgloss.Center)

	title := lipgloss.NewStyle().Bold(true).Foreground(t.Peach).Render("✦ Terminal Window Too Small ✧")
	current := lipgloss.NewStyle().Foreground(t.Red).Render(fmt.Sprintf("Current: %d×%d", currentW, currentH))
	required := lipgloss.NewStyle().Foreground(t.Green).Render(fmt.Sprintf("Required: %d×%d", minW, minH))
	hint := lipgloss.NewStyle().Foreground(t.Subtext).Render("Please expand your terminal window for optimal viewing.")

	content := fmt.Sprintf("%s\n\n%s  |  %s\n\n%s", title, current, required, hint)
	renderedBox := boxStyle.Render(content)
	if currentW <= 0 || currentH <= 0 {
		return renderedBox
	}
	return lipgloss.Place(currentW, currentH, lipgloss.Center, lipgloss.Center, renderedBox)
}

// RenderHierarchicalFooter renders an action bar with visual tier distinction (Primary, Actions, System).
func RenderHierarchicalFooter(t theme.Theme, width int, primary, actions, system []HelpBinding) string {
	style := lipgloss.NewStyle().
		Foreground(t.Text).
		Background(t.Surface).
		Width(width).
		Padding(0, 1)

	var parts []string
	for _, b := range primary {
		key := lipgloss.NewStyle().Bold(true).Foreground(t.Mauve).Background(t.Surface).Render("[" + b.Key + "]")
		desc := lipgloss.NewStyle().Foreground(t.Text).Background(t.Surface).Render(" " + b.Desc)
		parts = append(parts, key+desc)
	}
	for _, b := range actions {
		key := lipgloss.NewStyle().Bold(true).Foreground(t.Blue).Background(t.Surface).Render(b.Key)
		desc := lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface).Render(" " + b.Desc)
		parts = append(parts, key+desc)
	}
	for _, b := range system {
		key := lipgloss.NewStyle().Bold(true).Foreground(t.Overlay).Background(t.Surface).Render(b.Key)
		desc := lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface).Render(" " + b.Desc)
		parts = append(parts, key+desc)
	}

	keys := strings.Join(parts, "  ")
	brand := lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface).Render("resume-builder")
	keys, brand, gap := fitBar(keys, brand, width, 2, t.Surface)
	return style.Render(keys + gap + brand)
}

// FormatOSC52Copy formats text into an ANSI OSC 52 clipboard write sequence.
func FormatOSC52Copy(text string) string {
	b64 := base64.StdEncoding.EncodeToString([]byte(text))
	return fmt.Sprintf("\x1b]52;c;%s\x07", b64)
}
