package screens

import (
	"fmt"
	"image/color"
	"math"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// ProgressClosedMsg is emitted when the progress screen is dismissed. Quit
// distinguishes "q" (exit the whole app) from "esc" (back to the screen
// that opened Progress), matching Pipeline/Jobs's own PipelineClosedMsg/
// JobsClosedMsg -- previously both keys did the same thing here (always
// "back"), so "q" quit the app everywhere except this screen and Reports.
type ProgressClosedMsg struct{ Quit bool }

// ProgressModel implements the progress analytics screen.
type ProgressModel struct {
	metrics      model.ProgressMetrics
	scrollOffset int
	width        int
	height       int
	theme        theme.Theme
	// showHelp toggles the `?` categorized keybinding overlay (see
	// bars.go's renderHelpOverlay) over this screen's normal body.
	showHelp bool
}

var progressHelpCategories = []helpCategory{
	{"Navigation", []helpBinding{
		{"↑ ↓ / j k", "Scroll"},
		{"PgUp / PgDn", "Page up / down"},
	}},
	{"Exit", []helpBinding{
		{"Esc", "Back to Main Menu"},
		{"q", "Quit dashboard"},
	}},
}

// NewProgressModel creates a new progress screen.
func NewProgressModel(t theme.Theme, metrics model.ProgressMetrics, width, height int) ProgressModel {
	return ProgressModel{
		metrics: metrics,
		width:   width,
		height:  height,
		theme:   t,
	}
}

// Init implements tea.Model.
func (m ProgressModel) Init() tea.Cmd {
	return nil
}

// Resize updates dimensions.
func (m *ProgressModel) Resize(width, height int) {
	m.width = width
	m.height = height
	m.clampScrollOffset()
}

// Update handles input for the progress screen.
func (m ProgressModel) Update(msg tea.Msg) (ProgressModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.MouseWheelMsg:
		// Button, not Y (always >= 0, the screen row -- not a delta),
		// determines wheel direction. See jobs.go's identical fix.
		if msg.Button == tea.MouseWheelUp {
			if m.scrollOffset > 0 {
				m.scrollOffset -= 2
				if m.scrollOffset < 0 {
					m.scrollOffset = 0
				}
			}
		} else if msg.Button == tea.MouseWheelDown {
			m.scrollOffset += 2
			m.clampScrollOffset()
		}
		return m, nil
	case tea.KeyPressMsg:
		return m.handleKeyString(msg.String())
	case tea.KeyMsg:
		return m.handleKeyString(msg.String())
	}
	return m, nil
}

func (m ProgressModel) handleKeyString(k string) (ProgressModel, tea.Cmd) {
	if m.showHelp {
		switch k {
		case "?", "esc", "q":
			m.showHelp = false
		}
		return m, nil
	}
	switch k {
	case "?":
		m.showHelp = true
	case "q":
		return m, func() tea.Msg { return ProgressClosedMsg{Quit: true} }
	case "esc":
		return m, func() tea.Msg { return ProgressClosedMsg{} }
	case "down", "j":
		m.scrollOffset++
		m.clampScrollOffset()
	case "up", "k":
		if m.scrollOffset > 0 {
			m.scrollOffset--
		}
	case "pgdown", "ctrl+d":
		m.scrollOffset += m.height / 2
		m.clampScrollOffset()
	case "pgup", "ctrl+u":
		m.scrollOffset -= m.height / 2
		if m.scrollOffset < 0 {
			m.scrollOffset = 0
		}
	case "home", "g":
		m.scrollOffset = 0
	}
	return m, nil
}

