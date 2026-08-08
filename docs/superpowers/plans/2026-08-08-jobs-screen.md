# Jobs Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Go dashboard a new, additive "Jobs" screen that shows real JD evaluation data (composite/fit/interview-odds/practical-pursue scores, recommendation, reasoning, liveness, application status) in a split-pane list+detail layout, fed by a Python-side JSON export.

**Architecture:** `scripts/dashboard.py` writes a JSON export (via `picker.list_all_evaluated_jds()`, unchanged) to a temp file and passes its path to the Go binary via a new `-jobs-path` flag. Go gets a new `internal/model.JobRow` type, an `internal/data.LoadJobs()` loader, and a new `internal/ui/screens.JobsModel` split-pane screen — structurally mirroring the existing `PipelineModel` (`pipeline.go:678-696`'s split-pane layout) but scoped to list+detail+single-key-filter, no tabs/sort-cycle/search.

**Tech Stack:** Go 1.24 (`bubbletea`, `lipgloss`, already dependencies), Python 3.10+ (`json`, `tempfile`, stdlib `unittest`).

## Global Constraints

- `go run` only — never `go build` into a committed binary (existing project rule).
- This plan is read-only: no action triggers (Liveness Check, Tailor Resume, Update Status) get wired up here — that's a separate, later spec.
- The Jobs screen is additive. `PipelineModel`/`applications.md` are not modified.
- No feature parity with `pipeline.go` (1471 lines: 8-tab filter bar, 7-mode sort, live search, grouped view). This plan's filter is a single `f` key cycling All → Pending → Completed → All.
- Subscore groups render with real JSON keys (e.g. `functional_alignment: 5`), not `cli_art._FIT_DIMENSION_GROUPS`'s friendly per-dimension labels (`"Functional"`, `"North Star"`, ...) — porting that label map is deferred polish, not required to prove the pattern. The three *group*-level labels ("Fit", "Interview odds", "Practical pursue") do match `cli_art._FIT_DIMENSION_GROUPS` for visual consistency, per the spec.

---

### Task 1: Go model types + JSON loader

**Files:**
- Create: `dashboard/internal/model/job.go`
- Create: `dashboard/internal/data/jobs.go`
- Test: `dashboard/internal/data/jobs_test.go`

**Interfaces:**
- Produces: `model.JobRow`, `model.Evaluation`, `model.Liveness`, `model.Application` (JSON-decodable structs); `data.LoadJobs(path string) ([]model.JobRow, error)` — consumed by Task 5's `main.go`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/internal/data/jobs_test.go`:

```go
package data

import (
	"os"
	"path/filepath"
	"testing"
)

func writeTempJobsFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "jobs.json")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}
	return path
}

func TestLoadJobs_ValidFile(t *testing.T) {
	content := `[
		{
			"path": "jds/morgan/a.json",
			"status": "Pending",
			"title": "Marketing Lead",
			"company": "Acme",
			"evaluation": {
				"composite_score": 4.66,
				"fit_score": 4.85,
				"recommendation": "Strong pursue",
				"why": "Great fit.",
				"hard_blockers": [],
				"fit_subscores": {"functional_alignment": 5},
				"posting_age_days": 2,
				"evaluated_at": "2026-07-27T03:13:55"
			},
			"liveness": {"result": "active", "reason": "visible apply control detected", "checked_at": "2026-08-07T21:44:03"},
			"application": null
		}
	]`
	path := writeTempJobsFile(t, content)

	rows, err := LoadJobs(path)
	if err != nil {
		t.Fatalf("LoadJobs failed: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("expected 1 row, got %d", len(rows))
	}
	row := rows[0]
	if row.Company != "Acme" || row.Status != "Pending" {
		t.Fatalf("unexpected row: %+v", row)
	}
	if row.Evaluation.CompositeScore != 4.66 {
		t.Fatalf("expected composite_score 4.66, got %v", row.Evaluation.CompositeScore)
	}
	if row.Evaluation.FitSubscores["functional_alignment"] != 5 {
		t.Fatalf("expected fit_subscores.functional_alignment 5, got %+v", row.Evaluation.FitSubscores)
	}
	if row.Liveness == nil || row.Liveness.Result != "active" {
		t.Fatalf("expected liveness.result 'active', got %+v", row.Liveness)
	}
	if row.Application != nil {
		t.Fatalf("expected nil application, got %+v", row.Application)
	}
}

func TestLoadJobs_MalformedJSON(t *testing.T) {
	path := writeTempJobsFile(t, "not json")
	if _, err := LoadJobs(path); err == nil {
		t.Fatal("expected an error for malformed JSON, got nil")
	}
}

func TestLoadJobs_MissingFile(t *testing.T) {
	if _, err := LoadJobs(filepath.Join(t.TempDir(), "does-not-exist.json")); err == nil {
		t.Fatal("expected an error for a missing file, got nil")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && go test ./internal/data/... -run TestLoadJobs -v`
Expected: FAIL to compile — `undefined: LoadJobs` (and `model.JobRow` etc. don't exist yet, though this test file only references `LoadJobs` directly since it's in package `data`).

- [ ] **Step 3: Write the implementation**

Create `dashboard/internal/model/job.go`:

```go
package model

// JobRow is one JD with a persisted evaluation, as exported by
// scripts/dashboard.py's JSON bridge (picker.list_all_evaluated_jds()).
type JobRow struct {
	Path        string       `json:"path"`
	Status      string       `json:"status"` // "Pending" or "Completed"
	Title       string       `json:"title"`
	Company     string       `json:"company"`
	Evaluation  Evaluation   `json:"evaluation"`
	Liveness    *Liveness    `json:"liveness"`
	Application *Application `json:"application"`
}

// Evaluation mirrors the _evaluation key persisted by
// scripts/jd_manager.py's save_evaluation().
type Evaluation struct {
	CompositeScore           float64        `json:"composite_score"`
	FitScore                 float64        `json:"fit_score"`
	InterviewOddsScore       float64        `json:"interview_odds_score"`
	PracticalPursueScore     float64        `json:"practical_pursue_score"`
	Recommendation           string         `json:"recommendation"`
	Why                      string         `json:"why"`
	RecruiterRead            string         `json:"recruiter_read"`
	HardBlockers             []string       `json:"hard_blockers"`
	PostingLegitimacy        string         `json:"posting_legitimacy"`
	PostingLegitimacyNotes   string         `json:"posting_legitimacy_notes"`
	Archetype                string         `json:"archetype"`
	FitSubscores             map[string]int `json:"fit_subscores"`
	InterviewOddsSubscores   map[string]int `json:"interview_odds_subscores"`
	PracticalPursueSubscores map[string]int `json:"practical_pursue_subscores"`
	PostingAgeDays           int            `json:"posting_age_days"`
	EvaluatedAt              string         `json:"evaluated_at"`
}

// Liveness mirrors the _liveness key persisted by
// scripts/jd_manager.py's save_liveness().
type Liveness struct {
	Result    string `json:"result"`
	Reason    string `json:"reason"`
	CheckedAt string `json:"checked_at"`
}

// Application mirrors the _application key persisted by
// scripts/jd_manager.py's save_application_status().
type Application struct {
	Status          string  `json:"status"`
	AppliedAt       *string `json:"applied_at"`
	StatusChangedAt string  `json:"status_changed_at"`
	FollowUpCount   int     `json:"follow_up_count"`
	LastFollowupAt  *string `json:"last_followup_at"`
}
```

Create `dashboard/internal/data/jobs.go`:

```go
package data

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// LoadJobs reads the JD evaluation export written by
// scripts/dashboard.py (picker.list_all_evaluated_jds()) at path and
// decodes it into JobRows.
func LoadJobs(path string) ([]model.JobRow, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading jobs export %s: %w", path, err)
	}
	var rows []model.JobRow
	if err := json.Unmarshal(raw, &rows); err != nil {
		return nil, fmt.Errorf("parsing jobs export %s: %w", path, err)
	}
	return rows, nil
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && go test ./internal/data/... -run TestLoadJobs -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/model/job.go dashboard/internal/data/jobs.go dashboard/internal/data/jobs_test.go
git commit -m "feat(dashboard): add JobRow model and LoadJobs export reader"
```

---

### Task 2: Jobs icon + menu entry

**Files:**
- Modify: `dashboard/internal/theme/theme.go` (`Theme.Icons` struct)
- Modify: `dashboard/internal/theme/resumebuilder.go`
- Modify: `dashboard/internal/theme/catppuccin.go`
- Modify: `dashboard/internal/theme/catppuccin_latte.go`
- Modify: `dashboard/internal/ui/menu/list.go`

**Interfaces:**
- Produces: `Theme.Icons.Jobs` (string), a new `"Jobs"` `MenuItem` — consumed by Task 5's `main.go` (`MenuSelectMsg{Command: "Jobs"}`).

This task has no dedicated test (icon glyphs/menu item registration aren't unit-tested anywhere in this codebase today — `menu/list.go` has no test file) — verified via build.

- [ ] **Step 1: Add the `Jobs` field to `Theme.Icons`**

In `dashboard/internal/theme/theme.go`, find the `Icons` struct field on `Theme` (currently `Pipeline`, `Progress`, `Report`, `Quit`, `Menu` string fields) and add:

```go
	Icons struct {
		Pipeline string
		Progress string
		Report   string
		Quit     string
		Menu     string
		Jobs     string
	}
```

- [ ] **Step 2: Set it in all three palette constructors**

In each of `dashboard/internal/theme/resumebuilder.go`, `catppuccin.go`, `catppuccin_latte.go`, find the block setting `t.Icons.Pipeline`/`t.Icons.Progress`/`t.Icons.Report`/`t.Icons.Quit`/`t.Icons.Menu` and add one line to each:

```go
	t.Icons.Jobs = "💼"
```

- [ ] **Step 3: Add the menu entry**

In `dashboard/internal/ui/menu/list.go`'s `NewMenuModel`, add a new item to the `items` slice (after `"Reports"`, before `"Quit"`):

```go
		MenuItem{title: "Jobs", desc: "Evaluated job postings", icon: t.Icons.Jobs},
```

- [ ] **Step 4: Verify it builds**

Run: `cd dashboard && go build ./internal/theme/... ./internal/ui/menu/...`
Expected: builds clean, no errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/theme/theme.go dashboard/internal/theme/resumebuilder.go dashboard/internal/theme/catppuccin.go dashboard/internal/theme/catppuccin_latte.go dashboard/internal/ui/menu/list.go
git commit -m "feat(dashboard): add Jobs icon and menu entry"
```

---

### Task 3: JobsModel state & interaction

**Files:**
- Create: `dashboard/internal/ui/screens/jobs.go`
- Test: `dashboard/internal/ui/screens/jobs_test.go`

**Interfaces:**
- Consumes: `model.JobRow` (Task 1), `theme.Theme` (existing).
- Produces: `screens.JobsModel`, `screens.NewJobsModel(t theme.Theme, rows []model.JobRow, width, height int) JobsModel`, `(m JobsModel) CurrentJob() (model.JobRow, bool)`, `(m *JobsModel) Resize(width, height int)`, `(m JobsModel) Update(msg tea.Msg) (JobsModel, tea.Cmd)`, `screens.JobsClosedMsg{}` — consumed by Task 4 (rendering, same struct) and Task 5 (`main.go` wiring).

- [ ] **Step 1: Write the failing tests**

Create `dashboard/internal/ui/screens/jobs_test.go`:

```go
package screens

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func testJobRows() []model.JobRow {
	return []model.JobRow{
		{Path: "a.json", Status: "Pending", Company: "Acme", Title: "Role A", Evaluation: model.Evaluation{CompositeScore: 4.5}},
		{Path: "b.json", Status: "Completed", Company: "Beta", Title: "Role B", Evaluation: model.Evaluation{CompositeScore: 3.0}},
	}
}

func TestNewJobsModelDefaultsToAllFilterShowingEveryRow(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	if m.filter != "all" {
		t.Fatalf("expected default filter %q, got %q", "all", m.filter)
	}
	if len(m.filtered) != 2 {
		t.Fatalf("expected 2 filtered rows, got %d", len(m.filtered))
	}
}

func TestCursorMovementClampsAtBoundaries(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	if m.cursor != 0 {
		t.Fatalf("expected cursor clamped to 0, got %d", m.cursor)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	if m.cursor != 1 {
		t.Fatalf("expected cursor at 1, got %d", m.cursor)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	if m.cursor != 1 {
		t.Fatalf("expected cursor clamped to 1 (last row), got %d", m.cursor)
	}
}

func TestFilterCyclesAllPendingCompletedAll(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'f'}})
	if m.filter != "pending" {
		t.Fatalf("expected filter %q, got %q", "pending", m.filter)
	}
	if len(m.filtered) != 1 || m.filtered[0].Status != "Pending" {
		t.Fatalf("expected only Pending rows, got %+v", m.filtered)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'f'}})
	if m.filter != "completed" {
		t.Fatalf("expected filter %q, got %q", "completed", m.filter)
	}
	if len(m.filtered) != 1 || m.filtered[0].Status != "Completed" {
		t.Fatalf("expected only Completed rows, got %+v", m.filtered)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'f'}})
	if m.filter != "all" {
		t.Fatalf("expected filter to cycle back to %q, got %q", "all", m.filter)
	}
}

