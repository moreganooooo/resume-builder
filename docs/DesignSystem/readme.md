# resume-builder — Design System

An end-to-end, LLM-powered job application management system. It aggregates job
descriptions from many sources, scores each role by *realistic interview
probability* rather than keyword overlap, tailors resumes and cover letters from
a personal bullet bank, and tracks the whole application pipeline — all locally,
with no subscription.

The product is deliberately two things at once, and the design system carries
both:

1. **A terminal dashboard** (Go + the Charm ecosystem: Bubble Tea v2, Lip Gloss
   v2, Bubbles, Huh, Glamour, Harmonica). Vibrant, tactile, animated, and
   designed with the same rigor as a modern web dashboard.
2. **A print artifact** — the generated PDF resume. Pure black, white, and gray;
   DM Serif Display against DM Sans; no ornament, strict page budgets, ATS-safe.

DESIGN.md calls the north star **"The Command Center Editor."** The governing
rule is **The No-Bleed Rule**: *Print colors never bleed into the TUI, and TUI
neons never bleed into the print output. The boundary is absolute.*

---

## Sources

Everything in this system was read from one repository:

- **https://github.com/moreganooooo/resume-builder** (branch `main`)

Explore it further to build more accurately — especially these files, which are
where every value here came from:

| What | Where |
| --- | --- |
| Design narrative, colors, type scale, do/don't | `DESIGN.md`, `.impeccable/design.json` |
| Product positioning, users, principles | `PRODUCT.md` |
| Dashboard surface brief (topology, states) | `.impeccable/surface-dashboard.md` |
| CLI palette + icon sets (source of truth) | `scripts/theme.py` |
| Dashboard theme structs | `dashboard/internal/theme/*.go` |
| Shared TUI primitives (bars, overlays, footers) | `dashboard/internal/ui/screens/bars.go` |
| Pipeline / Jobs / Progress / KB screens | `dashboard/internal/ui/screens/{pipeline,jobs,progress,kb}.go` |
| Main menu | `dashboard/internal/ui/menu/list.go` |
| Spring physics + confetti | `dashboard/internal/anim/anim.go` |
| Print resume template (all print CSS) | `resume-engine/templates/cv-template.html` |
| Cover letter template | `resume-engine/templates/coverletter-template.html` |
| App icon (the brand mark) | `assets/app_icon.png` |

There is **no Figma file, no marketing website, and no web GUI** — "Out of
Scope: … any web-based GUI" (`.impeccable/surface-dashboard.md`). Everything in
this system is either the terminal product or the printed product.

---

## Index

| File / folder | What it is |
| --- | --- |
| `styles.css` | The one stylesheet consumers link. `@import`s everything below. |
| `tokens/colors.css` | TUI + print palettes, semantic aliases, score/status/tag colors |
| `tokens/typography.css` | DM Serif Display / DM Sans / mono stacks, print pt scale |
| `tokens/spacing.css` | Terminal cell metrics, Lip Gloss padding, print gaps |
| `tokens/motion.css` | Harmonica spring curves, tick rates, dim fraction |
| `tokens/surfaces.css` | Borders, radii, box-drawing + glyph tokens, ramps |
| `tokens/fonts.css` | Webfont loading (see Font substitution, below) |
| `guidelines/` | Foundation specimen cards (colors, type, motion, glyphs, states, content, layout, mouse) |
| `components/terminal/` | TUI chrome: panels, bars, tabs, rows, overlays |
| `components/data/` | Score/status/tag/bar/sparkline data display |
| `components/print/` | The resume PDF primitives |
| `ui_kits/dashboard/` | Click-through recreation of the TUI dashboard |
| `ui_kits/resume/` | The generated one-page resume PDF |
| `templates/` | Starting points consuming projects copy (see Templates, below) |
| `assets/` | `app_icon.png`, `macos_icon.png`, `glamour-resumebuilder.json` |
| `SKILL.md` | Agent Skills entry point |
| `thumbnail.html` | Homepage tile |
| `github.md` | Upstream source association + screen map |

---

## Templates

Twelve starting points live under `templates/<slug>/`. Each is one `.dc.html` entry
plus a `ds-base.js` that links this system's stylesheet and bundle.

| Template | What it starts |
| --- | --- |
| `tui-screen` | Empty split-pane screen with the full chrome stack, measured and in order |
| `dashboard` | The whole dashboard — menu plus screens |
| `pipeline-board` | The Pipeline *board* lens: five columns in pipeline order, keyboard moves, confirm-on-move, bare starfield in an empty column |
| `job-scorecard` | One role's full breakdown, sized for a Freeze PNG/SVG export — no chrome stack, no cursor |
| `glamour-report` | A rendered markdown report in the detail pane, section list beside it |
| `cli-script-menu` | A script screen inside the frozen banner/footer frame |
| `onboarding-wizard` | The bootstrap flow: resumable status table, Express Auto-Pilot first, eight individually runnable stages |
| `resume` | The print resume |
| `cover-letter` | The print cover letter |
| `tailoring-review` | The before/after redline: accept or reject each rewrite, the model's reason attached, nothing written until `w` |
| `report-archive` | Glow's stashed-document browser as a sortable table beside the reader — the columns are the longitudinal story |
| `settings-profile` | A Huh form page: grouped fields, blocking inline validation, secrets masked |

