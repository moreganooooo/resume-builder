# Design Specification: TUI Polish & "Shiny" Terminal Craft

> **Target**: Terminal UI & Go Dashboard (`dashboard/` and `scripts/cli_art.py` / `scripts/menu.py`)  
> **Origin**: `docs/to_do/TUI_POLISH_BLUEPRINT.md` & `TUI_AUDIT_PROMPT.md`  
> **Status**: Draft Spec for Review & Approval  
> **Guiding Principle**: Out-of-distribution terminal craft, 100% visual consistency, zero hardcoded hex drift, buttery 60 FPS motion, and an ultra-compassionate, frictionless UX designed specifically for non-technical, easily-overwhelmed job seekers.

---

## 1. Executive Summary & Design Vision

The `resume-builder` application features a dual-surface terminal architecture:
1. **Go / Bubble Tea Interactive Dashboard (`dashboard/`)**: Visual triage, analytics, job inspection, and document browsing.
2. **Python / Rich CLI Orchestrator (`scripts/cli_art.py`, `scripts/menu.py`)**: Multi-step build pipelines, scoring, tailoring, and package generation.

While the foundational mechanics (frame-locking, alt-screen protection, Catppuccin token trees, and base Harmonica springs) are in place, previous passes focused heavily on developer-facing architecture. For a **non-technical job seeker** (e.g., in sales, marketing, operations) who may be stressed, overwhelmed, or dealing with ADHD/burnout, technical jargon and multi-step menus create paralysis.

This specification closes the design loop by uniting **world-class terminal aesthetics** with a **deeply empathetic, intuitive UX**:
- **Flawless Visual Consistency**: 100% unified selection markers (`┃` hover border across all screens), universal `?` help overlays, and zero hardcoded hex values in either Go or Python.
- **Magazine-Quality Markdown Previews**: Harnessing `charmbracelet/glamour` themed via `theme.GlamourConfig` for rich, beautiful reports, CVs, and cover letters.
- **Organic Physics & Motion Language**: Standardized `harmonica.Spring` presets gated cleanly by `RESUME_BUILDER_MOTION=reduced`.
- **"Unhinged Shiny" Perceived Aliveness**: Real-time flowing gradient waves across headers, breathing empty-state starfields, and particle celebrations.
- **Compassionate & Frictionless UX**: Plain-language menu descriptions, automatic "What to do next" breadcrumbs, 1-click Express Setup, and friendly guided onboarding so anyone knows exactly what to do within 5 seconds.

---

## 2. Gap Catalog & Architectural Audit Reconciliation

| Domain / Item | Current State | Root Cause | Target Specification |
|---|---|---|---|
| **Audit Gap 1: Main Menu Selection** | Mauve background fill on selected row (`list.go:52`) | Diverged from sidebar selection convention | Standardize on `HoverStyle` (`┃` left-border indicator + 4.5:1 high-contrast foreground text). |
| **Audit Gap 2: Main Menu Help Overlay** | Static footer `"←↑↓→ navigate • ↩ select • q quit"`, no `?` binding | Only 3 keys were present, skipped modal | Add `?` keybinding toggle opening categorized `renderHelpOverlay` (Navigation, Actions, Exit) matching all other screens. |
| **Audit Gap 3: Hex Drift in `list.go`** | `theme.RenderGradient("✦ MAIN MENU ✧", "#FF60FF", "#00A4FF")` (line 147) | Direct hex arguments bypassed `lint_colors.go` | Resolve gradient endpoints dynamically through `t.Token.Mauve` / `t.Token.Sky` or theme colors. |
| **Audit Gap 4: Hex Drift in `cli_art.py`** | `colors = ["#f9e2af", "#f5c2e7", ...]` (`thinking_status:1570`) | Hardcoded Catppuccin hexes in Python loader | Export standard palette tokens in `theme.py` and consume them in `cli_art.py`. |
| **Audit Gap 5: `main.go` Spring Doc Mismatch** | Docstring says `1.0` (critically damped); code uses `0.7` | Stale comment from early prototype | Update docstring to explain the intentional `0.7` underdamped organic bounce curve. |
| **Audit Gap 6: `lint_colors.go` Path Resolution** | Fails when invoked from repo root (`go run dashboard/tools/lint_colors.go`) | Hardcoded relative directory paths | Auto-detect base directory (`.` vs `dashboard/`) for seamless CLI and CI execution. |
| **Tier 1.1: `huh` Profile Wizard** | Stub in `wizard.go` with minimal styling | Vendored but unpolished | Full themed form with focus rings, field transition animators, and home-directory-aware file picker. |
| **Tier 1.2: `glamour` Markdown Rendering** | Custom fallback line parser in `viewer.go` | Word-wrap edge cases deferred Glamour | Integrate `glamour.NewTermRenderer` with `theme.GlamourConfig(t)` + safe line-wrap post-processor. |
| **Tier 1.3: Animated Status Pills** | Static colored blocks in `bars.go` | Static styling | Spring-based fill width + subtle hue cycle on hover/active states. |
| **Tier 2: Motion Design System** | Ad-hoc `harmonica.NewSpring` in `main.go` | No central presets | Shared `anim` package with typed presets (`Snappy`, `Organic`, `Elastic`, `Shake`). |
| **Tier 3: Flowing Gradient Wave** | Static RGB interpolation | Only computes one frame | Real-time hue shift `f(glyphIdx, time.Now())` during 60 FPS tick loop. |
| **UX Polish: Plain-Language Subtitles** | Technical terminology ("Bullet Bank", "Ingestion", "Liveness") | Engineering-centric naming | Translate all menus to user-centric, goal-driven actions with clear explanations. |
| **UX Polish: Empty-State Breadcrumbs** | `(empty file)` or dead ends when no jobs/reports exist | No guidance on next action | Actionable callout cards in every empty view telling users exactly what to run. |
| **UX Polish: 3-Step Guided Help** | Help screen lists developer flags | Missing practical user workflow | Add "The 3-Step Job Search Playbook" to Help modal and menu. |

