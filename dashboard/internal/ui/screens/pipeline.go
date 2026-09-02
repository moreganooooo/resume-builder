package screens

import (
	"fmt"
	"image/color"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

// pipelineSidebarRatio is the fraction of the width given to the sidebar.
// The mouse hit-test must split where the renderer splits; two copies of
// 0.35 can drift apart silently.
const pipelineSidebarRatio = 0.35

// PipelineClosedMsg is emitted when the pipeline screen is dismissed.
// Quit distinguishes "q" (exit the whole app) from "esc" (back to the
// screen that opened Pipeline -- always the Main Menu today).
type PipelineClosedMsg struct{ Quit bool }

// PipelineOpenReportMsg is emitted when a report should be opened in FileViewer.
type PipelineOpenReportMsg struct {
	Path   string
	Title  string
	JobURL string
}

// PipelineOpenURLMsg is emitted when a job URL should be opened in browser.
type PipelineOpenURLMsg struct {
	URL string
}

// PipelineURLOpenFailedMsg is emitted when the OS command to open a job URL
// (open/xdg-open/etc., run from main.go) fails -- e.g. no default browser
// configured in a headless/SSH session. Previously that error was silently
// discarded, leaving the user to wonder why "o" did nothing.
type PipelineURLOpenFailedMsg struct {
	Err error
}

// PipelineLoadReportMsg requests lazy loading of a report summary.
type PipelineLoadReportMsg struct {
	CareerOpsPath string
	ReportPath    string
}

// PipelineUpdateStatusMsg requests a status update for an application.
type PipelineUpdateStatusMsg struct {
	CareerOpsPath string
	App           model.CareerApplication
	NewStatus     string
}

// PipelineRefreshMsg requests a full tracker reload from disk.
type PipelineRefreshMsg struct{}

// PipelineOpenProgressMsg is emitted when the progress screen should open.
type PipelineOpenProgressMsg struct{}

// starfieldTickMsg drives continuous twinkle animation when detail pane is empty.
type starfieldTickMsg time.Time

func tickStarfield() tea.Cmd {
	return tea.Tick(time.Millisecond*60, func(t time.Time) tea.Msg {
		return starfieldTickMsg(t)
	})
}

type reportSummary struct {
	archetype string
	tldr      string
	remote    string
	comp      string
}

// Sort modes
const (
	sortScore    = "score"
	sortDate     = "date"
	sortCompany  = "company"
	sortStatus   = "status"
	sortLocation = "location"
	sortPay      = "pay"
	sortLast     = "last"
)

// Filter modes
const (
	filterAll       = "all"
	filterEvaluated = "evaluated"
	filterApplied   = "applied"
	filterInterview = "interview"
	filterSkip      = "skip"
	filterRejected  = "rejected"
	filterDiscarded = "discarded"
	filterTop       = "top"
)

type pipelineTab struct {
	filter string
	label  string
}

var pipelineTabs = []pipelineTab{
	{filterAll, "ALL"},
	{filterEvaluated, "EVALUATED"},
	{filterApplied, "APPLIED"},
	{filterInterview, "INTERVIEW"},
	{filterTop, "TOP ≥4"},
	{filterSkip, "SKIP"},
	{filterRejected, "REJECTED"},
	{filterDiscarded, "DISCARDED"},
}

var sortCycle = []string{sortScore, sortDate, sortCompany, sortStatus, sortLocation, sortPay, sortLast}

var statusOptions = []string{"Evaluated", "Applied", "Responded", "Interview", "Offer", "Rejected", "Discarded", "SKIP"}

// statusGroupOrder defines display order for grouped view.
var statusGroupOrder = []string{"interview", "offer", "responded", "applied", "evaluated", "skip", "rejected", "discarded"}

// PipelineModel implements the career pipeline dashboard screen.
type PipelineModel struct {
	apps               []model.CareerApplication
	filtered           []model.CareerApplication
	metrics            model.PipelineMetrics
	cursor             int
	scrollOffset       int
	detailScrollOffset int
	sortMode           string
	activeTab          int
	viewMode           string // "grouped" or "flat"
	width, height      int
	theme              theme.Theme
	careerOpsPath      string
	reportCache        map[string]reportSummary
	// Status picker sub-state
	statusPicker bool
	statusCursor int
	// statusConfirm/pendingStatus hold the inline confirm step between
	// picking a status and actually committing it -- see
	// renderStatusPickerOverlay's doc comment in bars.go for why.
	statusConfirm bool
	pendingStatus string
	// Search sub-state — narrows the active tab by substring on company/role/notes.
	searchInput bool   // true while the user is typing the query
	searchQuery string // committed (or in-progress) lowercased query

	// Filter parity with Jobs (jobs.go's [w]/[e]/[$]/[r] filters) -- same
	// predicates, mirrored onto CareerApplication (see model/career.go).
	// roleTrackFilter uses [t] here instead of Jobs' [r], since [r] is
	// already Pipeline's refresh key. experienceBlockerFilter uses [x]
	// here vs. Jobs' [c] (Jobs' own [x] is its archive-confirm key) --
	// a deliberate per-screen keybinding divergence, not a parity gap;
	// both screens have the same opt-in filter/keybinding/detail-pane
	// rendering.
	workplaceFilter         string
	employmentFilter        string
	payFilter               string
	roleTrackFilter         bool
	experienceBlockerFilter bool

	// notice explains why a keypress was a no-op (e.g. "o" with no saved
	// URL) instead of silently doing nothing. Cleared on the next keypress,
	// same dismiss convention as jobs.go's actionError.
	notice string

	// showHelp toggles the `?` categorized keybinding overlay (see
	// bars.go's renderHelpOverlay) over this screen's normal body.
	showHelp bool

	undoStack []StatusChangeAction

	animDone bool
}

// StatusChangeAction represents a status transition for in-place undo.
type StatusChangeAction struct {
	App        model.CareerApplication
	PrevStatus string
	NewStatus  string
}

type animationMsg struct{}

// NewPipelineModel creates a new pipeline screen.
func NewPipelineModel(t theme.Theme, apps []model.CareerApplication, metrics model.PipelineMetrics, careerOpsPath string, width, height int) PipelineModel {
	m := PipelineModel{
		apps:          apps,
		metrics:       metrics,
		sortMode:      sortScore,
		activeTab:     0,
		viewMode:      "grouped",
		width:         width,
		height:        height,
		theme:         t,
		careerOpsPath: careerOpsPath,
		reportCache:   make(map[string]reportSummary),
	}
	m.applyFilterAndSort()
	return m
}

// Init implements tea.Model.
func (m *PipelineModel) Init() tea.Cmd {
	if os.Getenv("RESUME_BUILDER_MOTION") == "reduced" {
		m.animDone = true
		return nil
	}
	if len(m.filtered) == 0 {
		return tickStarfield()
	}
	// Kick off a short fade‑in animation.
	return tea.Tick(time.Millisecond*50, func(t time.Time) tea.Msg { return animationMsg{} })
}

// Resize updates dimensions.
func (m *PipelineModel) Resize(width, height int) {
	m.width = width
	m.height = height
}

// Width returns the current width.
func (m PipelineModel) Width() int { return m.width }

// Height returns the current height.
func (m PipelineModel) Height() int { return m.height }

// CopyReportCache copies the report cache from another pipeline model.
func (m *PipelineModel) CopyReportCache(other *PipelineModel) {
	for k, v := range other.reportCache {
		m.reportCache[k] = v
	}
}

// EnrichReport caches report summary data for preview.
func (m *PipelineModel) EnrichReport(reportPath, archetype, tldr, remote, comp string) {
	m.reportCache[reportPath] = reportSummary{
		archetype: archetype,
		tldr:      tldr,
		remote:    remote,
		comp:      comp,
	}
}

// WithReloadedData rebuilds the pipeline with fresh tracker data while preserving
// the current UI state so manual refresh feels seamless.
func (m PipelineModel) WithReloadedData(apps []model.CareerApplication, metrics model.PipelineMetrics) PipelineModel {
	selectedReportPath := ""
	selectedCompany := ""
	selectedRole := ""
	if app, ok := m.CurrentApp(); ok {
		selectedReportPath = app.ReportPath
		selectedCompany = app.Company
		selectedRole = app.Role
	}

	reloaded := NewPipelineModel(m.theme, apps, metrics, m.careerOpsPath, m.width, m.height)
	reloaded.sortMode = m.sortMode
	reloaded.activeTab = m.activeTab
	reloaded.viewMode = m.viewMode
	// Preserve search state across refresh — otherwise pressing `r` silently drops a
	// committed query and the user loses their place mid-investigation.
	reloaded.searchQuery = m.searchQuery
	reloaded.searchInput = m.searchInput
	reloaded.applyFilterAndSort()
	reloaded.CopyReportCache(&m)

	for i, app := range reloaded.filtered {
		if selectedReportPath != "" && app.ReportPath == selectedReportPath {
			reloaded.cursor = i
			reloaded.adjustScroll()
			return reloaded
		}
		if selectedReportPath == "" && app.Company == selectedCompany && app.Role == selectedRole {
			reloaded.cursor = i
			reloaded.adjustScroll()
			return reloaded
		}
	}

	if len(reloaded.filtered) == 0 {
		reloaded.cursor = 0
		reloaded.scrollOffset = 0
		return reloaded
	}

	if m.cursor >= len(reloaded.filtered) {
		reloaded.cursor = len(reloaded.filtered) - 1
	} else if m.cursor > 0 {
		reloaded.cursor = m.cursor
	}
	reloaded.adjustScroll()
	return reloaded
}

// CurrentApp returns the currently selected application, if any.
func (m PipelineModel) CurrentApp() (model.CareerApplication, bool) {
	if m.cursor < 0 || m.cursor >= len(m.filtered) {
		return model.CareerApplication{}, false
	}
	return m.filtered[m.cursor], true
}

// SetNotice sets the user-facing notice/error banner message.
func (m *PipelineModel) SetNotice(n string) {
	m.notice = n
}

// Notice returns the current notice message.
func (m PipelineModel) Notice() string {
	return m.notice
}

// Update handles input for the pipeline screen.
func (m PipelineModel) Update(msg tea.Msg) (PipelineModel, tea.Cmd) {
	switch msg := msg.(type) {
	case animationMsg:
		m.animDone = true
		return m, nil
	case starfieldTickMsg:
		if len(m.filtered) == 0 && os.Getenv("RESUME_BUILDER_MOTION") != "reduced" {
			return m, tickStarfield()
		}
		return m, nil
	case PipelineURLOpenFailedMsg:
		m.notice = fmt.Sprintf("Could not open URL: %v", msg.Err)
		return m, nil
	case tea.MouseClickMsg:
		if m.showHelp {
			m.showHelp = false
			return m, nil
		}
		if m.notice != "" {
			m.notice = ""
			return m, nil
		}
		for i := range pipelineTabs {
			if zone.InBoundsClick(fmt.Sprintf("pipeline_tab_%d", i), msg) {
				m.activeTab = i
				m.applyFilterAndSort()
				m.cursor = 0
				m.scrollOffset = 0
				return m, m.loadCurrentReport()
			}
		}
		for i := range m.filtered {
			if zone.InBoundsClick(fmt.Sprintf("pipeline_row_%d", i), msg) {
				m.cursor = i
				m.adjustScroll()
				return m, m.loadCurrentReport()
			}
		}
		return m, nil

	case tea.MouseWheelMsg:
		// Hit-test against the same split the renderer uses: scrolling over
		// the detail pane must scroll the detail pane, not retarget the
		// sidebar selection.
		leftWidth := int(float64(m.width) * pipelineSidebarRatio)
		if msg.X >= leftWidth {
			// msg.Y is the row the cursor is over on screen (always >= 0),
			// not a scroll delta -- direction comes from msg.Button. See
			// jobs.go's identical fix for the same bug: msg.Y < 0 was always
			// false, so every wheel-up event fell into the scroll-down branch.
			if msg.Button == tea.MouseWheelUp {
				if m.detailScrollOffset > 0 {
					m.detailScrollOffset--
				}
			} else if msg.Button == tea.MouseWheelDown {
				m.detailScrollOffset++
				m.clampDetailScroll()
			}
			return m, nil
		}
		if len(m.filtered) > 0 {
			oldCursor := m.cursor
			if msg.Button == tea.MouseWheelUp {
				m.cursor--
				if m.cursor < 0 {
					m.cursor = 0
				}
			} else if msg.Button == tea.MouseWheelDown {
				m.cursor++
				if m.cursor >= len(m.filtered) {
					m.cursor = len(m.filtered) - 1
				}
			}
			// Only reload when the selection actually moved -- a wheel held
			// at either end would otherwise fire a report read per notch.
			if m.cursor != oldCursor {
				m.detailScrollOffset = 0
				m.adjustScroll()
				return m, m.loadCurrentReport()
			}
		}
		return m, nil

	case tea.KeyPressMsg:
		if m.showHelp {
			switch msg.String() {
			case "?", "esc", "q":
				m.showHelp = false
			}
			return m, nil
		}
		if m.statusPicker {
			return m.handleStatusPicker(msg)
		}
		if m.searchInput {
			return m.handleSearchInput(msg)
		}
		return m.handleKey(msg)
	case tea.KeyMsg:
		if kp, ok := msg.(tea.KeyPressMsg); ok {
			return m.Update(kp)
		}
		return m.Update(tea.KeyPressMsg(tea.Key{Text: msg.String()}))
	case tea.WindowSizeMsg:

		m.width = msg.Width
		m.height = msg.Height
		return m, nil
	}
	return m, nil
}

func (m PipelineModel) handleKey(msg tea.KeyPressMsg) (PipelineModel, tea.Cmd) {
	if m.notice != "" {
		m.notice = ""
		return m, nil
	}

	switch msg.String() {
	case "?":
		m.showHelp = true

	case "esc":
		// While a search is committed, Esc clears the search first (matches vim's
		// `:nohl` ergonomics) rather than leaving the screen -- a cleared filter is
		// itself the useful "undo" here. With no query, Esc backs out to the Main
		// Menu; "q" alone still quits the whole app, so this can't reopen the
		// accidental-exit risk the old no-op was guarding against.
		if m.searchQuery != "" {
			m.searchQuery = ""
			m.applyFilterAndSort()
			m.cursor = 0
			m.scrollOffset = 0
			return m, m.loadCurrentReport()
		}
		return m, func() tea.Msg { return PipelineClosedMsg{Quit: false} }

	case "q":
		return m, func() tea.Msg { return PipelineClosedMsg{Quit: true} }

	case "/":
		// Open search input. Pre-fill with the current query so refining is one keystroke away.
		m.searchInput = true
		return m, nil

	case "down", "j":
		if len(m.filtered) > 0 {
			m.cursor++
			if m.cursor >= len(m.filtered) {
				m.cursor = len(m.filtered) - 1
			}
			m.adjustScroll()
			return m, m.loadCurrentReport()
		}

	case "up", "k":
		if len(m.filtered) > 0 {
			m.cursor--
			if m.cursor < 0 {
				m.cursor = 0
			}
			m.adjustScroll()
			return m, m.loadCurrentReport()
		}

	case "s":
		// Cycle sort mode
		for i, s := range sortCycle {
			if s == m.sortMode {
				m.sortMode = sortCycle[(i+1)%len(sortCycle)]
				break
			}
		}
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "f", "right", "l":
		m.activeTab++
		if m.activeTab >= len(pipelineTabs) {
			m.activeTab = 0
		}
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "left", "h":
		m.activeTab--
		if m.activeTab < 0 {
			m.activeTab = len(pipelineTabs) - 1
		}
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "v":
		if m.viewMode == "grouped" {
			m.viewMode = "flat"
		} else {
			m.viewMode = "grouped"
		}

	case "w":
		m.workplaceFilter = nextWorkplaceFilter(m.workplaceFilter)
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "e":
		m.employmentFilter = nextEmploymentFilter(m.employmentFilter)
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "$":
		m.payFilter = nextPayFilter(m.payFilter)
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "t":
		m.roleTrackFilter = !m.roleTrackFilter
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "x":
		m.experienceBlockerFilter = !m.experienceBlockerFilter
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0

	case "enter":
		if app, ok := m.CurrentApp(); ok && app.ReportPath != "" {
			fullPath := filepath.Join(m.careerOpsPath, app.ReportPath)
			title := fmt.Sprintf("%s — %s", app.Company, app.Role)
			jobURL := app.JobURL
			return m, func() tea.Msg {
				return PipelineOpenReportMsg{Path: fullPath, Title: title, JobURL: jobURL}
			}
		}

	case "o":
		if app, ok := m.CurrentApp(); ok {
			if app.JobURL != "" {
				return m, func() tea.Msg {
					return PipelineOpenURLMsg{URL: app.JobURL}
				}
			}
			m.notice = "No job URL saved for this application"
		}

	case "p":
		return m, func() tea.Msg { return PipelineOpenProgressMsg{} }

	case "r":
		return m, func() tea.Msg { return PipelineRefreshMsg{} }

	case "c":
		if len(m.filtered) > 0 {
			m.statusPicker = true
			m.statusCursor = 0
		}

	case "u":
		if len(m.undoStack) > 0 {
			lastAction := m.undoStack[len(m.undoStack)-1]
			m.undoStack = m.undoStack[:len(m.undoStack)-1]
			m.notice = fmt.Sprintf("Reverted %s status back to %s", lastAction.App.Company, lastAction.PrevStatus)
			return m, func() tea.Msg {
				return PipelineUpdateStatusMsg{
					CareerOpsPath: m.careerOpsPath,
					App:           lastAction.App,
					NewStatus:     lastAction.PrevStatus,
				}
			}
		}
		m.notice = "Nothing to undo"

	case "g":
		if len(m.filtered) > 0 {
			m.cursor = 0
			m.scrollOffset = 0
			return m, m.loadCurrentReport()
		}

	case "G":
		if len(m.filtered) > 0 {
			m.cursor = len(m.filtered) - 1
			m.adjustScroll()
			return m, m.loadCurrentReport()
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
			return m, m.loadCurrentReport()
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
			return m, m.loadCurrentReport()
		}
	}

	return m, nil
}

// handleSearchInput consumes keys while the search input bar is open.
func (m PipelineModel) handleSearchInput(msg tea.KeyPressMsg) (PipelineModel, tea.Cmd) {
	switch msg.String() {
	case "esc":
		m.searchInput = false
		m.searchQuery = ""
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0
		return m, m.loadCurrentReport()

	case "enter":
		m.searchInput = false
		return m, m.loadCurrentReport()

	case "backspace":
		if len(m.searchQuery) > 0 {
			runes := []rune(m.searchQuery)
			m.searchQuery = string(runes[:len(runes)-1])
			m.applyFilterAndSort()
			m.cursor = 0
			m.scrollOffset = 0
		}
		return m, nil

	case "ctrl+u":
		m.searchQuery = ""
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0
		return m, nil
	}

	if msg.Text != "" {
		m.searchQuery += strings.ToLower(msg.Text)
		m.applyFilterAndSort()
		m.cursor = 0
		m.scrollOffset = 0
		return m, nil
	}
	return m, nil
}

// handleStatusPicker handles input while the status picker overlay is
// open. When m.statusConfirm is set, the user has already picked a status
// and this only accepts the inline confirm/cancel keys -- see
// renderStatusPickerOverlay's doc comment in bars.go for why a status
// change doesn't commit on the first Enter.
func (m PipelineModel) handleStatusPicker(msg tea.KeyPressMsg) (PipelineModel, tea.Cmd) {
	if m.statusConfirm {
		switch msg.String() {
		case "enter", "y", "Y":
			m.statusPicker = false
			m.statusConfirm = false
			if app, ok := m.CurrentApp(); ok {
				newStatus := m.pendingStatus
				m.pendingStatus = ""
				m.undoStack = append(m.undoStack, StatusChangeAction{
					App:        app,
					PrevStatus: app.Status,
					NewStatus:  newStatus,
				})
				return m, func() tea.Msg {
					return PipelineUpdateStatusMsg{
						CareerOpsPath: m.careerOpsPath,
						App:           app,
						NewStatus:     newStatus,
					}
				}
			}

		case "esc", "n", "N":
			// Back out to the picker itself, not all the way out of it.
			m.statusConfirm = false
			m.pendingStatus = ""
		}
		return m, nil
	}

	switch msg.String() {
	case "esc", "q":
		m.statusPicker = false
		return m, nil

	case "down", "j":
		m.statusCursor++
		if m.statusCursor >= len(statusOptions) {
			m.statusCursor = len(statusOptions) - 1
		}

	case "up", "k":
		m.statusCursor--
		if m.statusCursor < 0 {
			m.statusCursor = 0
		}

	case "enter":
		if _, ok := m.CurrentApp(); ok {
			m.pendingStatus = statusOptions[m.statusCursor]
			m.statusConfirm = true
		}
	}
	return m, nil
}

func (m PipelineModel) loadCurrentReport() tea.Cmd {
	app, ok := m.CurrentApp()
	if !ok || app.ReportPath == "" {
		return nil
	}
	if _, cached := m.reportCache[app.ReportPath]; cached {
		return nil
	}
	path := m.careerOpsPath
	report := app.ReportPath
	return func() tea.Msg {
		return PipelineLoadReportMsg{CareerOpsPath: path, ReportPath: report}
	}
}

func matchesSearch(app model.CareerApplication, query string) bool {
	q := data.NormalizeUnicodeSearch(query)
	if q == "" {
		return true
	}
	if strings.Contains(data.NormalizeUnicodeSearch(app.Company), q) {
		return true
	}
	if strings.Contains(data.NormalizeUnicodeSearch(app.Role), q) {
		return true
	}
	if strings.Contains(data.NormalizeUnicodeSearch(app.Notes), q) {
		return true
	}
	return false
}

func (m *PipelineModel) applyFilterAndSort() {
	var filtered []model.CareerApplication

	currentFilter := pipelineTabs[m.activeTab].filter
	for _, app := range m.apps {
		if !matchesSearch(app, m.searchQuery) {
			continue
		}
		if !matchesPipelineFilters(app, *m) {
			continue
		}
		norm := data.NormalizeStatus(app.Status)
		switch currentFilter {
		case filterAll:
			filtered = append(filtered, app)
		case filterTop:
			if app.Score >= 4.0 && norm != "skip" {
				filtered = append(filtered, app)
			}
		default:
			if norm == currentFilter {
				filtered = append(filtered, app)
			}
		}
	}

	less := m.sortLess()
	sort.SliceStable(filtered, func(i, j int) bool {
		return less(filtered[i], filtered[j])
	})

	if m.viewMode == "grouped" {
		sort.SliceStable(filtered, func(i, j int) bool {
			pi := data.StatusPriority(filtered[i].Status)
			pj := data.StatusPriority(filtered[j].Status)
			if pi != pj {
				return pi < pj
			}
			return less(filtered[i], filtered[j])
		})
	}

	m.filtered = filtered
}

// matchesPipelineFilters applies the [w]/[e]/[$]/[t]/[x] opt-in view
// filters, same predicates as jobs.go's applyFilter. Empty/false means no
// restriction, same "opt-in, never a permanent gate" convention as Jobs.
func matchesPipelineFilters(app model.CareerApplication, m PipelineModel) bool {
	if m.workplaceFilter != "" && app.Workplace != m.workplaceFilter {
		return false
	}
	if m.employmentFilter != "" && !app.HasEmploymentType(m.employmentFilter) {
		return false
	}
	if m.payFilter == "stated" && !app.HasStatedPay {
		return false
	}
	if m.payFilter == "unstated" && app.HasStatedPay {
		return false
	}
	if m.roleTrackFilter && !app.IsManagerTrack() {
		return false
	}
	if m.experienceBlockerFilter && len(app.ExperienceBlockers) == 0 {
		return false
	}
	return true
}

func (m PipelineModel) sortLess() func(a, b model.CareerApplication) bool {
	switch m.sortMode {
	case sortDate:
		return func(a, b model.CareerApplication) bool { return a.Date > b.Date }
	case sortCompany:
		return func(a, b model.CareerApplication) bool {
			return strings.ToLower(a.Company) < strings.ToLower(b.Company)
		}
	case sortStatus:
		return func(a, b model.CareerApplication) bool {
			return data.StatusPriority(a.Status) < data.StatusPriority(b.Status)
		}
	case sortLocation:
		return func(a, b model.CareerApplication) bool {
			ra, rb := workModeRank(a.WorkMode), workModeRank(b.WorkMode)
			if ra != rb {
				return ra < rb
			}
			return a.Location < b.Location
		}
	case sortPay:
		return func(a, b model.CareerApplication) bool { return a.PayMax > b.PayMax }
	case sortLast:
		return func(a, b model.CareerApplication) bool { return a.LastContact > b.LastContact }
	default:
		return func(a, b model.CareerApplication) bool { return a.Score > b.Score }
	}
}

func workModeRank(mode string) int {
	switch mode {
	case "Remote":
		return 0
	case "Hybrid":
		return 1
	case "Full":
		return 2
	default:
		return 3
	}
}

// chromeRowsFixed budgets the fixed rows around the split pane: header,
// tabs (2 lines), metrics, sort bar, help, plus the search bar when one is
// showing. It previously didn't budget for renderNotice's own row either
// -- same overflow-by-one this function's jobs.go counterpart
// (chromeAvailHeight) had, whenever a notice is up (e.g. "o" with no saved
// URL) the split pane's declared height stayed put while an extra line got
// inserted above it, pushing the help bar one row past the terminal.
func (m PipelineModel) chromeRowsFixed() int {
	rows := 5
	if m.searchInput || m.searchQuery != "" {
		rows++
	}
	if m.notice != "" {
		rows++
	}
	return rows
}

const previewBudgetApprox = 6

func (m *PipelineModel) adjustScroll() {
	availHeight := m.height - m.chromeRowsFixed() - previewBudgetApprox
	if availHeight < 5 {
		availHeight = 5
	}
	line := m.cursorLineEstimate()
	margin := 3

	if line >= m.scrollOffset+availHeight-margin {
		m.scrollOffset = line - availHeight + margin + 1
	}
	if line < m.scrollOffset+margin {
		m.scrollOffset = line - margin
	}
	if m.scrollOffset < 0 {
		m.scrollOffset = 0
	}
}

func (m PipelineModel) cursorLineEstimate() int {
	if m.viewMode != "grouped" {
		return m.cursor
	}
	line := 0
	prevStatus := ""
	for i, app := range m.filtered {
		norm := data.NormalizeStatus(app.Status)
		if norm != prevStatus {
			line++
			prevStatus = norm
		}
		if i == m.cursor {
			return line
		}
		line++
	}
	return line
}

// View renders the pipeline screen.
var pipelineHelpCategories = []helpCategory{
	{"Navigation", []helpBinding{
		{"↑ ↓ / j k", "Move selection"},
		{"g / G", "Jump to top / bottom"},
		{"PgUp / PgDn", "Page up / down"},
		{"← → / h l", "Cycle tabs"},
	}},
	{"Actions", []helpBinding{
		{"Enter", "Open report"},
		{"o", "Open job URL in browser"},
		{"c", "Change application status"},
		{"r", "Refresh from disk"},
	}},
	{"View", []helpBinding{
		{"/", "Search company/role/notes"},
		{"s", "Cycle sort mode"},
		{"v", "Toggle grouped/flat view"},
		{"p", "Open Progress screen"},
	}},
	{"Filters", []helpBinding{
		{"w", "Cycle workplace mode"},
		{"e", "Cycle employment type"},
		{"$", "Cycle pay-disclosure mode"},
		{"t", "Toggle manager-track only"},
		{"x", "Toggle years/degree blocker only"},
	}},
	{"Exit", []helpBinding{
		{"Esc", "Clear search, or back to Main Menu"},
		{"q", "Quit dashboard"},
	}},
}

func (m PipelineModel) View() string {
	header := m.renderHeader()
	tabs := m.renderTabs()
	metricsBar := m.renderMetrics()
	sortBar := m.renderSortBar()
	searchBar := m.renderSearchBar()
	help := m.renderHelp()

	content := lipgloss.JoinVertical(lipgloss.Left, header, tabs, metricsBar, sortBar)
	if searchBar != "" {
		content = lipgloss.JoinVertical(lipgloss.Left, content, searchBar)
	}
	if notice := m.renderNotice(); notice != "" {
		content = lipgloss.JoinVertical(lipgloss.Left, content, notice)
	}

	leftWidth := int(float64(m.width) * pipelineSidebarRatio)
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
		// Pipeline bindings, NOT the Jobs ones: here "s" cycles the sort
		// mode and "b" is unbound. See renderEmptyDetailPane.
		rightPane = renderEmptyDetailPane(m.theme, rightWidth, availHeight, []string{
			"To change which applications show, press [ f ]",
			"To search by company or role, press [ / ]",
			"",
			"To reload from disk, press [ r ]",
		})
	}

	splitView := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)
	full := lipgloss.JoinVertical(lipgloss.Left, content, splitView, help)

	if !m.animDone {
		full = lipgloss.NewStyle().Foreground(m.theme.Subtext).Render(full)
	}

	if m.showHelp {
		helpContent := renderHelpOverlay(m.theme, "Pipeline", pipelineHelpCategories, int(float64(m.width)*0.75), m.height-4)
		return renderModalOverlay(m.theme, full, helpContent, m.width, m.height)
	}

	return full
}

