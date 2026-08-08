package screens

import (
	"fmt"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// JobsClosedMsg is emitted when the jobs screen is dismissed.
type JobsClosedMsg struct{}

// JobsModel implements the split-pane JD evaluation list+detail screen.
// Structurally mirrors PipelineModel (see pipeline.go) but scoped to a
// single-key filter cycle instead of a full tab bar/sort cycle/search.
type JobsModel struct {
	rows          []model.JobRow
	filtered      []model.JobRow
	cursor        int
	filter        string // "all", "pending", "completed"
	width, height int
	theme         theme.Theme

	jobsPath         string
	pythonPath       string
	projectRoot      string
	actionInProgress string // "", "liveness", "tailor", "status"
	actionError      string
	statusPicker     bool
	statusCursor     int
	spinner          spinner.Model
}

// jobsApplicationStatuses must match jd_manager.APPLICATION_STATUSES
// exactly (scripts/jd_manager.py) -- Python is the real validator
// (dashboard_actions.py's status subcommand rejects anything else), this
// is just what the picker offers.
var jobsApplicationStatuses = []string{"Applied", "Responded", "Interview", "Offer", "Rejected", "Withdrawn"}

// jobsActionCompleteMsg is emitted when a dashboard_actions.py subprocess
// finishes. output is stdout+stderr combined, used as the error message
// on failure (matches what a human running the command directly sees).
type jobsActionCompleteMsg struct {
	action string
	err    error
	output string
}

// NewJobsModel creates a new jobs screen from the rows loaded via
// data.LoadJobs. rows should already be sorted best-first (as
// picker.list_all_evaluated_jds() on the Python side does).
func NewJobsModel(t theme.Theme, rows []model.JobRow, width, height int) JobsModel {
	m := JobsModel{
		rows:    rows,
		filter:  "all",
		width:   width,
		height:  height,
		theme:   t,
		spinner: spinner.New(spinner.WithSpinner(spinner.Dot)),
	}
	m.applyFilter()
	return m
}

// WithActionConfig sets the fields needed to dispatch actions
// (liveness/tailor/status via dashboard_actions.py). Separate from
// NewJobsModel so existing callers/tests that don't exercise actions
// don't need updating.
func (m JobsModel) WithActionConfig(jobsPath, pythonPath, projectRoot string) JobsModel {
	m.jobsPath = jobsPath
	m.pythonPath = pythonPath
	m.projectRoot = projectRoot
	return m
}

func (m *JobsModel) applyFilter() {
	if m.filter == "all" {
		m.filtered = m.rows
	} else {
		var out []model.JobRow
		for _, r := range m.rows {
			if strings.EqualFold(r.Status, m.filter) {
				out = append(out, r)
			}
		}
		m.filtered = out
	}
	if m.cursor >= len(m.filtered) {
		m.cursor = len(m.filtered) - 1
	}
	if m.cursor < 0 {
		m.cursor = 0
	}
}

func nextJobsFilter(current string) string {
	switch current {
	case "all":
		return "pending"
	case "pending":
		return "completed"
	default:
		return "all"
	}
}

// CurrentJob returns the currently selected job, if any.
func (m JobsModel) CurrentJob() (model.JobRow, bool) {
	if m.cursor < 0 || m.cursor >= len(m.filtered) {
		return model.JobRow{}, false
	}
	return m.filtered[m.cursor], true
}

// Resize updates dimensions.
func (m *JobsModel) Resize(width, height int) {
	m.width = width
	m.height = height
}

// runAction builds and runs a dashboard_actions.py subprocess. Bubbletea
// runs the returned Cmd off the UI thread, so this blocking call doesn't
// freeze rendering.
func (m JobsModel) runAction(action, jdPath string, extraArgs ...string) tea.Cmd {
	return func() tea.Msg {
		args := append([]string{
			filepath.Join(m.projectRoot, "scripts", "dashboard_actions.py"),
			action, jdPath, "--jobs-path", m.jobsPath,
		}, extraArgs...)
		cmd := exec.Command(m.pythonPath, args...)
		cmd.Dir = m.projectRoot
		out, err := cmd.CombinedOutput()
		return jobsActionCompleteMsg{action: action, err: err, output: string(out)}
	}
}

// reloadAfterAction re-reads m.jobsPath (freshly written by a successful
// dashboard_actions.py run) and re-selects the previously-current job by
// Path, mirroring PipelineModel.WithReloadedData's selection-preserving
// reload.
func (m JobsModel) reloadAfterAction() JobsModel {
	rows, err := data.LoadJobs(m.jobsPath)
	if err != nil {
		m.actionError = err.Error()
		return m
	}
	var currentPath string
	if job, ok := m.CurrentJob(); ok {
		currentPath = job.Path
	}
	m.rows = rows
	m.applyFilter()
	if currentPath != "" {
		for i, r := range m.filtered {
			if r.Path == currentPath {
				m.cursor = i
				break
			}
		}
	}
	return m
}

func (m JobsModel) handleStatusPickerKey(msg tea.KeyMsg) (JobsModel, tea.Cmd) {
	switch msg.String() {
	case "esc":
		m.statusPicker = false
		return m, nil
	case "up", "k":
		if m.statusCursor > 0 {
			m.statusCursor--
		}
	case "down", "j":
		if m.statusCursor < len(jobsApplicationStatuses)-1 {
			m.statusCursor++
		}
	case "enter":
		m.statusPicker = false
		if job, ok := m.CurrentJob(); ok {
			chosen := jobsApplicationStatuses[m.statusCursor]
			m.actionInProgress = "status"
			return m, tea.Batch(m.runAction("status", job.Path, chosen), m.spinner.Tick)
		}
	}
	return m, nil
}

// Update handles input for the jobs screen.
func (m JobsModel) Update(msg tea.Msg) (JobsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case jobsActionCompleteMsg:
		m.actionInProgress = ""
		if msg.err != nil {
			m.actionError = strings.TrimSpace(msg.output)
			if m.actionError == "" {
				m.actionError = msg.err.Error()
			}
			return m, nil
		}
		return m.reloadAfterAction(), nil

	case tea.KeyMsg:
		if m.actionInProgress != "" {
			return m, nil
		}
		if m.actionError != "" {
			m.actionError = ""
			return m, nil
		}
		if m.statusPicker {
			return m.handleStatusPickerKey(msg)
		}
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
			}
		case "f":
			m.filter = nextJobsFilter(m.filter)
			m.applyFilter()
		case "l":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "liveness"
				return m, tea.Batch(m.runAction("liveness", job.Path), m.spinner.Tick)
			}
		case "t":
			if job, ok := m.CurrentJob(); ok && job.Status == "Pending" {
				m.actionInProgress = "tailor"
				return m, tea.Batch(m.runAction("tailor", job.Path), m.spinner.Tick)
			}
		case "u":
			if _, ok := m.CurrentJob(); ok {
				m.statusPicker = true
				m.statusCursor = 0
			}
		case "q", "esc":
			return m, func() tea.Msg { return JobsClosedMsg{} }
		}
	case spinner.TickMsg:
		if m.actionInProgress == "" {
			return m, nil
		}
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	}
	return m, nil
}