// renderBody assembles the scrollable panels (funnel/scores/rates/weekly)
// before scroll-offset slicing is applied. Shared by View() and
// maxScrollOffset() so the scroll ceiling always matches what actually
// gets rendered, instead of two separate computations that could drift.
func (m ProgressModel) renderBody() string {
	funnel := m.renderFunnel()
	funnelDrilldown := m.renderFunnelDrilldown()
	scores := m.renderScoreDistribution()
	rates := m.renderRates()
	radar := m.renderStrategyRadar()
	platforms := m.renderPlatformYield()
	companies := m.renderCompanyConcentration()
	scatter := m.renderScoreVsCoverage()
	weekly := m.renderWeeklyActivity()
	missionControl := m.renderMissionControl()

	return lipgloss.JoinVertical(lipgloss.Left,
		funnel,
		"",
		funnelDrilldown,
		"",
		scores,
		"",
		rates,
		"",
		radar,
		"",
		platforms,
		"",
		companies,
		"",
		scatter,
		"",
		weekly,
		"",
		missionControl,
	)
}

// bodyAvailHeight is the number of body rows visible between the header
// and help bar. Shared by View()'s render and the scroll clamp below so
// they always agree on where the bottom of the screen actually is.
func (m ProgressModel) bodyAvailHeight() int {
	availHeight := m.height - 4 // header + help + padding
	if availHeight < 3 {
		availHeight = 3
	}
	return availHeight
}

// maxScrollOffset is the highest scrollOffset that still reveals new
// content -- mirrors ViewerModel.clampScrollOffset's own maxScroll
// computation (see viewer.go).
func (m ProgressModel) maxScrollOffset() int {
	lines := strings.Split(m.renderBody(), "\n")
	max := len(lines) - m.bodyAvailHeight()
	if max < 0 {
		max = 0
	}
	return max
}

// clampScrollOffset bounds m.scrollOffset to [0, maxScrollOffset()].
// Previously only View() clamped scroll position, and only in a local
// copy used for rendering -- m.scrollOffset itself had no ceiling, so
// holding "down"/pgdown past the bottom of the content let it climb
// arbitrarily far past what the content needed. A single "up" press after
// that read as a dead key: decrementing an overshot value by one still
// clamped to the same bottom-of-content line in the next render, so
// nothing visibly moved until enough presses brought it back under the
// real ceiling. Matches ViewerModel's own clampScrollOffset (viewer.go),
// called after every scroll key and on resize there too.
func (m *ProgressModel) clampScrollOffset() {
	if max := m.maxScrollOffset(); m.scrollOffset > max {
		m.scrollOffset = max
	}
	if m.scrollOffset < 0 {
		m.scrollOffset = 0
	}
}

// View renders the progress screen.
func (m ProgressModel) View() string {
	header := m.renderHeader()
	help := m.renderHelp()
	body := m.renderBody()

	// Apply scroll
	bodyLines := strings.Split(body, "\n")
	offset := m.scrollOffset
	if offset >= len(bodyLines) {
		offset = len(bodyLines) - 1
	}
	if offset < 0 {
		offset = 0
	}
	if offset > 0 {
		bodyLines = bodyLines[offset:]
	}

	// Clamp to available height
	availHeight := m.bodyAvailHeight()
	if len(bodyLines) > availHeight {
		bodyLines = bodyLines[:availHeight]
	}

	body = strings.Join(bodyLines, "\n")

	full := lipgloss.JoinVertical(lipgloss.Left, header, body, help)
	if m.showHelp {
		helpContent := renderHelpOverlay(m.theme, "Progress", progressHelpCategories, int(float64(m.width)*0.75), m.height-4)
		return renderModalOverlay(m.theme, full, helpContent, m.width, m.height)
	}
	return full
}

func (m ProgressModel) renderHeader() string {
	style := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.theme.Text).
		Background(m.theme.Surface).
		Width(m.width)
	style = theme.PadHorizontal(style)

	title := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Peach).Background(m.theme.Surface).Render(m.theme.Icons.Progress+"  ") +
		lipgloss.NewStyle().Bold(true).Background(m.theme.Surface).Render(theme.RenderColorGradient("✦ SEARCH PROGRESS ✧", m.theme.Peach, m.theme.Pink))

	right := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)
	total := len(m.metrics.FunnelStages)
	totalCount := 0
	if total > 0 {
		totalCount = m.metrics.FunnelStages[0].Count
	}
	info := right.Render(fmt.Sprintf("%d evaluated | %.1f avg score", totalCount, m.metrics.AvgScore))

	title, info, gap := fitBar(title, info, m.width, 4, m.theme.Surface)

	return style.Render(title + gap + info)
}