func TestCurrentJobReturnsFalseWhenEmpty(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), nil, 100, 30)
	if _, ok := m.CurrentJob(); ok {
		t.Fatal("expected CurrentJob to return false for an empty model")
	}
}

func TestQPressEmitsJobsClosedMsg(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}})
	if cmd == nil {
		t.Fatal("expected a command from pressing q")
	}
	if _, ok := cmd().(JobsClosedMsg); !ok {
		t.Fatalf("expected JobsClosedMsg, got %T", cmd())
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && go test ./internal/ui/screens/... -run "TestNewJobsModel|TestCursorMovement|TestFilterCycles|TestCurrentJobReturnsFalseWhenEmpty|TestQPressEmits" -v`
Expected: FAIL to compile — `undefined: NewJobsModel`, `undefined: JobsClosedMsg`.

- [ ] **Step 3: Write the implementation**

Create `dashboard/internal/ui/screens/jobs.go`:

```go
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && go test ./internal/ui/screens/... -run "TestNewJobsModel|TestCursorMovement|TestFilterCycles|TestCurrentJobReturnsFalseWhenEmpty|TestQPressEmits" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/ui/screens/jobs.go dashboard/internal/ui/screens/jobs_test.go
git commit -m "feat(dashboard): add JobsModel state and interaction (no rendering yet)"
```

---

### Task 4: JobsModel rendering

**Files:**
- Modify: `dashboard/internal/ui/screens/jobs.go`
- Modify: `dashboard/internal/ui/screens/jobs_test.go`

**Interfaces:**
- Consumes: `JobsModel` (Task 3), `truncateRunes` (existing, defined in `pipeline.go`, same package — no import needed), `theme.PadHorizontal`/`theme.HoverStyle` (existing).
- Produces: `(m JobsModel) View() string` — consumed by Task 5's `main.go` (`appModel.View()`'s `viewJobs` case).

- [ ] **Step 1: Add the failing tests**

Append to `dashboard/internal/ui/screens/jobs_test.go` (add `"github.com/charmbracelet/x/ansi"` to the import block):

```go
func TestRenderJobDetailPaneShowsKeyFields(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	job := model.JobRow{
		Company: "Acme", Title: "Marketing Lead", Status: "Pending",
		Evaluation: model.Evaluation{
			CompositeScore: 4.66,
			Recommendation: "Strong pursue",
			Why:            "Great fit for the role.",
			RecruiterRead:  "Recruiter will see a match.",
			HardBlockers:   []string{},
			FitSubscores:   map[string]int{"functional_alignment": 5},
		},
	}

	rendered := ansi.Strip(m.renderJobDetailPane(job, 60, 20))

	for _, want := range []string{
		"Acme", "Marketing Lead", "4.7/5", "Strong pursue",
		"Great fit for the role.", "Recruiter will see a match.",
		"functional_alignment: 5",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("expected detail pane to contain %q, got %q", want, rendered)
		}
	}
}

