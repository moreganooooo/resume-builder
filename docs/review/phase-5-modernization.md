# Phase 5 — Modernization sweep

Model: Sonnet 5. Date: 2026-08-05. **Goal served: 5.**

**Ownership note:** Phase 5 has no `owns:` file list in `PLAN.md` (unlike
Phases 1–4) — its brief is explicitly cross-cutting ("Compare the stack
against what's current" across Gemini API usage, TUI libraries, the Go
dashboard, and packaging). Read that as license to touch any file for this
narrow research purpose; I did not do deep source reading anywhere,
per the phase's own instruction — grep and small targeted reads only, plus
live web research for anything Gemini-API-related (my training cutoff is
January 2026 and current model/API behavior has moved since).

No code changed.

---

## Answer to the phase question

> *Is the stack current, and where's the cheapest leverage?*

Mostly yes, with two real gaps. The Gemini integration is already
sophisticated — structured JSON output via `response_schema`, model
fallback, quota-aware retry, `google-genai` (the current unified SDK, not
the deprecated `google-generativeai`) — but it has never turned on **context
caching** or **Batch Mode**, both of which exist specifically for the
repeated-system-prompt / large-JD-volume shape this pipeline already has.
The TUI is not "hand-rolled instead of a library" so much as **hand-rolled
across three libraries at once** (Rich, questionary/prompt_toolkit, bare
`print()`), which is what's actually forcing `theme.py`'s three parallel
colorizer functions — consolidating renderers, not adopting a bigger
framework, is the fix. And there is currently no path from `git clone` to
an installed `resume` command shorter than "source this shell snippet and
hope your shell is zsh or bash," which is a real, cheap-to-close gap against
the "adoptable by strangers" goal even though it's filed under goal 5 here.

---

## Ranked opportunities

### 1. Pin `thinkingLevel` explicitly on `gemini-3.1-flash-lite` calls
**Effort: trivial. Goal: 5 (and 1 — cost/latency stability).**

`gemini_client.py:245-250` only sets `thinkingConfig` when `"gemma" in
model.lower()`. Every `gemini-3.1-flash-lite` call (`CRITIQUE_MODEL`,
`BUILDER_MODEL`, `FIND_WEBSITE_MODEL`, `SCORE_MODEL` — five call sites
across `orchestrator.py`, `rewrite_bullets.py`, `company_research.py`)
sends no `thinkingConfig` at all, so it runs at whatever Google's current
default is for that tier. Live docs confirm valid levels for 3.1
Flash-Lite are `minimal`/`low`/`medium`/`high`, that `minimal` is the
*current* default — and that defaults for this exact tier already shifted
once, in the Gemini 3.5 Flash rollout. The Gemma branch already made a
deliberate choice here (`minimal`, to suppress a billed "thought" preamble);
the flash-lite calls should make the same choice explicitly rather than
riding an undocumented default that can move under the code without any
local change.

### 2. Explicit context caching for the audit loop's system prompts
**Effort: medium. Goal: 1/5 (cost).**

`grep -rn "cached_content\|caches\."` across `scripts/` returns nothing —
no explicit caching anywhere. `orchestrator.py`'s audit loop sends the same
fixed system instruction (the rules files: `hard_failures.yaml`,
`truthfulness_rules.yaml`, `style_rules.yaml`, `formatting_rules.yaml`,
`verb_taxonomy.yaml`, etc., concatenated into the prompt) on every one of
Phase 4's measured 1,144 JDs. Implicit caching is on by default for 2.5+
models and may already be capturing some of this for free (90% discount on
a hit, 1,024–2,048 token minimum) — genuinely possible nobody knows the hit
rate today. Explicit caching (32,768-token minimum, same 90% discount,
deterministic instead of opportunistic) is the more reliable lever at this
call volume, but building it is real work: cache lifecycle management,
storage cost accounting, and confirming the cached content is actually
static across the loop rather than subtly JD-dependent. **Recommend:**
before building explicit-cache machinery, instrument one run to see whether
implicit caching is already firing (Gemini responses include cache-hit
token counts) — cheap experiment, and it tells you whether step 2 is "wire
up explicit caching" or "already free, do nothing."

### 3. Batch Mode — evaluate, don't blanket-adopt
**Effort: medium–large to implement; small to decide. Goal: 1/5 (cost).**

