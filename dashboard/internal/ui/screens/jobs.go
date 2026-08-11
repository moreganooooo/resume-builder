package screens

import (
	"bufio"
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/charmbracelet/bubbles/progress"
	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// JobsClosedMsg is emitted when the jobs screen is dismissed. Quit
// distinguishes "q" (exit the whole app) from "esc" (back to the screen
// that opened Jobs -- always the Main Menu today).
type JobsClosedMsg struct{ Quit bool }

// JobsModel implements the split-pane JD evaluation list+detail screen.
// Structurally mirrors PipelineModel (see pipeline.go) but scoped to a
// single-key filter cycle instead of a full tab bar/sort cycle/search.
type JobsModel struct {
	rows          []model.JobRow
	filtered      []model.JobRow
	cursor        int
	scrollOffset  int
	filter        string // "all", "pending", "completed"
	width, height int
	theme         theme.Theme

	jobsPath         string
	pythonPath       string
	projectRoot      string
	actionInProgress string // "", "liveness", "tailor", "status"
	// actionCancel kills the in-flight dashboard_actions.py subprocess (via
	// its exec.CommandContext) when the user presses esc mid-action, or
	// when the action completes on its own (to release the context).
	// Without this, quitting or backing out mid-action left the LLM/PDF
	// -render child process running unseen in the background.
	actionCancel context.CancelFunc
	actionError  string
	// notice explains why a keypress was a no-op (e.g. "t" on a non-Pending
	// job) instead of silently doing nothing. Dismissed on the next
	// keypress, same convention as actionError.
	notice       string
	statusPicker bool
	statusCursor int
	spinner      spinner.Model

	// actionChan carries progress/completion messages from the goroutine
	// runAction starts. Only "tailor" ever emits jobsActionProgressMsg (it's
	// the only action whose subprocess runs orchestrator.py's Step N: ...
	// pipeline) -- liveness/status stream straight to their completion
	// message and render the plain spinner instead of the progress bar.
	actionChan      chan tea.Msg
	actionStepLabel string
	progress        progress.Model
}

// jobsApplicationStatuses must match jd_manager.APPLICATION_STATUSES
// exactly (scripts/jd_manager.py) -- Python is the real validator
// (dashboard_actions.py's status subcommand rejects anything else), this
// is just what the picker offers.
var jobsApplicationStatuses = []string{"Applied", "Responded", "Interview", "Offer", "Rejected", "Withdrawn"}

// jobsActionCompleteMsg is emitted when a dashboard_actions.py subprocess
// finishes. output is stderr, used as the error message on failure
// (matches what a human running the command directly sees).
type jobsActionCompleteMsg struct {
	action string
	err    error
	output string
}

// jobsActionProgressMsg is emitted once per "Step N: <label>..." line the
// tailor subprocess prints to stdout (orchestrator.run_pipeline(), via
// cli_art.console.print() -- confirmed to flush per-line even when piped,
// not just on a real terminal). step is the parsed N (e.g. 5.5 for "Step
// 5.5"), used as step/totalPipelineSteps for the progress bar's percent.
type jobsActionProgressMsg struct {
	step  float64
	label string
}

// totalPipelineSteps mirrors orchestrator.py's highest step number
// ("Step 7: Rendering HTML and generating PDF..."). Step 5.5 is
// conditional (only fires if there are actionable recommendations), so
// this is an approximation, not an exact step count -- it still produces
// a monotonically increasing, roughly-accurate percent, which is the
// actual goal (a real signal, not a fake one -- see jobsActionCompleteMsg's
// sibling doc comment).
const totalPipelineSteps = 7.0

var stepLineRe = regexp.MustCompile(`^Step (\d+(?:\.\d+)?): (.+?)\.\.\.?$`)

// NewJobsModel creates a new jobs screen from the rows loaded via
// data.LoadJobs. rows should already be sorted best-first (as
// picker.list_all_evaluated_jds() on the Python side does).
func NewJobsModel(t theme.Theme, rows []model.JobRow, width, height int) JobsModel {
	sp := spinner.New(spinner.WithSpinner(spinner.Dot))
	// Blue (not Sky) -- Sky on Surface measures 3.64:1 under the
	// resume-builder theme, short of WCAG's 4.5:1 text minimum; Blue clears
	// 4.5:1+ on Surface across all three themes and is already the header
	// titles' own "info" accent, so it reads as the same semantic color.
	sp.Style = lipgloss.NewStyle().Foreground(t.Blue)
	m := JobsModel{
		rows:    rows,
		filter:  "all",
		width:   width,
		height:  height,
		theme:   t,
		spinner: sp,
		progress: progress.New(
			progress.WithGradient(string(t.Sky), string(t.Mauve)),
		),
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
	m.adjustScroll()
}

// hasExtraBar reports whether View() will render the action-status/error/
// notice bar above the split pane -- adjustScroll needs this to compute the
// same available height chromeAvailHeight(hasExtra) uses at render time, or
// scrolling and rendering could disagree about how many rows are visible.
func (m JobsModel) hasExtraBar() bool {
	return m.actionInProgress != "" || m.actionError != "" || m.notice != ""
}

// sidebarViewportLines returns how many body lines actually fit inside the
// bordered sidebar box for a given box height, mirroring the maxLines
// arithmetic renderSidebarList applies when truncating -- shared so
// scrolling (adjustScroll) and rendering never disagree about what's
// visible, the same class of bug chromeAvailHeight's own comment (below)
// already guards against for the extra-bar reservation.
func (m JobsModel) sidebarViewportLines(boxHeight int) int {
	maxLines := boxHeight - 2
	if m.statusPicker {
		maxLines -= len(jobsApplicationStatuses) + 1
	}
	if maxLines < 0 {
		maxLines = 0
	}
	return maxLines
}

// adjustScroll keeps the cursor's row within the sidebar's visible window,
// scrolling the list as needed. Each job renders as a fixed 2-line block
// (score+company, then title -- see renderSidebarRow in bars.go) with no separator
// line between jobs (see renderSidebarList), so a job's first line is
// always exactly 2*cursor; unlike pipeline.go's grouped view, no status-
// header lines can shift this, so no cursorLineEstimate walk is needed.
func (m *JobsModel) adjustScroll() {
	avail := m.sidebarViewportLines(m.chromeAvailHeight(m.hasExtraBar()))
	if avail < 1 {
		avail = 1
	}
	lineStart := m.cursor * 2
	lineEnd := lineStart + 1
	if lineEnd >= m.scrollOffset+avail {
		m.scrollOffset = lineEnd - avail + 1
	}
	if lineStart < m.scrollOffset {
		m.scrollOffset = lineStart
	}
	if m.scrollOffset < 0 {
		m.scrollOffset = 0
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
// waitForActionMsg blocks on the next message runAction's goroutine sends
// -- a jobsActionProgressMsg per Step N: line, then exactly one final
// jobsActionCompleteMsg. Re-issued after every progress message so the
// listen loop keeps going until completion.
func waitForActionMsg(ch chan tea.Msg) tea.Cmd {
	return func() tea.Msg {
		return <-ch
	}
}

// runAction starts action's dashboard_actions.py subprocess and streams
// its stdout line-by-line rather than buffering the whole run (the prior
// cmd.CombinedOutput() behavior) -- stdout lines matching "Step N: ..."
// (only ever emitted by "tailor", via orchestrator.py's pipeline) become
// jobsActionProgressMsg so the progress bar reflects real pipeline
// progress instead of a fake/animated percent. stderr is captured
// separately for jobsActionCompleteMsg's error-display output, matching
// the prior behavior's error text.
func (m JobsModel) runAction(ctx context.Context, ch chan tea.Msg, action, jdPath string, extraArgs ...string) tea.Cmd {
	args := append([]string{
		filepath.Join(m.projectRoot, "scripts", "dashboard_actions.py"),
		action, jdPath, "--jobs-path", m.jobsPath,
	}, extraArgs...)
	// CommandContext (not Command) so cancelling ctx -- via actionCancel,
	// wired to the esc key while an action is in progress -- kills this
	// subprocess instead of leaving it orphaned in the background.
	cmd := exec.CommandContext(ctx, m.pythonPath, args...)
	cmd.Dir = m.projectRoot

	go func() {
		var stderrBuf bytes.Buffer
		cmd.Stderr = &stderrBuf

		stdout, err := cmd.StdoutPipe()
		if err != nil {
			ch <- jobsActionCompleteMsg{action: action, err: err}
			return
		}
		if err := cmd.Start(); err != nil {
			ch <- jobsActionCompleteMsg{action: action, err: err}
			return
		}

		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if match := stepLineRe.FindStringSubmatch(line); match != nil {
				step, parseErr := strconv.ParseFloat(match[1], 64)
				if parseErr == nil {
					ch <- jobsActionProgressMsg{step: step, label: match[2]}
				}
			}
		}

		waitErr := cmd.Wait()
		ch <- jobsActionCompleteMsg{action: action, err: waitErr, output: stderrBuf.String()}
	}()

	return waitForActionMsg(ch)
}

// jobsReloadedMsg carries the result of reloadJobsCmd's off-thread reload
// back into Update().
type jobsReloadedMsg struct {
	rows []model.JobRow
	err  error
}

// reloadJobsCmd re-reads m.jobsPath (freshly written by a successful
// dashboard_actions.py run) as a tea.Cmd -- bubbletea runs it on its own
// goroutine -- instead of synchronously inside Update(), mirroring
// runAction's own async convention for subprocess work.
func reloadJobsCmd(jobsPath string) tea.Cmd {
	return func() tea.Msg {
		rows, err := data.LoadJobs(jobsPath)
		return jobsReloadedMsg{rows: rows, err: err}
	}
}

// applyReloadedRows swaps in freshly reloaded rows and re-selects the
// previously-current job by Path, mirroring PipelineModel.WithReloadedData's
// selection-preserving reload.
func (m JobsModel) applyReloadedRows(rows []model.JobRow) JobsModel {
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
	// applyFilter's own adjustScroll ran against the pre-reselection cursor
	// (0, or whatever it was clamped to) -- re-run now that m.cursor may
	// have moved to the re-selected job's new index.
	m.adjustScroll()
	return m
}

func (m JobsModel) handleStatusPickerKey(msg tea.KeyMsg) (JobsModel, tea.Cmd) {
	switch msg.String() {
	case "esc", "q":
		// pipeline.go's handleStatusPicker accepts both -- this picker only
		// accepted esc, an inconsistency between two near-identical pickers.
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
			m.actionChan = make(chan tea.Msg)
			ctx, cancel := context.WithCancel(context.Background())
			m.actionCancel = cancel
			return m, tea.Batch(m.runAction(ctx, m.actionChan, "status", job.Path, chosen), m.spinner.Tick)
		}
	}
	return m, nil
}

// Update handles input for the jobs screen. Resizing is not handled here --
// main.go's top-level WindowSizeMsg case calls Resize() directly on every
// screen before its own early-returns, so a tea.WindowSizeMsg never
// actually reaches this Update() in the real app; a case for it here was
// dead code.
func (m JobsModel) Update(msg tea.Msg) (JobsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case jobsActionCompleteMsg:
		m.actionInProgress = ""
		m.actionChan = nil
		if m.actionCancel != nil {
			m.actionCancel()
			m.actionCancel = nil
		}
		if msg.err != nil {
			m.actionError = strings.TrimSpace(msg.output)
			if m.actionError == "" {
				m.actionError = msg.err.Error()
			}
			return m, nil
		}
		return m, reloadJobsCmd(m.jobsPath)

	case jobsReloadedMsg:
		if msg.err != nil {
			m.actionError = msg.err.Error()
			return m, nil
		}
		return m.applyReloadedRows(msg.rows), nil

	case jobsActionProgressMsg:
		if m.actionInProgress == "" || m.actionChan == nil {
			return m, nil
		}
		m.actionStepLabel = msg.label
		progressCmd := m.progress.SetPercent(msg.step / totalPipelineSteps)
		return m, tea.Batch(progressCmd, waitForActionMsg(m.actionChan))

	case progress.FrameMsg:
		newModel, cmd := m.progress.Update(msg)
		if pm, ok := newModel.(progress.Model); ok {
			m.progress = pm
		}
		return m, cmd

	case tea.KeyMsg:
		if m.actionInProgress != "" {
			// esc kills the in-flight subprocess instead of leaving it
			// orphaned -- previously every key (including esc/Ctrl+C) was
			// swallowed here with no way to cancel, and quitting the app
			// left dashboard_actions.py running unseen in the background.
			if msg.String() == "esc" && m.actionCancel != nil {
				m.actionCancel()
				m.actionCancel = nil
				m.actionInProgress = ""
				m.actionChan = nil
				m.notice = "Cancelled"
			}
			return m, nil
		}
		if m.actionError != "" {
			m.actionError = ""
			return m, nil
		}
		if m.notice != "" {
			m.notice = ""
			return m, nil
		}
		if m.statusPicker {
			return m.handleStatusPickerKey(msg)
		}
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
				m.adjustScroll()
			}
		case "down", "j":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
				m.adjustScroll()
			}
		case "g":
			if len(m.filtered) > 0 {
				m.cursor = 0
				m.adjustScroll()
			}
		case "G":
			if len(m.filtered) > 0 {
				m.cursor = len(m.filtered) - 1
				m.adjustScroll()
			}
		case "pgdown", "ctrl+d":
			if len(m.filtered) > 0 {
				halfPage := m.height / 2
				if halfPage < 1 {
					halfPage = 1
				}
				m.cursor += halfPage
				if m.cursor >= len(m.filtered) {
					m.cursor = len(m.filtered) - 1
				}
				m.adjustScroll()
			}
		case "pgup", "ctrl+u":
			if len(m.filtered) > 0 {
				halfPage := m.height / 2
				if halfPage < 1 {
					halfPage = 1
				}
				m.cursor -= halfPage
				if m.cursor < 0 {
					m.cursor = 0
				}
				m.adjustScroll()
			}
		case "f":
			m.filter = nextJobsFilter(m.filter)
			m.applyFilter()
		case "l":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "liveness"
				m.actionChan = make(chan tea.Msg)
				ctx, cancel := context.WithCancel(context.Background())
				m.actionCancel = cancel
				return m, tea.Batch(m.runAction(ctx, m.actionChan, "liveness", job.Path), m.spinner.Tick)
			}
		case "t":
			if job, ok := m.CurrentJob(); ok {
				if job.Status == "Pending" {
					m.actionInProgress = "tailor"
					m.actionChan = make(chan tea.Msg)
					m.progress = progress.New(progress.WithGradient(string(m.theme.Sky), string(m.theme.Mauve)))
					m.actionStepLabel = ""
					ctx, cancel := context.WithCancel(context.Background())
					m.actionCancel = cancel
					return m, m.runAction(ctx, m.actionChan, "tailor", job.Path)
				}
				m.notice = fmt.Sprintf("Only Pending jobs can be tailored (this one is %s)", job.Status)
			}
		case "u":
			if _, ok := m.CurrentJob(); ok {
				m.statusPicker = true
				m.statusCursor = 0
			}
		case "q":
			return m, func() tea.Msg { return JobsClosedMsg{Quit: true} }
		case "esc":
			return m, func() tea.Msg { return JobsClosedMsg{Quit: false} }
		}
	case spinner.TickMsg:
		if m.actionInProgress == "" {
			return m, nil
		}
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
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