The rules each one encodes are written as comments in its logic class — read
those before changing layout, since most of them exist because a specific
version of the surface failed somebody.

---

## Content fundamentals

**Who is speaking.** A precise, opinionated tool built by one person who was
annoyed at "predatory, subscription-based web resume builders." The copy is
matter-of-fact and technical, never salesy, never encouraging in a HR-software
way. It states what happened and what key to press.

**Person and address.** UI copy is almost entirely **imperative or nominal** —
no "I", very little "you". Labels are bare nouns: `Interview Probability:`,
`Score Distribution`, `Top Employers & Staffing Detection`. Instructions are
imperative and bracket the key: `To scan for new roles, press [ s ]`. Second
person appears only when the sentence is genuinely about the user's own
judgment: *"ALL / EVALUATED hide scored roles under 3.5"*, *"Roles you have
applied to are never hidden by that bar."*

**Casing.** Three registers, used consistently — with the four message
prefixes, at `guidelines/content-casing.card.html`:
- `UPPERCASE` for screen titles and tab labels, letter-spaced with sparkle
  flourishes: `✦ CAREER PIPELINE ✧`, `✦ MAIN MENU ✧`, `ALL`, `EVALUATED`,
  `TOP ≥4`, `LOW <3.5`. Status pills are uppercase too: `INTERVIEW`.
- `Title Case` for section headings inside a pane: `Scores`, `Stress & Stretch`,
  `Skills Gap Matrix`, `Pipeline Funnel`, `Conversion Rates`, `Mission Control
  (Heatmap & Trends)`.
- `lower case` for keybinding hints in the footer: `nav`, `top/bot`, `sort`,
  `refresh`, `report`, `url`, `quit`.

**Labels name the real thing.** The product refuses euphemism. It is
"Interview Probability", not "Match". A score that was never computed says so
(`-`, colored muted) rather than rendering `0.0` — *"'not evaluated' and
'evaluated badly' are different facts, and coloring the first like the second
reads as a verdict that was never made."* Abbreviations were deliberately
un-abbreviated: `Fit 4.5 / Odds 3.9`, because *"single-letter abbreviations
saved 4 columns at the cost of being completely opaque to a first-time user."*

**Empty, error, and no-op states all explain themselves.** (All five side by
side: `guidelines/states-gallery.card.html`.)
- Empty pane: `✦ No active selection ✧` over a twinkling starfield, then two or
  three `press [ x ]` hints that are *screen-specific* (the same letter means
  different things on Jobs and Pipeline).
- No-op: a yellow notice with no "Error:" prefix — *"this isn't a failure, it's
  an unavailable action"*: `No job URL saved for this application (press any key
  to dismiss)`.
- Failure: red, prefixed `Error:`, plain-language first with raw stderr behind
  `d`: `(d for details, any other key to dismiss)`.
- Long-running: `Tailoring resume... (esc to cancel)`, and past a threshold,
  `-- still going after 7m, which is longer than usual; esc to cancel`.
- Too-small window: `✦ Terminal Window Too Small ✧` / `Current: 62×20` /
  `Required: 80×24` / `Please expand your terminal window for optimal viewing.`

**Encouragement is earned, not sprinkled.** Positive copy appears only where the
scoring model actually rewarded something: `No stress signals detected — earned
the low-stress bonus`, `No experience gaps flagged`. The one promotional line in
the whole product is the banner over a genuinely strong match:
`★ NEXT BEST MOVE: High match at Acme (4.4) — Press 't' to tailor now!`
And one analytics row nudges directly: `12 roles (Write bullets next!)`.

**Punctuation.** Em dashes for asides, `•` as an inline separator, `|` as a
field separator in dense bars and in print, `·` inside a single badge
(`⌂ On-site · 6.2 mi`), `↳` for a nested item, `→`/`↩`/`↑↓` for keys. Ellipsis
is always the single character `…`.

**Emoji: no.** This is an explicit, tested rule, not a preference. `theme.py`:
*"Every glyph here must be TEXT presentation, never emoji"* — emoji break
Rich's column-width math and ignore the palette. Glamour is configured with
*"No emoji by default: resume reports are technical/professional."* A unit test
asserts it, because the table drifted back to emoji twice. **Never use emoji in
anything built with this system** — reach for the glyph table under Iconography
instead.

The rule is stricter than "no colourful pictures": a character counts as emoji
if it has **Emoji_Presentation=Yes**, i.e. it renders in colour without a
variation selector. Several characters that look like line art qualify, and
they are the ones that slip through review. The known offenders and their
replacements — also carded at `guidelines/content-emoji.card.html`:

| Do not use | | Use instead | | Why |
| --- | --- | --- | --- | --- |
| `⚡` | U+26A1 | `▶` | U+25B6 | Express / auto-pilot. Wide + colour-by-default. |
| `⏺` | U+23FA | `●` | U+25CF | Active-filter dot. Wide + colour-by-default. |
| `⏻` | U+23FB | `✕` | U+2715 | Quit / exit. Colour-by-default; `✕` is already the set's exit glyph. |
| `📑 📖 🎯` | | `▥ ⇪ ⌖` | | `cli.py`'s RAG retrieval headers — the one place upstream still prints emoji. |

**The test before adding any glyph:** it must be `Emoji_Presentation=No` and
preferably `East_Asian_Width=Neutral`, so it measures exactly one terminal
cell. A wide glyph silently breaks Rich's and Lip Gloss's column math, which
is the practical reason for the ban — the aesthetic objection is secondary.

**Print copy.** The resume itself is all-caps section titles
(`PROFESSIONAL SUMMARY`, `WORK EXPERIENCE`, `TRAINING & CERTIFICATIONS`), an
uppercase tagline under the name, and pipe-separated meta lines
(`Company | Size | Location | Dates`). Bullets are never bolded — *"keep them
400-weight to let the content breathe."*

---

## Visual foundations

### Color

Two palettes, never mixed. The TUI palette is **Charmtone** (the Charm
ecosystem's own branded set), with every accent tuned until it clears 4.5:1
against *both* backgrounds — `--tui-base` (#1e1e2e) and the lighter
`--tui-surface` (#313244). Surface is the tighter constraint and has caught two
real bugs upstream. Two of Charmtone's own picks were replaced for contrast:
Charple → Hazy for BRAND, Sriracha → lightened Coral for ERROR.

- Neutrals (Catppuccin Mocha, untouched): Base `#1e1e2e`, Surface `#313244`,
  Overlay `#45475a`, Text `#cdd6f4`, Subtext `#a6adc8`.
