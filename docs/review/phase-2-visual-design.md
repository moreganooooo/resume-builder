# Phase 2 — Visual design system (TUI + PDF)

Run 2026-08-05, Opus 5. **Goal served: 4 (Beautiful)**, with one inherited
blocker serving goal 2.

**Owned this phase:** `scripts/cli_art.py`, `scripts/menu.py`,
`scripts/picker.py`, `scripts/bullet_bank_menu.py`, `ResumeDesignSystem.md`,
`resume-engine/templates/*.html`, `scripts/render_html.py`,
`scripts/render_coverletter.py`, `dashboard/` (visual layer), and
`output/morgan/pdf/`'s two PDFs read as images.

**Plan gap — claimed:** `scripts/theme.py` is the color source of truth for
the entire CLI and is not listed under *any* phase in `PLAN.md`. Phase 2 owns
the color question, so I read it. Findings 2 and 8 land in it. No other phase
should be blocked on this.

---

## Answer to the phase question

> *Is there one design language here, or several that merely coexist?*

**One language, applied unevenly — plus one genuine second dialect.**

The intent is real and unusually well-documented: `theme.py` is a true
semantic-token module, `dashboard/internal/theme/resumebuilder.go` deliberately
ports those tokens with its trade-offs written down, and every Rich table in
`cli_art.py` routes through one `TABLE_HEADER_STYLE`. That is better discipline
than most projects this size have.

What breaks the illusion is not stray colors — the hardcoded-value hunt came
back nearly clean (Finding 8 is two small leaks). It is that **the palette was
never validated against a background.** Six of seven tokens fail WCAG AA on a
light terminal, and the one that passes there is the one that fails on dark —
and it is the token driving the selection pointer and every table header. The
system has a source of truth; it does not have a contrast contract.

The second dialect is the printed output: the resume and the cover letter
disagree on name size (42pt vs 32pt), separator color, body size, and line
height. Placed side by side they do not read as two documents from one system.

---

## Findings

### 1. BLOCKER — Ligatures corrupt ATS keywords in every PDF

`resume-engine/templates/cv-template.html:59-77`,
`resume-engine/templates/coverletter-template.html:54-66`. **Goals: 2, 4.**

Inherited from Phase 3 as a blocking handoff. **Confirmed, root-caused, and
the fix location is now pinned.**

Reproduced on the committed PDFs:

```
CoverLetter.pdf -> 7 tokens: human-ﬁrst uniﬁed ofﬁcial ﬂuency workﬂows
                             efﬁciently. ﬂexible
Resume.pdf      -> 8 tokens: workﬂows revenue-ﬁrst Workﬂows, ofﬁcial
                             fulﬁlling Certiﬁcation| Certiﬁcation| ﬁlm
```

**New information Phase 3 could not have had — the damage is
extractor-dependent.** PyMuPDF normalizes U+FB01/FB02 back to `fi`/`fl` and
reports **zero** corrupted tokens. pypdf does not, and reports all 15. Both
were run against the same two files. So the corruption is invisible to some
tooling and total to others, which is exactly why it survived this long. Real
ATS stacks are built on pdfbox/pdfminer-class extractors that behave like
pypdf, so the pessimistic reading is the operative one.

`Certiﬁcation` appears **twice**, in the Training & Certifications entries —
a generic high-frequency ATS term, corrupted in the section that exists to be
keyword-matched. `workﬂows` is verbatim JD language the pipeline correctly
mirrored and the renderer then broke.

**Fix** — add to the `body` rule of *both* templates:

```css
font-variant-ligatures: none;
font-feature-settings: "liga" 0, "clig" 0;
```

Re-run the pypdf scan afterward and require zero hits. Note it must be both
files; the cover letter is the worse offender per-word.

---

### 2. MAJOR — The palette has no contrast contract; the selection pointer is the least legible element in the app