Batch Mode is 50% off input+output tokens with an up to 24-hour turnaround,
submitted as an async job — and its discount does *not* stack with a cache
hit (cache wins when both apply). Good fit for genuinely offline,
unattended work; the codebase already has some of that shape (batch
`resume run` processes every pending JD in one unattended sweep, and
`cluster_bullet_bank.py`/`embed_bullet_bank.py` already do their own manual
batching against `batchEmbedContents`, which is a different, older
mechanism from Batch Mode). Bad fit for single-file `resume run
jds/.../file.txt` mode and for the checkpoint-resume architecture, both of
which assume synchronous request/response per JD and a result the user is
about to look at. **This needs someone who owns `orchestrator.py`
(Phase 4's territory) to separate "calls a human is waiting on" from "calls
that happen inside an unattended batch run" before deciding** — recording
the opportunity here rather than a recommendation, since that split isn't
visible from outside the orchestration logic.

### 4. Consolidate two of the three TUI renderers
**Effort: medium. Goal: 5, with a real 4/1 side-benefit (fewer places for
color/behavior to drift).**

`theme.py:106-157` carries `colorize_icon()` (Rich markup), fewer
`colorize_icon_ansi()` (raw ANSI, for bare `print()` call sites), and
`questionary_icon_tuple()` (prompt_toolkit's `(style, text)` tuples) —
three functions for one palette. `colorize_icon_ansi()`'s own docstring
already flags itself as the workaround: "use this ... in any script that
calls the plain `print()` builtin directly." That's the tell — the third
renderer exists only because some scripts never got a `rich.Console`
threaded through them, not because bare `print()` earns its keep anywhere.
questionary sits on `prompt_toolkit` and genuinely renders differently from
Rich (different color-injection mechanism), so that split is real and
inherent — but the `print()` branch is not. Current guidance (checked live,
2026) still treats Rich+questionary as the standard pairing for a
prompt-driven CLI like this one; Textual is the right tool only if the
interactive menu becomes a persistent full-screen app, which is a much
bigger behavior change than this codebase is asking for and not
recommended here. **Recommend:** audit which of the ten files using
Rich/questionary still fall back to bare `print()` and route them through a
shared `Console`, collapsing three colorizers to two.

### 5. Go dashboard vs. Python TUI: close the theme gap, don't merge
**Effort: n/a (decision) + small (theme-gap fix, Phase 2's territory).
Goal: 5, informed by goal 4.**

The Go dashboard (`bubbletea` v1.3.10, `lipgloss` v1.1.0 — current,
well-maintained) is read-only analytics/tracker surface (Pipeline /
Progress / Viewer, per `IDEAS.md`). The Python TUI is where the Gemini
pipeline actually executes — bullet-bank editing, JD picking, tailoring,
checkpoint resume. Porting that to Go means reimplementing or bridging the
entire Gemini client for no clear payoff; porting the dashboard's
analytics into Python loses nothing but a second language and gains
nothing either. Phase 2's finding that the dashboard already supports
light/dark + Catppuccin theming while the Python TUI is dark-only is real,
but it argues for extending `theme.py`'s palette to support a light variant
(small, additive, stays in Phase 2's ownership), not for a dashboard/TUI
merge. **Keep both, close the theme asymmetry, do not retire either.**

### 6. No `pipx install` / `uv tool install` path
**Effort: medium. Goal: 5, with direct payoff against goal 3.**

No `pyproject.toml` or `setup.py` exists anywhere in the repo (confirmed:
`ls` comes back empty for both). `scripts/resume-cli.sh` is a hand-rolled
shell function sourced into `~/.zshrc`/`~/.bashrc` that shells out to
`python scripts/cli.py` — not an installed entry point. Both `uv tool
install` and `pipx` expect a `pyproject.toml` with a `[project.scripts]`
table; that's the current (2026) standard for distributing a Python CLI,
and adopting it doesn't require giving up the existing venv-based dev flow
— it's additive packaging metadata over the same `requirements.txt`
dependency set. This directly shortens the "clone → source a shell
snippet → hope your shell is zsh or bash" first-run sequence Phase 1
already flagged as a stranger-adoption cost. Cheap relative to payoff: one
`pyproject.toml`, one entry-point function wrapping `cli.py`'s existing
`main()`, a `README.md` update.

### 7. Stale model reference in a docstring
**Effort: trivial. Goal: 5.**

`rewrite_bullets.py:67`'s usage example: `python rewrite_bullets.py
--retry-manual --model gemini-2.5-pro`. Gemini 2.5 models shut down
October 2026 — two months from today. Low risk (it's a copy-paste example,
not load-bearing code) but a two-minute fix while it's still cheap, rather
than after the model starts 404ing on whoever tries the example.

### 8. Structured output — already current, no action
Confirmed `gemini_client.py` already sends `responseMimeType:
application/json` plus a real `responseSchema` derived from Pydantic
models. This is the one item in the plan's Gemini bullet that's a
non-finding — recorded so nobody re-investigates it.

---

## IDEAS.md / ImprovementConcepts scan

- `ImprovementConcepts/*.docx` and the `jobright-*.md` files are
  competitive/feature research (JobRight comparison, MCP connector
  analysis) — not modernization-tech opportunities, out of scope for this
  phase, not re-summarized here.
- `IDEAS.md` currently has no packaging/pipx item and no context-caching or
  Batch Mode item. **Recommend folding opportunities #2, #3, and #6 above
  into `IDEAS.md`** (Medium tier, per its own difficulty scale) since that
  file is the living backlog and this document is a one-time snapshot.

---

## Handoffs

None. Every file touched here (`gemini_client.py`, `theme.py`,
`orchestrator.py`, `rewrite_bullets.py`, `dashboard/go.mod`) was read only
for the specific cross-cutting question Phase 5's brief poses, not
critiqued more broadly — deeper findings in any of those files belong to
whichever phase already owns them (mostly Phase 4).