- Accents: Blue/INFO `#4dabf7`, Mauve/BRAND_ACCENT `#ff60ff`, Green/SUCCESS
  `#9ab63f` (olive-lime), Yellow/WARNING `#f5ef34`, Sky/BRAND `#a47bff`, Peach `#ff985a`,
  Red/ERROR `#ff7b99`, Teal `#12e6c8`, Muted `#a3a3a3`.
- Print: `#000000` text, `#ffffff` paper, `#9aa3af` dividers. Nothing else, ever.

**Three accents diverge from upstream.** The repo ships Pink `#ff84ff`,
Sky `#8b75ff` and Green `#12c78f`. Pink sat 6° from Mauve and was
indistinguishable from it in the toast border and the Progress gradient, so it
was replaced with **Teal `#12e6c8`** — the cool side of the palette was empty
while the warm side held five accents. Sky was rotated to **`#a47bff`** so it
reads as purple rather than a second blue next to `#4dabf7`. Green moved to
**`#9ab63f`** (olive-lime) so it no longer competes with the new Teal. All
three keep their semantic roles and their contrast floors. The token is named
`--tui-teal`; the corresponding Go/Python field upstream is still `Pink`.

**Overlay is not a text color.** `#45475a` is the border/divider token and
measures 1.4–2.3:1 against Surface and Base. Muted text is always Subtext.

**Sky only on Base.** `#a47bff` clears Base at ~5.3:1 but sits near the line on
Surface (~4.0:1) — never put it on a Surface-backed bar.

**Color is never the only signal.** Every score tier carries a redundant glyph
(`✓ ✦ ★ ⊘`), every semantic color in the CLI is paired with a distinct icon, and
company rows carry literal `[AGENCY]` / `[DIRECT]` text badges.

**DESIGN.md also declares** `tui-brand: #4dabf7` (Electric Sky) and
`tui-accent: #b39ddb` (Vibrant Mauve). These are the documentation-surface brand
pair; the shipped dashboard renders the Charmtone values above. Both are
tokenized (`--brand-electric-sky`, `--brand-vibrant-mauve`).

### Type

Print is the only place with a real type scale, and it is extreme-contrast by
design: decorative **DM Serif Display** for the name (36pt / 0.5625in
line-height) and section titles (16pt), against utilitarian **DM Sans** for
everything else — tagline 15pt, and one single body size, **9.75pt at 1.15
line-height**, for bullets, job titles, meta, skills, education and
certifications alike. Hierarchy comes from weight (400 vs 800) and rules, not
size. The 1.15 line-height was measured: dropping from 1.2 recovered ~123pt of
page-1 whitespace on a real two-page build.

The TUI has no type scale at all — one monospace family at one terminal size.
Hierarchy is carried entirely by **color, bold, letter-tracking, and
box-drawing**. `FormatTrackedHeader` spaces a title out letter by letter and
brackets it with sparkles: `✦  P I P E L I N E  ✧`.

### Backgrounds, texture, imagery

Flat fills only. There are **no images, no gradients-as-backgrounds, no
patterns, no illustrations** anywhere in the product — the only raster asset in
the repo is the app icon. Two texture-like effects exist, both character-based:

- **The starfield.** An empty detail pane fills with `✦ ✧ ·` at ~6.5% density,
  placed by a deterministic 2D coordinate hash, each star twinkling on its own
  sine phase at 1.5–4.5 rad/s, cycling Mauve → Sky → Blue → Overlay by
  brightness. Ticks every 60ms.

  **Where it may go.** The starfield fills *empty regions*, and the rule is
  literal: it belongs in space that has no content, never behind content.
  Stars under letters read as noise rather than texture, and the twinkle
  competes with the thing you are trying to read. Three sanctioned placements:
  the empty detail pane (6.5%, with the centred card), an empty kanban column
  (6.5%, no card — the column header already names the stage), and the region
  beside the main menu (3%, as a field the menu sits next to, not on). Anywhere
  else, ask whether the region is genuinely empty or merely sparse. It fills
  its container in terminal cells and respects `prefers-reduced-motion`.
- **The heatmap.** A GitHub-style 7-row calendar of `■` cells colored in five
  steps: Surface (empty) → Subtext → Blue → Peach → Green.