func TestRenderSidebarListShowsEmptyStateWhenNoRows(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), nil, 100, 30)
	rendered := ansi.Strip(m.renderSidebarList(40, 20))
	if !strings.Contains(rendered, "No evaluated jobs match this filter") {
		t.Fatalf("expected empty-state message, got %q", rendered)
	}
}

func TestViewDoesNotPanicAndIncludesTitle(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	rendered := ansi.Strip(m.View())
	if !strings.Contains(rendered, "JOBS") {
		t.Fatalf("expected header to contain %q, got %q", "JOBS", rendered)
	}
}
```

Also add `"strings"` is already imported (Task 3 added it); this step also needs `github.com/charmbracelet/x/ansi` added to the test file's import block.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && go test ./internal/ui/screens/... -run "TestRenderJobDetailPane|TestRenderSidebarListShows|TestViewDoesNotPanic" -v`
Expected: FAIL to compile — `undefined: m.renderJobDetailPane`, `undefined: m.renderSidebarList`, `undefined: m.View` (on `JobsModel`).

- [ ] **Step 3: Write the implementation**

Append to `dashboard/internal/ui/screens/jobs.go` (add `"fmt"` and `"sort"` to the import block, alongside the existing `"strings"`, `tea`, `model`, `theme` imports, plus `"github.com/charmbracelet/lipgloss"`):