// chromeAvailHeight budgets room for the header and help bars, plus the
// action-status/error/notice bar when one is showing -- the split-pane's
// declared Height() previously stayed at height-2 regardless, so whenever
// extra rendered (any liveness/tailor/status action, or a dismissable
// notice) the total output grew to height-1 lines, one past the terminal's
// visible height. Mirrors the reservation status-picker overlays already
// make for themselves in renderSidebarList below.
func (m JobsModel) chromeAvailHeight(hasExtra bool) int {
	h := m.height - 2 // header + help
	if hasExtra {
		h--
	}
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
	} else if m.notice != "" {
		extra = m.renderNotice()
	}
	help := m.renderHelp()

	leftWidth := int(float64(m.width) * 0.35)
	rightWidth := m.width - leftWidth
	availHeight := m.chromeAvailHeight(extra != "")

	leftPane := m.renderSidebarList(leftWidth, availHeight)
	var rightPane string
	if job, ok := m.CurrentJob(); ok {
		rightPane = m.renderJobDetailPane(job, rightWidth, availHeight)
	} else {
		rightPane = renderEmptyDetailPane(m.theme, rightWidth, availHeight)
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

	// "tailor" is the only action with a real progress signal (Step N: ...
	// lines from orchestrator.py's pipeline, see jobsActionProgressMsg) --
	// liveness/status have no such signal and stay on the indeterminate
	// spinner rather than faking a percent.
	if m.actionInProgress == "tailor" {
		m.progress.Width = m.width - 6
		label := m.actionStepLabel
		if label == "" {
			label = actionLabel(m.actionInProgress)
		}
		return style.Render(label + " (esc to cancel)" + "\n" + m.progress.View())
	}

	// The spinner carries its own pre-rendered style (see NewJobsModel's
	// sp.Style), which ends in its own SGR reset -- concatenating it raw
	// into a single style.Render call (the previous form here) wipes this
	// bar's Yellow-on-Surface styling for everything rendered after it,
	// confirmed via a raw-ANSI capture: the label text after the spinner
	// glyph rendered in the terminal's bare default colors, not themed at
	// all. Every segment (left pad, spinner, label, right pad) is styled
	// and joined independently instead of nesting the spinner inside one
	// more Render call, so the Surface fill survives regardless of what
	// resets the spinner's own style emits.
	bg := lipgloss.NewStyle().Background(m.theme.Surface)
	labelStyle := lipgloss.NewStyle().Foreground(m.theme.Yellow).Background(m.theme.Surface)
	left := bg.Render("  ") + bg.Render(m.spinner.View()) +
		labelStyle.Render(" "+actionLabel(m.actionInProgress)+"... (esc to cancel)")
	if pad := m.width - lipgloss.Width(left); pad > 0 {
		left += bg.Render(strings.Repeat(" ", pad))
	}
	return left
}