**Gradients exist, but only on text** — carded at
`guidelines/type-title-gradients.card.html`. `RenderColorGradient` interpolates a
string character-by-character between two palette colors — used on every screen
title (`✦ CAREER PIPELINE ✧` runs Blue → Mauve; Jobs runs Blue → Mauve → Peach;
Progress runs Peach → Mauve → Teal; Main Menu runs Mauve → Blue). Jobs and
Progress carry that Mauve midpoint deliberately: their endpoints sit on
opposite sides of the wheel, and a straight two-stop blend between them passes
through a desaturated brown at the middle of the string. Any wide hue jump
gets a third stop rather than the muddy midpoint. `RenderFlowingGradient` adds a
traveling sine wave for animated text. A six-stop "thinking gradient"
(Peach → Teal → Mauve → Lavender → Blue → Sky) runs during LLM work.

### Borders, elevation, shadow

**No shadows. Anywhere.** Depth is border color and background step only:
Base → Surface → Overlay. Panels use Lip Gloss `RoundedBorder()` (the
`╭─╮ │ ╰─╯` set). Border color *is* the state:

| Border | Meaning |
| --- | --- |
| `--tui-overlay` | idle / detail pane / empty pane |
| `--tui-blue` | the active sidebar list, modal dialogs |
| `--tui-mauve` | help overlay, focused element |
| `--tui-peach` | warning box (terminal too small) |
| `--tui-teal` | toast (over a Mauve fill) |

Print is *absolutely flat*: no shadow, no overlap, and exactly one rule weight
(`0.018cm` solid `#9aa3af`) under section titles, job meta lines and education
headers.

### Hover, selection, press

`guidelines/states-selection.card.html` shows this rendered.

There is no mouse hover in a terminal — **selection is the hover state**, and it
is expressed three ways, never by a background tint on the row itself:

1. **A left bar.** `HoverStyle` swaps in a one-cell `┃` left border in Mauve and
   drops left padding from 2 to 1 so text stays aligned with unselected rows.
   This is the primary selection language (main menu, both sidebars).
2. **Bold + full color.** The selected row's company name goes bold and keeps
   the full palette.
3. **Dimming everything else.** Unselected rows are re-rendered with the *whole
   theme* blended 55% toward Base (`Theme.Dimmed()`), so each row keeps its
   internal color relationships at lower contrast. Flattening to one gray was
   tried first and read as a wall of gray.

Inverted fills (`Background(Mauve)` / `Background(Sky)` with Base-colored text)
are reserved for genuinely modal selections: KB category tabs, KB list rows, the
status-picker cursor (`Background(Overlay)` + `> ` prefix).

**Press** has no visual state — a keypress either performs the action instantly
or opens a confirm. Destructive-but-free actions (status changes) require a
second Enter: the first press is a proposal (`Change status to Interview?` /
`Enter/y confirm  Esc/n cancel`), not a commit.

### Motion

Four Harmonica spring curves, defined as (frequency, damping):

| Curve | Params | Used for |
| --- | --- | --- |
| Snappy | 6.0 / 0.9 | cursor movement, pane switching |
| Organic | 4.0 / 0.7 | reveals, score bars settling to value |
| Elastic | 3.5 / 0.5 | celebration badges |
| Shake | 8.0 / 0.4 | error/warning cues |

Pane switching is **instant** by design. Score bars spring to their value and
the number animates with them. The empty pane twinkles at 60ms. Confetti is a
real particle system (gravity 0.05/frame, drag 0.95, 8 glyphs `✦✧★◆●■•✢`, six
Catppuccin colors, 20–35 frame lifetimes) fired by toast celebrations only.
Progress has two modes: a determinate 3-line-thick Bubbles bar for `tailor` (the
only action with real step signal) and an indeterminate spinner for everything
else — *never a faked percent*.

Reduced motion is a first-class path: `RESUME_BUILDER_MOTION=reduced` (or
`REDUCED_MOTION=1`) snaps every spring to its target and suppresses confetti
entirely.

### Layout

Split-pane, keyboard-first, and budgeted to the row
(`guidelines/layout-budget.card.html`). Pipeline gives the sidebar
**35%**, Jobs gives it **60%** (scanning a list beats previewing detail there).
Fixed chrome stacks top to bottom: header bar → tabs + underline → metrics bar →
sort/filter bar → optional search bar → optional notice → split pane → help bar.
Every one of those is measured, not assumed, before the pane height is computed,
because a bar that wraps to two lines pushes the footer off screen.

Narrow terminals **degrade, never overflow**: bars truncate right-then-left with
`…` and pad the gap; the tab row truncates and appends a Peach ` ›more`; the KB
screen stacks its panes vertically below 70 columns. Minimum viewport is 80×24,
relaxed to 35×12 on Termux/mobile. Modals are 80% of width, capped at 100
columns, floor 40.

Print is one `.page`, `width: 100%; max-width: 8.5in`, centered, zero padding,
with `break-inside: avoid` on every job, education and certification block.

### Transparency and blur

None — a terminal has no alpha channel. "Semi-transparent" is expressed by
blending a color toward the background by a fixed 0.55 (`DimFraction`), which is
what opacity would have computed anyway. Modal backdrops are not blurred or
darkened by alpha either: the background is ANSI-stripped and re-rendered in
Overlay gray.

### Radius and cards

