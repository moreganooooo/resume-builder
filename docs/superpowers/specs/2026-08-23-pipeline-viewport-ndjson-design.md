# Pipeline Viewport: NDJSON events + Bubble Tea screen

**Date:** 2026-08-23
**Status:** Proposed
**Goal:** Run the batch pipeline inside a Bubble Tea viewport (Crush-shaped
scrollback with a pinned header/footer) instead of raw Rich output scrolling
the terminal.

---

## 1. What the codebase actually looks like

Four measurements taken before planning; two of them change the shape of the
work substantially.

### 1.1 There is exactly ONE Console object

The single most important finding. Neither `orchestrator.py` nor
`rewrite_bullets.py` constructs a `Console`:

```
$ grep -c "^console = Console" scripts/*.py
scripts/cli_art.py:1        # the only one, cli_art.py:39
$ grep -cE "(^|[^.a-zA-Z_])console\.print\(" scripts/orchestrator.py
0                           # zero bare console.print
$ grep -c "cli_art\.console\.print(" scripts/orchestrator.py
93
```

Every call site in both modules is `cli_art.console.print(...)` — reaching
through the module into one shared object. Repo-wide, the surface used on it
is only five members:

| Member | Uses | Notes |
| --- | --- | --- |
| `.print` | 471 | the whole game |
| `.rule` | 37 | step separators (`Step 2: Mining bullet bank...`) |
| `.status` | 6 | context manager, spinner |
| `.width` | 5 | property |
| `.is_terminal` | 3 | property |

**Consequence:** the sink swap is a *five-member duck type*, not a
278-site refactor. Replacing `cli_art.console` with an object exposing
those five members redirects every call site in the program at once,
with zero edits to `orchestrator.py` or `rewrite_bullets.py`.

### 1.2 The print-site count is lower than estimated

Actual `grep -c print`: **166** in `orchestrator.py`, **63** in
`rewrite_bullets.py` (229, not 278). And per 1.1, most need no edit at all
— only the subset we want to *promote* from prose to a typed event
(`step`, `validator`, `score`, `done`) gets touched. Estimate: **~40
deliberate call-site edits**, not 229.

### 1.3 The prompt path inverts, and that is the real hard part

Today: Python is the parent. `cli_art.confirm()` → `charm_prompt.py` →
`subprocess.run(dashboard/cmd/prompt)` → a huh TUI owns the terminal for
one blocking question → one JSON blob back.

Under this design **Go is the parent** and already owns the terminal.
A child process cannot open a second TUI on that same terminal — huh
would fight the parent's Bubble Tea program for the alt-screen and input.
So in event mode `charm_prompt` must be *bypassed entirely*, not reused:
Python emits a `prompt` event and blocks reading a response line from
**stdin**; the parent renders the prompt inline in its own program and
writes the answer back down the pipe. This is a genuine second protocol
(bidirectional, correlated by id), not an extension of the existing one.

### 1.4 Go side has what it needs

`charm.land/bubbles/v2 v2.1.1` (viewport, spinner), `harmonica v0.2.0`,
`glamour v1.0.0` are already in `go.mod`. Screens follow a settled
convention (`progress.go:22,48`): `type XClosedMsg struct{ Quit bool }`
and `func NewXModel(t theme.Theme, data T, width, height int) XModel`,
with `Update` returning `(XModel, tea.Cmd)`. New screen conforms.

---

## 2. Architecture

```
menu.py (tailor_all)
  └─ Popen([dashboard, run-pipeline, --jd, PATH])        Go = parent, owns TTY
        └─ Popen([python, orchestrator.py, PATH],        Python = child
                  env=RESUME_EVENT_STREAM=fd3)
              stdout ─── NDJSON ──▶ goroutine ──▶ tea.Msg ──▶ viewport
              stdin  ◀── replies ── program (prompt answers only)
```

### 2.1 Which fd carries events

**Not stdout.** Anything the child prints outside our sink — a
traceback, a `warnings` line, a chatty dependency — would land in the
NDJSON stream and break the decoder. Events go to **fd 3**, opened by Go
via `exec.Cmd.ExtraFiles`; the child's stdout/stderr stay a plain byte
stream the viewport can render as raw log lines. `RESUME_EVENT_STREAM=3`
both gates the sink and names the fd.

Python must `flush=True` per line (or open fd 3 line-buffered) — a pipe
is block-buffered by default and events would arrive in 4 KB clumps at
process exit.

### 2.2 Event schema (NDJSON, one object per line)

Every event carries `type` and a monotonic `seq` (lets the reader detect
a truncated line rather than silently dropping it).

```json
{"seq":1,  "type":"step",      "n":4, "total":9, "label":"Building resume..."}
{"seq":2,  "type":"log",       "level":"info", "text":"Mined 30 bullets from bank"}
{"seq":3,  "type":"log",       "level":"warn", "text":"Context cache creation failed (429)"}
{"seq":4,  "type":"validator", "attempt":2, "max":4, "temperature":0.2,
           "issues":["Bullet is 136 chars..."]}
{"seq":5,  "type":"score",     "label":"summary_alignment", "value":90}
{"seq":6,  "type":"prompt",    "id":"abc123", "kind":"confirm",
           "text":"Apply this recommendation?"}
{"seq":7,  "type":"done",      "ok":true, "artifact":"/path/to.pdf"}
```

Reply frames (Go → Python stdin), same NDJSON shape:

```json
{"type":"reply","id":"abc123","value":true}
```

Rules:
- Unknown `type` renders as a dim raw line, never an error. Forward
  compatibility is free here and worth taking.