func (m PipelineModel) renderSidebarList(width, height int) string {
	if len(m.filtered) == 0 {
		emptyStyle := lipgloss.NewStyle().
			Foreground(m.theme.Subtext).
			Width(width-2).
			Height(height-2).
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
		line := renderSidebarRow(m.theme, app.Score, app.Company, app.Role, width-4, selected)
		lines = append(lines, zone.Mark(fmt.Sprintf("pipeline_row_%d", i), line))
	}

	body := strings.Join(lines, "\n")
	bodyLines := strings.Split(body, "\n")

	if m.scrollOffset > 0 && m.scrollOffset < len(bodyLines) {
		bodyLines = bodyLines[m.scrollOffset:]
	}

	// Reserve room for the status picker's own lines (a "Change status:"
	// header plus one row per option) before truncating -- otherwise the
	// picker gets appended on top of content already filling the box to
	// height-2, so the bordered box (a fixed Height(), which pads short
	// content but never truncates long content) grows past its declared
	// size and pushes the rest of the screen's layout down on short
	// terminals.
	maxLines := height - 2
	if m.statusPicker {
		maxLines -= len(statusOptions) + 1
		if maxLines < 0 {
			maxLines = 0
		}
	}
	if len(bodyLines) > maxLines {
		bodyLines = bodyLines[:maxLines]
	}

	content := strings.Join(bodyLines, "\n")

	if m.statusPicker {
		confirmLabel := ""
		if m.statusConfirm {
			confirmLabel = fmt.Sprintf("Change status to %s?", m.pendingStatus)
		}
		content = renderStatusPickerOverlay(m.theme, content, width-4, "Change status:", statusOptions, m.statusCursor, confirmLabel)
	}

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Blue).
		Width(width-2).
		Height(height-2).
		Padding(0, 1)

	return borderStyle.Render(content)
}