Rounded terminal borders only — one corner shape, no scale of radii. A "card" in
this system is a bordered box with a colored border and `Padding(0,1)` or
`Padding(1,2)`; it never has a fill distinct from the pane behind it, except the
centered empty-state card (Surface fill) and toasts (Mauve fill).

---

## Script output — the third surface

The dashboard and the PDF are the two surfaces with their own palettes, but
most of the product is neither: it is Python scripts printing through Rich,
driven from `menu.py`. Those scripts share one frame, and matching it is what
makes a new script feel like part of the program rather than a utility someone
bolted on.

**Every script runs inside a frozen frame.** The terminal is split into three
regions before a single line of output appears:

1. `cli_art.display_compact_banner("ONBOARDING | DOCUMENT INGESTION")` paints
   rows 1–4 — the `› resume-builder` mark in Blue plus an UPPERCASE,
   pipe-separated context string naming the flow and the step within it.
2. `cli_art.display_execution_footer()` pins the bottom row.
3. A DECSTBM scroll region (`\x1b[5;{rows-1}r`) clamps the scrollable area to
   everything between them, and is released in a `finally` block.

The consequence is a hard rule: **script output never repaints the banner and
never scrolls the footer away.** It also means prompts drawn by
`prompt_toolkit` cannot render inside that region at all, which is why every
interactive prompt routes through `charm_prompt.py` (Go/huh) and falls back to
questionary only when Go is missing.

**The two footers are a state indicator.** `display_footer_commands` shows
`↑↓ / JK navigate │ ENTER select │ CTRL+C cancel / exit`; the moment a script
starts, `display_execution_footer` replaces it with `CTRL+C stop active script
│ Please wait for execution to complete...`. Both are sparkle-bracketed and
pipe-separated, keys bold and coloured by consequence — Blue moves, Green
commits, Red stops. Leaving the nav footer up during execution is a bug: it
offers keys that no longer do anything.

**Message prefixes are fixed.** `cli_art` defines four, each an icon in bold
semantic colour: `✓` SUCCESS, `✗` ERROR, `⚠` WARNING, `✦` HINT. They are
prefixes, not panels — a panel (`box.ROUNDED`, `padding=(0, 2)`, semantic
border) is for something the user must act on. Tables use
`TABLE_HEADER_STYLE`, bold Mauve.

**Long flows open with a resumable status table.** `render_bullet_bank_status`
is shared by the onboarding wizard and the bullet-bank menu, and its status
vocabulary is a closed set of four: `Up to date` (Green), `In progress`
(Blue), `Never run` (Subtext), `Locked` (Yellow). The detail column always
says *why* — `3/11 processed (8 pending)`, `checkpoint at bullet 40/212 --
resumable`, `finish Step 0 (ingestion) first`. A `Locked` row with no reason
is a bug.

**Failure output names the stage.** Unattended multi-stage runs write the
traceback to a file (`bootstrap-error.log`) rather than the terminal, because
the scroll region is still clamped, then print the stage that died, the
exception type, the log path, and a recovery line: *"Your profile still exists
-- fix the problem and re-run setup to resume from where it stopped."*

### The new-user flow

Onboarding is the one flow a user meets before they know anything about the
product, and it is built around a single premise: **eight stages, each
individually runnable, none of them opaque.** It replaced a flow that ran
everything as one subprocess with no way to see or resume from where it
stopped, and every rule below exists because that version failed somebody.

The wizard (`bootstrap_menu.run_bootstrap_menu`) opens with the progress
table, then the menu — the table so you can see where you are, the menu so you
can act on it. Rules the surface enforces:

- **Two ways in, never one.** `▶ Express Auto-Pilot (Recommended)` runs all
  eight stages unattended; the individual steps sit below it for anyone
  resuming or re-running one. The recommendation is explicit in the label.
- **Plain language, not internal sequencing.** The menu says *Upload Your
  Documents* and *Draft Your Profile*, never "Phase 0" / "Phase 0.5". The
  progress table keeps the 0 / 0.5 / 1–6 ordering because sequence is useful
  there, but renders with `show_numbers=False` — row order carries it.
- **The table and the menu use the same words.** A step named one thing in the
  status table and another in the menu that runs it is the defect this rule
  was written against.
- **Dependencies are visible gates, not comments.** A step that cannot run yet
  reads `Locked` with the reason attached, and refuses to run rather than
  producing a blank result the user still pays for.
- **Never fake progress.** A missing API key stops the flow with a warning that
  names the exact profile-scoped file (`profiles/<name>/.env`), links the page
  that issues free keys, and offers the prompt once more rather than
  dead-ending. A stage that did nothing must not checkpoint as done.
- **Completion is the last artifact, not the first.** Status is derived from
  the final file a stage writes, so an interrupted run reads `In progress`,
  never `Up to date`.

`ui_kits/cli/` recreates both: the wizard with its progress table, and what a
script looks like mid-execution inside the frozen frame.

---

## The Charm surface

The dashboard is built on the Charm stack, and the stack is doing real work:
**Bubble Tea v2** (the loop), **Lip Gloss v2** (every border, pad and colour),
**Bubbles** (list, progress, spinner), **Huh** (every interactive prompt, via
the `dashboard/cmd/prompt` binary `charm_prompt.py` shells out to), **Glamour**
(rendered reports), **Harmonica** (the four spring curves).

