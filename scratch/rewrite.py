import os
import re

file_path = "/Users/morganescott/resume-builder/dashboard/internal/ui/screens/pipeline.go"

with open(file_path, "r") as f:
    content = f.read()

# Replace chromeRowsFixed
chrome_old = """func (m PipelineModel) chromeRowsFixed() int {
	rows := 8 // header + tabs(2) + metrics + sortbar + column header + help + preview baseline
	if m.searchInput || m.searchQuery != "" {
		rows++
	}
	return rows
}"""
chrome_new = """func (m PipelineModel) chromeRowsFixed() int {
	rows := 5 // header + tabs(2) + metrics + sortbar + help
	if m.searchInput || m.searchQuery != "" {
		rows++
	}
	return rows
}"""
content = content.replace(chrome_old, chrome_new)


# Replace View
view_old = """// View renders the pipeline screen.
func (m PipelineModel) View() string {
	header := m.renderHeader()
	tabs := m.renderTabs()
	metricsBar := m.renderMetrics()
	sortBar := m.renderSortBar()
	searchBar := m.renderSearchBar()
	body := m.renderBody()
	preview := m.renderPreview()
	help := m.renderHelp()

	// Apply scroll to body
	bodyLines := strings.Split(body, "\\n")
	if m.scrollOffset > 0 && m.scrollOffset < len(bodyLines) {
		bodyLines = bodyLines[m.scrollOffset:]
	}

	// Calculate available height for body
	previewLines := strings.Count(preview, "\\n") + 1
	availHeight := m.height - m.chromeRowsFixed() - previewLines
	if availHeight < 3 {
		availHeight = 3
	}
	if len(bodyLines) > availHeight {
		bodyLines = bodyLines[:availHeight]
	}
	body = strings.Join(bodyLines, "\\n")

	// Status picker overlay
	if m.statusPicker {
		body = m.overlayStatusPicker(body)
	}

	sections := []string{header, tabs, metricsBar, sortBar}
	if searchBar != "" {
		sections = append(sections, searchBar)
	}
	sections = append(sections, m.renderColumnHeader(), body, preview, help)
	return lipgloss.JoinVertical(lipgloss.Left, sections...)
}"""

