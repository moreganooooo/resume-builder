# Jobs Screen (Data Bridge + Split-Pane Screen) — Design

## Context: the broader Charmbracelet redesign

This is sub-project 2 of the larger Charmbracelet redesign effort (see
[docs/superpowers/specs/2026-08-08-charm-prompt-migration-design.md](2026-08-08-charm-prompt-migration-design.md)
for the full four-sub-project breakdown; sub-project 1, the prompt
migration, is complete). This spec covers two of sub-project 2's three
planned pieces, bundled together because a data source with nothing
rendering it isn't independently satisfying:

1. **JD data export bridge** — Python exports real evaluation/liveness/
   application data as JSON; Go gets a loader for it.
2. **Split-pane list + detail screen** — a new dashboard screen renders
   that data, following the Command Center Editor design system already
   on file in `.impeccable/surface-dashboard.md`.

**Deferred to a later spec:** action triggers (Liveness Check, Tailor
Resume) that shell back to Python for real work with a spinner, then
reload the export. That's piece 3, not touched here.

## Problem

The dashboard (`dashboard/`, launched via `resume dashboard`) currently
reads only `data/<profile>/applications.md` — a sparse, mostly-empty
career-ops-style tracker (`data/morgan/applications.md` today: company/
role show `unknown`, status `new`, no scores for nearly every row). The
rich data this project's own evaluation pipeline actually produces —
composite score, fit/interview-odds/practical-pursue subscores,
recommendation, reasoning ("why"), recruiter read, hard blockers, posting
legitimacy, liveness result, real application status — lives entirely in
each JD's own JSON file under `_evaluation`/`_liveness`/`_application`
(see CLAUDE.md's "JD JSON metadata convention"), read via
`scripts/jd_manager.py`. The Go dashboard has no access to any of it
today.

The `.impeccable/surface-dashboard.md` brief ("true interview probability
scores, explicit reasoning for the score... application status") is
describing this JD-JSON data, not `applications.md`. Closing that gap is
the actual prerequisite for anything in the surface brief to be real.

## Goals

- A Python function that assembles the real per-JD data (reusing
  `scripts/picker.py`'s existing `list_all_evaluated_jds()` — already
  returns path/status/title/company/evaluation/liveness/application,
  pre-sorted by composite score) and writes it as JSON to a temp file.
- `scripts/dashboard.py`'s `run()` writes that export before launching
  the Go binary, passes its path via a new `-jobs-path` flag (alongside
  the existing `-path` flag for `applications.md`, untouched), and
  removes the temp file after the Go process exits.
- New Go types (`internal/model.JobRow` + nested `Evaluation`/`Liveness`/
  `Application` structs) and a loader (`internal/data.LoadJobs(path
  string) ([]model.JobRow, error)`) mirroring the existing
  `CareerApplication`/`ParseApplications` pair.
- A new `JobsModel` screen (`internal/ui/screens/jobs.go`) added
  alongside the existing Pipeline/Progress/Reports menu options (not
  replacing Pipeline — `applications.md`-based long-term tracking stays
  as-is), following `PipelineModel`'s existing split-pane pattern
  (`pipeline.go:678-696`: 35% left sidebar / 65% right detail, cursor
  nav): left pane lists jobs by company/title/score, right pane shows
  the full evaluation breakdown for the selected job.
- A new `Theme.Icons.Jobs` field, set identically in all three palette
  constructors (`resumebuilder.go`, `catppuccin.go`,
  `catppuccin_latte.go` — confirmed today they set the same 5 fields
  identically), and a new `MenuItem` for "Jobs" in `menu/list.go`.

## Non-Goals

- **Action triggers** (Liveness Check, Tailor Resume, Update Status from
  inside the dashboard). Deferred to piece 3's own spec — this screen is
  read-only for now.
- **Feature parity with `PipelineModel`.** `pipeline.go` is 1471 lines
  with an 8-tab filter bar, a 7-mode sort cycle, live search, and a
  grouped-by-status view. `JobsModel`'s first cut: split-pane list +
  detail, cursor up/down, a single Pending/Completed filter (matching the
  `status` field `list_all_evaluated_jds()` already returns). No search,
  sort cycle, or grouped view yet — same "prove the pattern, extend
  later" scoping sub-project 1 used for `confirm()`-only.
- **Replacing `applications.md` or the Pipeline screen.** Both stay
  exactly as they are; `Jobs` is purely additive.
- **Caching or persisting the JSON export.** It's a fresh-every-launch
  temp file, not a profile-scoped artifact — evaluation/liveness/
  application data can change between dashboard launches via the Python
  menu, so a stale cached export would be actively misleading.

## Architecture

**Python side — `scripts/picker.py`** gains no new logic;
`list_all_evaluated_jds()` (picker.py:196) already returns exactly the
row shape needed. **`scripts/dashboard.py`**'s `run()` gains a step
before invoking the Go binary: call `picker.list_all_evaluated_jds()`,
serialize to JSON, write to a `tempfile.NamedTemporaryFile` (not deleted
on close, since the Go subprocess needs to open it by path), pass that
path via `-jobs-path`, and remove the file in a `finally` block after
`subprocess.run(...)` returns — mirroring the existing `-path
<data_dir>` flag for `applications.md`, not sub-project 1's
subprocess-JSON-on-stdin pattern, since this is a long-lived full-screen
session reading a startup snapshot, not a single request/response.

**JSON shape** (array of objects, one per JD with a persisted
`_evaluation`):

```json
[
  {
    "path": "jds/morgan/2026-07-25_BairesDev_....json",
    "status": "Pending",
    "title": "Customer Lifecycle Marketing Lead",
    "company": "BairesDev",
    "evaluation": {
      "composite_score": 4.66,
      "fit_score": 4.85,
      "interview_odds_score": 4.8,
      "practical_pursue_score": 4.0,
      "recommendation": "Strong pursue",
      "why": "...",
      "recruiter_read": "...",
      "hard_blockers": [],
      "posting_legitimacy": "High Confidence",
      "posting_legitimacy_notes": "...",
      "archetype": "Lifecycle Marketing Lead",
      "fit_subscores": {"functional_alignment": 5, "north_star_alignment": 5, "level_plausibility": 5, "work_style_sustainability": 4, "tools_process_overlap": 5},
      "interview_odds_subscores": {"title_continuity": 5, "evidence_match": 5, "domain_credibility": 5, "recruiter_legibility": 5, "narrative_burden": 5, "funnel_friction": 3},
      "practical_pursue_subscores": {"remote_quality": 5, "compensation_viability": 3, "growth_value": 4, "time_to_offer": 3, "company_reputation": 3, "cultural_signals": 4, "posting_legitimacy_score": 5},
      "posting_age_days": 2,
      "evaluated_at": "2026-07-27T03:13:55"
    },
    "liveness": {"result": "active", "reason": "visible apply control detected", "checked_at": "2026-08-07T21:44:03"},
    "application": null
  }
]
```

`liveness` and `application` are `null` when never checked/set (matches
`jd_manager.read_liveness()`/`read_application_status()` returning
`None`). `application`, when present:
`{"status", "applied_at", "status_changed_at", "follow_up_count",
"last_followup_at"}` (verified against `jd_manager.save_application_status()`
— `applied_at`/`last_followup_at` are nullable strings, not always set).

**Go side — `internal/model/job.go`** (new):

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

type Evaluation struct {
	CompositeScore          float64        `json:"composite_score"`
	FitScore                float64        `json:"fit_score"`
	InterviewOddsScore      float64        `json:"interview_odds_score"`
	PracticalPursueScore    float64        `json:"practical_pursue_score"`
	Recommendation          string         `json:"recommendation"`
	Why                     string         `json:"why"`
	RecruiterRead           string         `json:"recruiter_read"`
	HardBlockers            []string       `json:"hard_blockers"`
	PostingLegitimacy       string         `json:"posting_legitimacy"`
	PostingLegitimacyNotes  string         `json:"posting_legitimacy_notes"`
	Archetype               string         `json:"archetype"`
	FitSubscores            map[string]int `json:"fit_subscores"`
	InterviewOddsSubscores  map[string]int `json:"interview_odds_subscores"`
	PracticalPursueSubscores map[string]int `json:"practical_pursue_subscores"`
	PostingAgeDays          int            `json:"posting_age_days"`
	EvaluatedAt             string         `json:"evaluated_at"`
}

type Liveness struct {
	Result    string `json:"result"`
	Reason    string `json:"reason"`
	CheckedAt string `json:"checked_at"`
}

type Application struct {
	Status          string  `json:"status"`
	AppliedAt       *string `json:"applied_at"`
	StatusChangedAt string  `json:"status_changed_at"`
	FollowUpCount   int     `json:"follow_up_count"`
	LastFollowupAt  *string `json:"last_followup_at"`
}
```

**`internal/data/jobs.go`** (new): `LoadJobs(path string) ([]model.JobRow, error)`
reads the file at `path` and `json.Unmarshal`s into `[]model.JobRow`.

**`internal/ui/screens/jobs.go`** (new): `JobsModel`, structurally
mirroring `PipelineModel` — `rows []model.JobRow`, `filtered
[]model.JobRow`, `cursor int`, `filter string` ("all"/"pending"/
"completed"), `width`/`height`/`theme`. `View()` follows
`pipeline.go:665-702`'s exact composition: header, a one-line filter
indicator (not a full tab bar — that's deferred), `leftPane` (sidebar:
company, title, composite score per row, selected row highlighted) at
35% width via `renderSidebarList`-equivalent, `rightPane` (detail: full
`Evaluation` breakdown — scores, recommendation, why, recruiter read,
hard blockers, subscores under labeled groups exactly matching
`cli_art._FIT_DIMENSION_GROUPS`' three groups/labels on the Python side
for visual consistency with the CLI's own evaluation detail view, plus
liveness result and application status) at 65% width, help footer.
`Resize`/`Update` follow `PipelineModel`'s existing method shapes
(`Resize(width, height int)`, `Update(msg tea.Msg) (JobsModel, tea.Cmd)`)
for consistency with how `main.go` already dispatches to sibling screens.

**Wiring in `dashboard/main.go`:** new `viewJobs` constant in the
`viewState` enum, a `jobs screens.JobsModel` field on `appModel`,
`WindowSizeMsg`/default-case dispatch extended to route to `m.jobs` when
`m.state == viewJobs` (matching the existing `viewReport`/`viewProgress`
branches), `MenuSelectMsg{Command: "Jobs"}` sets `m.state = viewJobs`,
and a new `-jobs-path` flag in `main()` feeding `data.LoadJobs()` at
startup (failure here does not abort the whole dashboard — see Error
Handling).

## Error Handling

- **`-jobs-path` not passed, or the file doesn't exist/is empty:** the
  Jobs screen shows an empty-state message ("No evaluated jobs found —
  run an evaluation from the main menu first") rather than the dashboard
  refusing to start. This mirrors `applications.md`'s own current
  behavior of failing gracefully per-screen, not process-wide (only a
  missing `applications.md` itself is currently a hard `os.Exit(1)` in
  `main()` — the new jobs data must NOT be held to that same
  all-or-nothing standard, since `Jobs` is an additive screen, not the
  dashboard's core requirement).
- **Malformed JSON in the export file:** `LoadJobs()` returns the
  `json.Unmarshal` error; `main()` logs it to stderr (not fatal) and
  starts with `m.jobs` empty, same empty-state screen as above.
- **Python-side export failure** (e.g., `picker.list_all_evaluated_jds()`
  raises): `dashboard.py`'s `run()` lets the exception propagate before
  ever launching the Go subprocess — a real, loud crash rather than
  silently launching the dashboard with an empty/absent jobs file, since
  a Python-side crash building the export means something is actually
  broken (unlike an empty result, which is a legitimate real state: no
  evaluated JDs yet).
- **Temp file cleanup:** the `finally` block removing the temp file runs
  even if the Go subprocess itself fails (non-zero exit) — matches
  `_handle_bootstrap()`'s existing pattern of cleaning up regardless of
  subprocess outcome.

## Testing

- **Python:** a new test asserting `dashboard.py`'s export step (a
  small helper function, e.g. `_write_jobs_export(profile) -> str`
  returning the temp file path) writes valid JSON matching
  `list_all_evaluated_jds()`'s return shape, using
  `unittest.mock.patch("dashboard.picker.list_all_evaluated_jds")` to
  control the input rows rather than touching real JD files.
- **Go — `internal/data/jobs_test.go`:** `LoadJobs()` against a valid
  fixture JSON string (via a temp file), a malformed-JSON case (expects
  an error), and a missing-file case (expects an error, not a panic).
- **Go — `internal/ui/screens/jobs_test.go`:** cursor movement clamps at
  list boundaries (mirroring
  `TestViewerRebuildRenderClampsScrollOffset`'s style), the detail pane
  renders a selected row's `Recommendation`/`Why` text, the empty-state
  message appears when `rows` is empty, and the Pending/Completed filter
  actually narrows `filtered`.