// pipelineDetailContentLines builds the detail pane's content before any
// scroll offset is applied, so clampDetailScroll can measure what it is
// about to scroll. See JobsModel.clampDetailScroll for why the renderer
// cannot do the clamping itself.
func (m PipelineModel) pipelineDetailContentLines(app model.CareerApplication, width, height int) []string {
	styles := newDetailPaneStyles(m.theme, width, height)

	var content []string

	// HEADER: Company & Role
	content = append(content, styles.Title.Render(app.Company))
	content = append(content, styles.Value.Render(app.Role))
	content = append(content, "")

	// PROOF: Score, Status, Date
	score := scoreStyle(m.theme, app.Score)
	norm := data.NormalizeStatus(app.Status)
	statusColor := m.statusColorMap()[norm]

	content = append(content, styles.Subtext.Render("Interview Probability: ")+score.Render(scoreIcon(m.theme, app.Score)+" "+fmt.Sprintf("%.1f", app.Score)))
	statusPill := lipgloss.NewStyle().
		Background(statusColor).
		Foreground(m.theme.Base).
		Padding(0, 1).
		Bold(true).
		Render(strings.ToUpper(statusLabel(norm)))
	content = append(content, styles.Subtext.Render("Status: ")+statusPill)

	dateStr := app.Date
	if dateStr == "" {
		dateStr = "Unknown"
	}
	content = append(content, styles.Subtext.Render("Date Scanned/Posted: ")+styles.Value.Render(dateStr))
	// formatTimeAgo/LastContact power sortLast (the "L" sort mode) but were
	// never actually surfaced anywhere -- the sort existed with nothing to
	// show what it was sorting by.
	if app.LastContact != "" {
		content = append(content, styles.Subtext.Render("Last Contact: ")+styles.Value.Render(formatTimeAgo(app.LastContact)))
	}
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
		content = append(content, styles.Subtext.Render("Details: ")+styles.Value.Render(facts))
		content = append(content, "")
	}

	// FILTER-PARITY FACTS (see model/career.go) -- same fields the Jobs
	// screen surfaces, shown here read-only regardless of whether a
	// filter narrowed to them.
	if label := app.EmploymentLabel(); label != "" {
		content = append(content, styles.Subtext.Render("Employment: ")+styles.Value.Render(label))
	}
	if app.PayText != "" {
		content = append(content, styles.Subtext.Render("Pay: ")+styles.Value.Render(app.PayText))
	}
	if app.HoursText != "" {
		content = append(content, styles.Subtext.Render("Hours: ")+styles.Value.Render(app.HoursText))
	}
	if app.HasStressSignals() {
		content = append(content, styles.Subtext.Render("Stress signals: ")+styles.Value.Render(strings.Join(app.StressSignals, ", ")))
	}
	if app.HasCapabilityGaps() {
		content = append(content, styles.Subtext.Render("Capability gaps: ")+styles.Value.Render(strings.Join(app.CapabilityGaps, "; ")))
	}
	if app.IsManagerTrack() {
		content = append(content, styles.Subtext.Render("Role track: ")+styles.Value.Render("manager"))
	}
	if len(app.ExperienceBlockers) > 0 {
		texts := make([]string, len(app.ExperienceBlockers))
		for i, b := range app.ExperienceBlockers {
			texts[i] = b.Text
		}
		content = append(content, styles.Subtext.Render("Experience blockers: ")+styles.Value.Render(strings.Join(texts, "; ")))
	}
	content = append(content, "")

	// MATCHED / MISSING SKILLS & REASONING (from Report Summary if available)
	if summary, ok := m.reportCache[app.ReportPath]; ok {
		if summary.tldr != "" {
			content = append(content, styles.Title.Render("Analysis"))
			content = append(content, styles.Value.Render(truncateRunes(summary.tldr, width-6)))
			content = append(content, "")
		}
		if summary.archetype != "" {
			content = append(content, styles.Subtext.Render("Archetype: ")+styles.Value.Render(summary.archetype))
		}
	} else if app.Notes != "" {
		content = append(content, styles.Title.Render("Notes"))
		content = append(content, styles.Subtext.Render(truncateRunes(app.Notes, width-6)))
	}

	return content
}

