repo: moreganooooo/resume-builder
branch: main

## Last sync

date: 2026-09-21T03:05:00Z

### Updated in this project

- Built the design system from scratch: tokens, 20 foundation cards, 26 components, 2 UI kits.
- TUI palette taken from the shipped dashboard theme, not DESIGN.md's declared brand pair (both tokenized).
- Print scale lifted verbatim from the resume and cover-letter templates.
- Palette divergence (deliberate, documented in readme.md "Three accents diverge from upstream"): Pink #ff84ff -> Teal #12e6c8, Sky #8b75ff -> #a47bff, Green #12c78f -> #9ab63f.
- Font binaries are gitignored upstream; the user supplied them directly — DM Serif Display / DM Sans now load locally from `assets/fonts/`.

## Screen map

| Project screen / file | Repo files |
| --- | --- |
| `tokens/colors.css` | `scripts/theme.py`, `dashboard/internal/theme/{resumebuilder,catppuccin,tokens}.go`, `DESIGN.md`, `.impeccable/design.json` |
| `tokens/typography.css`, `tokens/spacing.css` | `resume-engine/templates/cv-template.html`, `dashboard/internal/theme/layout.go` |
| `tokens/motion.css` | `dashboard/internal/anim/anim.go` |
| `tokens/surfaces.css`, `guidelines/brand-glyphs.card.html` | `scripts/theme.py`, `dashboard/internal/theme/icons.go` |
| `components/terminal/*` | `dashboard/internal/ui/screens/bars.go`, `dashboard/internal/ui/menu/list.go`, `dashboard/internal/theme/theme.go` |
| `components/data/*` | `dashboard/internal/ui/screens/{bars,jobs,progress}.go` |
| `components/print/*` | `resume-engine/templates/cv-template.html` |
| `ui_kits/dashboard/MainMenu.jsx` | `dashboard/internal/ui/menu/list.go` |
| `ui_kits/dashboard/PipelineScreen.jsx` | `dashboard/internal/ui/screens/pipeline.go` |
| `ui_kits/dashboard/JobsScreen.jsx` | `dashboard/internal/ui/screens/jobs.go` |
| `ui_kits/dashboard/ProgressScreen.jsx` | `dashboard/internal/ui/screens/progress.go` |
| `ui_kits/dashboard/KBScreen.jsx` | `dashboard/internal/ui/screens/kb.go` |
| `ui_kits/resume/Resume.jsx` | `resume-engine/templates/cv-template.html` |
| `ui_kits/resume/CoverLetter.jsx` | `resume-engine/templates/coverletter-template.html` |
| `assets/app_icon.png`, `assets/macos_icon.png` | `assets/` |
| `readme.md` | `DESIGN.md`, `PRODUCT.md`, `.impeccable/surface-dashboard.md`, `dashboard/CLAUDE.md` |