```go
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
	return lipgloss.JoinVertical(lipgloss.Left, header, splitView, help)
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

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(m.theme.Blue).
		Width(width - 2).
		Height(height - 2).
		Padding(0, 1)

	return borderStyle.Render(content)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && go test ./internal/ui/screens/... -v`
Expected: PASS — every test in the package, including all the pre-existing `pipeline_test.go`/`viewer_test.go`/`sort_test.go`/`timeago_test.go` tests (this step must not regress anything in the package Task 1 of the previous plan already got green).

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/ui/screens/jobs.go dashboard/internal/ui/screens/jobs_test.go
git commit -m "feat(dashboard): add JobsModel rendering (split-pane list + detail)"
```

---

### Task 5: Wire the Jobs screen into `main.go`

**Files:**
- Modify: `dashboard/main.go`

**Interfaces:**
- Consumes: `screens.NewJobsModel`, `screens.JobsModel`, `screens.JobsClosedMsg` (Task 3/4), `data.LoadJobs` (Task 1).

No new test file (package `main` has no existing tests) — verified via build and a manual review of the diff against the existing `viewReport`/`viewProgress` dispatch pattern already in the file.

- [ ] **Step 1: Add the `viewJobs` state and `jobs` field**

In `dashboard/main.go`, extend the `viewState` enum:

```go
const (
	viewPipeline viewState = iota
	viewReport
	viewProgress
	viewMenu
	viewJobs
)
```

Add a field to `appModel`:

```go
type appModel struct {
	pipeline        screens.PipelineModel
	viewer          screens.ViewerModel
	progress        screens.ProgressModel
	jobs            screens.JobsModel
	menu            menu.MenuModel
	state           viewState
	careerOpsPath   string
	theme           theme.Theme
	progressMetrics model.ProgressMetrics
}
```

- [ ] **Step 2: Route messages to the jobs screen**

In `Update()`'s `tea.WindowSizeMsg` case, add jobs resize alongside the existing viewer/progress resize:

```go
	case tea.WindowSizeMsg:
		m.pipeline.Resize(msg.Width, msg.Height)
		if m.state == viewReport {
			m.viewer.Resize(msg.Width, msg.Height)
		}
		if m.state == viewProgress {
			m.progress.Resize(msg.Width, msg.Height)
		}
		if m.state == viewJobs {
			m.jobs.Resize(msg.Width, msg.Height)
		}
		pm, cmd := m.pipeline.Update(msg)
		m.pipeline = pm
		return m, cmd