func (m PipelineModel) renderJobDetailPane(app model.CareerApplication, width, height int) string {
	styles := newDetailPaneStyles(m.theme, width, height)
	content := m.pipelineDetailContentLines(app, width, height)

	// Clamp rather than ignore an over-scrolled offset: slicing only while
	// offset < len(lines) silently rendered from the TOP once the offset
	// ran past the end, so scrolling down far enough snapped back to the
	// start of the pane.
	lines := content
	if m.detailScrollOffset > 0 {
		start := m.detailScrollOffset
		if maxScroll := detailMaxScrollFor(len(lines), height); start > maxScroll {
			start = maxScroll
		}
		if start > 0 && start < len(lines) {
			lines = lines[start:]
		}
	}
	joined := strings.Join(lines, "\n")
	return styles.Border.Render(joined)
}

// clampDetailScroll pins detailScrollOffset to the selected application's
// real content length.
func (m *PipelineModel) clampDetailScroll() {
	if m.detailScrollOffset <= 0 {
		m.detailScrollOffset = 0
		return
	}
	app, ok := m.CurrentApp()
	if !ok {
		m.detailScrollOffset = 0
		return
	}
	leftWidth := int(float64(m.width) * pipelineSidebarRatio)
	height := m.height - m.chromeRowsFixed()
	if height < 5 {
		height = 5
	}
	lines := m.pipelineDetailContentLines(app, m.width-leftWidth, height)
	if maxScroll := detailMaxScrollFor(len(lines), height); m.detailScrollOffset > maxScroll {
		m.detailScrollOffset = maxScroll
	}
}

