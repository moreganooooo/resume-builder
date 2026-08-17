# TUI Polish Blueprint — "All Out / Unhinged Shiny"

> Companion to `TUI_AUDIT_PROMPT.md`. Captures every polish opportunity found
> during the audit *plus* a brainstormed "ignore practicality" wishlist for a
> terminal UI that feels alive. Use this as the north star + backlog for
> making `resume-builder`'s CLI/TUI "unbelievably shiny, polished, modern,
> sparkly, animated."

---

## 0. Audit recap (status of every item in TUI_AUDIT_PROMPT.md)

| # | Audit Objective | Audit Finding | Status |
|---|---|---|---|
| 1 | Frame locking & alt-screen scroll protection | All interactive entryppoints (`menu.py:2090`, `bootstrap_menu.py:113/168/218`, `menu.py:1022/1157/2055`) lock `\x1b[5;{rows-1}r` + `try/finally` restore of `\x1b[r`; alt-screen via `\x1b[?1049h/l` | ✅ Compliant |
| 2a | Lip gloss / color tokens | All colors route through `theme.Theme` fields; color linter clean | ✅ Compliant |
| 2b | Gradient title banners (char-by-char lerp) | Python `cli_art.make_gradient_text` (1670) + `_gradient_grid`; Go `theme.RenderGradient` (`theme/theme.go:142`) | ✅ Compliant |
| 2c | Active list selection = left-border `┃` + HoverStyle | Go sidebars use `HoverStyle` (layout.go:23); main MENU list uses Mauve bg-fill — see Minor Gap #1 | ✅ + ⚠️ see fixes |
| 2d | Harmonica physics motion | `main.go:104` uses `harmonica.NewSpring(FPS(60), 7.0, 0.7)` | ✅ + ⚠️ stale comment |
| 2e | "Thinking" dynamic gradient-wave | `cli_art.thinking_status` (1562) cycles Peach/Pink/Mauve/Lavender/Blue/Sky | ✅ Compliant |
| 2f | Empty/zero states starfield | Go `renderEmptyDetailPane` (bars.go:159-260) = time-driven `✦ ✧ ·` twinkling + label | ✅ Compliant |
| 3a | No "wall of text" / breathing room | Panels padded (cli_art `padding=(0,2)`; Go `PadHorizontal`/`detailPaneStyles`); tables have gaps | ✅ Compliant |
| 3b | Categorized `?` keybinding overlay | `bars.go:296` `renderHelpOverlay`; Jobs/Pipeline/Progress/Viewer each wire `?` → modal, dismissed `?, esc, q` | ✅ + ⚠️ see Minor Gap #2 |
| 3c | Responsive width (ansi.Truncate/wrap) | Go `fitBar` (bars.go:40) + `truncateRunes`; Python Rich `soft_wrap`/panel width | ✅ Compliant |
| 4a | Go color linter runs | `tools/lint_colors.go` passes clean | ✅ Compliant |
| 4b | No hardcoded hex bypassing tokens | Linter covers `internal/ui`, `internal/theme`, `internal/model`, `internal/data`, `cmd`, `main.go` | ✅ Compliant |

### Tiny audit fixes (already noted, listed here so nothing is lost)

- **`main.go:87-88` stale doc comment**: `startTransition` says "damping of 1.0
  is critically damped — no bounce/overshoot," but the code uses `0.7`
  (underdamped = the intended organic spring bounce). Fix the comment to
  match `0.7` (or note both: 1.0 = critically damped, 0.7 = the chosen
  bouncier curve the audit explicitly recommends).
- **Python `thinking_status` hardcodes Catppuccin hexes** (`cli_art.py:1570`)
  instead of `theme.py` tokens — only safe today because `theme.py` exposes
  no pastel shades. Low risk, but if a future palette change touches those,
  it's a drift vector outside linter scope.

### Minor Gap #1 — menu list selection visuals
`dashboard/internal/ui/menu/list.go` selected row uses a **Mauve background fill**
(`selectedStyle`, lines 52-55) rather than the left-border `┃` indicator the
audit specifically calls out for "active list selections." The sidebars
(`bars.go` `HoverStyle`) *do* use the `┃` border. The bg-fill is deliberately
high-contrast (comment verifies 4.5:1+ across all themes), so it's not a
regression — but it's visually inconsistent with the sidebar's border style.
Consider making the menu use `HoverStyle` too for a unified "active = border
glow" language.

### Minor Gap #2 — Main Menu has no `?` overlay
The Main Menu footer (`list.go:172`) is a single packed line
`"←↑↓→ navigate • ↩ select • q quit"` with no `?` help binding. It only
carries 3 bindings (never "overcrowded"), so it's within the spirit of the
rule — but every *other* screen has the categorized `?` overlay. For
consistency, add a minimal `?` overlay to the menu too (Navigation + Exit).

---

## 1. Tier-1 lift (flip already-vendored deps — do these first)