// truncateRow bounds a rendered label+bar+count row to the width actually
// available inside PadHorizontal's 2+2 padding. renderFunnel/
// renderScoreDistribution/renderWeeklyActivity each floor their bar width
// at a minimum of 10 columns so a bar is never invisible, but that floor
// can still push label+bar+count past m.width on a narrow terminal --
// unlike bars.go's fitBar (used by the header/help bars), these rows had
// no truncation fallback, so an over-width row wrapped onto a second
// terminal line instead of degrading. That silently breaks the scroll
// math in View(), which assumes each row is exactly one line. ansi.Truncate
// mirrors renderTabs's own guard in pipeline.go for the identical problem
// -- ANSI-escape-aware, so it can safely shorten an already-styled row.
func (m ProgressModel) truncateRow(row string) string {
	avail := m.width - 4 // PadHorizontal's own 2+2 columns
	if avail < 0 {
		avail = 0
	}
	if lipgloss.Width(row) > avail {
		row = ansi.Truncate(row, avail, "…")
	}
	return row
}

func (m ProgressModel) renderFunnel() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Pipeline Funnel")))

	if len(m.metrics.FunnelStages) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No data")))
		return strings.Join(lines, "\n")
	}

	// Find max count for bar scaling
	maxCount := 0
	for _, s := range m.metrics.FunnelStages {
		if s.Count > maxCount {
			maxCount = s.Count
		}
	}

	labelW := 10
	barMaxW := m.width - labelW - 20 // room for label, count, pct
	if barMaxW < 10 {
		barMaxW = 10
	}

	// Colors for funnel stages (gradient from cool to warm)
	stageColors := []color.Color{
		m.theme.Blue,
		m.theme.Sky,
		m.theme.Green,
		m.theme.Yellow,
		m.theme.Peach,
	}

	for i, stage := range m.metrics.FunnelStages {
		barW := 0
		if maxCount > 0 {
			barW = stage.Count * barMaxW / maxCount
		}
		if barW < 1 && stage.Count > 0 {
			barW = 1
		}

		color := m.theme.Text
		if i < len(stageColors) {
			color = stageColors[i]
		}

		barStyle := lipgloss.NewStyle().Foreground(color) // no padding needed
		labelStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(labelW)
		countStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

		bar := barStyle.Render(strings.Repeat("\u2588", barW))
		label := labelStyle.Render(stage.Label)

		pctStr := ""
		if i > 0 {
			pctStr = fmt.Sprintf(" (%.0f%%)", stage.Pct)
		}
		count := countStyle.Render(fmt.Sprintf("  %d%s", stage.Count, pctStr))

		lines = append(lines, padStyle.Render(m.truncateRow(label+bar+count)))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderScoreDistribution() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Score Distribution")))

	if len(m.metrics.ScoreBuckets) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No data")))
		return strings.Join(lines, "\n")
	}

	// Find max count for bar scaling
	maxCount := 0
	for _, b := range m.metrics.ScoreBuckets {
		if b.Count > maxCount {
			maxCount = b.Count
		}
	}

	labelW := 8
	barMaxW := m.width - labelW - 14
	if barMaxW < 10 {
		barMaxW = 10
	}

	// Colors for score ranges (green to red)
	bucketColors := []color.Color{
		m.theme.Green,
		m.theme.Green,
		m.theme.Yellow,
		m.theme.Peach,
		m.theme.Red,
	}

	for i, bucket := range m.metrics.ScoreBuckets {
		barW := 0
		if maxCount > 0 {
			barW = bucket.Count * barMaxW / maxCount
		}
		if barW < 1 && bucket.Count > 0 {
			barW = 1
		}

		color := m.theme.Text
		if i < len(bucketColors) {
			color = bucketColors[i]
		}

		barStyle := lipgloss.NewStyle().Foreground(color)
		labelStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(labelW)
		countStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

		bar := barStyle.Render(strings.Repeat("\u2588", barW))
		label := labelStyle.Render(bucket.Label)
		count := countStyle.Render(fmt.Sprintf("  %d", bucket.Count))

		lines = append(lines, padStyle.Render(m.truncateRow(label+bar+count)))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderRates() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Conversion Rates")))

	labelStyle := lipgloss.NewStyle().Foreground(m.theme.Text)
	valueStyle := lipgloss.NewStyle().Bold(true)
	// Subtext, not Overlay -- see renderHelp's brand comment: Overlay is the
	// border/divider token and fails text contrast (1.4-2.3:1) here.
	sepStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

	responseColor := m.rateColor(m.metrics.ResponseRate)
	interviewColor := m.rateColor(m.metrics.InterviewRate)
	offerColor := m.rateColor(m.metrics.OfferRate)

	sep := sepStyle.Render("  |  ")

	rates := labelStyle.Render("Response Rate: ") +
		valueStyle.Foreground(responseColor).Render(fmt.Sprintf("%.1f%%", m.metrics.ResponseRate)) +
		sep +
		labelStyle.Render("Interview Rate: ") +
		valueStyle.Foreground(interviewColor).Render(fmt.Sprintf("%.1f%%", m.metrics.InterviewRate)) +
		sep +
		labelStyle.Render("Offer Rate: ") +
		valueStyle.Foreground(offerColor).Render(fmt.Sprintf("%.1f%%", m.metrics.OfferRate))

	lines = append(lines, padStyle.Render(m.truncateRow(rates)))

	// Active summary
	dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
	activeInfo := dimStyle.Render(fmt.Sprintf(
		"%d active applications | %d total offers",
		m.metrics.ActiveApps, m.metrics.TotalOffers,
	))
	lines = append(lines, padStyle.Render(m.truncateRow(activeInfo)))

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderMissionControl() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Mission Control (Heatmap & Trends)")))
	lines = append(lines, "")

	// 1. Calendar Heatmap
	lines = append(lines, m.renderHeatmap())
	lines = append(lines, "")

	// 2. Sparklines
	trendLines := m.renderSparklines()
	lines = append(lines, trendLines)

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderHeatmap() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())

	if len(m.metrics.DailyActivity) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		return padStyle.Render(dimStyle.Render("No activity data for heatmap"))
	}

	// Determine max count for color scaling
	maxCount := 0
	for _, count := range m.metrics.DailyActivity {
		if count > maxCount {
			maxCount = count
		}
	}

	// Calculate date range: show last 24 weeks (~6 months) based on width
	cols := (m.width - 15) / 2 // each column is 2 chars, 15 chars for labels/margins
	if cols > 52 {
		cols = 52
	}
	if cols < 4 {
		cols = 4
	}

	// End on the most recent Saturday or today? Let's just end on today.
	endDate := time.Now()
	// Find the Sunday of the week cols-weeks ago
	daysToSubtract := int(endDate.Weekday()) + (cols-1)*7
	startDate := endDate.AddDate(0, 0, -daysToSubtract)

	// Colors
	cEmpty := lipgloss.NewStyle().Foreground(m.theme.Surface)
	cLow := lipgloss.NewStyle().Foreground(m.theme.Subtext)
	cMed := lipgloss.NewStyle().Foreground(m.theme.Blue)
	cHigh := lipgloss.NewStyle().Foreground(m.theme.Peach)
	cMax := lipgloss.NewStyle().Foreground(m.theme.Green)

	getColor := func(count int) lipgloss.Style {
		if count == 0 {
			return cEmpty
		}
		if maxCount <= 1 {
			return cMax
		}
		pct := float64(count) / float64(maxCount)
		switch {
		case pct > 0.75:
			return cMax
		case pct > 0.50:
			return cHigh
		case pct > 0.25:
			return cMed
		default:
			return cLow
		}
	}

	block := "■ "
	var rows [7]strings.Builder

	// Day labels
	labels := []string{"Sun ", "Mon ", "Tue ", "Wed ", "Thu ", "Fri ", "Sat "}

	for i := 0; i < 7; i++ {
		rows[i].WriteString(lipgloss.NewStyle().Foreground(m.theme.Subtext).Render(labels[i]))
	}

	curr := startDate
	for {
		if curr.After(endDate) {
			break
		}

		d := curr.Format("2006-01-02")
		count := m.metrics.DailyActivity[d]

		weekday := int(curr.Weekday())
		rows[weekday].WriteString(getColor(count).Render(block))

		curr = curr.AddDate(0, 0, 1)
	}

	var lines []string
	for i := 0; i < 7; i++ {
		lines = append(lines, padStyle.Render(rows[i].String()))
	}

	return strings.Join(lines, "\n")
}