---

## 3. Technical & Aesthetic Component Specifications

### 3.1 Unifying Menu & Sidebar Selection Languages

#### Problem
In `dashboard/internal/ui/menu/list.go`, selected items render with a solid Mauve background block (`delegate.Styles.SelectedTitle = selectedStyle`). Everywhere else (Jobs list, Pipeline sidebar in `bars.go`), active items use `HoverStyle`: a left-border `┃` in Mauve with adjusted horizontal padding.

#### Solution
1. Update `list.go` to use the left-border `┃` indicator:
   - Left border: `┃` (`t.Token.Mauve`).
   - Title: Bold `t.Token.Text` (or `t.Token.Mauve` for primary emphasis).
   - Description: Visible on selected item in `t.Token.Subtext`.
   - Normal (unselected) items: Left padding of 2 (no border), title in `t.Token.Text`, description dimmed or hidden.
2. Result: A 100% unified visual grammar across all list and table surfaces.

---

### 3.2 Main Menu Help Overlay (`?`)

#### Problem
`pipeline.go`, `jobs.go`, `progress.go`, and `viewer.go` all wire `?` to toggle `showHelp bool` and render `renderHelpOverlay(t, width, height, categories)`. The Main Menu only had a static footer line.

#### Solution
1. Add `showHelp bool` to `menu.MenuModel`.
2. Intercept `?` in `m.list.Update(msg)`:
   ```go
   case "?":
       m.showHelp = !m.showHelp
       return m, nil
   case "esc":
       if m.showHelp {
           m.showHelp = false
           return m, nil
       }
   ```
3. In `View()`, if `m.showHelp` is true, render `renderHelpOverlay`:
   - **Navigation**: `↑ / ↓ / j / k` (Move selection), `Home / End` (Jump to top/bottom).
   - **Actions**: `Enter` (Select menu item), `/` (Filter items).
   - **General**: `?` (Toggle help overlay), `q / Ctrl+C` (Exit dashboard).
4. Update the footer bar to include `? help`:
   `"←↑↓→ navigate • ↩ select • ? help • q quit"`

---

### 3.3 Glamour-Powered Markdown Viewer (`viewer.go`)

#### Problem
`viewer.go` currently uses a handwritten 400-line Markdown-to-terminal parser to avoid long unbroken token wrapping bugs. This produces plain text that misses Glamour's magazine-quality formatting (styled blockquotes, distinct header weights, themed syntax highlighting, and elegant tables).

#### Solution
1. Leverage `glamour.NewTermRenderer` configured with `theme.GlamourConfig(m.theme)`:
   ```go
   r, err := glamour.NewTermRenderer(
       theme.GlamourConfig(m.theme)...,
   )
   out, err := r.Render(m.rawContent)
   ```
2. Implement a post-processing wrap pass on `out` using `ansi.Wrap(line, m.width - 4, "")` to guarantee unbreakable tokens and code lines never cause horizontal layout corruption or clipping.
3. Fallback: If Glamour rendering returns an error, gracefully fall back to the clean line parser.
4. Add live viewport scrolling (`PgUp`, `PgDn`, `j`, `k`, `g`, `G`, mouse wheel when enabled) with smooth clamp boundaries.

