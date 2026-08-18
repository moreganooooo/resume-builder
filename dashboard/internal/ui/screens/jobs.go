package screens

import (
	"bufio"
	"bytes"
	"context"
	"fmt"
	"image/color"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"charm.land/bubbles/v2/progress"
	"charm.land/bubbles/v2/spinner"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

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
	detailScrollOffset int // scroll position in the detail pane (J/K keys)
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
	// actionErrorDetail is the full raw stderr behind actionError -- kept
	// separately so a USER_ERROR: marker line (see parseActionError) can
	// promote a plain-language sentence to actionError while the raw text
	// stays reachable behind the "d for details" affordance instead of
	// being discarded.
	actionErrorDetail   string
	actionErrorExpanded bool
	// notice explains why a keypress was a no-op (e.g. "t" on a non-Pending
	// job) instead of silently doing nothing. Dismissed on the next
	// keypress, same convention as actionError.
	notice       string
	statusPicker bool
	statusCursor int
	// statusConfirm/pendingStatus hold the inline confirm step between
	// picking a status and actually committing it -- application-status
	// changes are destructive-but-free (see renderStatusPickerOverlay's own
	// doc comment in bars.go), so the first Enter on a picker option is a
	// proposal, not a commit.
	statusConfirm bool
	pendingStatus string
	// Search sub-state -- narrows the active filter by substring on
	// company/title. Mirrors pipeline.go's identical searchInput/
	// searchQuery pair exactly (same key to enter, same cancel/commit keys,
	// same live-filter-as-you-type behavior) so a user who learns search on
	// Pipeline finds it identical here.
	searchInput bool   // true while the user is typing the query
	searchQuery string // committed (or in-progress) lowercased query
	// showHelp toggles the `?` categorized keybinding overlay (see
	// bars.go's renderHelpOverlay) over this screen's normal body.
	showHelp bool
	spinner  spinner.Model

	// actionChan carries progress/completion messages from the goroutine
	// runAction starts. Only "tailor" ever emits jobsActionProgressMsg (it's
	// the only action whose subprocess runs orchestrator.py's Step N: ...
	// pipeline) -- liveness/status stream straight to their completion
	// message and render the plain spinner instead of the progress bar.
	// actionStartedAt marks when the in-flight action began, so a hung
	// subprocess can be told apart from a slow one -- without it the
	// spinner spins identically forever either way.
	actionStartedAt time.Time

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
			progress.WithColors(t.Sky, t.Mauve),
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

// applyFilter recomputes m.filtered from m.rows using the active filter
// (status-based, score-based, or recency) and any search query (m.searchQuery).
// Search narrows *within* the active filter rather than resetting it --
// mirrors pipeline.go's applyFilterAndSort behavior. Supports:
// - Status: all, pending, completed
// - Score: high_fit (4.0+), good_fit (3.5+)
// - Recency: recent (jobs already sorted by score are treated as recent)
func (m *JobsModel) applyFilter() {
	var out []model.JobRow
	for _, r := range m.rows {
		// Apply active filter based on mode
		switch m.filter {
		case "pending", "completed":
			if !strings.EqualFold(r.Status, m.filter) {
				continue
			}
		case "high_fit":
			if r.Evaluation.CompositeScore < 4.0 {
				continue
			}
		case "good_fit":
			if r.Evaluation.CompositeScore < 3.5 {
				continue
			}
		case "recent":
			// "Recent" jobs are those already at the top of the list
			// (already sorted by score), so we show the first 50 high-quality jobs
			if r.Evaluation.CompositeScore < 3.0 {
				continue
			}
		// "all" has no score/status restriction
		}

		// Apply search query within the active filter
		if !matchesJobSearch(r, m.searchQuery) {
			continue
		}
		out = append(out, r)
	}
	m.filtered = out
	if m.cursor >= len(m.filtered) {
		m.cursor = len(m.filtered) - 1
	}
	if m.cursor < 0 {
		m.cursor = 0
	}
	m.adjustScroll()
}

// matchesJobSearch reports whether job matches the lowercased search query
// against company, title, and description -- the free-text fields a job
// seeker actually searches by. Description is included so a skill keyword
// or requirement buried in the body surfaces without needing to know which
// company posted it.
func matchesJobSearch(job model.JobRow, query string) bool {
	if query == "" {
		return true
	}
	q := strings.ToLower(query)
	if strings.Contains(strings.ToLower(job.Company), q) {
		return true
	}
	if strings.Contains(strings.ToLower(job.Title), q) {
		return true
	}
	if job.Description != "" && strings.Contains(strings.ToLower(job.Description), q) {
		return true
	}
	return false
}

// countForStatusFilter returns how many rows match the active status filter
// alone, ignoring any search query -- the denominator for renderSearchBar's
// "N/M matching" display, mirroring pipeline.go's countForFilter/tabFiltered.
func (m JobsModel) countForStatusFilter() int {
	if m.filter == "all" {
		return len(m.rows)
	}
	count := 0
	for _, r := range m.rows {
		if strings.EqualFold(r.Status, m.filter) {
			count++
		}
	}
	return count
}

// hasExtraBar reports whether View() will render the action-status/error/
// notice bar above the split pane -- adjustScroll needs this to compute the
// same available height chromeAvailHeight(extraRows) uses at render time, or
// scrolling and rendering could disagree about how many rows are visible.
func (m JobsModel) hasExtraBar() bool {
	return m.actionInProgress != "" || m.actionError != "" || m.notice != ""
}

// extraRows returns how many extra chrome rows View() renders above the
// split pane: the action-status/error/notice bar (0 or 1) plus the search
// bar (0 or 1) when a search is active or has a committed query. The two
// can be visible at once -- e.g. a "Cancelled" notice while a search query
// is still active -- so this sums rather than picking one, unlike
// hasExtraBar's plain bool. Mirrors pipeline.go's chromeRowsFixed, which
// budgets an extra row for the same two conditions.
func (m JobsModel) extraRows() int {
	rows := 0
	if m.hasExtraBar() {
		rows++
	}
	if m.searchInput || m.searchQuery != "" {
		rows++
	}
	return rows
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
	avail := m.sidebarViewportLines(m.chromeAvailHeight(m.extraRows()))
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
	// Cycle through filter modes: status → score-based → more
	switch current {
	case "all":
		return "pending"
	case "pending":
		return "completed"
	case "completed":
		return "high_fit"
	case "high_fit":
		return "good_fit"
	case "good_fit":
		return "recent"
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

// handleStatusPickerKey handles input while the status picker overlay is
// open. When m.statusConfirm is set, the user has already picked a status
// and this only accepts the inline confirm/cancel keys -- see
// renderStatusPickerOverlay's doc comment in bars.go for why a status
// change doesn't commit on the first Enter.
func (m JobsModel) handleStatusPickerKey(msg tea.KeyPressMsg) (JobsModel, tea.Cmd) {
	if m.statusConfirm {
		switch msg.String() {
		case "enter", "y", "Y":
			m.statusPicker = false
			m.statusConfirm = false
			if job, ok := m.CurrentJob(); ok {
				chosen := m.pendingStatus
				m.pendingStatus = ""
				m.actionInProgress = "status"
				m.actionStartedAt = time.Now()
				m.actionChan = make(chan tea.Msg)
				ctx, cancel := context.WithCancel(context.Background())
				m.actionCancel = cancel
				return m, tea.Batch(m.runAction(ctx, m.actionChan, "status", job.Path, chosen), m.spinner.Tick)
			}
		case "esc", "n", "N":
			// Back out to the picker itself, not all the way out of it --
			// changing your mind about which status shouldn't mean redoing
			// the "u" keypress too.
			m.statusConfirm = false
			m.pendingStatus = ""
		}
		return m, nil
	}

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
		if _, ok := m.CurrentJob(); ok {
			m.pendingStatus = jobsApplicationStatuses[m.statusCursor]
			m.statusConfirm = true
		}
	}
	return m, nil
}

// handleSearchInput consumes keys while the search input bar is open.
// Mirrors pipeline.go's handleSearchInput exactly: same cancel key (esc,
// which also discards the in-progress query), same commit key (enter, which
// just closes the input and keeps whatever's typed), same clear-all key
// (ctrl+u), and the same live-filter-on-every-keystroke behavior via
// applyFilter after backspace/typing. Being routed here at all (see the
// `if m.searchInput` check in Update, checked before the main key switch)
// is what stops a typed letter from also triggering a single-letter Jobs
// shortcut like "f"/"l"/"t"/"u" -- this function is the only place keys are
// interpreted while the input is focused.
func (m JobsModel) handleSearchInput(msg tea.KeyPressMsg) (JobsModel, tea.Cmd) {
	switch msg.String() {
	case "esc":
		m.searchInput = false
		m.searchQuery = ""
		m.applyFilter()
		m.cursor = 0
		m.scrollOffset = 0
		return m, nil

	case "enter":
		m.searchInput = false
		return m, nil

	case "backspace":
		if len(m.searchQuery) > 0 {
			runes := []rune(m.searchQuery)
			m.searchQuery = string(runes[:len(runes)-1])
			m.applyFilter()
			m.cursor = 0
			m.scrollOffset = 0
		}
		return m, nil

	case "ctrl+u":
		m.searchQuery = ""
		m.applyFilter()
		m.cursor = 0
		m.scrollOffset = 0
		return m, nil
	}

	if msg.Text != "" {
		m.searchQuery += strings.ToLower(msg.Text)
		m.applyFilter()
		m.cursor = 0
		m.scrollOffset = 0
		return m, nil
	}
	return m, nil
}

// parseActionError splits a failed dashboard_actions.py run into a
// display message and the full raw detail behind it. dashboard_actions.py
// may emit a final "USER_ERROR: <plain-language sentence>" stderr line for
// failures it recognizes (that module's own docstring documents the
// contract); when present, its remainder becomes the plain-language
// display text a non-developer can actually understand, while the raw
// stderr always stays available as detail so nothing is silently lost --
// only deprioritized behind the "d for details" affordance. Falls back to
// showing the raw output/error directly when no marker line is present,
// exactly matching the previous behavior.
func parseActionError(output string, fallbackErr error) (display, detail string) {
	detail = strings.TrimSpace(output)
	if detail == "" && fallbackErr != nil {
		detail = fallbackErr.Error()
	}
	if detail == "" {
		detail = "Unknown error"
	}

	lines := strings.Split(detail, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if line == "" {
			continue
		}
		if rest, ok := strings.CutPrefix(line, "USER_ERROR:"); ok {
			display = strings.TrimSpace(rest)
			if display == "" {
				display = "Something went wrong."
			}
			return display, detail
		}
		break
	}
	return detail, detail
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
			m.actionError, m.actionErrorDetail = parseActionError(msg.output, msg.err)
			m.actionErrorExpanded = false
			return m, nil
		}
		return m, reloadJobsCmd(m.jobsPath)

	case jobsReloadedMsg:
		if msg.err != nil {
			// Not a dashboard_actions.py failure (no USER_ERROR: contract
			// here, just a local file-read error), so display and detail are
			// the same text -- renderActionError only offers the "d for
			// details" affordance when they actually differ.
			m.actionError = msg.err.Error()
			m.actionErrorDetail = m.actionError
			m.actionErrorExpanded = false
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
		m.progress = newModel
		return m, cmd

	case tea.KeyPressMsg:
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
			// "d" toggles the raw-detail view instead of dismissing, but
			// only when there's actually a distinct detail to show (a plain
			// USER_ERROR: message with the raw text behind it) -- otherwise
			// "d" dismisses like any other key, matching the plain fallback
			// case where display and detail are identical.
			if msg.String() == "d" && m.actionErrorDetail != "" && m.actionErrorDetail != m.actionError {
				m.actionErrorExpanded = !m.actionErrorExpanded
				return m, nil
			}
			m.actionError = ""
			m.actionErrorDetail = ""
			m.actionErrorExpanded = false
			return m, nil
		}
		if m.notice != "" {
			m.notice = ""
			return m, nil
		}
		if m.showHelp {
			switch msg.String() {
			case "?", "esc", "q":
				m.showHelp = false
			}
			return m, nil
		}
		if m.statusPicker {
			return m.handleStatusPickerKey(msg)
		}
		// Checked before the main switch below, same placement pipeline.go
		// uses for its own searchInput check -- while the search input is
		// focused, every keystroke (including single letters that would
		// otherwise be shortcuts like "f"/"l"/"t"/"u") must go into the query
		// instead of triggering an action, or typing "letter" would silently
		// fire "letter" as a keybinding too.
		if m.searchInput {
			return m.handleSearchInput(msg)
		}
		switch msg.String() {
		case "?":
			m.showHelp = true
		case "/":
			// Open search input. Pre-fill with the current query (if any) so
			// refining a committed search is one keystroke away -- mirrors
			// pipeline.go's identical "/" case.
			m.searchInput = true
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
				m.detailScrollOffset = 0
				m.adjustScroll()
			}
		case "down", "j":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
				m.detailScrollOffset = 0
				m.adjustScroll()
			}
		case "g":
			if len(m.filtered) > 0 {
				m.cursor = 0
				m.detailScrollOffset = 0
				m.adjustScroll()
			}
		case "G":
			if len(m.filtered) > 0 {
				m.cursor = len(m.filtered) - 1
				m.detailScrollOffset = 0
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
				m.detailScrollOffset = 0
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
				m.detailScrollOffset = 0
				m.adjustScroll()
			}
		case "f":
			m.filter = nextJobsFilter(m.filter)
			m.applyFilter()
		case "l":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "liveness"
				m.actionStartedAt = time.Now()
				m.actionChan = make(chan tea.Msg)
				ctx, cancel := context.WithCancel(context.Background())
				m.actionCancel = cancel
				return m, tea.Batch(m.runAction(ctx, m.actionChan, "liveness", job.Path), m.spinner.Tick)
			}
		case "t":
			if job, ok := m.CurrentJob(); ok {
				if job.Status == "Pending" {
					m.actionInProgress = "tailor"
					m.actionStartedAt = time.Now()
					m.actionChan = make(chan tea.Msg)
					m.progress = progress.New(progress.WithColors(m.theme.Sky, m.theme.Mauve))
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
		case "a":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "archive"
				m.actionStartedAt = time.Now()
				m.actionChan = make(chan tea.Msg)
				ctx, cancel := context.WithCancel(context.Background())
				m.actionCancel = cancel
				return m, tea.Batch(m.runAction(ctx, m.actionChan, "archive", job.Path), m.spinner.Tick)
			}
		case "J":
			if _, ok := m.CurrentJob(); ok {
				m.detailScrollOffset++
			}
		case "K":
			if m.detailScrollOffset > 0 {
				m.detailScrollOffset--
			}
		case "v":
			m.showHelp = true
		case "q":
			return m, func() tea.Msg { return JobsClosedMsg{Quit: true} }
		case "esc":
			// While a search is committed, Esc clears the search first (matches
			// vim's `:nohl` ergonomics, and pipeline.go's identical esc case)
			// rather than leaving the screen -- a cleared filter is itself the
			// useful "undo" here. With no query, Esc backs out to the Main
			// Menu as before.
			if m.searchQuery != "" {
				m.searchQuery = ""
				m.applyFilter()
				return m, nil
			}
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

// chromeAvailHeight budgets room for the header and help bars, plus
// extraRows chrome rows (action-status/error/notice, and/or the search bar)
// when they're showing -- the split-pane's declared Height() previously
// stayed at height-2 regardless, so whenever extra rendered (any
// liveness/tailor/status action, or a dismissable notice) the total output
// grew to height-1 lines, one past the terminal's visible height. Mirrors
// the reservation status-picker overlays already make for themselves in
// renderSidebarList below.
func (m JobsModel) chromeAvailHeight(extraRows int) int {
	h := m.height - 2 - extraRows // header + help
	if h < 5 {
		h = 5
	}
	return h
}

var jobsHelpCategories = []helpCategory{
	{"Navigation", []helpBinding{
		{"↑ ↓ / j k", "Move selection"},
		{"J / K", "Scroll detail pane down / up"},
		{"g / G", "Jump to top / bottom"},
		{"PgUp / PgDn", "Page up / down"},
	}},
	{"Actions", []helpBinding{
		{"l", "Check posting liveness"},
		{"t", "Tailor resume for this job (Pending only)"},
		{"u", "Change application status"},
		{"a", "Archive this job (removes from all filters)"},
	}},
	{"Filters", []helpBinding{
		{"f", "Cycle filters: All → Pending → Completed → High Fit → Good Fit → Recent"},
		{"/", "Search company/title (narrows within active filter)"},
	}},
	{"Quick Reference", []helpBinding{
		{"v", "View terminology definitions"},
		{"?", "Show this help overlay"},
	}},
	{"Terminology", []helpBinding{
		{"Composite Score", "Overall fit (40% Fit + 40% Interview Odds + 20% Practical Pursue)"},
		{"Fit", "How well your background matches job requirements"},
		{"Interview Odds", "Likelihood of advancing past initial screening"},
		{"North Star", "Your target skill/role that guides tailoring"},
		{"Liveness", "Whether a job posting is still actively being filled"},
	}},
	{"Exit", []helpBinding{
		{"Esc", "Clear search, or back to Main Menu"},
		{"q", "Quit dashboard"},
	}},
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
	searchBar := m.renderSearchBar()
	help := m.renderHelp()

	// Wider left sidebar (job selection) makes sense for scanning a list;
	// narrower right pane (details) is enough for truncated previews. Users
	// can read full details by selecting; description wrapping is acceptable.
	leftWidth := int(float64(m.width) * 0.60)
	rightWidth := m.width - leftWidth
	availHeight := m.chromeAvailHeight(m.extraRows())

	leftPane := m.renderSidebarList(leftWidth, availHeight)
	var rightPane string
	if job, ok := m.CurrentJob(); ok {
		rightPane = m.renderJobDetailPane(job, rightWidth, availHeight)
	} else {
		rightPane = renderEmptyDetailPane(m.theme, rightWidth, availHeight)
	}

	splitView := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)

	// searchBar before extra (action-status/error/notice), matching
	// pipeline.go's View() ordering of its own searchBar/notice rows.
	content := header
	if searchBar != "" {
		content = lipgloss.JoinVertical(lipgloss.Left, content, searchBar)
	}
	if extra != "" {
		content = lipgloss.JoinVertical(lipgloss.Left, content, extra)
	}
	fullContent := lipgloss.JoinVertical(lipgloss.Left, content, splitView, help)

	// Render help as a centered modal overlay if showing
	if m.showHelp {
		helpContent := renderHelpOverlay(m.theme, "Jobs", jobsHelpCategories, int(float64(m.width)*0.75), m.height-4)
		return renderModalOverlay(m.theme, fullContent, helpContent, m.width, m.height)
	}

	return fullContent
}