func downsampleSparkline(vals []int, maxLen int) []int {
	if maxLen <= 0 {
		return nil
	}
	if len(vals) <= maxLen {
		return vals
	}
	res := make([]int, maxLen)
	chunkSize := float64(len(vals)) / float64(maxLen)
	for i := 0; i < maxLen; i++ {
		start := int(float64(i) * chunkSize)
		end := int(float64(i+1) * chunkSize)
		if end > len(vals) {
			end = len(vals)
		}
		if start >= end {
			start = end - 1
		}
		sum := 0
		count := 0
		for j := start; j < end; j++ {
			sum += vals[j]
			count++
		}
		if count > 0 {
			res[i] = sum / count
		} else {
			res[i] = vals[start]
		}
	}
	return res
}

func (m ProgressModel) renderSparklines() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	labelStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(15)
	sparkStyle := lipgloss.NewStyle().Foreground(m.theme.Mauve)
	volStyle := lipgloss.NewStyle().Foreground(m.theme.Blue)

	maxSparkW := m.width - 25
	if maxSparkW < 10 {
		maxSparkW = 10
	}
	if maxSparkW > 60 {
		maxSparkW = 60
	}

	var lines []string

	// Score Trend
	if len(m.metrics.ScoreTrend) > 0 {
		downsampled := downsampleSparkline(m.metrics.ScoreTrend, maxSparkW)
		scoreStr := RenderSparkline(downsampled)
		lines = append(lines, padStyle.Render(labelStyle.Render("Score Trend")+sparkStyle.Render(scoreStr)))
	} else {
		lines = append(lines, padStyle.Render(labelStyle.Render("Score Trend")+lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("No data")))
	}

	// Volume Trend
	if len(m.metrics.VolumeTrend) > 0 {
		downsampled := downsampleSparkline(m.metrics.VolumeTrend, maxSparkW)
		volStr := RenderSparkline(downsampled)
		lines = append(lines, padStyle.Render(labelStyle.Render("Weekly Volume")+volStyle.Render(volStr)))
	} else {
		lines = append(lines, padStyle.Render(labelStyle.Render("Weekly Volume")+lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("No data")))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderWeeklyActivity() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Weekly Activity")))

	if len(m.metrics.WeeklyActivity) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No data")))
		return strings.Join(lines, "\n")
	}

	// Find max count for bar scaling
	maxCount := 0
	for _, w := range m.metrics.WeeklyActivity {
		if w.Count > maxCount {
			maxCount = w.Count
		}
	}

	labelW := 10
	barMaxW := m.width - labelW - 12
	if barMaxW < 10 {
		barMaxW = 10
	}

	for _, week := range m.metrics.WeeklyActivity {
		barW := 0
		if maxCount > 0 {
			barW = week.Count * barMaxW / maxCount
		}
		if barW < 1 && week.Count > 0 {
			barW = 1
		}

		barStyle := lipgloss.NewStyle().Foreground(m.theme.Blue)
		labelStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(labelW)
		countStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

		// Show short week label (e.g., "W14" from "2026-W14")
		shortWeek := week.Week
		if idx := strings.Index(shortWeek, "-"); idx >= 0 {
			shortWeek = shortWeek[idx+1:]
		}

		bar := barStyle.Render(strings.Repeat("\u2588", barW))
		label := labelStyle.Render(shortWeek)
		count := countStyle.Render(fmt.Sprintf("  %d", week.Count))

		lines = append(lines, padStyle.Render(m.truncateRow(label+bar+count)))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderHelp() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Blue).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Text).Background(m.theme.Surface)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)

	// Subtext, not Overlay -- Overlay is the border/divider token (1.4-2.3:1
	// against Surface/Base across all three themes, see statusColorMap's own
	// comment in pipeline.go for the same measurement) and was never meant
	// to carry readable text.
	brand := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface).Render("resume-builder dashboard")

	keys := keyStyle.Render("\u2191\u2193/jk") + descStyle.Render(" scroll  ") +
		keyStyle.Render("PgUp/Dn") + descStyle.Render(" page  ") +
		keyStyle.Render("?") + descStyle.Render(" help  ") +
		keyStyle.Render("Esc") + descStyle.Render(" back  ") +
		keyStyle.Render("q") + descStyle.Render(" quit")

	keys, brand, gap := fitBar(keys, brand, m.width, 2, m.theme.Surface)

	return style.Render(keys + gap + brand)
}