view_new = """// View renders the pipeline screen.
func (m PipelineModel) View() string {
	header := m.renderHeader()
	tabs := m.renderTabs()
	metricsBar := m.renderMetrics()
	sortBar := m.renderSortBar()
	searchBar := m.renderSearchBar()
	help := m.renderHelp()

	leftWidth := int(float64(m.width) * 0.35)
	rightWidth := m.width - leftWidth

	availHeight := m.height - m.chromeRowsFixed()
	if availHeight < 5 {
		availHeight = 5
	}

	leftPane := m.renderSidebarList(leftWidth, availHeight)
	
	var rightPane string
	if app, ok := m.CurrentApp(); ok {
		rightPane = m.renderJobDetailPane(app, rightWidth, availHeight)
	} else {
		rightPane = m.renderEmptyDetailPane(rightWidth, availHeight)
	}

	splitView := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)

	sections := []string{header, tabs, metricsBar, sortBar}
	if searchBar != "" {
		sections = append(sections, searchBar)
	}
	sections = append(sections, splitView, help)
	return lipgloss.JoinVertical(lipgloss.Left, sections...)
}

func (m PipelineModel) renderSidebarList(width, height int) string {
	if len(m.filtered) == 0 {
		emptyStyle := lipgloss.NewStyle().
			Foreground(m.theme.Subtext).
			Width(width - 2).
			Height(height - 2).
			Padding(1, 1).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(m.theme.Overlay)
		return emptyStyle.Render("No offers match this filter")
	}

	var lines []string
	prevStatus := ""
	
	for i, app := range m.filtered {
		norm := data.NormalizeStatus(app.Status)

		if m.viewMode == "grouped" && norm != prevStatus {
			count := m.countByNormStatus(norm)
			headerStyle := lipgloss.NewStyle().
				Bold(true).
				Foreground(m.theme.Blue).
				PaddingTop(1)
			lines = append(lines, headerStyle.Render(fmt.Sprintf("%s (%d)", strings.ToUpper(statusLabel(norm)), count)))
			prevStatus = norm
		}

		selected := i == m.cursor
		line := m.renderSidebarAppLine(app, width-4, selected) // -4 for padding/border
		lines = append(lines, line)
	}

	body := strings.Join(lines, "\\n")
	bodyLines := strings.Split(body, "\\n")

	if m.scrollOffset > 0 && m.scrollOffset < len(bodyLines) {
		bodyLines = bodyLines[m.scrollOffset:]
	}
	
	// Subtract 2 from height for the border
	if len(bodyLines) > height-2 {
		bodyLines = bodyLines[:height-2]
	}

	content := strings.Join(bodyLines, "\\n")

	// Status picker overlay on the left pane
	if m.statusPicker {
		content = m.overlayStatusPicker(content)
	}

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Overlay).
		Width(width - 2).
		Height(height - 2).
		Padding(0, 1)

	// If the left pane is focused (which it always is unless we build a pane switcher), glow blue
	borderStyle = borderStyle.BorderForeground(m.theme.Blue)

	return borderStyle.Render(content)
}

func (m PipelineModel) renderSidebarAppLine(app model.CareerApplication, width int, selected bool) string {
	scoreStyle := m.scoreStyle(app.Score)
	score := scoreStyle.Render(fmt.Sprintf("%.1f", app.Score))
	
	compWidth := width - 6 // space for score and padding
	company := truncateRunes(app.Company, compWidth)
	companyStyle := lipgloss.NewStyle().Foreground(m.theme.Text)
	if selected {
		companyStyle = companyStyle.Bold(true)
	}

	line1 := fmt.Sprintf("%s %s", score, companyStyle.Render(company))
	
	roleWidth := width - 2
	role := truncateRunes(app.Role, roleWidth)
	roleStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
	line2 := roleStyle.Render(role)
	
	block := line1 + "\\n" + line2

	if selected {
		return lipgloss.NewStyle().
			Background(m.theme.Surface).
			Width(width).
			Padding(0, 1).
			Render(block)
	}
	return lipgloss.NewStyle().Padding(0, 1).Render(block)
}

func (m PipelineModel) renderJobDetailPane(app model.CareerApplication, width, height int) string {
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Overlay).
		Width(width - 2).
		Height(height - 2).
		Padding(1, 2)
	
	titleStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue)
	subtextStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)
	valueStyle := lipgloss.NewStyle().Foreground(m.theme.Text)
	
	var content []string
	
	// HEADER: Company & Role
	content = append(content, titleStyle.Render(app.Company))
	content = append(content, valueStyle.Render(app.Role))
	content = append(content, "")
	
	// PROOF: Score, Status, Date
	scoreStyle := m.scoreStyle(app.Score)
	norm := data.NormalizeStatus(app.Status)
	statusColor := m.statusColorMap()[norm]
	
	content = append(content, subtextStyle.Render("Interview Probability: ") + scoreStyle.Render(fmt.Sprintf("%.1f", app.Score)))
	content = append(content, subtextStyle.Render("Status: ") + lipgloss.NewStyle().Foreground(statusColor).Render(statusLabel(norm)))
	
	dateStr := app.Date
	if dateStr == "" {
		dateStr = "Unknown"
	}
	content = append(content, subtextStyle.Render("Date Scanned/Posted: ") + valueStyle.Render(dateStr))
	content = append(content, "")
	
	// QUICK FACTS
	if app.WorkMode != "" || app.Location != "" || app.PayRange != "" {
		facts := ""
		if app.WorkMode != "" {
			facts += app.WorkMode + " "
		}
		if app.Location != "" {
			facts += app.Location + " "
		}
		if app.PayRange != "" {
			facts += "| " + app.PayRange
		}
		content = append(content, subtextStyle.Render("Details: ") + valueStyle.Render(facts))
		content = append(content, "")
	}

	// MATCHED / MISSING SKILLS & REASONING (from Report Summary if available)
	if summary, ok := m.reportCache[app.ReportPath]; ok {
		if summary.tldr != "" {
			content = append(content, titleStyle.Render("Analysis"))
			content = append(content, valueStyle.Render(truncateRunes(summary.tldr, width-6)))
			content = append(content, "")
		}
		if summary.archetype != "" {
			content = append(content, subtextStyle.Render("Archetype: ") + valueStyle.Render(summary.archetype))
		}
	} else if app.Notes != "" {
		content = append(content, titleStyle.Render("Notes"))
		content = append(content, subtextStyle.Render(truncateRunes(app.Notes, width-6)))
	}

	// Make sure we fill out the string
	joined := strings.Join(content, "\\n")
	return borderStyle.Render(joined)
}

func (m PipelineModel) renderEmptyDetailPane(width, height int) string {
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Overlay).
		Width(width - 2).
		Height(height - 2).
		Padding(1, 2)
	
	return borderStyle.Render(lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("Select a job to view details"))
}"""
content = content.replace(view_old, view_new)

# We need to remove renderBody, renderColumnHeader, renderAppLine, renderPreview.
# It's easier to just leave them as dead code for now, or we can regex remove them.
# I'll leave them in to ensure I don't break the build by stripping too much. We can clean them up after testing.

with open(file_path, "w") as f:
    f.write(content)
print("Updated pipeline.go")