var jobsFitGroups = []struct {
	label string
	get   func(model.Evaluation) map[string]int
}{
	{"Fit", func(e model.Evaluation) map[string]int { return e.FitSubscores }},
	{"Interview odds", func(e model.Evaluation) map[string]int { return e.InterviewOddsSubscores }},
	{"Practical pursue", func(e model.Evaluation) map[string]int { return e.PracticalPursueSubscores }},
}

func formatSubscores(scores map[string]int) string {
	if len(scores) == 0 {
		return "-"
	}
	keys := make([]string, 0, len(scores))
	for k := range scores {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := make([]string, len(keys))
	for i, k := range keys {
		parts[i] = fmt.Sprintf("%s: %d", k, scores[k])
	}
	return strings.Join(parts, ", ")
}

func (m JobsModel) chromeAvailHeight() int {
	h := m.height - 2 // header + help
	if h < 5 {
		h = 5
	}
	return h
}

// View renders the jobs screen.
func (m JobsModel) View() string {
	header := m.renderHeader()
	var extra string
	if m.actionInProgress != "" {
		extra = m.renderActionStatus()
	} else if m.actionError != "" {
		extra = m.renderActionError()
	}
	help := m.renderHelp()

	leftWidth := int(float64(m.width) * 0.35)
	rightWidth := m.width - leftWidth
	availHeight := m.chromeAvailHeight()

	leftPane := m.renderSidebarList(leftWidth, availHeight)
	var rightPane string
	if job, ok := m.CurrentJob(); ok {
		rightPane = m.renderJobDetailPane(job, rightWidth, availHeight)
	} else {
		rightPane = m.renderEmptyDetailPane(rightWidth, availHeight)
	}

	splitView := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)
	if extra != "" {
		return lipgloss.JoinVertical(lipgloss.Left, header, extra, splitView, help)
	}
	return lipgloss.JoinVertical(lipgloss.Left, header, splitView, help)
}

