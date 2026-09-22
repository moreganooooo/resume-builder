# UI kit — Dashboard (TUI)

A click-through recreation of the Go / Bubble Tea terminal dashboard, launched
in the real product with `resume dashboard`.

**Screens**

| File | Source |
| --- | --- |
| `MainMenu.jsx` | `dashboard/internal/ui/menu/list.go` |
| `PipelineScreen.jsx` | `dashboard/internal/ui/screens/pipeline.go` |
| `JobsScreen.jsx` | `dashboard/internal/ui/screens/jobs.go` |
| `ProgressScreen.jsx` | `dashboard/internal/ui/screens/progress.go` |
| `KBScreen.jsx` | `dashboard/internal/ui/screens/kb.go` |
| shared chrome | `dashboard/internal/ui/screens/bars.go` |
| `data.js` | shapes from `dashboard/internal/model/{job,career}.go`; values invented |

**What works**

Keyboard-first, as the product is. From the menu, click or press a row to open a
screen; `Esc` returns.

- **Pipeline** — `j`/`k` or arrows move the selection, `h`/`l` cycle the eight
  filter tabs, `/` opens live search, `?` opens the categorised help overlay,
  `o` fires the "no URL saved" notice.
- **Jobs** — `j`/`k`, `/` search, `t` runs a fake tailor (3-line-thick
  determinate progress bar), `s` runs a fake scan (indeterminate spinner). The
  NEXT BEST MOVE banner appears when a pending role scores ≥ 4.0.
- **Progress** — scrolls through funnel, drill-down, score distribution,
  conversion rates, strategy radar, platform yield, employer concentration,
  the coverage quadrants and Mission Control (heatmap + sparklines).
- **Knowledge Base** — `Tab` cycles categories, `/` filters, rows invert on
  selection.
- Select nothing and the detail pane fills with the twinkling starfield and the
  screen's own `[ key ]` hints.

**What is faked**

Everything behind the UI. No subprocess runs, no scoring happens, `Enter` does
not open a report, and status changes are not persisted. Scroll is browser
scroll rather than the product's measured row budget.

**One substitution**

The product renders in the user's terminal font — Nerd Font by default, with a
plain-Unicode fallback under `RESUME_BUILDER_ICONS=unicode`. Nerd Font glyphs
are Private Use Area code points and cannot render in a browser, so this kit
uses the Unicode fallback set throughout, in JetBrains Mono.