"Use the library instead of hand-rolling it" is a design decision as much as an
engineering one: the library's version already handles truncation, reflow and
narrow terminals. Several surfaces the product hand-rolls now have a designed
counterpart in this system, specified so the Go side can adopt the real library
rather than re-derive the look.

**Designed here, ready to adopt.**

| Charm library | Component | Replaces |
| --- | --- | --- |
| `lipgloss/table`, `bubbles/table` | `DataTable` | hand-computed column widths in `bars.go`; the KB and Jobs lists |
| `lipgloss/tree` | `ClusterTree` | `↳`-prefixed bullet clusters, skills matrix, KB hierarchy |
| `bubbles/paginator` | `Paginator` | no paging affordance at all on 60+ role result sets |
| `bubbles/viewport` | `ScrollIndicator` | scrollable panes with no evidence they scroll |
| `bubbles/help` | `HelpBar` | the hand-built footer and its duplicate help overlay |
| `huh` | `HuhField` | three ad-hoc input surfaces — status picker, search, onboarding prompts |
| `glamour` | `assets/glamour-resumebuilder.json` | Glamour's default dark theme, which is near our palette but not it |
| `bubblezone` | `guidelines/layout-mouse.card.html` | nothing — mouse support does not exist yet |
| `bubbles/filepicker` | `FilePicker` | onboarding stage one, which asks for documents with no designed picker |
| `bubbles/textarea` | `TextEditor` | the cover letter and hand-corrected bullets, with no editing surface at all |
| `bubbles/stopwatch`, `timer` | `ElapsedTimer` | the "still going after 7m" sentence, currently prose rather than a component |
| `lipgloss/list` | `EnumList` | the remaining hand-written `↳` and `•` prefixes across the screens |
| `tea.Printf` | `Toast` | success messages that steal a pane to say something that needed no answer |
| `fang` | `guidelines/cli-fang.card.html` | three separately hand-styled things: `--help`, version output, error formatting |

Two things are new rather than replacements. A fuzzy **command palette**
(`CommandPalette`, `ctrl-k` or `:`) answers recall, not navigation: nine screens
and roughly forty bindings have made remembering the binding the bottleneck.
And `DiffLine` with the **tailoring review** screen makes the rewrite itself
visible — the product's core value previously happened with no surface showing
it, which meant trusting it was the only option.

**Deliberately not adopted.** Wish and Soft Serve (SSH and git hosting — this is
a single-user local tool), Skate, Melt, Keygen. Sequin is a contributor
debugging aid, not product surface.

**Things Charm does that the product does not do at all yet.**

- **VHS** — scripted terminal recordings as GIFs. The README and the docs have
  no motion in them, and a `.tape` file makes the onboarding flow demonstrable
  and reproducible instead of screenshotted once and left to rot.
- **Freeze** — renders terminal output to PNG/SVG. A scored pipeline view or a
  single job's scorecard exported as an image is a genuinely useful artifact
  for a job search, and it is the only sanctioned way a TUI screen should ever
  leave the terminal (the print palette stays for the resume — see The
  No-Bleed Rule).
- **charmbracelet/log** — `bootstrap-error.log` is currently a raw Python
  traceback. On the Go side, structured levelled logging with the same palette
  would make the log file look like the program that wrote it.
- **Gum** — for the shell scripts around the edges (`build_mobile.sh`), which
  today have no styling at all while everything they sit next to does.

**Crush and Ultraviolet** are worth reading rather than adopting: Crush is the
reference for how far this stack goes visually, and Ultraviolet is the
primitive layer underneath Bubble Tea v2 if a custom renderer is ever needed.

### Pipeline: list and board are one screen

Pipeline and its board are two lenses on the same object, so they are one
screen with a view toggle (`v`), not two menu entries. Everything else about
the screen — header, footer, back/quit — stays put across the switch; only
the middle region changes shape.

- **List** is the original split-pane: tabs across the top (`ALL`,
  `EVALUATED`, `APPLIED`, `INTERVIEW`, `TOP ≥4`, `LOW <3.5`, `SKIP`,
  `REJECTED`), grouped sidebar, detail pane.
- **Board** is five columns in pipeline order — `EVALUATED`, `APPLIED`,
  `RESPONDED`, `INTERVIEW`, `OFFER`. `Skip` and `Rejected` stay list-only: a
  board is for work in flight, and a closed-out column would spend a fifth
  of the width saying nothing happens here.
- **The focused column carries the Blue border**, the same signal the list's
  panes use; unfocused columns are Overlay. Selection is the same three
  signals as everywhere else: the Mauve `┃` bar, bold, and dimming what's
  not focused.
- **Moving a card is a proposal.** `H` / `L` open the same confirm dialog the
  status picker uses (`Enter/y confirm  Esc/n cancel`) rather than committing
  on a keypress. Moving into `Interview` or `Offer` is one of the four
  moments that earns confetti.
- **No drag.** Terminal drag needs mouse cell reporting and a zone library
  (`bubblezone`) for hit-testing, and keyboard-first is the product's stated
  posture. If mouse support is added later, the drag target should be the
  column, never a specific insertion index — the columns are unordered sets.

A card shows only what fits at a fifth of the width: score badge with its
tier glyph, company, role, employment tag. `ui_kits/dashboard/PipelineScreen`
recreates both views.

---

## Dashboard menus, reworked