func (m JobsModel) renderActionError() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Red).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)
	return style.Render("Error: " + truncateRunes(m.actionError, m.width-12) + " (press any key to dismiss)")
}

// renderNotice explains why the last keypress was a no-op (see the "t" case
// in Update), rather than leaving the user to wonder whether it registered
// at all. Yellow/no "Error:" prefix -- this isn't a failure, it's an
// unavailable action. Mirrors pipeline.go's renderNotice.
func (m JobsModel) renderNotice() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Yellow).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)
	return style.Render(truncateRunes(m.notice, m.width-12) + " (press any key to dismiss)")
}

func (m JobsModel) renderHeader() string {
	style := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.theme.Text).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)

	right := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)
	info := right.Render(fmt.Sprintf("%d job(s) | filter: %s", len(m.filtered), strings.ToUpper(m.filter)))

	title := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue).Background(m.theme.Surface).Render(m.theme.Icons.Jobs + " JOBS")
	title, info, gap := fitBar(title, info, m.width, 4, m.theme.Surface)
	return style.Render(title + gap + info)
}

func (m JobsModel) renderSidebarList(width, height int) string {
	if len(m.filtered) == 0 {
		emptyStyle := lipgloss.NewStyle().
			Foreground(m.theme.Subtext).
			Width(width-2).
			Height(height-2).
			Padding(1, 1).
			Border(lipgloss.RoundedBorder()).
			BorderForeground(m.theme.Overlay)
		return emptyStyle.Render("No evaluated jobs match this filter")
	}

	var lines []string
	for i, job := range m.filtered {
		selected := i == m.cursor
		lines = append(lines, renderSidebarRow(m.theme, job.Evaluation.CompositeScore, job.Company, job.Title, width-4, selected))
	}

	body := strings.Join(lines, "\n")
	bodyLines := strings.Split(body, "\n")

	// Scroll before truncating to the viewport -- otherwise a cursor past
	// the first screenful was simply invisible with no way to reach it (see
	// adjustScroll). Mirrors pipeline.go's renderSidebarList ordering.
	if m.scrollOffset > 0 && m.scrollOffset < len(bodyLines) {
		bodyLines = bodyLines[m.scrollOffset:]
	}

	// Reserve room for the status picker before truncating -- see the
	// matching comment in pipeline.go's renderSidebarList, which has the
	// same fixed-height overflow risk.
	maxLines := m.sidebarViewportLines(height)
	if len(bodyLines) > maxLines {
		bodyLines = bodyLines[:maxLines]
	}
	content := strings.Join(bodyLines, "\n")

	if m.statusPicker {
		content = renderStatusPickerOverlay(m.theme, content, width-4, "Set status:", jobsApplicationStatuses, m.statusCursor)
	}

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Blue).
		Width(width-2).
		Height(height-2).
		Padding(0, 1)

	return borderStyle.Render(content)
}