- `text` is already-scrubbed. `cli_art.scrub_pii()` (cli_art.py:58) runs
  in the sink before serialization, not on the Go side — PII must not
  cross the pipe at all.
- `level` ∈ `debug|info|warn|error`, mapping `cli_art.detail()`'s
  verbosity levels; the viewport can filter client-side.

### 2.3 The sink

```python
class EventSink:
    """Duck-types the five Console members used repo-wide (see §1.1)."""
    def print(self, *objects, **kwargs): ...   # → {"type":"log"}
    def rule(self, title="", **kwargs): ...    # → {"type":"step"}
    def status(self, message, **kwargs): ...   # → contextmanager, log + no-op
    width = 100          # fixed; the viewport re-wraps anyway
    is_terminal = False  # suppresses Rich's own animation paths
```

The `print` implementation renders Rich renderables (Table, Panel, Text)
to plain text via a throwaway `Console(file=StringIO(), width=100)` and
emits the result as a `log` event. That is the fallback that makes the
mode work *on day one* for all 471 sites, including the tables we have
not yet given typed events. Typed events are then an incremental
upgrade, site by site, not a precondition.

Install point: `cli_art.py` module scope, gated on the env var, so
`import cli_art` alone selects the sink and no caller changes.

---

## 3. Phases

Each phase is independently shippable and leaves the tree working.

### Phase 1 — Python sink (no Go)
1. `scripts/event_stream.py`: `emit(dict)`, seq counter, fd resolution,
   flush, `enabled()` predicate.
2. `EventSink` in `cli_art.py` + module-scope gate.
3. Promote the ~40 high-value sites to typed events: the `console.rule`
   step separators → `step`; validator attempt blocks in
   `orchestrator.py` → `validator`; critique score table → `score`;
   pipeline exit → `done`.
4. SIGINT handler emits `{"type":"done","ok":false,"cancelled":true}`
   before re-raising, so a Ctrl-C is a frame, not a silence.
5. **Exit gate:** `RESUME_EVENT_STREAM=1 python scripts/orchestrator.py
   fixtures/sample_jd.txt 3>events.ndjson` produces a file where every
   line parses and `seq` is gap-free.

Test impact is smaller than feared: only tests asserting on *promoted*
sites need rewriting, and they get *easier* — asserting
`{"type":"step","n":4}` beats regex-matching styled console text.
`test_orchestrator_retry_hints.py` is the main one. Untouched sites keep
passing through the Rich path unchanged, because the sink is off by
default under `unittest`.

### Phase 2 — Static Go viewer
`dashboard/internal/ui/screens/pipeline_run.go`, reading a **saved**
NDJSON file. All rendering parity work lands here with zero concurrency
risk:

| Rich | lipgloss/bubbles |
| --- | --- |
| Panels (banner, execution footer) | `lipgloss.Border` |
| Gradient "Thinking..." | `bubbles/v2/spinner` + existing gradient helper |
| ✓ / ⚠ / ✗ | `theme` constants (already Go-side) |
| Validator issues, score tables | `lipgloss/v2/table` |
| `[3/30]` bullet audit tree | small custom renderer |

Exit gate: `pipeline_run_test.go` renders a committed fixture NDJSON and
golden-matches the frame, same as `progress_test.go` does today.

### Phase 3 — Live streaming
Swap file read for `exec.Cmd` + `ExtraFiles` fd 3. A goroutine
`bufio.Scanner`s the pipe into a channel; a `tea.Cmd` reads one message
per call and re-arms — the standard bubbletea streaming shape. Must
handle:
- clean EOF *without* a `done` event → render "pipeline exited
  unexpectedly (code N)", never hang;
- non-zero exit → surface stderr tail;
- parent Ctrl-C → forward SIGINT to the child, then wait for its
  `cancelled` frame with a ~2 s deadline before SIGKILL;
- `Scanner` buffer raised past the 64 KB default — a validator event
  carrying many issues will exceed it.

### Phase 4 — Prompt round-trip + cutover
Bidirectional half from §1.3, then route `menu.py`'s batch actions
through the new screen behind `RESUME_PIPELINE_VIEWPORT=0` as an escape
hatch for one release.

---

## 4. Risks

| Risk | Mitigation |
| --- | --- |
| Stray child stdout corrupts stream | fd 3, §2.1 — structural, not defensive |
| Buffering stalls the viewport | explicit flush per event; Phase 1 exit gate catches it |
| Prompt deadlock (both sides waiting) | reply timeout on the Python side → treat as default answer, emit `warn` |
| Rendering drift Rich↔lipgloss | Phase 2 goldens before any concurrency exists |
| Sink leaks into tests | gate defaults off; assert it in `test_cli_art.py` |

---

## 5. Part 2 — independent polish (not blocked on any of the above)

1. **Markdown that renders.** `cli_art.py` imports
   `rich.markdown.Markdown` but uses it in exactly one place
   (`display_applications_tracker`, cli_art.py:1203). Rich's default
   markup is BBCode (`[bold]`), so validator skills output prints
   `**CRM & Marketing Operations:**` with literal asterisks. Fix: route
   that content through the `Markdown()` renderer already imported.
   Contained, visible, ~an hour.
2. **Native lipgloss table/tree.** `lipgloss/v2` ships both; check
   whether `jobs.go` (65 KB) and `pipeline.go` (39 KB) are hand-drawing
   them. Potentially removes code rather than adding it — and Phase 2
   wants `lipgloss/v2/table` anyway, so doing this first de-risks that.

**Recommendation:** do Part 2 first. It is small, ships value
immediately, and item 2 is a direct dependency of Phase 2.