The main menu and its neighbors went through one pass to fix real
inconsistencies, not a redesign. Six changes, each with a specific problem
behind it:

- **Pipeline absorbed its board** (above) — one menu entry, not two whose
  names differed by one word.
- **Build Documents folded into the dashboard.** A single role's document
  work happens where that role lives — Jobs and Pipeline both bind `t` to
  tailor. What's left — a batch run over every pending role, a recruiter
  resume with no role attached, re-rendering a PDF from saved JSON with no
  AI, and conversational polish — isn't about any one role, so it got its
  own **Documents** menu entry rather than living nowhere.
- **Progress split into Progress and Insights.** One screen had grown into
  eleven sections and would not fit a 24-row terminal. The split follows a
  real question boundary: Progress answers *where do things stand* (funnel,
  conversion rates, coverage gaps, top employers) — the screen you check
  often, so it stays fast to scan. Insights answers *what's working and what
  changed* (source yield, response-time distribution, score histogram,
  week-over-week deltas, streaks) — a slower question, asked less often.
- **Skills tools moved from Settings to Knowledge Base**, as a second tab
  (`shift+Tab` to switch): viewing/managing profile skills, scanning the
  pending pipeline for skills to verify, recomputing stale skill-gap
  matrices, discovering local employers with ATS boards, and enriching local
  company addresses. The rule that sorted this: **Settings changes how the
  program behaves going forward; the dashboard shows what the program
  found.** A skill is a fact about the profile — it belongs beside the
  knowledge it's a claim about, the same as everything else in that screen.
  Doctor checks and anything that changes future behavior stay in Settings.
- **"Track & Follow Up" renamed to Command Center.** The name undersold what
  the screen is — DESIGN.md's own north star is literally "The Command
  Center Editor" — and "Track & Follow Up" told you an action, not what
  you'd find there.
- **Menu descriptions got a second line.** A label followed by `(a full
  sentence in parentheses, same weight and color)` reads as one run-on
  string; ten of those in a row reads as a wall. Descriptions now sit under
  the label in a dimmer tone, so the label leads and the description is
  optional reading.

### Celebrations are a closed set

Confetti — the Peach/Mauve/Blue/Sky/Green/Teal burst already defined under
Motion — is reserved for four moments: **the first resume ever tailored**, a
status moving to **Interview** or **Offer**, **onboarding completing**, and a
**weekly application-goal being hit**. Everything else that succeeds (a
routine status change, a normal save, a completed scan) gets the plain
success prefix and nothing more. The reasoning is the same one that governs
message prefixes generally: a signal that fires on everything stops meaning
anything. `Toast` takes a `celebrate` prop that renders the burst; reach for
it only for something on that list.

---

## Reviewing for a new, overwhelmed user

Read against a specific persona — a distractible, somewhat overwhelmed job
seeker in their mid-30s, tech-comfortable but new to terminal tools — three
things stood out as risks, and two were already handled well.

**Handled well.** The onboarding wizard's `Express Auto-Pilot` default means
a new user is never staring at eight menu items with no idea which to press
first — one obvious action, with the individual steps available but visually
secondary. And `NEXT BEST MOVE` on the Jobs screen already does the single
most useful thing for this persona: it names the one action worth taking
right now instead of asking the user to derive it from a list.

**Worth watching.**

- **`NEXT BEST MOVE` only appears on Jobs.** For someone who opens the
  dashboard unsure what to do, that banner is the highest-value thing in the
  product, and it's one menu level deep. Surfacing a version of it on the
  main menu — even just "3 jobs are worth a look" pointing at Jobs — would
  put the answer to "what do I do right now" at the first screen instead of
  the third.
- **Density on Progress and Insights.** Both are built for someone who
  already wants the numbers. Someone in a low-focus moment is more likely to
  bounce off eleven sections of tables than read them. The split helps, but
  neither screen currently orders itself "most actionable first" — that's
  worth a second pass if this persona is the primary one, not a secondary
  audience.
- **Recovery language matters more than usual.** The bootstrap failure
  copy — *"Your profile still exists -- fix the problem and re-run setup to
  resume from where it stopped"* — is exactly the right instinct: it says
  nothing was lost. That same instinct should extend everywhere a run can be
  interrupted, not just the top-level bootstrap failure, since an
  overwhelmed user is more likely to close the terminal mid-run than debug
  it.

Nothing here is a design defect the way the emoji or the muddy gradients
were — it's a set of judgment calls about where to spend attention, and they
should be made deliberately rather than left as whatever the original
implementation happened to prioritize.

---

**There is no icon font, no SVG sprite, and no PNG icon set.** Every icon in the
product is a character.

Two complete, interchangeable sets are defined in `scripts/theme.py` and mirrored
in `dashboard/internal/theme/icons.go`:

1. **Nerd Font glyphs (default).** Font Awesome code points from the Private Use
   Area (`nf-fa-cog`, `nf-fa-bar_chart`, `nf-fa-user`, `nf-fa-search`,
   `nf-fa-magic`, `nf-fa-trash`, `nf-fa-pencil`, `nf-fa-external_link`,
   `nf-fa-map_marker`, `nf-fa-filter`, …). These need a patched terminal font.