func (m JobsModel) renderJobDetailPane(job model.JobRow, width, height int) string {
	styles := newDetailPaneStyles(m.theme, width, height)

	var content []string
	content = append(content, styles.Title.Render(job.Company))
	content = append(content, styles.Value.Render(job.Title))
	content = append(content, "")

	eval := job.Evaluation
	score := scoreStyle(m.theme, eval.CompositeScore)
	content = append(content, styles.Subtext.Render("Composite score: ")+score.Render(fmt.Sprintf("%.1f/5", eval.CompositeScore)))
	content = append(content, styles.Subtext.Render("Recommendation: ")+styles.Value.Render(eval.Recommendation))
	content = append(content, styles.Subtext.Render("Status: ")+styles.Value.Render(job.Status))
	content = append(content, "")

	if eval.Why != "" {
		content = append(content, styles.Title.Render("Why"))
		content = append(content, styles.Value.Render(truncateRunes(eval.Why, width-6)))
		content = append(content, "")
	}
	if eval.RecruiterRead != "" {
		content = append(content, styles.Title.Render("Recruiter read"))
		content = append(content, styles.Value.Render(truncateRunes(eval.RecruiterRead, width-6)))
		content = append(content, "")
	}
	if len(eval.HardBlockers) > 0 {
		content = append(content, styles.Subtext.Render("Hard blockers: ")+styles.Value.Render(strings.Join(eval.HardBlockers, ", ")))
		content = append(content, "")
	}

	for _, group := range jobsFitGroups {
		scores := group.get(eval)
		if len(scores) == 0 {
			continue
		}
		content = append(content, styles.Subtext.Render(group.label+": ")+styles.Value.Render(formatSubscores(scores)))
	}
	content = append(content, "")

	// Only surfaced when there's an actual concern -- "High Confidence" (the
	// common case) says nothing worth a line of its own, mirroring
	// menu.py's _print_evaluation_summary()'s identical gate/ordering (right
	// before Liveness) so the CLI and TUI agree on when this is worth
	// showing. Previously decoded from the evaluation JSON but never
	// rendered anywhere in this screen -- a fake/stale-posting warning had
	// no way to reach the user here.
	if eval.PostingLegitimacy != "" && eval.PostingLegitimacy != "High Confidence" {
		color := m.theme.Yellow
		if eval.PostingLegitimacy == "Suspicious" {
			color = m.theme.Red
		}
		warningStyle := lipgloss.NewStyle().Bold(true).Foreground(color)
		line := warningStyle.Render("Posting legitimacy: " + eval.PostingLegitimacy)
		if eval.PostingLegitimacyNotes != "" {
			line += styles.Value.Render(" -- " + truncateRunes(eval.PostingLegitimacyNotes, width-6))
		}
		content = append(content, line)
		content = append(content, "")
	}

	if job.Liveness != nil {
		content = append(content, styles.Subtext.Render("Liveness: ")+styles.Value.Render(job.Liveness.Result))
	}
	if job.Application != nil {
		content = append(content, styles.Subtext.Render("Application: ")+styles.Value.Render(job.Application.Status))
	}

	joined := strings.Join(content, "\n")
	return styles.Border.Render(joined)
}

func (m JobsModel) renderHelp() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Blue).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Text).Background(m.theme.Surface)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)

	return style.Render(
		keyStyle.Render("↑↓/jk") + descStyle.Render(" nav  ") +
			keyStyle.Render("g/G") + descStyle.Render(" top/bot  ") +
			keyStyle.Render("PgUp/Dn") + descStyle.Render(" page  ") +
			keyStyle.Render("f") + descStyle.Render(" filter  ") +
			keyStyle.Render("l") + descStyle.Render(" liveness  ") +
			keyStyle.Render("t") + descStyle.Render(" tailor  ") +
			keyStyle.Render("u") + descStyle.Render(" status  ") +
			keyStyle.Render("Esc") + descStyle.Render(" back  ") +
			keyStyle.Render("q") + descStyle.Render(" quit"))
}