### 1.1 `huh` profile wizard
- **Dep:** `charmbracelet/huh` (in `go.mod:8` already, currently unused).
- **Where:** build a real Go form in `dashboard/internal/ui/bootstrap/wizard.go`
  (stub exists) + wire from `cmd/bootstrap/main.go`. Migrate the onboarding
  identity/tags/cv.md flow off `scripts/bootstrap_profile.py`'s raw questionary
  prompts.
- **Shine:** themed forms, focus rings, `glamour`-styled help, smooth field
  transitions via `huh`'s built-in animators.

### 1.2 Glamour-powered markdown preview
- **Dep:** `charmbracelet/glamour` (`theme/glamour.go` already themed!).
- **Where:** `internal/ui/screens/viewer.go` — swap plaintext report output for
  `glamour.NewTermRenderer(theme.GlamourConfig(...)...)`.
- **Shine:** code blocks, tables, and headings render in your palette; CV/cover
  letter preview becomes magazine-quality.

### 1.3 Animated status pills
- **Where:** `bars.go` `scoreStyle`/`scoreIcon` badges.
- **Shine:** spring the fill-width and run a `tea.Tick` that shifts the
  `RenderGradient` endpoints so badges color-cycle / "breathe."

---

## 2. Tier-2 motion language (extend existing physics)

- **Physics design system** — a shared `anim/` package of `harmonica.Spring`
  presets, all gated behind `RESUME_BUILDER_MOTION=reduced`:
  - list hover: `Spring(12, 0.8)` fast snappy
  - sidebar open: `Spring(7, 0.7)` organic bounce (already in main.go)
  - score fill: `Spring(20, 0.9)` tight elastic "pop"
  - menu shake (error): underdamped impulse
- **Parallax depth layers** — split render into z0 (starfield), z1 (chrome),
  z2 (content); lateral navigation moves z0 at 0.3× via `x/cellbuf`
  compositing.
- **Depth-aware `HoverStyle`** — extend `layout.go:23` to optionally emit a
  twinkling left `┃` + a single animated `✦` apex at the active row's top.
- **Lipgloss v2 table** for the Jobs list — striped rows + hover tints on the
  existing two-line `renderSidebarRow` shape.

---

## 3. Tier-3 "ignore practicality" wishlist (unhinged shiny)

### 3.1 Terminal VJ / reactive canvas
Transparent `x/cellbuf` particle canvas behind `View()` at 30 FPS: every Gemini
call, pipeline tick, or keypress emits particles from the cursor that drift on
a spring field and fade along a `✦ ✧ ·` gradient. Terminal *breathes*.

### 3.2 Flowing per-character gradient wave
`theme.RenderGradient` is static lerp. Make it **flow**: re-derive each
glyph's color per `tea.Tick` as `f(glyphIndex, time.Now())` → a hue-shift
wave crawling across title banners and pills. Gated by `RESUME_BUILDER_MOTION`.

### 3.3 Huh "card-stack" form navigation
Each `huh` field set = a swipeable card stack: fields slide in on springs, and
"submit" does a terminal-3D flip (fade old out as new slides up from baseline).

### 3.4 Context-aware "weather" theming
Shift the whole palette in real time off your actual weather / search intensity:
cloudy day → desaturate accents 20%; active pipeline → bump saturation &
brightness. Gradients re-derive from the shifted token map.

### 3.5 Living brand-accent system
Replace fixed `BRAND_ACCENT` with a **procedural accent** seeded by the active
job-title hash → unique, WCAG-verified pastel per context, re-theming borders
and pills live. Same motion language, different color per role.

### 3.6 Director's mode
`resume dashboard --demo` runs a scripted timeline: particles on cue, menu
auto-selects + springs through screens, a golden `✦` traces focus, HUD ticks
off each polish rule. Ships the README reel.

### 3.7 Particle celebration
Upgrade `display_success_celebration` (`cli_art.py:1692`) from a 12-frame
screen-clear flash to a `harmonica`-eased scale + `✦` confetti emitter.

---

## 4. Implementation priority

1. **Showcase piece first:** flowing gradient wave across the Main Menu header
   (`✦ MAIN MENU ✧`) + breathing starfield in empty states. Uses only
   `time.Now()` + re-rendered lipgloss styles under the existing tick loop.
   Highest perceived-aliveness per lines-of-code.
2. Then 1.1–1.3 (flip the unused glamour/huh deps that are already downloaded).
3. Then 2.x (motion system + parallax).
4. Then 3.x (VJ canvas / director mode) only if you want to go full demo-reel.

---

## 5. Verification gates (re-run after each layer)

- `cd dashboard && go test ./...`
- `go run dashboard/tools/lint_colors.go`  (no hardcoded hex — re-check after
  any new accent logic!)
- `source .venv/bin/activate && python -m unittest discover -s tests`
- `resume doctor`  (color-lint + theme-sync gates included)

Keep `tools/lint_colors.go` green as the non-negotiable guardrail: every new
animated accent / color must still resolve through `theme.Theme` fields.
