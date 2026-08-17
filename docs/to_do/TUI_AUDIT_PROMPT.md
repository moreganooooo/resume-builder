# TUI & Charmbracelet Audit Guide

A re-runnable audit framework and prompt for AI coding assistants to review, refine, and elevate the Terminal User Interface (TUI) and Charmbracelet ecosystem integration across `resume-builder`.

---

## 🤖 AI Agent Prompt Template

```markdown
# TASK: TUI & Charmbracelet Ecosystem Design, Usability & Architecture Audit

Perform a comprehensive UX, visual craft, and architectural review of the CLI/TUI screens across both the Python CLI (`scripts/`) and Go Bubble Tea Dashboard (`dashboard/`). Identify opportunities to elevate visual design, fix layout bugs, and incorporate advanced Charmbracelet ecosystem components.

---

## 🎯 AUDIT OBJECTIVES & SCOPE

### 1. Frame Locking & Alternate Screen Scroll Protection
- **Issue to catch**: Long-running commands, subprocess logs, or menu transitions outputting raw text that pushes fixed graphic banners or sticky command footers off the visible screen.
- **Checklist**:
  - [ ] Inspect all entrypoints and submenus (`menu.py`, `bootstrap_menu.py`, `cli.py`).
  - [ ] Ensure subprocess runs and streaming logs are wrapped in double-locked ANSI scrolling regions (`\x1b[<top>;<bottom>r`), freezing top headers (rows 1–4) and bottom command footers (`rows`).
  - [ ] Confirm `try...finally` or cleanup handlers restore full-screen terminal scrolling (`\x1b[r`) on completion, crash, or interrupt.

### 2. Charmbracelet Ecosystem & Visual Craft Polish Pass
- **Lip Gloss & Color Tokens**:
  - [ ] Audit screen titles, list items, and status badges.
  - [ ] Ensure all status tags use high-contrast background-colored pill badges (e.g. `Background(statusColor).Foreground(t.Base)`).
  - [ ] Verify multi-color title banners use character-by-character linear interpolation gradients (`theme.RenderGradient`).
  - [ ] Confirm active list selections use left-border indicators (`┃`, `HoverStyle`) with tokenized accent colors.
- **Harmonica Physics Motion**:
  - [ ] Check screen reveal animations in Go (`main.go`). Ensure transition springs use a tuned physics curve (e.g., `harmonica.NewSpring(FPS(60), 7.0, 0.7)` for a subtle, organic spring bounce).
- **Dynamic & Reactive States**:
  - [ ] Inspect "Thinking" or long-running AI API calls (e.g., Gemini calls in Python). Ensure they use dynamic, color-shifting gradient-wave indicators (`cli_art.thinking_status`).
  - [ ] Inspect empty/zero states (e.g. "no item selected" detail panes). Ensure they utilize ambient visual elements (e.g., coordinate-hashed, time-driven twinkling "Starry Night" starfields `✦ ✧ ·`).

### 3. Layout, Spacing & Information Hierarchy
- **Anti-Pattern Check**:
  - [ ] Identify "wall of text" screens lacking vertical whitespace or categorized visual groupings.
  - [ ] Verify keybindings are organized into categorized overlays (`?` key) rather than overcrowded single-line footers.
  - [ ] Ensure internal content components adjust fluidly to varying terminal dimensions (e.g. truncating cleanly with `ansi.Truncate` or wrapping properly).

### 4. Design System Discipline & Color Linting
- **Strict Compliance**:
  - [ ] Run the Go dashboard color linter (`dashboard/tools/lint_colors.go` or `resume doctor`).
  - [ ] Confirm no hardcoded hex strings or un-tokenized ANSI escapes bypass the Catppuccin Mocha / Charmtone design system tokens (`theme.Theme`).

---

## 🧪 VERIFICATION & QUALITY GATE

Before declaring the audit complete, execute and verify:
1. **Go TUI Package Suite**: `cd dashboard && go test ./...`
2. **Dashboard Color Linter**: `go run dashboard/tools/lint_colors.go`
3. **Python Test Suite**: `source .venv/bin/activate && python -m unittest discover -s tests`
4. **Environment Health Check**: `resume doctor`

Report all findings, implemented fixes, and test results clearly upon completion.
```

---

## 📚 Charmbracelet Ecosystem Resource Directory

Here is a curated directory of **Charmbracelet** libraries, tools, and repositories applicable to `resume-builder` now and for future enhancements:

### 🎨 Styling & Animation Libraries
* **[charmbracelet/lipgloss](https://github.com/charmbracelet/lipgloss)**: Style definitions, alignment, borders, layout compositing, and truecolor support. Used extensively across the dashboard for layout frames, pills, and custom text gradients.
* **[charmbracelet/harmonica](https://github.com/charmbracelet/harmonica)**: Physics-based animation engine for smooth terminal motion (springs, dampening, spring bounce screen reveals).
* **[charmbracelet/glamour](https://github.com/charmbracelet/glamour)**: Markdown rendering engine for the terminal. Powers stylesheet-driven rendering of tailored CV preview reports, cover letters, and job descriptions in `viewer.go`.

### 🏗️ TUI Frameworks & Component Libraries
* **[charmbracelet/bubbletea](https://github.com/charmbracelet/bubbletea)**: The Elm-architecture TUI framework for Go powering the main interactive dashboard.
* **[charmbracelet/bubbles](https://github.com/charmbracelet/bubbles)**: Core TUI component library including list selectors, scrollable viewports, text inputs, progress bars, and help overlays.
* **[charmbracelet/huh](https://github.com/charmbracelet/huh)**: Lightweight interactive form builder for terminal applications. Excellent for multi-field profile setup, onboarding wizard flows, or status updating prompts.

### 🛠️ Utilities & CLI Utilities
* **[charmbracelet/gum](https://github.com/charmbracelet/gum)**: Shell script toolset providing interactive terminal primitives (`gum choose`, `gum input`, `gum confirm`, `gum spin`). Used in `resume-cli.sh` for profile selection dialogs.
* **[charmbracelet/log](https://github.com/charmbracelet/log)**: Human-readable, structured, colorful logging library with level-based formatting.
* **[charmbracelet/vhs](https://github.com/charmbracelet/vhs)**: Terminal GIF recorder driven by `.tape` scripts. Ideal for generating automated, high-definition animated terminal demos for `README.md`.
* **[charmbracelet/freeze](https://github.com/charmbracelet/freeze)**: Tool for generating high-resolution PNG image snapshots of terminal outputs and code blocks for documentation and portfolio showcases.

### 🌐 Advanced & Remote Application Capabilities
* **[charmbracelet/wish](https://github.com/charmbracelet/wish)**: SSH server framework for hosting Bubble Tea applications over SSH. Allows serving the `resume dashboard` as a zero-install remote SSH app (e.g., `ssh resume.yourdomain.com`).
* **[charmbracelet/pop](https://github.com/charmbracelet/pop)**: Terminal email sending utility. Useful for emailing generated PDF resumes or follow-up notes directly from the command line.