func actionLabel(action string) string {
	switch action {
	case "liveness":
		return "Checking liveness"
	case "tailor":
		return "Tailoring resume"
	case "status":
		return "Updating status"
	default:
		return "Working"
	}
}

func (m JobsModel) renderActionStatus() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Yellow).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)
	return style.Render(m.spinner.View() + " " + actionLabel(m.actionInProgress) + "...")
}

func (m JobsModel) renderActionError() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Red).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)
	return style.Render("Error: " + truncateRunes(m.actionError, m.width-12) + " (press any key to dismiss)")
}

func (m JobsModel) renderHeader() string {
	style := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.theme.Text).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)

	right := lipgloss.NewStyle().Foreground(m.theme.Blue)
	info := right.Render(fmt.Sprintf("%d job(s) | filter: %s", len(m.filtered), strings.ToUpper(m.filter)))

	title := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue).Render(m.theme.Icons.Jobs + " JOBS")
	gap := m.width - lipgloss.Width(title) - lipgloss.Width(info) - 4
	if gap < 1 {
		gap = 1
	}
	return style.Render(title + strings.Repeat(" ", gap) + info)
}

func (m JobsModel) renderSidebarList(width, height int) string {
	if len(m.filtered) == 0 {
		emptyStyle := lipgloss.NewStyle().
			Foreground(m.theme.Blue).
			Width(width - 2).
			Height(height - 2).
			Padding(1, 1).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(m.theme.Overlay)
		return emptyStyle.Render("No evaluated jobs match this filter")
	}

	var lines []string
	for i, job := range m.filtered {
		selected := i == m.cursor
		lines = append(lines, m.renderSidebarLine(job, width-4, selected))
	}

	body := strings.Join(lines, "\n")
	bodyLines := strings.Split(body, "\n")
	if len(bodyLines) > height-2 {
		bodyLines = bodyLines[:height-2]
	}
	content := strings.Join(bodyLines, "\n")

	if m.statusPicker {
		content = m.overlayStatusPicker(content)
	}

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Blue).
		Width(width - 2).
		Height(height - 2).
		Padding(0, 1)

	return borderStyle.Render(content)
}

func (m JobsModel) overlayStatusPicker(body string) string {
	bodyLines := strings.Split(body, "\n")

	pickerWidth := 30
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	borderStyle := lipgloss.NewStyle().Foreground(m.theme.Blue).Bold(true)

	var picker []string
	picker = append(picker, padStyle.Render(borderStyle.Render("Set status:")))
	for i, opt := range jobsApplicationStatuses {
		style := lipgloss.NewStyle().Foreground(m.theme.Blue).Width(pickerWidth)
		if i == m.statusCursor {
			style = style.Background(m.theme.Overlay).Bold(true)
		}
		prefix := "  "
		if i == m.statusCursor {
			prefix = "> "
		}
		picker = append(picker, padStyle.Render(style.Render(prefix+opt)))
	}

	bodyLines = append(bodyLines, picker...)
	return strings.Join(bodyLines, "\n")
}