`scripts/theme.py:17-23` (tokens), `scripts/theme.py:160-171`
(`QUESTIONARY_STYLE`). **Goals: 3, 4.**

Measured WCAG contrast, every token, both backgrounds:

| token | on `#1e1e1e` dark | on `#ffffff` light |
|---|---|---|
| BRAND `#4dabf7` | 6.73 | **2.48** |
| BRAND_ACCENT `#673ab7` | **2.27** | 7.33 |
| SUCCESS `#4caf50` | 6.00 | **2.78** |
| ERROR `#c96a6a` | 4.57 | **3.65** |
| WARNING `#f5c542` | 10.28 | **1.62** |
| INFO `#2196f3` | 5.34 | **3.12** |
| MUTED `#888888` | 4.70 | **3.54** |

Bold = fails AA (4.5:1). **There is no token that passes on both**, so the
palette silently assumes a dark terminal — an assumption `theme.py`'s own
docstring never states while going to real trouble to defend against terminal
theming in general.

The sharpest consequence: **BRAND_ACCENT is the single lowest-contrast color
in the system on the background the palette actually assumes (2.27:1), and it
is what `QUESTIONARY_STYLE` uses for `pointer` and `highlighted`** —
`theme.py:163-164` — i.e. the cursor showing which menu row you are on. It is
also `TABLE_HEADER_STYLE` (`cli_art.py:38`), so every column header in every
table inherits it.

This is measurable inside the dashboard too, which unlike the Python TUI
*declares* its own background, so no assumption is needed:

| accent | vs Base `#1e1e2e` | vs Surface `#313244` |
|---|---|---|
| Mauve / BRAND_ACCENT | **2.24** | **1.72** |
| Red / ERROR | 4.49 | **3.44** |

WARNING `#f5c542` at **1.62:1 on white** is effectively invisible on a light
terminal — and it is the color of `warning` icons and the "Low-priority
pursue" tier.

**Fix direction:** BRAND_ACCENT needs to move light enough to clear 4.5:1 on
dark while staying usable on light (roughly `#a583e0`–`#b39ddb`), or the
pointer/header role should be reassigned to BRAND, which already passes on
dark at 6.73. Longer term the honest fix is two ramps selected by background,
which the Go side already does correctly (Finding 9) — the Python side has no
equivalent.

---

### 3. MAJOR — The launch banner takes ~27s to play a 1.6s animation

`scripts/cli_art.py:144-153`, with `_stats_line_text()` at
`scripts/cli_art.py:135-141`. **Goals: 1, 3, 4.**

Phase 0 observed a 20–25s banner and asked whether it was intentional brand
polish or unaddressed cost, flagging it for a design judgment call. **It needs
no judgment call — it is a bug, and the code states the intent explicitly.**

`_reveal_banner` is written to run `frame_count = 30`, `total_seconds = 1.6`
(`cli_art.py:126-127`). But `render_frame(threshold)` calls
`_stats_line_text()` on **every frame**, and that function walks the JD
directory on each call:

```
get_pending_jds()   -> 1144 items in 1.46s
_stats_line_text()  -> 0.88s per call
31 frames x 0.88s   => ~27.2s of pure recomputation
```

Measured on the live `morgan` profile. That matches Phase 0's observed 20–25s.
The stats string cannot change during a 1.6-second animation, so **100% of
that time is recomputing a constant.**

**Fix:** hoist one `_stats_line_text()` call above `render_frame` and close
over the string. One line moved; ~27s → ~1.6s. This is the highest
effort-to-payoff item in the phase and it is the first thing any new user
experiences.

---

### 4. MAJOR — Tables are unreadable at 80 and 100 columns

`scripts/cli_art.py:335-371` (`render_pipeline_table`, 9 columns),
`scripts/cli_art.py:263-309` (`render_fit_table`, 7 columns). **Goals: 3, 4.**

Phase 0 flagged mid-word truncation in Browse & Manage Jobs but could not tell
whether it was a no-TTY capture artifact, and handed the verification here.
**It is a real bug.** Rendered at controlled widths against live evaluated JDs:

- **80 cols** — the *column headers themselves* truncate: `Recom…`, `Compa…`,
  `Liven…`, `Foll…`. Company names become `SailP…`, `Avala…`, `Dynat…`. Titles
  wrap to four lines. The table is not usable.
- **100 cols** — headers still truncate (`Recommend…`), dates cut to
  `(2026-07-…`, titles wrap to three lines.
- **120 cols** — readable; titles still wrap to 2–3 lines.
- **160 cols** — clean, one row per record, nothing lost.

80 and 100 are ordinary terminal widths; 160 is a maximized window on a large
display. The design currently only works at the last one.

Root cause: nine columns with no `no_wrap`, no width ratios, and no priority
ordering, so Rich divides the deficit evenly and eats the headers. **Fix:**
give `#`/`Score`/`Posted` fixed widths, let `Title` absorb the remainder, and
drop `Last Liveness` + `Follow-up` below ~110 columns rather than shrinking
every column past legibility.

---

### 5. MAJOR — The resume and cover letter are visibly not the same document family

`resume-engine/templates/cv-template.html:91-98` vs
`resume-engine/templates/coverletter-template.html:73-99`;
`ResumeDesignSystem.md:113`. **Goal: 4.**

Read as images side by side, the two PDFs disagree on their most prominent
element — the name:

| | resume | cover letter | design system |
|---|---|---|---|
| `h1` size | **42pt** | 32pt | **32pt** (`ResumeDesignSystem.md:113`) |
| `h1` line-height | 0.75in | 0.5in | — |
| body size | 9.75pt | 10.5pt | 9.75pt |
| body line-height | 1.2 | 1.6 | — |
| contact separator | `#9aa3af` | **`#000000`** | `#9aa3af` only (`:108`) |

Body size and line-height differing is defensible — a letter should breathe
more than a resume. **The name size is not.** These are two halves of one
application sent to one recruiter, and the wordmark changes size between them.
The cover letter is the one that matches the written spec; the resume is 31%
larger than its own design system says.

The separator color is a straight spec violation: `ResumeDesignSystem.md:108`
says rules and separators are `#9aa3af` "only", and the cover letter's are
pure black.

**Fix:** pick one name size, put it in both templates, and update
`ResumeDesignSystem.md` if 42pt is the intended new value — right now the doc
and the resume disagree and there is no way to tell which is stale.

---

### 6. MINOR — "Career Note:" renders as a synthesized Type3 font

`resume-engine/templates/cv-template.html:242-256`, with the `@font-face` set
at `:35-57`. **Goals: 2, 4.**

The resume PDF embeds a **Type3 font with an empty BaseFont name** alongside
the four real TrueType subsets. It renders exactly three tokens:
`Career`, `Note`, `:`.

Root cause: `.career-note` is `font-style: italic` and `.career-note strong`
is `font-weight: 800`, but only three faces are declared — Regular 400 normal,
ExtraBold 800 normal, Italic 400 italic. **There is no ExtraBold-Italic face**,
so Chromium synthesizes one by outlining glyphs, which exports as Type3.