func actionLabel(action string) string {
	switch action {
	case "liveness":
		return "Checking liveness"
	case "tailor":
		return "Tailoring resume"
	case "status":
		return "Updating status"
	case "archive":
		return "Archiving job"
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
		m.progress.SetWidth(m.width - 6)
		label := m.actionStepLabel
		if label == "" {
			label = actionLabel(m.actionInProgress)
		}
		// Render progress bar 3 lines thick for a bolder appearance
		progressView := renderThickProgress(m.progress, m.theme, 3)
		return style.Render(label + " (esc to cancel)" + m.stalledHint() + "\n" + progressView)
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
		labelStyle.Render(" "+actionLabel(m.actionInProgress)+"... (esc to cancel)"+m.stalledHint())
	if pad := m.width - lipgloss.Width(left); pad > 0 {
		left += bg.Render(strings.Repeat(" ", pad))
	}
	return left
}

// renderActionError shows m.actionError (the plain-language line, if
// dashboard_actions.py's failure included a USER_ERROR: marker -- see
// parseActionError) with the full raw stderr in m.actionErrorDetail
// reachable behind "d" instead of always dumping raw subprocess output at
// the user. dashboard_actions.py's own stderr forwarding is by design
// (see that module's docstring) -- this only changes what's shown first.
func (m JobsModel) renderActionError() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Red).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)

	hasDetail := m.actionErrorDetail != "" && m.actionErrorDetail != m.actionError
	if m.actionErrorExpanded && hasDetail {
		return style.Render("Error: " + truncateRunes(m.actionErrorDetail, m.width-12) + " (d to collapse, any other key to dismiss)")
	}
	hint := " (press any key to dismiss)"
	if hasDetail {
		hint = " (d for details, any other key to dismiss)"
	}
	return style.Render("Error: " + truncateRunes(m.actionError, m.width-12) + hint)
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

	// Format filter display with human-readable labels and color
	filterLabel := m.getFilterLabel()
	filterStyle := lipgloss.NewStyle().
		Foreground(m.theme.Mauve).
		Background(m.theme.Surface).
		Bold(true)

	countStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)
	info := countStyle.Render(fmt.Sprintf("%d job(s) ", len(m.filtered))) +
		filterStyle.Render("⏺ " + filterLabel)

	title := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue).Background(m.theme.Surface).Render(m.theme.Icons.Jobs + "  ") +
		lipgloss.NewStyle().Bold(true).Background(m.theme.Surface).Render(theme.RenderColorGradient("✦ JOBS ✧", m.theme.Blue, m.theme.Peach))
	title, info, gap := fitBar(title, info, m.width, 4, m.theme.Surface)
	return style.Render(title + gap + info)
}