func (m JobsModel) renderSidebarLine(job model.JobRow, width int, selected bool) string {
	scoreStyle := m.scoreStyle(job.Evaluation.CompositeScore)
	score := scoreStyle.Render(fmt.Sprintf("%.1f", job.Evaluation.CompositeScore))

	compWidth := width - 6
	company := truncateRunes(job.Company, compWidth)
	companyStyle := lipgloss.NewStyle().Foreground(m.theme.Text)
	if selected {
		companyStyle = companyStyle.Bold(true)
	}
	line1 := fmt.Sprintf("%s %s", score, companyStyle.Render(company))

	titleWidth := width - 2
	title := truncateRunes(job.Title, titleWidth)
	titleStyle := lipgloss.NewStyle().Foreground(m.theme.Blue)
	line2 := titleStyle.Render(title)

	block := line1 + "\n" + line2
	base := theme.PadHorizontal(lipgloss.NewStyle())
	if selected {
		base = theme.HoverStyle(base)
	}
	return base.Render(block)
}

func (m JobsModel) renderJobDetailPane(job model.JobRow, width, height int) string {
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Overlay).
		Width(width - 2).
		Height(height - 2).
		Padding(1, 2)

	titleStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue)
	subtextStyle := lipgloss.NewStyle().Foreground(m.theme.Blue)
	valueStyle := lipgloss.NewStyle().Foreground(m.theme.Text)

	var content []string
	content = append(content, titleStyle.Render(job.Company))
	content = append(content, valueStyle.Render(job.Title))
	content = append(content, "")

	eval := job.Evaluation
	scoreStyle := m.scoreStyle(eval.CompositeScore)
	content = append(content, subtextStyle.Render("Composite score: ")+scoreStyle.Render(fmt.Sprintf("%.1f/5", eval.CompositeScore)))
	content = append(content, subtextStyle.Render("Recommendation: ")+valueStyle.Render(eval.Recommendation))
	content = append(content, subtextStyle.Render("Status: ")+valueStyle.Render(job.Status))
	content = append(content, "")

	if eval.Why != "" {
		content = append(content, titleStyle.Render("Why"))
		content = append(content, valueStyle.Render(truncateRunes(eval.Why, width-6)))
		content = append(content, "")
	}
	if eval.RecruiterRead != "" {
		content = append(content, titleStyle.Render("Recruiter read"))
		content = append(content, valueStyle.Render(truncateRunes(eval.RecruiterRead, width-6)))
		content = append(content, "")
	}
	if len(eval.HardBlockers) > 0 {
		content = append(content, subtextStyle.Render("Hard blockers: ")+valueStyle.Render(strings.Join(eval.HardBlockers, ", ")))
		content = append(content, "")
	}

	for _, group := range jobsFitGroups {
		scores := group.get(eval)
		if len(scores) == 0 {
			continue
		}
		content = append(content, subtextStyle.Render(group.label+": ")+valueStyle.Render(formatSubscores(scores)))
	}
	content = append(content, "")

	if job.Liveness != nil {
		content = append(content, subtextStyle.Render("Liveness: ")+valueStyle.Render(job.Liveness.Result))
	}
	if job.Application != nil {
		content = append(content, subtextStyle.Render("Application: ")+valueStyle.Render(job.Application.Status))
	}

	joined := strings.Join(content, "\n")
	return borderStyle.Render(joined)
}

func (m JobsModel) renderEmptyDetailPane(width, height int) string {
	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Overlay).
		Width(width - 2).
		Height(height - 2).
		Padding(1, 2)
	return borderStyle.Render(lipgloss.NewStyle().Foreground(m.theme.Blue).Render("Select a job to view details"))
}

func (m JobsModel) renderHelp() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Blue).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Text)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Blue)

	return style.Render(
		keyStyle.Render("↑↓/jk") + descStyle.Render(" nav  ") +
			keyStyle.Render("f") + descStyle.Render(" filter  ") +
			keyStyle.Render("l") + descStyle.Render(" liveness  ") +
			keyStyle.Render("t") + descStyle.Render(" tailor  ") +
			keyStyle.Render("u") + descStyle.Render(" status  ") +
			keyStyle.Render("q") + descStyle.Render(" quit"))
}

func (m JobsModel) scoreStyle(score float64) lipgloss.Style {
	switch {
	case score >= 4.2:
		return lipgloss.NewStyle().Foreground(m.theme.Green).Bold(true)
	case score >= 3.8:
		return lipgloss.NewStyle().Foreground(m.theme.Yellow)
	case score >= 3.0:
		return lipgloss.NewStyle().Foreground(m.theme.Text)
	default:
		return lipgloss.NewStyle().Foreground(m.theme.Red)
	}
}