// renderSearchBar returns an empty string when there is no active or in-progress
// search; otherwise it renders a vim-style status line showing the query and the
// match count. While in input mode, a trailing cursor is appended.
func (m PipelineModel) renderSearchBar() string {
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

	tabFiltered := m.countForFilter(pipelineTabs[m.activeTab].filter)
	matchInfo := hintStyle.Render(fmt.Sprintf("  %d/%d matching", len(m.filtered), tabFiltered))

	hint := ""
	if m.searchInput {
		hint = hintStyle.Render("   Enter: keep   Esc: cancel   Ctrl+U: clear")
	} else {
		hint = hintStyle.Render("   Esc: clear   /: edit")
	}

	return style.Render(prompt + " " + display + matchInfo + hint)
}

// renderNotice explains why the last keypress was a no-op (see the "o" case
// in handleKey), rather than leaving the user to wonder whether it
// registered at all. Yellow/no-prefix, distinct from renderActionStatus's
// "Error:" framing in jobs.go -- this isn't a failure, it's an unavailable
// action.
func (m PipelineModel) renderNotice() string {
	if m.notice == "" {
		return ""
	}
	style := lipgloss.NewStyle().
		Foreground(m.theme.Yellow).
		Width(m.width).
		Padding(0, 2)
	return style.Render(m.notice + " (press any key to dismiss)")
}