func (m JobsModel) getFilterLabel() string {
	switch m.filter {
	case "pending":
		return "PENDING"
	case "completed":
		return "COMPLETED"
	case "high_fit":
		return "HIGH FIT (4.0+)"
	case "good_fit":
		return "GOOD FIT (3.5+)"
	case "recent":
		return "RECENT"
	default:
		return "ALL JOBS"
	}
}

// renderSearchBar returns an empty string when there is no active or
// in-progress search; otherwise it renders a vim-style status line showing
// the query and the match count. While in input mode, a trailing cursor is
// appended. Mirrors pipeline.go's renderSearchBar exactly -- same prompt
// glyph, same "N/M matching" count, same hint text, same live-cursor
// treatment -- so search looks and behaves identically on both screens.
func (m JobsModel) renderSearchBar() string {
	if !m.searchInput && m.searchQuery == "" {
		return ""
	}

	style := lipgloss.NewStyle().
		Foreground(m.theme.Text).
		Width(m.width).
		Padding(0, 2)

	var prompt string
	if m.searchInput {
		prompt = lipgloss.NewStyle().Bold(true).Foreground(m.theme.Surface).Background(m.theme.Blue).Padding(0, 1).Render(" SEARCH ")
	} else {
		prompt = lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue).Render("/")
	}
	queryStyle := lipgloss.NewStyle().Foreground(m.theme.Text)
	hintStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext)

	display := queryStyle.Render(m.searchQuery)
	if m.searchInput {
		display += lipgloss.NewStyle().Foreground(m.theme.Blue).Render("█")
	}

	matchInfo := hintStyle.Render(fmt.Sprintf("  %d/%d matching", len(m.filtered), m.countForStatusFilter()))

	hint := ""
	if m.searchInput {
		hint = hintStyle.Render("   Enter: keep   Esc: cancel   Ctrl+U: clear")
	} else {
		hint = hintStyle.Render("   Esc: clear   /: edit")
	}

	return style.Render(prompt + " " + display + matchInfo + hint)
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
		// Plain-language empty state distinct from the plain filter-empty
		// message below -- "no jobs match this filter" reads as a dead end,
		// while naming the query tells the user exactly what to clear or
		// retype next.
		msg := "No evaluated jobs match this filter"
		if m.searchQuery != "" {
			msg = fmt.Sprintf("No jobs match %q -- press Esc to clear the search", m.searchQuery)
		}
		return emptyStyle.Render(msg)
	}

	var lines []string
	for i, job := range m.filtered {
		selected := i == m.cursor
		// The subtitle carries the title plus, when there's room, the two
		// layer scores behind the composite. Composed here rather than by
		// changing renderSidebarRow's signature, which pipeline.go also
		// calls -- Pipeline rows are about application progress, not fit,
		// so they have no use for these.
		subtitle := jobSubtitleWithScores(m.theme, job, width-4)
		lines = append(lines, renderSidebarRow(m.theme, job.Evaluation.CompositeScore, job.Company, subtitle, width-4, selected))
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
		confirmLabel := ""
		if m.statusConfirm {
			confirmLabel = fmt.Sprintf("Mark as %s?", m.pendingStatus)
		}
		content = renderStatusPickerOverlay(m.theme, content, width-4, "Set status:", jobsApplicationStatuses, m.statusCursor, confirmLabel)
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
	// Remove the fixed Height() from the border so the pane is not clipped
	// before we scroll -- we impose our own line-budget via detailScrollOffset.
	scrollBorder := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Overlay).
		Width(width - 2).
		Padding(1, 2)

	wrapWidth := width - 10 // inner content width for wrapped text
	if wrapWidth < 20 {
		wrapWidth = 20
	}
	wrapStyle := lipgloss.NewStyle().Width(wrapWidth).Foreground(m.theme.Text)
	accent := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Mauve)
	score := scoreStyle(m.theme, job.Evaluation.CompositeScore)

	jobStatusPill := func(status string) string {
		var color color.Color
		switch strings.ToLower(status) {
		case "pending":
			color = m.theme.Yellow
		case "completed":
			color = m.theme.Green
		case "applied":
			color = m.theme.Sky
		case "responded":
			color = m.theme.Blue
		case "interview", "offer":
			color = m.theme.Green
		case "rejected", "discarded", "withdrawn":
			color = m.theme.Subtext
		default:
			color = m.theme.Text
		}
		return lipgloss.NewStyle().
			Background(color).
			Foreground(m.theme.Base).
			Padding(0, 1).
			Bold(true).
			Render(strings.ToUpper(status))
	}

	var content []string
	eval := job.Evaluation

	// -- Header --
	content = append(content, styles.Title.Render(job.Company))
	content = append(content, styles.Value.Render(job.Title))
	if job.SourcePlatform != "" {
		content = append(content, styles.Subtext.Render("via "+job.SourcePlatform))
	}
	content = append(content, "")

	// -- Scores --
	content = append(content, accent.Render("Scores"))
	content = append(content,
		styles.Subtext.Render("Composite: ")+
			score.Render(scoreIcon(m.theme, eval.CompositeScore)+" "+fmt.Sprintf("%.1f/5", eval.CompositeScore)))
	content = append(content,
		styles.Subtext.Render("  Fit: ")+layerScoreText(m.theme, eval.FitScore))
	content = append(content,
		styles.Subtext.Render("  Interview odds: ")+layerScoreText(m.theme, eval.InterviewOddsScore))

	// Subscores: each subcategory on its own line
	for _, group := range jobsFitGroups {
		scores := group.get(eval)
		if len(scores) == 0 {
			continue
		}
		content = append(content, "")
		content = append(content, accent.Render(group.label+" subscores"))
		keys := make([]string, 0, len(scores))
		for k := range scores {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			label, ok := theme.SubscoreLabels[k]
			if !ok {
				label = k
			}
			content = append(content, fmt.Sprintf("  %s: %d", label, scores[k]))
		}
	}

	content = append(content, "")
	content = append(content, styles.Subtext.Render("Recommendation: ")+styles.Value.Render(eval.Recommendation))
	content = append(content, styles.Subtext.Render("Status: ")+jobStatusPill(job.Status))

	// -- Why / Recruiter Read --
	if eval.Why != "" {
		content = append(content, "")
		content = append(content, accent.Render("Why"))
		content = append(content, wrapStyle.Render(eval.Why))
	}
	if eval.RecruiterRead != "" {
		content = append(content, "")
		content = append(content, accent.Render("Recruiter read"))
		content = append(content, wrapStyle.Render(eval.RecruiterRead))
	}
	if len(eval.HardBlockers) > 0 {
		content = append(content, "")
		content = append(content, accent.Render("Hard blockers"))
		for _, b := range eval.HardBlockers {
			content = append(content, "  • "+b)
		}
	}

	// -- Posting legitimacy warning --
	if eval.PostingLegitimacy != "" && eval.PostingLegitimacy != "High Confidence" {
		color := m.theme.Yellow
		if eval.PostingLegitimacy == "Suspicious" {
			color = m.theme.Red
		}
		warningStyle := lipgloss.NewStyle().Bold(true).Foreground(color)
		content = append(content, "")
		content = append(content, warningStyle.Render("⚠ Posting legitimacy: "+eval.PostingLegitimacy))
		if eval.PostingLegitimacyNotes != "" {
			content = append(content, wrapStyle.Render(eval.PostingLegitimacyNotes))
		}
	}

	// -- Skills graph --
	if len(job.Skills) > 0 {
		content = append(content, "")
		content = append(content, accent.Render("Skills"))
		// Render skills as a wrapped list of badges
		line := ""
		for i, s := range job.Skills {
			badge := "[" + s + "]"
			if i == 0 {
				line = badge
			} else if len(line)+1+len(badge) <= wrapWidth {
				line += " " + badge
			} else {
				content = append(content, "  "+line)
				line = badge
			}
		}
		if line != "" {
			content = append(content, "  "+line)
		}
	}

	// -- Liveness --
	if job.Liveness != nil {
		content = append(content, "")
		content = append(content, accent.Render("Liveness"))
		content = append(content, styles.Subtext.Render("Result: ")+styles.Value.Render(job.Liveness.Result))
		if job.Liveness.CheckedAt != "" {
			content = append(content, styles.Subtext.Render("Checked: ")+
				lipgloss.NewStyle().Foreground(m.theme.Subtext).Render(job.Liveness.CheckedAt))
		}
		if job.Liveness.Reason != "" {
			content = append(content, wrapStyle.Render(job.Liveness.Reason))
		}
	}

	// -- Application status / progress pipeline --
	if job.Application != nil {
		content = append(content, "")
		content = append(content, accent.Render("Application"))
		content = append(content, styles.Subtext.Render("Status: ")+jobStatusPill(job.Application.Status))
		if job.Application.AppliedAt != nil {
			content = append(content, styles.Subtext.Render("Applied: ")+styles.Value.Render(*job.Application.AppliedAt))
		}
		// Progress pipeline: Resume → Cover Letter → Ready → Applied → Interview → Offer
		pipeline := []string{"Resume", "Cover Letter", "Ready", "Applied", "Interview", "Offer"}
		statusOrder := map[string]int{
			"Pending": 0, "Completed": 2, "Applied": 3,
			"Interview": 4, "Offer": 5, "Responded": 4,
		}
		currentStep := statusOrder[job.Status]
		var pipelineStr string
		for i, stage := range pipeline {
			if i > 0 {
				pipelineStr += " → "
			}
			if i <= currentStep {
				pipelineStr += lipgloss.NewStyle().Foreground(m.theme.Green).Bold(true).Render(stage)
			} else {
				pipelineStr += lipgloss.NewStyle().Foreground(m.theme.Subtext).Render(stage)
			}
		}
		content = append(content, pipelineStr)
	}

	// -- Apply link --
	if job.SourceURL != "" {
		content = append(content, "")
		content = append(content, accent.Render("Apply"))
		content = append(content, lipgloss.NewStyle().Foreground(m.theme.Blue).Render(job.SourceURL))
	}

	// -- Research highlights --
	if job.Research != nil {
		content = append(content, "")
		content = append(content, accent.Render("Company Research"))
		if job.Research.CompanyHQLocation != "" {
			content = append(content, styles.Subtext.Render("HQ: ")+styles.Value.Render(job.Research.CompanyHQLocation))
		}
		for _, fact := range job.Research.CompanyFacts {
			content = append(content, "  • "+fact)
		}
		for _, h := range job.Research.NotableHighlights {
			content = append(content, "  ★ "+h)
		}
		if job.Research.ResearchedAt != "" {
			content = append(content,
				lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("Researched: "+job.Research.ResearchedAt))
		}
	}

	// -- Keyword Coverage / Gap Analysis --
	if job.Coverage != nil {
		content = append(content, "")
		content = append(content, accent.Render("Keyword Coverage & Gap Analysis"))

		// Render Score & Band
		var bandColor color.Color
		switch job.Coverage.Band {
		case "excellent_match":
			bandColor = m.theme.Green
		case "good_match":
			bandColor = m.theme.Green
		case "weak_match":
			bandColor = m.theme.Yellow
		default:
			bandColor = m.theme.Red
		}

		scoreStyle := lipgloss.NewStyle().Foreground(bandColor).Bold(true)
		bandStr := strings.ToUpper(strings.ReplaceAll(job.Coverage.Band, "_", " "))
		content = append(content, styles.Subtext.Render("Match Score: ")+scoreStyle.Render(fmt.Sprintf("%.0f%% (%s)", job.Coverage.Score, bandStr)))

		// Render Matched Keywords
		if len(job.Coverage.Matched) > 0 {
			matchedStr := strings.Join(job.Coverage.Matched, ", ")
			content = append(content, styles.Subtext.Render("✓ Matched: ")+lipgloss.NewStyle().Foreground(m.theme.Green).Render(matchedStr))
		}

		// Render Missing Gaps
		if len(job.Coverage.Missing) > 0 {
			missingStr := strings.Join(job.Coverage.Missing, ", ")
			content = append(content, styles.Subtext.Render("✗ Missing Gaps: ")+lipgloss.NewStyle().Foreground(m.theme.Red).Render(missingStr))
		} else {
			content = append(content, lipgloss.NewStyle().Foreground(m.theme.Green).Render("✓ Perfect coverage! No missing target keywords."))
		}

		if job.Coverage.CheckedAt != "" {
			content = append(content,
				lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("Checked: "+job.Coverage.CheckedAt))
		}
	}

	// -- Full JD description (at the bottom since it's long) --
	if job.Description != "" {
		content = append(content, "")
		content = append(content, accent.Render("Job Description"))
		content = append(content, wrapStyle.Render(job.Description))
	}

	// Apply detailScrollOffset: skip the first N lines
	joined := strings.Join(content, "\n")
	lines := strings.Split(joined, "\n")
	visibleBudget := height - 6 // border + padding
	if visibleBudget < 5 {
		visibleBudget = 5
	}
	// Clamp scroll so we can't scroll past all content
	maxScroll := len(lines) - visibleBudget
	if maxScroll < 0 {
		maxScroll = 0
	}
	offset := m.detailScrollOffset
	if offset > maxScroll {
		offset = maxScroll
	}
	if offset > 0 && offset < len(lines) {
		lines = lines[offset:]
	}
	// Truncate to visible budget to prevent overflow
	if len(lines) > visibleBudget {
		lines = lines[:visibleBudget]
	}

	// Scroll hint at the bottom if there's more
	hasMore := offset < maxScroll
	hasAbove := offset > 0
	var scrollHint string
	if hasAbove && hasMore {
		scrollHint = lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("↑ K / J ↓")
	} else if hasAbove {
		scrollHint = lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("↑ K  (top)")
	} else if hasMore {
		scrollHint = lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("  J ↓ more")
	}
	if scrollHint != "" {
		lines = append(lines, scrollHint)
	}

	joined = strings.Join(lines, "\n")
	return scrollBorder.Render(joined)
}

