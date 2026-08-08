package screens

import (
	"strings"

	tea "github.com/charmbracelet/bubbletea"

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
}

// NewJobsModel creates a new jobs screen from the rows loaded via
// data.LoadJobs. rows should already be sorted best-first (as
// picker.list_all_evaluated_jds() on the Python side does).
func NewJobsModel(t theme.Theme, rows []model.JobRow, width, height int) JobsModel {
	m := JobsModel{
		rows:   rows,
		filter: "all",
		width:  width,
		height: height,
		theme:  t,
	}
	m.applyFilter()
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

// Update handles input for the jobs screen.
func (m JobsModel) Update(msg tea.Msg) (JobsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
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
		case "q", "esc":
			return m, func() tea.Msg { return JobsClosedMsg{} }
		}
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	}
	return m, nil
}