func (m PipelineModel) renderHeader() string {
	style := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.theme.Text).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)

	right := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)
	avg := fmt.Sprintf("%.1f", m.metrics.AvgScore)
	info := right.Render(fmt.Sprintf("%d offers | Avg %s/5", m.metrics.Total, avg))

	title := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Blue).Background(m.theme.Surface).Render(m.theme.Icons.Pipeline+"  ") +
		lipgloss.NewStyle().Bold(true).Background(m.theme.Surface).Render(theme.RenderColorGradient("✦ CAREER PIPELINE ✧", m.theme.Blue, m.theme.Mauve))
	title, info, gap := fitBar(title, info, m.width, 4, m.theme.Surface)

	return style.Render(title + gap + info)
}

func (m PipelineModel) renderTabs() string {
	var tabs []string
	var underParts []string

	for i, tab := range pipelineTabs {
		// Count items for this tab
		count := m.countForFilter(tab.filter)
		label := fmt.Sprintf(" %s (%d) ", tab.label, count)

		if i == m.activeTab {
			style := lipgloss.NewStyle().
				Bold(true).
				Foreground(m.theme.Blue).
				Padding(0, 0)
			tabs = append(tabs, zone.Mark(fmt.Sprintf("pipeline_tab_%d", i), style.Render(label)))
			underParts = append(underParts, strings.Repeat("━", lipgloss.Width(label)))
		} else {
			style := lipgloss.NewStyle().
				Foreground(m.theme.Subtext).
				Padding(0, 0)
			tabs = append(tabs, zone.Mark(fmt.Sprintf("pipeline_tab_%d", i), style.Render(label)))
			underParts = append(underParts, strings.Repeat("─", lipgloss.Width(label)))
		}
	}

	row := lipgloss.JoinHorizontal(lipgloss.Top, tabs...)
	underline := lipgloss.NewStyle().Foreground(m.theme.Overlay).Render(strings.Join(underParts, ""))

	// All 8 tabs joined at full label width routinely exceed a narrow
	// terminal -- unlike the header/help/search bars (see fitBar in
	// bars.go), this row previously had no width awareness at all, so it
	// would overflow rather than degrade. ansi.Truncate is ANSI-escape-
	// aware, same as fitBar's own use of it, so it can safely shorten the
	// already-styled/rendered row and underline without corrupting color
	// codes mid-escape-sequence.
	//
	// ansi.Truncate's own "…" tail already signals "a label got cut", but
	// that reads the same whether one character or five whole tabs are
	// hidden -- cycle keys (←→/hl, see renderHelp) still reach every one of
	// the 8 tabs regardless of what's visible, so a narrow terminal needs
	// an explicit "more tabs exist" affordance, not just an ambiguous
	// ellipsis. moreMarker gets its own reserved room instead of being
	// swallowed by ansi.Truncate's tail, and only appears when the tab bar
	// actually overflows.
	if lipgloss.Width(row) > m.width {
		moreMarker := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Peach).Render(" ›more")
		markerWidth := lipgloss.Width(moreMarker)
		budget := m.width - markerWidth
		if budget < 0 {
			budget = 0
		}
		row = ansi.Truncate(row, budget, "…") + moreMarker
		if lipgloss.Width(underline) > budget {
			underline = ansi.Truncate(underline, budget, "")
		}
		underline += strings.Repeat(" ", markerWidth)
	}
	if lipgloss.Width(underline) > m.width {
		underline = ansi.Truncate(underline, m.width, "")
	}

	padStyle := theme.PadVertical(lipgloss.NewStyle())
	return padStyle.Render(row) + "\n" + padStyle.Render(underline)
}