// rateColor returns a color based on the rate value.
func (m ProgressModel) rateColor(rate float64) color.Color {
	switch {
	case rate >= 30:
		return m.theme.Green
	case rate >= 15:
		return m.theme.Yellow
	case rate >= 5:
		return m.theme.Peach
	default:
		return m.theme.Red
	}
}

// RenderSparkline converts a slice of integers into a compact Unicode sparkline.
func RenderSparkline(values []int) string {
	if len(values) == 0 {
		return ""
	}
	if len(values) == 1 {
		return "█"
	}
	min, max := values[0], values[0]
	for _, v := range values {
		if v < min {
			min = v
		}
		if v > max {
			max = v
		}
	}
	runes := []rune{' ', '▂', '▃', '▄', '▅', '▆', '▇', '█'}
	var sb strings.Builder
	for _, v := range values {
		if max == min {
			sb.WriteRune(' ')
			continue
		}
		fraction := float64(v-min) / float64(max-min)
		idx := int(fraction * 7.0)
		if v > min && idx == 0 {
			idx = 1
		}
		if idx > 7 {
			idx = 7
		}
		if idx < 0 {
			idx = 0
		}
		sb.WriteRune(runes[idx])
	}
	return sb.String()
}

// RenderBlockBar renders an eighth-step block progress bar of the given total character width.
func RenderBlockBar(width int, fraction float64) string {
	if width <= 0 {
		return ""
	}
	if fraction <= 0.0 {
		return strings.Repeat(" ", width)
	}
	if fraction >= 1.0 {
		return strings.Repeat("█", width)
	}
	eighthRunes := []rune{' ', '▏', '▎', '▍', '▌', '▋', '▊', '▉'}
	totalEighths := int(math.Round(fraction * float64(width) * 8.0))
	fullBlocks := totalEighths / 8
	rem := totalEighths % 8

	if fullBlocks > width {
		fullBlocks = width
		rem = 0
	}

	var sb strings.Builder
	for i := 0; i < fullBlocks; i++ {
		sb.WriteRune('█')
	}
	used := fullBlocks
	if rem > 0 && used < width {
		sb.WriteRune(eighthRunes[rem])
		used++
	}
	for used < width {
		sb.WriteRune(' ')
		used++
	}
	return sb.String()
}

