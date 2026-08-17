# Implementation Plan: TUI Polish, "Shiny" Terminal Craft & Compassionate UX

> **Target Spec**: [`docs/superpowers/specs/2026-08-17-tui-polish-design.md`](file:///Users/morganescott/resume-builder/docs/superpowers/specs/2026-08-17-tui-polish-design.md)  
> **Status**: Ready for Implementation (TDD, phase-by-phase)  
> **Primary Goals**:
> 1. Complete visual unification (`┃` hover styling, universal `?` overlays, zero hardcoded hex drift).
> 2. Activate vendored power (`glamour` magazine-grade markdown, `huh` onboarding wizard).
> 3. Standardize Harmonica physics curves (`anim/`) with strict `RESUME_BUILDER_MOTION=reduced` respect.
> 4. Add dynamic living polish (flowing gradient waves, celebratory particles).
> 5. Implement compassionate, ADHD-friendly UX (plain-language jargon, "never-lost" breadcrumbs, 1-click auto-pilot, 3-step playbook).

---

## Phase 1: Foundation & Audit Fixes (Zero Hex Drift & Tooling Parity)

### 1.1 Goal
Eliminate all remaining hardcoded hex colors, fix stale documentation comments, and make tooling (`lint_colors.go`) work seamlessly regardless of invocation directory.

### 1.2 Tasks
1. **Fix `main.go` Spring Doc Comment**:
   - Update lines 86-88 in `dashboard/main.go` to accurately describe the `0.7` underdamped spring curve (organic bounce vs. rigid critical damping).
2. **Tokenize `scripts/cli_art.py` Thinking Status Loader**:
   - In `scripts/theme.py`, expose canonical Catppuccin palette tokens: `PEACH`, `PINK`, `MAUVE`, `LAVENDER`, `BLUE`, `SKY`.
   - In `scripts/cli_art.py:1570`, replace hardcoded hex list with `[theme.PEACH, theme.PINK, theme.MAUVE, theme.LAVENDER, theme.BLUE, theme.SKY]`.
3. **Tokenize `dashboard/internal/ui/menu/list.go` Gradient Banner**:
   - Replace hardcoded hexes `#FF60FF` and `#00A4FF` with dynamic theme token colors (`colorToHex(m.theme.Mauve)` and `colorToHex(m.theme.Sky)` or equivalent helper).
4. **Make `dashboard/tools/lint_colors.go` Directory-Agnostic**:
   - Update `lint_colors.go` to inspect `.` or `dashboard/` automatically so running `go run dashboard/tools/lint_colors.go` from repo root works without failing on directory not found.
   - Run `go run dashboard/tools/lint_colors.go` and confirm zero errors.

### 1.3 Tests & Verification
- `tests/test_cli_art.py`: Add test verifying `thinking_status` uses theme tokens and has no hardcoded hex strings.
- Verify `go run dashboard/tools/lint_colors.go` passes from both repo root and `dashboard/`.

---

## Phase 2: Visual Consistency & Interactive Help Overlays

### 2.1 Goal
Unify the Main Menu's selection grammar with the rest of the application (`┃` left-border indicator) and add interactive `?` help overlays.

### 2.2 Tasks
1. **Unify Main Menu Item Selection in `dashboard/internal/ui/menu/list.go`**:
   - Update `delegate.Styles.SelectedTitle` and `delegate.Styles.SelectedDesc` to use `theme.HoverStyle` formatting (`┃` border in `t.Token.Mauve`, left padding 1, clear high-contrast text).
   - Ensure unselected items have left padding 2 for pixel-perfect vertical alignment.
2. **Add `?` Help Overlay to Main Menu**:
   - Add `showHelp bool` to `MenuModel` in `list.go`.
   - In `Update()`, intercept `?` to toggle `showHelp`, and `Esc` to dismiss `showHelp`.
   - In `View()`, when `showHelp` is true, render `renderHelpOverlay` with categorized shortcuts:
     - **Navigation**: `↑ / ↓ / j / k` (Move selection), `Home / End` (Jump to top/bottom).
     - **Actions**: `Enter` (Select menu item).
     - **General**: `?` (Toggle help overlay), `q / Ctrl+C` (Exit dashboard).
   - Update footer line to: `"←↑↓→ navigate • ↩ select • ? help • q quit"`.

### 2.3 Tests & Verification
- `dashboard/internal/ui/menu/list_test.go`: Add tests for menu selection formatting, `?` key toggle, and help overlay dismissal on `Esc`.

---

## Phase 3: Tier 1 - Glamour Markdown Rendering & Huh Onboarding Wizard

### 3.1 Goal
Deliver magazine-grade markdown rendering for reports, cover letters, and CVs using `glamour`, and refine the `huh` onboarding wizard.

### 3.2 Tasks
1. **Implement Glamour-Powered Renderer in `dashboard/internal/ui/screens/viewer.go`**:
   - Initialize `glamour.NewTermRenderer` using `theme.GlamourConfig(m.theme)`.
   - Render `m.rawContent` through Glamour.
   - Apply a post-processing line wrap pass using `ansi.Wrap(line, m.width - 4, "")` to prevent unbroken code strings or wide table cells from causing horizontal overflows.
   - Maintain clean fallback to line-parser if rendering fails.
   - Ensure smooth scrolling, page up/down, and jump to top/bottom (`g`/`G`).
2. **Polish Huh Onboarding Form in `dashboard/internal/ui/bootstrap/wizard.go`**:
   - Enhance Huh theme integration with clear focus rings and descriptive hints.
   - Ensure `FilePicker` starts in user home directory and supports `.pdf`, `.json`, `.jsonl`, `.txt`, `.md`.
   - Verify non-zero exit code on user abort (`huh.ErrUserAborted` returns exit code 130).

### 3.3 Tests & Verification
- `dashboard/internal/ui/screens/viewer_test.go`: Test Glamour rendering with sample markdown, long unbroken tokens, table wrapping, and scroll bounds.
- `dashboard/cmd/bootstrap/main_test.go` or wizard tests.

---

## Phase 4: Tier 2 - Shared Harmonica Physics & Motion Design System

### 4.1 Goal
Standardize all UI animations onto mathematical `harmonica.Spring` curves with clean reduced-motion accessibility.

### 4.2 Tasks
1. **Create Shared Physics Package `dashboard/internal/ui/anim/springs.go`**:
   - Define typed presets:
     - `Snappy`: `harmonica.NewSpring(harmonica.FPS(60), 12.0, 0.8)` (list hovers, cursor moves).
     - `Organic`: `harmonica.NewSpring(harmonica.FPS(60), 7.0, 0.7)` (screen reveals, sidebars).
     - `Elastic`: `harmonica.NewSpring(harmonica.FPS(60), 20.0, 0.9)` (score pill fills, badges).
     - `Shake`: `harmonica.NewSpring(harmonica.FPS(60), 25.0, 0.4)` (invalid actions / error cues).
   - Implement `ReducedMotion() bool` checking `os.Getenv("RESUME_BUILDER_MOTION") == "reduced"`.
2. **Wire Components to `anim/` Presets**:
   - Refactor `dashboard/main.go` screen transitions to use `anim.Organic` and `anim.ReducedMotion()`.
   - In `dashboard/internal/ui/screens/bars.go`, apply spring-based fill calculations for score pills.

### 4.3 Tests & Verification
- `dashboard/internal/ui/anim/springs_test.go`: Test spring step calculation and `ReducedMotion` bypass.

---

## Phase 5: Tier 3 - Living Shimmer, Flowing Gradients & Particle Emitters

### 5.1 Goal
Add living, responsive visual polish without distracting from core productivity.

### 5.2 Tasks
1. **Implement Flowing Gradient Wave in `dashboard/internal/theme/theme.go`**:
   - Implement `RenderFlowingGradient(text string, startHex, endHex string, tOffset float64) string` calculating character-by-character sinusoidal color shifts.
   - Wire header banners in `menu/list.go` and `screens/bars.go` to increment `tOffset` on each ~60 FPS tick.
2. **Upgrade Python Celebratory Particle Emitter in `scripts/cli_art.py`**:
   - Refactor `display_success_celebration()` to render an in-place Rich `Live` particle display (`✦ ✧ · ✨ 🚀`) that settles into the `ACHIEVEMENT UNLOCKED` card without harsh screen flicker.

### 5.3 Tests & Verification
- `dashboard/internal/theme/theme_test.go`: Test `RenderFlowingGradient` color output and string length preservation.
- `tests/test_cli_art.py`: Test celebration animation runner and non-interactive fallbacks.

---

## Phase 6: Compassionate UX Architecture for ADHD & Non-Technical Users

### 6.1 Goal
Eliminate all confusion, cognitive friction, and jargon for non-technical job seekers looking for sales, marketing, and business roles.

### 6.2 Tasks
1. **Plain-Language Menus & Jargon Translation in `scripts/menu.py`**:
   - Update menu choices and subtitles:
     - `find_jobs`: `"Find Jobs"` $\rightarrow$ Subtitle: `"Search job boards or paste a job link you want to apply for"`
     - `build_documents`: `"Build Documents"` $\rightarrow$ Subtitle: `"Generate tailored resumes & cover letters for specific roles"`
     - `bullet_bank`: `"Bullet Bank (Master Accomplishment Vault)"` $\rightarrow$ Subtitle: `"Your master career wins, tailored automatically for each job"`
     - `track_followup`: `"Track & Follow Up"` $\rightarrow$ Subtitle: `"See your active applications, match odds & interview reminders"`
     - `settings_upkeep`: `"Settings & Upkeep"` $\rightarrow$ Subtitle: `"Profile settings, health checks & system updates"`
2. **1-Click Express Auto-Pilot Default in `scripts/bootstrap_menu.py`**:
   - Ensure `⚡ Express Auto-Pilot (Recommended)` is the first choice with plain-language explanation: `"(Sets up your profile & accomplishment vault in 2 minutes automatically so you can start applying!)"`.
   - Rename technical phases ("Ingestion", "Phase 0.5") to plain English ("Upload Resumes", "Draft Profile", "Build Vault").
3. **"Never Get Stuck" Actionable Breadcrumbs**:
   - In `_handle_build_documents()`: If no jobs are pending in `jds/`, instead of an error message, display an actionable prompt:
     - Option 1: `Scan for new jobs now`
     - Option 2: `Paste a job link or description manually`
     - Option 3: `Back to Main Menu`
4. **"The 3-Step Job Search Playbook" Guide**:
   - Add a friendly, 3-step walkthrough to the Help menu in `scripts/menu.py` and the `?` overlay in Go dashboard.
5. **Actionable Empty-State Cards in Go Dashboard**:
   - Update empty state views in `bars.go`, `jobs.go`, `pipeline.go`, `viewer.go` to display encouraging callout cards with exact shortcut keys and terminal commands.

### 6.3 Tests & Verification
- `tests/test_menu_ux.py`: Write comprehensive unit tests verifying:
  - Plain-language menu options and subtitles.
  - Express auto-pilot choice formatting.
  - Empty job queue breadcrumb routing.
  - Help menu 3-step playbook display.

---

## Phase 7: Full System Verification & Regression Testing

### 7.1 Tasks
1. Run `go run dashboard/tools/lint_colors.go` from repo root and `dashboard/` $\rightarrow$ must pass with 0 errors.
2. Run `cd dashboard && go test ./...` $\rightarrow$ all Go tests must pass.
3. Run `pytest` across the entire Python test suite $\rightarrow$ all 1,663+ tests must pass.
4. Verify end-to-end UX flows (`resume`, `resume menu`, `resume dashboard`, `resume package`).