func (m PipelineModel) countForFilter(filter string) int {
	count := 0
	for _, app := range m.apps {
		norm := data.NormalizeStatus(app.Status)
		switch filter {
		case filterAll:
			count++
		case filterTop:
			if app.Score >= 4.0 && norm != "skip" {
				count++
			}
		default:
			if norm == filter {
				count++
			}
		}
	}
	return count
}

func (m PipelineModel) renderMetrics() string {
	style := lipgloss.NewStyle().
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)

	var parts []string
	statusColors := m.statusColorMap()

	for _, status := range statusGroupOrder {
		count, ok := m.metrics.ByStatus[status]
		if !ok || count == 0 {
			continue
		}
		color := statusColors[status]
		s := lipgloss.NewStyle().Foreground(color)
		parts = append(parts, s.Render(fmt.Sprintf("%s:%d", statusLabel(status), count)))
	}

	return style.Render(strings.Join(parts, "  "))
}

func (m PipelineModel) renderSortBar() string {
	style := lipgloss.NewStyle().Foreground(m.theme.Subtext).
		Width(m.width).
		Padding(0, 2)

	sortLabel := fmt.Sprintf("[Sort: %s]", m.sortMode)
	viewLabel := fmt.Sprintf("[View: %s]", m.viewMode)
	count := fmt.Sprintf("%d shown", len(m.filtered))

	parts := []string{sortLabel, viewLabel}
	if m.workplaceFilter != "" {
		parts = append(parts, workplaceFilterLabel(m.workplaceFilter))
	}
	if m.employmentFilter != "" {
		parts = append(parts, employmentFilterLabel(m.employmentFilter))
	}
	if m.payFilter != "" {
		parts = append(parts, payFilterLabel(m.payFilter))
	}
	if m.roleTrackFilter {
		parts = append(parts, "[manager roles]")
	}
	if m.experienceBlockerFilter {
		parts = append(parts, "[years/degree blocker]")
	}
	parts = append(parts, count)

	return style.Render(strings.Join(parts, "  "))
}