func (m ProgressModel) renderPlatformYield() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Source-Platform Yield & Quality")))

	if len(m.metrics.PlatformStats) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No platform data")))
		return strings.Join(lines, "\n")
	}

	maxRoles := 0
	for _, p := range m.metrics.PlatformStats {
		if p.TotalRoles > maxRoles {
			maxRoles = p.TotalRoles
		}
	}

	labelW := 15
	barMaxW := m.width - labelW - 35
	if barMaxW < 10 {
		barMaxW = 10
	}
	if barMaxW > 30 {
		barMaxW = 30
	}

	labelStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(labelW)
	countStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Width(8).Align(lipgloss.Right)
	scoreStyle := lipgloss.NewStyle().Bold(true)

	for _, p := range m.metrics.PlatformStats {
		barW := 0
		if maxRoles > 0 {
			barW = p.TotalRoles * barMaxW / maxRoles
		}
		if barW < 1 && p.TotalRoles > 0 {
			barW = 1
		}

		scoreColor := m.theme.Subtext
		if p.AvgScore >= 4.0 {
			scoreColor = m.theme.Green
		} else if p.AvgScore >= 3.5 {
			scoreColor = m.theme.Yellow
		}

		bar := lipgloss.NewStyle().Foreground(m.theme.Mauve).Render(strings.Repeat("■", barW))
		cnt := fmt.Sprintf("%d jobs", p.TotalRoles)
		sc := "-"
		if p.AvgScore > 0 {
			sc = fmt.Sprintf("%.2f avg", p.AvgScore)
		}

		row := labelStyle.Render(p.Platform) + " " + bar + " " + countStyle.Render(cnt) + "  " + scoreStyle.Foreground(scoreColor).Render(sc)
		lines = append(lines, padStyle.Render(m.truncateRow(row)))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderCompanyConcentration() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Top Employers & Staffing Detection")))

	if len(m.metrics.CompanyStats) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No company data")))
		return strings.Join(lines, "\n")
	}

	nameStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(24)
	countStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Width(8).Align(lipgloss.Right)
	scoreStyle := lipgloss.NewStyle().Bold(true)
	agencyBadge := lipgloss.NewStyle().Foreground(m.theme.Yellow).Render("[AGENCY]")
	directBadge := lipgloss.NewStyle().Foreground(m.theme.Blue).Render("[DIRECT]")

	for _, c := range m.metrics.CompanyStats {
		badge := directBadge
		if c.IsAgency {
			badge = agencyBadge
		}

		scoreColor := m.theme.Subtext
		if c.AvgScore >= 4.0 {
			scoreColor = m.theme.Green
		} else if c.AvgScore >= 3.5 {
			scoreColor = m.theme.Yellow
		}

		cnt := fmt.Sprintf("%d roles", c.TotalRoles)
		sc := "-"
		if c.AvgScore > 0 {
			sc = fmt.Sprintf("%.2f avg", c.AvgScore)
		}

		compName := c.Company
		if len(compName) > 22 {
			compName = compName[:21] + "…"
		}

		row := badge + " " + nameStyle.Render(compName) + " " + countStyle.Render(cnt) + "  " + scoreStyle.Foreground(scoreColor).Render(sc)
		lines = append(lines, padStyle.Render(m.truncateRow(row)))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderScoreVsCoverage() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Score vs. Bullet Coverage (High-ROI Gap Radar)")))

	q := m.metrics.Quadrants
	total := q.ReadyToApply + q.HighFitLowCoverage + q.OverCoveredLowerFit + q.Deprioritized
	if total == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No scored & covered roles yet")))
		return strings.Join(lines, "\n")
	}

	readyStyle := lipgloss.NewStyle().Foreground(m.theme.Green).Bold(true)
	gapStyle := lipgloss.NewStyle().Foreground(m.theme.Yellow).Bold(true)
	dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

	row1 := fmt.Sprintf("• Ready to Apply (Score ≥ 4.0, Cov ≥ 70%%): %s", readyStyle.Render(fmt.Sprintf("%d roles", q.ReadyToApply)))
	row2 := fmt.Sprintf("• High-ROI Bullet Gaps (Score ≥ 4.0, Cov < 70%%): %s", gapStyle.Render(fmt.Sprintf("%d roles (Write bullets next!)", q.HighFitLowCoverage)))
	row3 := fmt.Sprintf("• Over-Covered / Lower Fit (Score < 4.0, Cov ≥ 70%%): %s", dimStyle.Render(fmt.Sprintf("%d roles", q.OverCoveredLowerFit)))
	row4 := fmt.Sprintf("• Deprioritized (Score < 4.0, Cov < 70%%): %s", dimStyle.Render(fmt.Sprintf("%d roles", q.Deprioritized)))

	lines = append(lines, padStyle.Render(m.truncateRow(row1)))
	lines = append(lines, padStyle.Render(m.truncateRow(row2)))
	lines = append(lines, padStyle.Render(m.truncateRow(row3)))
	lines = append(lines, padStyle.Render(m.truncateRow(row4)))

	if len(m.metrics.HighFitLowCoverageRoles) > 0 {
		lines = append(lines, "")
		subtitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Peach).Render("  Write Bullets For (High Fit, Low Coverage):")
		lines = append(lines, padStyle.Render(m.truncateRow(subtitle)))

		for i, r := range m.metrics.HighFitLowCoverageRoles {
			if i >= 4 {
				break
			}
			item := fmt.Sprintf("  ↳ %s @ %s (Score: %.1f, Cov: %.0f%%)", r.Title, r.Company, r.Score, r.Coverage)
			lines = append(lines, padStyle.Render(m.truncateRow(item)))
		}
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderFunnelDrilldown() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Mauve)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render("Funnel Drill-Down & Drop-Off Diagnostics")))

	if len(m.metrics.FunnelDrilldown) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No funnel data available")))
		return strings.Join(lines, "\n")
	}

	stageStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(20)
	volStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Width(8).Align(lipgloss.Right)
	convStyle := lipgloss.NewStyle().Bold(true).Width(10).Align(lipgloss.Right)
	frictStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

	for _, s := range m.metrics.FunnelDrilldown {
		cColor := m.theme.Green
		if s.Conversion < 30.0 {
			cColor = m.theme.Yellow
		}
		if s.Conversion < 10.0 {
			cColor = m.theme.Subtext
		}

		convStr := fmt.Sprintf("%.1f%%", s.Conversion)
		volStr := fmt.Sprintf("%d", s.Volume)
		row := stageStyle.Render(s.Stage) + " " + volStyle.Render(volStr) + " " + convStyle.Foreground(cColor).Render(convStr) + "  " + frictStyle.Render("• "+s.Friction)
		lines = append(lines, padStyle.Render(m.truncateRow(row)))
	}

	return strings.Join(lines, "\n")
}