2. **Plain Unicode fallback** (`RESUME_BUILDER_ICONS=unicode`). The set this
   design system uses on the web, because PUA code points don't render in a
   browser:

   | Role | Glyph | Role | Glyph |
   | --- | --- | --- | --- |
   | success / complete | `✓` | menu | `≡` |
   | error | `✗` | pipeline / utility | `⚙` |
   | warning | `⚠` | progress / evaluate | `▤` |
   | hint / gem / magic | `✦` | report | `▥` |
   | discovery / search | `⌖` | jobs | `▣` |
   | skip | `⊘` | profile | `◉` |
   | build | `⚒` | source | `◰` |
   | bullet bank | `◈` | path | `⌗` |
   | save | `↧` | trash | `⌫` |
   | resume / play | `▶` | edit | `✎` |
   | recruiter | `◉` | external | `↗` |
   | location | `⌂` | clock | `◷` |
   | filter | `▽` | graph | `▨` |
   | knowledge | `⇪` | quit / exit | `✕` |
   | prev / next / back | `❮` `❯` | answers / chat | `¶` |
   | check for updates | `↻` | manage profiles | `◐` |

**Structural glyphs** (not part of either icon set, always literal): box-drawing
`╭─╮│╰─╯` for panels, `┃` for the selection bar, `━`/`─` for active/inactive tab
underlines, `█` for funnel and progress bars, `▆` for score bars (the lower
three-quarters block — the top quarter gap is what keeps stacked bars from
fusing into one slab), `■` for heatmap and platform bars, `▁▂▃▄▅▆▇█` for
sparklines, `▏▎▍▌▋▊▉` for eighth-step progress, `░` for the unfilled half of a
radar bar, `✦ ✧ ·` for the starfield, `★` for target/next-best-move, `↳` for
nested list items.

**Score tiers pair color with shape**, always: `✓` strong (≥4.2), `✦` good
(≥3.8), `★` fair (≥3.0), `⊘` weak.

**Emoji are banned** (see Content fundamentals, which carries the offender /
replacement table). Unicode glyphs must be
text-presentation and preferably `East_Asian_Width=Neutral`, so they measure one
cell.

**The only raster assets** are `assets/app_icon.png` and `assets/macos_icon.png`
— the app icon, a neon outlined terminal-document with a diamond, in the
product's own Sky/Mauve/Pink range on near-black. That icon is the brand mark;
this system uses it as the logo wherever a mark is needed. The one wordmark is the
CLI launcher banner (`CliBanner`): "RESUME BUILDER" in figlet ANSI Shadow block
letters (`cli_art.MAIN_BANNER_LINES`), painted with a single diagonal gradient
from Sky to Mauve inside a double-ruled Sky panel, with a sparkle field to its
right. Use it only there — it is a launch moment, not a logo. Everywhere else,
render "resume-builder" in plain type (lowercase, hyphenated, monospace). The
footer of every dashboard screen does exactly that, in Subtext:
`resume-builder dashboard`.

---

## Components

**`components/terminal/`** — the dashboard and CLI chrome:
`Glyph`, `GradientText`, `TuiPanel`, `TuiHeaderBar`, `TuiFooterBar`, `TuiTabs`,
`SidebarRow`, `NoticeBar`, `SearchBar`, `Modal`, `HelpOverlay`, `HelpBar`,
`Toast`, `MenuList`, `EnumList`, `GlamourDoc`, `ScrollIndicator`, `Paginator`,
`CommandPalette`, `HuhField`, `FilePicker`, `TextEditor`, `ElapsedTimer`,
`CliBanner`, `CliMenu`, `CliModeBar`, `CliFooterBar`, `CliStatusTable`.

**`components/data/`** — everything that displays a number or a state:
`ScoreBadge`, `StatusPill`, `EmploymentTag`, `ScoreBar`, `ProgressBar`,
`FunnelBar`, `Sparkline`, `Heatmap`, `StarfieldPane`, `DataTable`,
`ClusterTree`, `DiffLine`.

**`components/print/`** — the PDF resume:
`PrintPage`, `PrintHeader`, `PrintSection`, `PrintEntry`, `PrintSkills`.

Each has a sibling `.d.ts` (props) and `.prompt.md` (what & when, with an
example). Every one maps to a real rendering function in the repo — see
"Intentional additions" below for the two that are packaging decisions.

## Intentional additions

Nothing in `components/` was invented as a "design systems usually have one" —
every component maps to a real rendering function in the repo. One is a
packaging decision rather than a one-to-one port:

- **`Glyph`** wraps the Unicode fallback icon table so consumers don't hardcode
  code points. The table itself is the product's (`theme.py`'s `_UNICODE_ICONS`).

## Fonts

The product's own binaries — `dm-serif-display-latin.woff2`,
`dm-serif-display-latin-ext.woff2`, `DMSans-Regular-static.ttf`,
`DMSans-ExtraBold-static.ttf`, `DMSans-Italic-static.ttf` — are served locally
from `assets/fonts/` and declared with `@font-face` in `tokens/fonts.css`. These
are *static instances*, not the variable fonts: the product bakes them that way
because Chromium's print-to-PDF path scrambled the text layer when given a
variable font. DM Sans weight 500 maps to Regular, since the shipped set has
only Regular / ExtraBold / Italic.

The TUI's monospace is a pure substitution: the product has no webfont and uses
the user's terminal font ("preferably a Nerd Font"). This system renders in
**JetBrains Mono**. Nerd Font PUA glyphs cannot render in a browser, so every
component uses the Unicode fallback set.