---

### 3.4 Shared Physics Engine (`anim` Package)

#### Architecture
Create `dashboard/internal/ui/anim/springs.go` providing standard, mathematically tuned Harmonica spring curves:

```go
package anim

import "github.com/charmbracelet/harmonica"

// Presets for different UI interaction moods.
var (
    // Snappy: Fast, responsive transitions (list hovers, cursor moves).
    Snappy = harmonica.NewSpring(harmonica.FPS(60), 12.0, 0.8)

    // Organic: Gentle bounce for screen reveals and sidebars.
    Organic = harmonica.NewSpring(harmonica.FPS(60), 7.0, 0.7)

    // Elastic: High-energy pop for score pill fills and celebratory badges.
    Elastic = harmonica.NewSpring(harmonica.FPS(60), 20.0, 0.9)

    // Impulsive: Underdamped oscillation for error shakes / invalid actions.
    Shake = harmonica.NewSpring(harmonica.FPS(60), 25.0, 0.4)
)
```

- Every animated component queries `reducedMotion()`:
  ```go
  func ReducedMotion() bool {
      return os.Getenv("RESUME_BUILDER_MOTION") == "reduced"
  }
  ```
- If `ReducedMotion()` is true, animations jump immediately to target values (`t = 1.0`), ensuring instant accessibility compliance.

---

### 3.5 Flowing Dynamic Gradient Waves

#### Mechanics
In `theme/theme.go`, upgrade `RenderGradient` and introduce `RenderFlowingGradient`:

```go
// RenderFlowingGradient calculates a dynamic, traveling color wave across text
// based on character index, time offset, and palette endpoints.
func RenderFlowingGradient(text string, startHex, endHex string, tOffset float64) string
```

- Each character's interpolation weight $w_i$ is computed as:
  $$w_i = \frac{1 + \sin\left(\frac{2\pi \cdot i}{N} - tOffset\right)}{2}$$
- On each ~60 FPS tick, the header banner (`✦ MAIN MENU ✧`, `✦ PIPELINE ✧`, `✦ PROGRESS ✧`) advances `tOffset += 0.05`.
- Generates a shimmering, living header banner that moves smoothly across the screen without taxing CPU.

---

### 3.6 Python CLI & Menu Polish (`cli_art.py` & `theme.py`)

1. **Catppuccin Palette Tokens in `theme.py`**:
   Define canonical hex values in `theme.py`:
   ```python
   PEACH = "#f9e2af"
   PINK = "#f5c2e7"
   MAUVE = "#cba6f7"
   LAVENDER = "#b4befe"
   BLUE = "#89b4fa"
   SKY = "#89dceb"
   ```
2. **`cli_art.thinking_status()` Refactor**:
   Import `[PEACH, PINK, MAUVE, LAVENDER, BLUE, SKY]` directly from `theme.py`.
3. **`display_success_celebration()` Upgrade**:
   Replace full-screen clearing with an in-place Rich `Live` render containing animated particle sparkles (`✦ ✧ · ✨`) that settle cleanly into the `ACHIEVEMENT UNLOCKED` panel.
4. **Automated Verification**:
   Make `lint_colors.go` inspect all Go and Python theme paths during `resume doctor`.

---

## 4. Compassionate UX Architecture for Non-Technical & ADHD Job Seekers

### 4.1 Plain-Language Mental Model & Jargon Translation
To prevent cognitive fatigue and intimidation, all technical terms in menus and CLI prompts are translated into user-centric benefits:

| Internal / Technical Term | User-Facing Label & Plain-Language Subtitle | Why This Helps |
|---|---|---|
| **Bullet Bank** | **Bullet Bank (Your Master Accomplishment Vault)**<br>*(Your central library of career wins, tailored automatically for each job)* | Removes mystery; explains that they don't have to rewrite their resume from scratch every time. |
| **Document Ingestion / Phase 0** | **Import Past Resumes / CV**<br>*(Upload your existing PDF or text resume so the AI learns your background)* | Clear call to action; no confusing "Phase 0" dev language. |
| **Liveness Gate** | **Verify Job is Still Open**<br>*(Checks if the posting is active so you never waste time applying to expired jobs)* | Answers "Why should I care about this?" immediately. |
| **ATS Classification / Front-Loading** | **Recruiter & ATS Optimization**<br>*(Aligns key skills to pass applicant tracking systems & catch recruiter attention)* | Clear value proposition for non-tech job seekers. |
| **Express Setup** | **⚡ Express Auto-Pilot (Recommended)**<br>*(Sets up your profile and achievement vault in 2 minutes automatically)* | Provides one obvious "Happy Path" button to combat decision paralysis. |