func (m ProgressModel) renderStrategyRadar() string {
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	sectionTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue)

	var lines []string
	lines = append(lines, padStyle.Render(sectionTitle.Render(fmt.Sprintf("Application Strategy Radar & Situation Room (Score: %d/100)", m.metrics.StrategyRadar.Overall))))

	radar := m.metrics.StrategyRadar
	if len(radar.Axes) == 0 {
		dimStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
		lines = append(lines, padStyle.Render(dimStyle.Render("No strategy radar data available")))
		return strings.Join(lines, "\n")
	}

	nameStyle := lipgloss.NewStyle().Foreground(m.theme.Text).Width(22)
	scoreStyle := lipgloss.NewStyle().Bold(true).Width(10)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

	for _, axis := range radar.Axes {
		// Render mini progress bar
		barWidth := 10
		filled := int(math.Round(float64(axis.Score) / 100.0 * float64(barWidth)))
		if filled > barWidth {
			filled = barWidth
		}
		bar := strings.Repeat("█", filled) + strings.Repeat("░", barWidth-filled)

		bColor := m.theme.Green
		if axis.Score < 75 {
			bColor = m.theme.Yellow
		}
		if axis.Score < 60 {
			bColor = m.theme.Peach
		}

		barStr := lipgloss.NewStyle().Foreground(bColor).Render("[" + bar + "]")
		scStr := fmt.Sprintf("%d%% (%s)", axis.Score, axis.Grade)

		row := nameStyle.Render(axis.Name) + " " + barStr + " " + scoreStyle.Foreground(bColor).Render(scStr) + " " + descStyle.Render(axis.Description)
		lines = append(lines, padStyle.Render(m.truncateRow(row)))
	}

	if len(radar.Playbooks) > 0 {
		lines = append(lines, "")
		pbTitle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Sky).Render("  Tactical Playbooks & Action Levers:")
		lines = append(lines, padStyle.Render(m.truncateRow(pbTitle)))
		for _, pb := range radar.Playbooks {
			pbRowClean := fmt.Sprintf("  • %s (%s): %s", pb.Name, pb.Focus, pb.Action)
			lines = append(lines, padStyle.Render(m.truncateRow(pbRowClean)))
		}
	}

	return strings.Join(lines, "\n")
}