```

Add a case for `MenuSelectMsg{Command: "Jobs"}` in the existing `menu.MenuSelectMsg` switch:

```go
	case menu.MenuSelectMsg:
		switch msg.Command {
		case "Pipeline":
			m.state = viewPipeline
		case "Progress":
			m.state = viewProgress
		case "Reports":
			m.state = viewReport
		case "Jobs":
			m.state = viewJobs
		case "Quit":
			return m, tea.Quit
		}
		return m, nil
```

Add a case for `screens.JobsClosedMsg` alongside the existing `screens.PipelineClosedMsg` case:

```go
	case screens.JobsClosedMsg:
		return m, tea.Quit
```

In the `default:` case, add jobs dispatch before falling through to pipeline:

```go
	default:
		if m.state == viewReport {
			vm, cmd := m.viewer.Update(msg)
			m.viewer = vm
			return m, cmd
		}
		if m.state == viewProgress {
			pg, cmd := m.progress.Update(msg)
			m.progress = pg
			return m, cmd
		}
		if m.state == viewJobs {
			jm, cmd := m.jobs.Update(msg)
			m.jobs = jm
			return m, cmd
		}
		pm, cmd := m.pipeline.Update(msg)
		m.pipeline = pm
		return m, cmd
```

- [ ] **Step 3: Add the `viewJobs` case to `View()`**

```go
func (m appModel) View() string {
	switch m.state {
	case viewReport:
		return m.viewer.View()
	case viewProgress:
		return m.progress.View()
	case viewMenu:
		return m.menu.View()
	case viewJobs:
		return m.jobs.View()
	default:
		return m.pipeline.View()
	}
}
```

- [ ] **Step 4: Add the `-jobs-path` flag and load the export in `main()`**

```go
func main() {
	pathFlag := flag.String("path", ".", "Path to career-ops directory")
	jobsPathFlag := flag.String("jobs-path", "", "Path to the JD evaluation export JSON (see scripts/dashboard.py)")
	themeFlag := flag.String("theme", "resume-builder", "Theme name: resume-builder, catppuccin-mocha, catppuccin-latte, or auto")
	flag.Parse()

	careerOpsPath := *pathFlag

	// Load applications
	apps := data.ParseApplications(careerOpsPath)
	if apps == nil {
		fmt.Fprintf(os.Stderr, "Error: could not find applications.md in %s or %s/data/\n", careerOpsPath, careerOpsPath)
		os.Exit(1)
	}

	// Compute metrics
	metrics := data.ComputeMetrics(apps)
	progressMetrics := data.ComputeProgressMetrics(apps)

	// Batch-load all report summaries
	t := theme.NewTheme(*themeFlag)
	pm := screens.NewPipelineModel(t, apps, metrics, careerOpsPath, 120, 40)

	for _, app := range apps {
		if app.ReportPath == "" {
			continue
		}
		archetype, tldr, remote, comp := data.LoadReportSummary(careerOpsPath, app.ReportPath)
		if archetype != "" || tldr != "" || remote != "" || comp != "" {
			pm.EnrichReport(app.ReportPath, archetype, tldr, remote, comp)
		}
	}

	var jobRows []model.JobRow
	if *jobsPathFlag != "" {
		rows, err := data.LoadJobs(*jobsPathFlag)
		if err != nil {
			fmt.Fprintf(os.Stderr, "WARN: failed to load jobs export: %v\n", err)
		} else {
			jobRows = rows
		}
	}
	jm := screens.NewJobsModel(t, jobRows, 120, 40)

	m := appModel{
		pipeline:        pm,
		jobs:            jm,
		careerOpsPath:   careerOpsPath,
		theme:           t,
		progressMetrics: progressMetrics,
	}

	p := tea.NewProgram(m, tea.WithAltScreen())
	if _, err := p.Run(); err != nil && !errors.Is(err, tea.ErrInterrupted) {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
```

A missing or unreadable `-jobs-path` is a warning, not a fatal error (`os.Exit(1)`) — unlike the existing `applications.md` check above it. The Jobs screen is additive; its own empty-state rendering (Task 4's `renderSidebarList`) already handles zero rows gracefully, so the whole dashboard must not refuse to start just because the jobs export is missing or malformed.

- [ ] **Step 5: Verify it builds**

Run: `cd dashboard && go build ./...` — expect the same, already-known, out-of-scope failure in `internal/ui/bootstrap` (the `ShowIf` issue) and nothing else. Then run the narrower, real check:

Run: `cd dashboard && go build ./cmd/prompt/... ./internal/ui/prompt/... ./internal/ui/screens/... ./internal/data/... ./internal/theme/... ./internal/ui/menu/... .`
Expected: builds clean (the trailing `.` builds the `main` package itself).

- [ ] **Step 6: Commit**

```bash
git add dashboard/main.go
git commit -m "feat(dashboard): wire the Jobs screen into the app model"
```

---

### Task 6: Python export bridge

**Files:**
- Modify: `scripts/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `picker.list_all_evaluated_jds()` (existing, unchanged), `profile_paths.set_active_profile()` (existing).
- Produces: `dashboard._write_jobs_export(profile: str = None) -> str` (path to the written temp file).

- [ ] **Step 1: Update the existing tests that assert on `subprocess.run`'s exact args**

`test_dashboard.py`'s `test_launches_go_run_with_the_profile_data_dir` currently asserts an exact args list, but the new `-jobs-path <temp file>` argument has a non-deterministic path. Replace it and add `picker.list_all_evaluated_jds` mocking (so it doesn't touch real JD files) to both existing subprocess-invoking tests:

```python
    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_launches_go_run_with_the_profile_data_dir(self, mock_go, mock_exists, mock_subproc, mock_list):
        mock_subproc.return_value = MagicMock(returncode=0)
        success, message = dashboard.run("morgan")
        self.assertTrue(success)
        expected_data_dir = dashboard.profile_paths.data_dir("morgan")
        args = mock_subproc.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], ".")
        self.assertEqual(args[3], "-path")
        self.assertEqual(args[4], expected_data_dir)
        self.assertEqual(args[5], "-jobs-path")
        self.assertTrue(args[6])  # a real temp path was generated; cleanup itself is TestRunCleansUpJobsExport's job
        self.assertEqual(mock_subproc.call_args[1], {"cwd": dashboard.DASHBOARD_DIR})

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_returns_false_when_dashboard_process_exits_nonzero(self, mock_go, mock_exists, mock_subproc, mock_list):
        mock_subproc.return_value = MagicMock(returncode=1)
        success, message = dashboard.run("morgan")
        self.assertFalse(success)
        self.assertIn("exited with an error", message)
```

Add a new test class for the export helper and temp-file cleanup:

```python
class TestWriteJobsExport(unittest.TestCase):

    @patch("dashboard.picker.list_all_evaluated_jds")
    def test_writes_valid_json_matching_picker_rows(self, mock_list):
        rows = [{"path": "jds/morgan/a.json", "status": "Pending", "title": "T", "company": "C",
                 "evaluation": {"composite_score": 4.5}, "liveness": None, "application": None}]
        mock_list.return_value = rows

        path = dashboard._write_jobs_export()
        try:
            with open(path, "r", encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(written, rows)
        finally:
            os.remove(path)

    @patch("dashboard.profile_paths.set_active_profile")
    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    def test_sets_active_profile_when_explicit_profile_given(self, mock_list, mock_set_active):
        path = dashboard._write_jobs_export("dominick")
        try:
            mock_set_active.assert_called_once_with("dominick")
        finally:
            os.remove(path)

    @patch("dashboard.profile_paths.set_active_profile")
    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    def test_does_not_touch_active_profile_when_none_given(self, mock_list, mock_set_active):
        path = dashboard._write_jobs_export()
        try:
            mock_set_active.assert_not_called()
        finally:
            os.remove(path)


class TestRunCleansUpJobsExport(unittest.TestCase):

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_temp_file_removed_after_successful_run(self, mock_go, mock_exists, mock_subproc, mock_list):
        mock_subproc.return_value = MagicMock(returncode=0)
        dashboard.run("morgan")
        jobs_path = mock_subproc.call_args[0][0][6]
        self.assertFalse(os.path.exists(jobs_path))

    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_temp_file_removed_even_when_process_fails(self, mock_go, mock_exists, mock_subproc, mock_list):
        mock_subproc.return_value = MagicMock(returncode=1)
        dashboard.run("morgan")
        jobs_path = mock_subproc.call_args[0][0][6]
        self.assertFalse(os.path.exists(jobs_path))
```

Add `import json` to the top of `test_dashboard.py` alongside the existing `import os`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard -v`
Expected: FAIL — `AttributeError: module 'dashboard' has no attribute '_write_jobs_export'` (`TestWriteJobsExport`, `TestRunCleansUpJobsExport`), and the two rewritten existing tests FAIL on the args-list assertions since `run()` doesn't add `-jobs-path` yet.

- [ ] **Step 3: Implement `_write_jobs_export` and update `run()`**

In `scripts/dashboard.py`, add imports and the new function, and update `run()`:

```python
import json
import os
import shutil
import subprocess
import tempfile

import picker
import profile_paths

DASHBOARD_DIR = os.path.join(profile_paths.PROJECT_ROOT, "dashboard")


def go_available() -> bool:
    return shutil.which("go") is not None


def _write_jobs_export(profile: str = None) -> str:
    """Writes picker.list_all_evaluated_jds() to a fresh temp JSON file
    and returns its path, for the Go dashboard's -jobs-path flag. Always
    a fresh snapshot, never cached -- evaluation/liveness/application
    data changes between dashboard launches via the Python menu, so a
    stale export would be actively misleading. Only touches the active
    profile when an explicit one is given (mirrors _handle_bootstrap()'s
    own pattern in menu.py) -- the real call site (run(), with
    profile=None) never needs the reload."""
    if profile:
        profile_paths.set_active_profile(profile)
    rows = picker.list_all_evaluated_jds()
    fd, path = tempfile.mkstemp(suffix=".json", prefix="dashboard_jobs_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return path


def run(profile: str = None) -> tuple[bool, str]:
    """Launches the dashboard TUI against `profile`'s applications.md,
    full-screen and interactive -- inherits this process's stdio (unlike
    every other subprocess call in this codebase, which captures output)
    since the whole point is a live terminal UI the user actually drives.
    Returns (success, message); message is only meaningful on failure."""
    if not go_available():
        return False, (
            "Go isn't installed -- the dashboard is a separate Go/Bubble Tea "
            "TUI (dashboard/). Install it (e.g. `brew install go`) and try "
            "again."
        )

    data_dir = profile_paths.data_dir(profile)
    if not os.path.exists(os.path.join(data_dir, "applications.md")):
        return False, (
            f"No applications logged yet for this profile ({data_dir} has no "
            "applications.md) -- log at least one application status via "
            "\"Browse & Manage Jobs\" first, then the dashboard has something "
            "to show."
        )

    jobs_path = _write_jobs_export(profile)
    try:
        result = subprocess.run(
            ["go", "run", ".", "-path", data_dir, "-jobs-path", jobs_path],
            cwd=DASHBOARD_DIR,
        )
    finally:
        os.remove(jobs_path)

    if result.returncode != 0:
        return False, f"Dashboard exited with an error (code {result.returncode})."
    return True, ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add scripts/dashboard.py tests/test_dashboard.py
git commit -m "feat: export JD evaluation data as JSON for the Go dashboard's Jobs screen"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `source .venv/bin/activate && python -m unittest discover -s tests 2>&1 | tail -20`
Expected: the same pre-existing, unrelated failures as before this plan (`test_audit_keepers`, `test_cli_art.TestRenderDoctorReport`, `test_orchestrator_main_batch` — 3 failures, 5 errors, none in files this plan touches), plus all new/updated tests in `test_dashboard.py` passing. No new failures.

- [ ] **Step 2: Run the full Go test suite**

Run: `cd dashboard && go test ./... 2>&1`
Expected: the same pre-existing, out-of-scope failure in `internal/ui/bootstrap` (`ShowIf` build error) and its `cmd/bootstrap` dependent, plus every other package — including `internal/ui/screens` (now with `jobs_test.go` added) and `internal/data` (now with `jobs_test.go` added) — passing.

- [ ] **Step 3: Confirm the Jobs screen is reachable from the menu**

Run: `grep -n '"Jobs"' dashboard/internal/ui/menu/list.go dashboard/main.go`
Expected: one match in each file (the `MenuItem` and the `MenuSelectMsg` case).

No commit for this task — it's verification only.