---

### 4.2 "Never Get Stuck" Actionable Breadcrumbs & Empty States
When a user visits a screen with no data yet, they must never see a blank screen or a cryptic error. Every empty state provides a warm, 1-step action plan:

#### In the Go Dashboard (`dashboard/`):
- **Empty Jobs Tab**:
  ```
  ✦ NO JOBS SAVED YET ✦
  
  Ready to find your next opportunity?
  1. Open your terminal and run: resume scan (to auto-find postings)
  2. Or run: resume package <job_url> (to build a resume for a link immediately)
  ```
- **Empty Pipeline Tab**:
  ```
  ✦ NO ACTIVE APPLICATIONS ✦
  
  Your pipeline tracks applications from draft to interview.
  • Select a job in the Jobs tab (press 'j') to start tailoring!
  ```
- **Empty Reports Tab**:
  ```
  ✦ NO REPORTS SELECTED ✦
  
  Reports show detailed match scores, keyword audits, and hiring odds.
  • Open Pipeline ('p') or Jobs ('j') and press Enter on any role to view its report.
  ```

#### In the Python Interactive Menu (`menu.py`):
- If the user clicks **Build Documents** but has no pending jobs saved:
  ```
  💡 No jobs in your queue yet!
  
  Let's add one in 10 seconds:
  ➔ [1] Scan for new jobs from online boards
  ➔ [2] Paste a job posting URL or text manually
  ➔ [3] Back to Main Menu
  ```
  *(Automatically routes them to add a job instead of kicking them back with an error!)*

---

### 4.3 The "3-Step Job Search Playbook" (Accessible via `?` and Help Menu)
A dedicated, crystal-clear guide that gives anyone the entire workflow in 3 bullet points:

```
✦ ─── HOW RESUME BUILDER WORKS IN 3 SIMPLE STEPS ─── ✦

1. 📥 STEP 1: IMPORT YOUR EXPERIENCE (One time only)
   Upload your current resume or LinkedIn export. We extract your achievements 
   into your Master Vault so you never have to re-type them.

2. 🎯 STEP 2: PICK A JOB
   Found a role you like? Paste the job link or run 'Find Jobs' to browse.

3. 🚀 STEP 3: BUILD YOUR APPLICATION (1 Click!)
   Run 'Build Full Application Package' ➔ Get a 100% tailored, ATS-optimized 
   Resume (PDF + DOCX) and a personalized Cover Letter in seconds!

💡 Need help? Press '?' on any dashboard screen or select Help in the menu.
```

---

### 4.4 Low-Friction Reassurance & Dopamine Micro-Copy
- **Warm Welcome**: If a user runs the app for the first time without a profile, greet them warmly:
  `"👋 Welcome! Let's get you set up in 2 quick minutes so you can start landing interviews."`
- **Milestone Celebrations**: When a resume is generated, celebrate their progress with motivating, gentle copy:
  `"🎉 Application Package Ready! Every tailored resume brings you closer to your dream role."`
- **Soft Error Handling**: If an API key or file is missing, provide a single copy-paste fix with no intimidating stack traces.

---

## 5. Verification & Testing Strategy

1. **Color Token Linter (`dashboard/tools/lint_colors.go`)**:
   - Verify zero hardcoded hex strings in `internal/ui`, `internal/theme`, `internal/model`, `internal/data`, `cmd`, and `main.go`.
   - Ensure `lint_colors.go` runs seamlessly from both repo root and `dashboard/`.
2. **Go Unit & Component Tests**:
   - `viewer_test.go`: Test Glamour rendering, fallback behavior, and width clamping.
   - `menu_test.go`: Test `?` help toggle, selection cursor navigation, and `HoverStyle` formatting.
   - `bars_test.go`: Test animated score badges and empty state starfields.
   - `pipeline_test.go` & `jobs_test.go`: Verify table formatting and keybinding modals.
3. **Python Test Suite**:
   - `tests/test_cli_art.py`: Test `make_gradient_text`, `thinking_status`, and HUD rendering.
   - `tests/test_theme_sync.py`: Verify Python and Go color token parity.
   - `tests/test_menu_ux.py`: Verify plain-language menu choices, breadcrumbs, and empty-state fallbacks.
   - Complete suite: Run all 1,663+ Python unit tests to guarantee zero regressions.

---

## 6. Next Steps

Upon review and approval of this expanded design specification:
1. We will author the granular **Implementation Plan** (specifying file modifications, test cases, and commit milestones).
2. We will implement using our strict **TDD workflow** (test first, verify failing, implement, verify passing).