func (m JobsModel) renderHelp() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Blue).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Text).Background(m.theme.Surface)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)

	if m.searchInput {
		// Mirrors pipeline.go's own searchInput help-bar swap -- while typing,
		// the normal shortcut list is misleading (those keys aren't live), so
		// it's replaced with the keys that actually do something right now.
		style = style.Foreground(m.theme.Subtext)
		keyStyle = keyStyle.Foreground(m.theme.Subtext).Bold(false)
		descStyle = descStyle.Foreground(m.theme.Subtext)
		return style.Render(
			keyStyle.Render("type") + descStyle.Render(" filter live  ") +
				keyStyle.Render("Enter") + descStyle.Render(" keep  ") +
				keyStyle.Render("Ctrl+U") + descStyle.Render(" clear  ") +
				keyStyle.Render("Esc") + descStyle.Render(" cancel"))
	}

	return style.Render(
		keyStyle.Render("↑↓/jk") + descStyle.Render(" nav  ") +
			keyStyle.Render("J/K") + descStyle.Render(" scroll detail  ") +
			keyStyle.Render("g/G") + descStyle.Render(" top/bot  ") +
			keyStyle.Render("PgUp/Dn") + descStyle.Render(" page  ") +
			keyStyle.Render("/") + descStyle.Render(" search  ") +
			keyStyle.Render("f") + descStyle.Render(" filter  ") +
			keyStyle.Render("l") + descStyle.Render(" liveness  ") +
			keyStyle.Render("t") + descStyle.Render(" tailor  ") +
			keyStyle.Render("u") + descStyle.Render(" status  ") +
			keyStyle.Render("a") + descStyle.Render(" archive  ") +
			keyStyle.Render("v") + descStyle.Render(" vocabulary  ") +
			keyStyle.Render("?") + descStyle.Render(" help  ") +
			keyStyle.Render("Esc") + descStyle.Render(" back  ") +
			keyStyle.Render("q") + descStyle.Render(" quit"))
}

