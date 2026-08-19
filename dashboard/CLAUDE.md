# dashboard/ (Go module)

- `dashboard/` is a native Go module leveraging the Charmbracelet ecosystem (Bubble Tea v2, Lip Gloss v2, Glamour Markdown, Harmonica physics, and Huh forms, launched via `resume dashboard`).
  - Pre-compilation: `scripts/dashboard.py` and `scripts/charm_prompt.py` dynamically compile their Go binaries (`dashboard/bin/dashboard` and `dashboard/bin/prompt`) on first launch for sub-millisecond execution (gitignored - never committed). They gracefully fall back to slow `go run` or Questionary prompts if Go is unavailable.
  - Interactive Screens: Includes Pipeline checkpoint tracker, Jobs accordion browser, Knowledge Base Explorer (`viewKB` for browsing tools, metrics, facts, and projects with Glamour-rendered markdown viewports and live substring filtering), Progress monitor with Bubbles progress bars, and Report view.
  - Harmonica Physics & Responsive Viewport: Smooth spring-eased reveal animations and automatic terminal resize reflow with 80x24 minimum viewport warning cards.
  - **Visual TUI Inspection**: Generate high-DPI retina snapshots with `python3 scripts/capture_tui_visuals.py --out artifacts/tui_capture.png`. Claude can read/view `artifacts/tui_capture.png` directly to visually audit terminal layout, alignment, and color contrast.
  - **VHS Recordings**: Tapes located in `dashboard/tapes/` (`menu.tape`, `pipeline.tape`, `jobs.tape`, `kb_view.tape`, `mobile.tape`) record animated GIFs via `vhs <tape_path>`.
  - **Android & Mobile Termux**: Termux (`TERMUX_VERSION`) and mobile mode (`RESUME_BUILDER_MOBILE=1`) are auto-detected, relaxing minimum terminal dimensions to 35x12 and enabling full touch/tap navigation via `tea.WithMouseCellMotion()`. Run `./scripts/build_mobile.sh` to cross-compile static ARM64/AMD64 binaries into `dist/mobile/`. Slash commands `/visual-tui`, `/build-mobile`, and `/audit-tui` are available in `.claude/commands/`.
- **`dashboard/` was vendored from the `career-ops` sibling repo's
  `dashboard/` on 2026-07-22** (themed to this project's palette/icons,
  plus two real bugs fixed there — a tracker-column-count mismatch and a
  narrow-terminal crash). This repo's copy is authoritative going
  forward; `career-ops/dashboard/` is not where future dashboard changes
  should land, and may drift stale over time. See `docs/IDEAS_ARCHIVE.md`
  for the full writeup.