func (m PipelineModel) renderHelp() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Blue).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Text).Background(m.theme.Surface)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface)

	if m.statusPicker {
		if m.statusConfirm {
			return style.Render(
				keyStyle.Render("Enter/y") + descStyle.Render(" confirm  ") +
					keyStyle.Render("Esc/n") + descStyle.Render(" cancel"))
		}
		return style.Render(
			keyStyle.Render("↑↓/jk") + descStyle.Render(" navigate  ") +
				keyStyle.Render("Enter") + descStyle.Render(" select  ") +
				keyStyle.Render("Esc") + descStyle.Render(" cancel"))
	}

	if m.searchInput {
		style = style.Foreground(m.theme.Subtext)
		keyStyle = keyStyle.Foreground(m.theme.Subtext).Bold(false)
		descStyle = descStyle.Foreground(m.theme.Subtext)
		return style.Render(
			keyStyle.Render("type") + descStyle.Render(" filter live  ") +
				keyStyle.Render("Enter") + descStyle.Render(" keep  ") +
				keyStyle.Render("Ctrl+U") + descStyle.Render(" clear  ") +
				keyStyle.Render("Esc") + descStyle.Render(" cancel"))
	}

	// Subtext, not Overlay -- see statusColorMap's own comment below for the
	// same 1.4-2.3:1 measurement; Overlay is the border/divider token, not
	// a readable-text one.
	brand := lipgloss.NewStyle().Foreground(m.theme.Subtext).Background(m.theme.Surface).Render("resume-builder dashboard")

	keys := keyStyle.Render("↑↓/jk") + descStyle.Render(" nav  ") +
		keyStyle.Render("g/G") + descStyle.Render(" top/bot  ") +
		keyStyle.Render("PgUp/Dn") + descStyle.Render(" page  ") +
		keyStyle.Render("←→/hl") + descStyle.Render(" tabs  ") +
		keyStyle.Render("/") + descStyle.Render(" search  ") +
		keyStyle.Render("s") + descStyle.Render(" sort  ") +
		keyStyle.Render("r") + descStyle.Render(" refresh  ") +
		keyStyle.Render("Enter") + descStyle.Render(" report  ") +
		keyStyle.Render("o") + descStyle.Render(" url  ") +
		keyStyle.Render("c") + descStyle.Render(" change  ") +
		keyStyle.Render("v") + descStyle.Render(" view  ") +
		keyStyle.Render("p") + descStyle.Render(" progress  ") +
		keyStyle.Render("w/e/$/t/x") + descStyle.Render(" filter  ") +
		keyStyle.Render("?") + descStyle.Render(" help  ") +
		keyStyle.Render("Esc") + descStyle.Render(" back  ") +
		keyStyle.Render("q") + descStyle.Render(" quit")

	keys, brand, gap := fitBar(keys, brand, m.width, 2, m.theme.Surface)

	return style.Render(keys + gap + brand)
}

// -- Helpers --

// statusColorMap gives each pipeline status a distinct color so the metrics
// bar and detail pane carry meaning at a glance, not just a label. Closed-out
// statuses (rejected/discarded) get the theme's own muted Subtext tone --
// previously all three of responded/rejected/discarded shared theme.Blue,
// so a rejected application read identically to one that had just gotten a
// response, undercutting the whole point of a color-coded pipeline. Overlay
// (the border/divider token) was the first instinct for "muted" but measures
// as low as 1.4:1 against the metrics bar's Surface background -- Subtext is
// the token actually designed to be read as dimmed body text (4.7-7.4:1
// across all three themes' Surface/Base pairs).
func (m PipelineModel) statusColorMap() map[string]color.Color {
	return map[string]color.Color{
		"interview": m.theme.Green,
		"offer":     m.theme.Green,
		"applied":   m.theme.Sky,
		"responded": m.theme.Blue,
		"evaluated": m.theme.Text,
		"skip":      m.theme.Red,
		"rejected":  m.theme.Subtext,
		"discarded": m.theme.Subtext,
	}
}

func (m PipelineModel) countByNormStatus(status string) int {
	count := 0
	for _, app := range m.filtered {
		if data.NormalizeStatus(app.Status) == status {
			count++
		}
	}
	return count
}

// formatTimeAgo renders an ISO date as a relative duration: hours while the
// contact is less than a day old ("5h ago"), days otherwise ("3d ago").
// Tracker dates are day-granular, so hours count from local midnight of that day.
func formatTimeAgo(dateStr string) string {
	t, err := time.ParseInLocation("2006-01-02", dateStr, time.Local)
	if err != nil {
		return dateStr // not a date — show it untouched rather than lie
	}
	d := time.Since(t)
	if d < 0 {
		d = 0
	}
	hours := int(d.Hours())
	if hours < 24 {
		return fmt.Sprintf("%dh ago", hours)
	}
	return fmt.Sprintf("%dd ago", hours/24)
}

// truncateRunes truncates a string to at most maxRunes runes, appending "..." if truncated.
// maxRunes is floored at 0 -- callers derive it from terminal-width arithmetic
// (e.g. paneWidth - 6) that goes negative on a sufficiently narrow terminal,
// and runes[:maxRunes] panics on a negative index.
func truncateRunes(s string, maxRunes int) string {
	if maxRunes < 0 {
		maxRunes = 0
	}
	runes := []rune(s)
	if len(runes) <= maxRunes {
		return s
	}
	if maxRunes <= 3 {
		return string(runes[:maxRunes])
	}
	return string(runes[:maxRunes-3]) + "..."
}

func statusLabel(norm string) string {
	switch norm {
	case "interview":
		return "Interview"
	case "offer":
		return "Offer"
	case "responded":
		return "Responded"
	case "applied":
		return "Applied"
	case "evaluated":
		return "Evaluated"
	case "skip":
		return "Skip"
	case "rejected":
		return "Rejected"
	case "discarded":
		return "Discarded"
	default:
		return norm
	}
}