// jobsScoreDetailMinWidth is the narrowest sidebar that still has room for
// the per-layer scores. Fit and Odds are ADDITIVE detail -- the composite
// already leads every row -- so when space is tight they are the FIRST
// thing dropped, never the job title, which is what a user actually scans
// by. Adding them unconditionally is the mistake the Python side made
// first (see _FIT_SCORE_DETAIL_COLUMNS in scripts/cli_art.py): it pushed
// existing content off the edge instead of yielding.
const jobsScoreDetailMinWidth = 34

// layerScore formats one layer score, or "-" when it is absent. A zero
// here means "not recorded" rather than "scored zero" -- these fields
// postdate some evaluations, and the scale starts at 1.
func layerScore(score float64) string {
	if score <= 0 {
		return "-"
	}
	return fmt.Sprintf("%.1f", score)
}

// layerScoreText renders a layer score with the same icon+color tier
// pairing scoreStyle/scoreIcon give the composite, so no number in the
// detail pane signals by color alone.
func layerScoreText(t theme.Theme, score float64) string {
	if score <= 0 {
		return lipgloss.NewStyle().Foreground(t.Token.Subtext).Render("-")
	}
	return scoreStyle(t, score).Render(scoreIcon(t, score) + " " + layerScore(score))
}

// jobSubtitleWithScores appends a compact "F 4.5 / O 3.9" to the row's
// title when the sidebar is wide enough to carry it.
//
// Rendered in flat Subtext rather than tier colors on purpose: at this
// size the two numbers sit inches from the composite's own colored tier
// icon, and three competing color signals per row turns a scannable list
// into noise. Carrying no color here also means there is no color-only
// signal to make redundant -- the numbers are the whole message.
func jobSubtitleWithScores(t theme.Theme, job model.JobRow, width int) string {
	eval := job.Evaluation
	if width < jobsScoreDetailMinWidth || (eval.FitScore <= 0 && eval.InterviewOddsScore <= 0) {
		return job.Title
	}
	// Spell out "Fit"/"Odds" in full -- single-letter abbreviations saved 4
	// columns at the cost of being completely opaque to a first-time user;
	// the detail pane already carries the full labels, and the extra chars
	// are worth the clarity.
	suffix := fmt.Sprintf("  Fit %s / Odds %s", layerScore(eval.FitScore), layerScore(eval.InterviewOddsScore))
	// Reserve the suffix's room before the title is truncated, so the
	// scores survive a long title instead of being cut off with it.
	titleRoom := width - 2 - lipgloss.Width(suffix)
	if titleRoom < 8 {
		return job.Title
	}
	return truncateRunes(job.Title, titleRoom) + lipgloss.NewStyle().Foreground(t.Subtext).Render(suffix)
}

// Stall thresholds. These are "something is wrong" signals, not progress
// hints, so they sit well above how long the work legitimately takes:
// orchestrator.py allows 180s for a single PDF render alone, and a tailor
// action runs a whole multi-step Gemini pipeline around that, so anything
// under a few minutes would cry wolf constantly. Liveness and status are
// bounded network calls and get a much shorter leash.
const (
	stalledTailorAfter   = 6 * time.Minute
	stalledLivenessAfter = 90 * time.Second
)

// stalledHint returns a plain-language warning once an action has run
// long enough to look hung, or "" while it's still within normal time.
// The user can always press esc -- this exists so they know they should.
func (m JobsModel) stalledHint() string {
	if m.actionInProgress == "" || m.actionStartedAt.IsZero() {
		return ""
	}
	limit := stalledLivenessAfter
	if m.actionInProgress == "tailor" {
		limit = stalledTailorAfter
	}
	elapsed := time.Since(m.actionStartedAt)
	if elapsed < limit {
		return ""
	}
	return fmt.Sprintf(" -- still going after %dm, which is longer than usual; esc to cancel",
		int(elapsed.Minutes()))
}