This is the precise failure mode `cv-template.html:26-34` documents baking
static font instances to avoid ("dozens of near-duplicate Type3 subsets …
coincided with garbled copy-pasted text"). One case survived the fix.

**Severity is minor, not major, because I verified the text still extracts** —
pypdf reads `Career Note:` correctly. So this is a typography defect (faux
bold, visibly different weight from every other 800-weight label) with modest
residual ATS risk, not active corruption.

Note it also violates `ResumeDesignSystem.md:330-331`, which specifies bold
`Career Note:` followed by the note *in italics* — currently the label is
bold **and** italic. **One fix serves both:** drop `font-style: italic` from
the `strong`, which removes the synthesized face and matches the spec.

---

### 7. MINOR — Page 2 is 70% empty while page 1 runs to the margin

`output/morgan/pdf/…_Resume.pdf`. **Goal: 4.**

Measured text bounds:

| | content height | bottom whitespace |
|---|---|---|
| page 1 | 9.67in | 0.86in |
| page 2 | **3.19in** | **7.33in** |

Margins themselves are correct and enforced at `scripts/generate-pdf.mjs:183-188`
(0.5in all sides; measured left edge is exactly 0.500in on every page) — this
is **not** a margin bug.

It is a balance problem: page 1 is visually dense to its last line, page 2
holds only Training & Certifications and Education and then stops two-thirds
of the way up. As a printed artifact it reads as a document that ran out of
content rather than one that was composed.

The whitespace is a symptom, not the disease — see Handoffs; three employers
the design system places on page 2 are absent, and there is clearly room for
them. I am not proposing a CSS fix, because padding this out visually would
paper over the content question.

---

### 8. MINOR — Two hardcoded color leaks

**Goal: 4.**

The hunt across all four owned TUI files came back nearly clean. Two leaks:

- `scripts/menu.py:848-849` — `[yellow]…[/yellow]` on the demo-profile
  warning. A named ANSI color, which is exactly what `theme.py:13-16` warns
  against ("Named colors get remapped by whatever terminal theme is active;
  this project has already hit that in practice"). Should be `theme.WARNING`.
- `scripts/cli_art.py:289, 331, 356` — `"white"` as the `.get()` fallback for
  an unrecognized recommendation/urgency tier. Same class, lower stakes since
  it only fires on unknown enum values. Should be `theme.MUTED`.

`dim` is used 24 times across `cli_art.py`/`menu.py`; that is a Rich attribute
rather than a color and is fine as-is.

---

### 9. MINOR — The palette is maintained twice, in two languages, synced only by comments

`scripts/theme.py:17-23` and
`dashboard/internal/theme/resumebuilder.go:32-39`. **Goals: 4, 5.**

I went in expecting to find the vendored Catppuccin palette bleeding through
and largely did not — `resumebuilder.go` is the best-documented file I read
this phase, and its two reused slots (Peach→WARNING, Pink→BRAND_ACCENT) are
explicitly reasoned rather than accidental. The dashboard also ships
`resume-builder` / `catppuccin-mocha` / `catppuccin-latte` / `auto` themes
(`dashboard/main.go:156`), so the Catppuccin hexes are alternate themes, not
leftovers. **Credit where due: the Go side is architecturally ahead of the
Python side here** — it has a theme abstraction and light/dark variants that
`theme.py` does not.

The actual defect is narrow: the six brand hexes are **hand-copied** into Go,
annotated with comments naming their Python constants. Change `BRAND_ACCENT`
in `theme.py` — which Finding 2 says should happen — and the dashboard keeps
the old value with a comment claiming it matches. Nothing detects the drift.

**Fix:** emit the Go color block from `theme.py` (or have both read one JSON).
Low effort, and it becomes load-bearing the moment Finding 2 is acted on.

---

## Portfolio bar — what a designer notices first

In order, on a cold look:

1. **The 27-second banner** (Finding 3). Before any content is judged, the
   tool feels slow. Nothing else in this report costs as little to fix or
   changes the first impression as much.
2. **The selection cursor is hard to see** (Finding 2). Purple at 2.27:1 on a
   dark terminal reads as "unstyled", not "branded" — the most-looked-at pixel
   in the whole TUI is the one that fails hardest.
3. **The tables break when the window isn't maximized** (Finding 4).
4. **The two PDFs don't match** (Finding 5). This one a *recruiter* notices,
   not just a designer.

The block-letter banner, the Rich panel language, the recommendation-tier
color legend, and the cover letter's typography are all genuinely good and
should not be touched. The cover letter in particular — real signature image,
correct margins, clean rhythm — is the strongest single artifact this system
produces. The gap between it and the resume is the most fixable quality
difference in the project.

One note on the gradient: `display_main_banner` sweeps BRAND → BRAND_ACCENT
(`cli_art.py:145`), and those two endpoints are only 2.96:1 apart from *each
other*, with the BRAND_ACCENT end at 2.27:1 against a dark terminal. The
"BUILDER" half of the wordmark is measurably dimmer than the "RESUME" half.
Fixing BRAND_ACCENT per Finding 2 fixes the banner for free.

---

## Handoffs

- **Phase 3 or 4 (content, not visual):** the resume PDF's page 2 contains
  only Training & Certifications and Education. `ResumeDesignSystem.md:130-133`
  places Element 8 / Strategy LLC, VML, and Callahan Creek on page 2, and they
  are absent from the rendered document. With 7.33in of free vertical space
  (Finding 7), this cannot be space-driven trimming. Either the trim logic is
  over-firing or those employers are being dropped upstream. I did not read
  the builder or the resume JSON — out of phase.
- **Phase 4:** `jd_manager.get_completed_jds()` returns **0** against the live
  `morgan` profile, so the launch banner advertises "0 Resumes Customized
  All-Time" on a tool that has demonstrably produced resumes. Either the
  counter or the move-to-completed step is wrong. Surfaced visually, but the
  bug is not in the presentation layer.
- **Phase 4:** `_stats_line_text()` costing 0.88s is itself worth a look —
  `get_pending_jds()` walks and parses 1,144 JD files on every call. Finding 3
  removes 30 of the 31 calls, but the remaining one still delays every launch
  by ~1s.
- **Phase 5:** `theme.py` has one hardcoded palette with no light-terminal
  variant, while the Go dashboard already implements light/dark theme
  selection. If Phase 5 recommends consolidating the interactive surface, the
  Go side is the more mature theming implementation, not the Python side.
- **Plan maintenance — RESOLVED 2026-08-05, no action needed.**
  `scripts/theme.py` and `scripts/generate-pdf.mjs` were unowned by any phase
  in `PLAN.md`. I claimed `theme.py`'s color layer; I read only the
  margin/font-path handling of `generate-pdf.mjs` to rule it in or out as the
  cause of Findings 1 and 7, and did not review it. `PLAN.md` has since been
  updated: `generate-pdf.mjs` and `validate_pdf_text.py` now belong to
  Phase 4 (with a dedicated scope section), `theme.py`'s icon layer to
  Phase 1, its renderer-count question to Phase 5, and a new "Unowned files"
  operating rule prevents a recurrence.

  One item surfaced while scoping that work and is recorded here so it is not
  lost: `generate-pdf.mjs:211` still prints a raw `❌` emoji, the last
  instance the 2026-08-05 consistency sweep missed. Observed during plan
  maintenance, **not** a reviewed Phase 2 finding — the file was unowned and I
  did not review it. Noted in `PLAN.md` under Phase 4.

---

## Verified as NOT defects

Recorded so later phases don't re-investigate:

- **Relative `./fonts/` paths in both templates are correct.**
  `generate-pdf.mjs:130-141` rewrites them to absolute `file://` URLs before
  writing the temp HTML. Both PDFs embed real DM Serif Display and DM Sans
  subsets — no system-font fallback. This looks like a violation of CLAUDE.md's
  absolute-`file://` rule but is handled. (The rewrite regex only matches
  `url('./fonts/`, so a *new* asset type — an `<img src="./logo.png">` — would
  not be covered. CLAUDE.md's rule stands for anything new.)
- **PDF margins are correct**: 0.5in, enforced at `generate-pdf.mjs:183-188`,
  measured at exactly 0.500in on the left edge of all three pages.
- **Page count is correct**: resume is exactly 2 pages per
  `ResumeDesignSystem.md:122`.
- **Hardcoded-color sweep is clean** apart from Finding 8 — the recent
  consistency-sweep commits did their job.
