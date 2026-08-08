# Charm Prompt Migration — Design

## Context: the broader Charmbracelet redesign

This is the first of four sub-projects in a larger effort to bring the
Charmbracelet ecosystem (`bubbletea`, `lipgloss`, `huh`, `glamour`) deeper
into the project, building on `dashboard/`'s existing use of them. The four
sub-projects, in planned order:

1. **Charm prompt migration** (this spec) — generalize the pattern already
   proven by `dashboard/cmd/bootstrap` (a Go/`huh` binary invoked via
   subprocess, returning JSON) so the rest of `scripts/menu.py`'s
   `questionary` prompts can move to it.
2. **TUI Dashboard build-out** — continue `dashboard/`'s main `resume
   dashboard` view against the `.impeccable/surface-dashboard.md` "Command
   Center Editor" design system already on file.
3. **Console-output standardization (Python)** — finish the `print()` →
   `cli_art` helper sweep already underway in `audit_keepers.py`,
   `liveness.py`, `batch_evaluate.py`, etc. `rich`-based, not Charm, but
   the same polish goal.
4. **Opportunistic Charm tooling** — `gum` for any raw shell prompts in
   `resume-cli.sh`, `charmbracelet/log` for structured Go logging in
   `dashboard/`, possibly `glow`/`freeze` for terminal-rendered docs.

Sub-projects 2-4 are out of scope for this spec and get their own
spec/plan cycle when picked up.

## Problem

`dashboard/cmd/bootstrap` proved a working pattern for bringing `huh`'s
interactive prompts into the Python-orchestrated CLI: a small Go binary,
invoked via `go run` from `menu.py`, that renders a form and prints JSON
to stdout for Python to consume. `_handle_bootstrap()` in `scripts/menu.py`
already uses it.

But that binary is bespoke — one Go program purpose-built for exactly the
bootstrap wizard's four fields. `menu.py` has 18 more `questionary` call
sites (`select`, `confirm`, `checkbox` — no raw `text()` prompts remain
outside the migrated bootstrap flow) with no path to Charm without writing
a new bespoke Go binary per call site, which doesn't scale.

Separately, `test_menu_bootstrap.py` still patches `menu.questionary.text`
and asserts a name prompt fires on the guest-mode path — but
`_handle_bootstrap()` no longer calls `questionary.text()` at all since it
shells out to the Go binary unconditionally. Those assertions currently
pass against a mock that's never exercised by the real code path, which is
worse than a failing test: it reports coverage that isn't there.

## Goals

- A generic Go binary (`dashboard/cmd/prompt`) that renders `select`,
  `confirm`, or `checkbox` from a JSON spec on stdin and writes the result
  as JSON to stdout — no new Go binary needed per prompt.
- A Python wrapper (`scripts/charm_prompt.py`) exposing `select()`,
  `confirm()`, `checkbox()` with the same call shape as the `questionary`
  functions they replace, so call-site conversions in `menu.py` are
  near-mechanical.
- Icon-colored options (the main menu's `theme.questionary_icon_tuple`
  styling) carry over: an optional `icon` key per option resolves to
  glyph+color via `dashboard/internal/theme`, the Go-side mirror of
  `theme.py`'s icon system.
- Cancellation (ESC/Ctrl-C) maps to Python `None`, matching `questionary`'s
  `.ask()` contract exactly, so every existing `if not choice: return
  False` guard in `menu.py` keeps working without modification.
- Convert `menu.py`'s 5 `confirm()` call sites to prove the pattern
  end-to-end (binary, wrapper, theme lookup, cancellation, test-mock
  boundary) before the more visually complex `select()`/`checkbox()`
  sites.
- Fix `test_menu_bootstrap.py`'s stale `questionary.text` patch as part of
  this spec.

## Non-Goals

- Converting the remaining 13 `select()`/`checkbox()` call sites in
  `menu.py` (including the icon-heavy main menu `_CHOICES` list) — this
  spec proves the architecture on `confirm()` only. Once validated,
  converting the rest is straightforward mechanical follow-up.
- Field-level validators (e.g. `bootstrap`'s path-exists check) — none of
  the 18 remaining call sites need them; the bootstrap wizard's own
  per-field validation stays exactly where it is, in its own bespoke
  binary, and is not touched here.
- Merging entire flows (e.g. the whole main-menu loop) into one long-lived
  Go process. Measured: `go run` on the existing bootstrap binary takes
  ~30ms warm / ~108ms cold — invisible at human interaction speed, so
  per-prompt subprocess calls are fine even for a looping menu. No need to
  avoid subprocess overhead architecturally.
- `go build` / a compiled binary anywhere in the repo. This follows the
  same rule `dashboard/` already operates under (see CLAUDE.md) — `go run`
  only.

## Architecture

**`dashboard/cmd/prompt/main.go`** (new): reads a JSON spec from stdin —

```json
{
  "type": "confirm",
  "message": "Ready to process 3 document(s)?",
  "default": true
}
```

— and for `select`/`checkbox`, an `options` array of
`{"label", "value", "icon"}`. Dispatches to `huh.NewConfirm()`,
`huh.NewSelect[string]()`, or `huh.NewMultiSelect[string]()` based on
`type`, applying `theme.NewTheme("")` the same way `dashboard/cmd/bootstrap`
does today. On submit, writes `{"value": ...}` (or `{"values": [...]}` for
checkbox) to stdout and exits 0. On cancel (ESC/Ctrl-C), writes nothing to
stdout and exits with a distinct non-zero code reserved for cancellation
(130, matching shell SIGINT convention) so the wrapper can tell "user
backed out" apart from "the binary crashed."

**`scripts/charm_prompt.py`** (new): thin wrapper mirroring `questionary`'s
call shape —

```python
def confirm(message: str, default: bool = True) -> bool | None: ...
def select(message: str, choices: list, default=None) -> str | None: ...
def checkbox(message: str, choices: list) -> list | None: ...
```

Each builds the JSON spec, runs `go run ./dashboard/cmd/prompt` via
`subprocess.run` (same `cwd` pattern `_handle_bootstrap()` already uses),
and parses stdout. Exit code 130 → return `None`. Exit code 0 but
unparseable JSON, or any other non-zero exit → raise `RuntimeError` with
stderr attached, so a real failure is loud rather than silently treated as
a user cancellation.

`choices` accepts the same shape `menu.py` already builds for
`questionary.Choice` — `{"title", "value", "icon"}` — so call sites mostly
just swap the function name and drop the trailing `.ask()`.

## Data Flow

1. `menu.py` calls `charm_prompt.confirm("Ready to process 3 document(s)?", default=True)`.
2. `charm_prompt.py` serializes the spec, invokes `go run
   ./dashboard/cmd/prompt`, writes the JSON spec to the subprocess's stdin.
3. `dashboard/cmd/prompt` renders the `huh.Confirm`, captures the answer.
4. On submit: prints `{"value": true}`, exits 0. On cancel: prints
   nothing, exits 130.
5. `charm_prompt.py` parses the result and returns `True`/`False`/`None` to
   `menu.py`, which uses it exactly like the `questionary` return value it
   replaced.

## Error Handling

- **User cancels (ESC/Ctrl-C):** exit 130, empty stdout → `None`. Existing
  `menu.py` guards (`if not proceed: return False`) already handle this.
- **Go binary crashes or emits malformed JSON:** any other non-zero exit,
  or exit 0 with unparseable stdout → `charm_prompt.py` raises
  `RuntimeError(stderr)`. This is a deliberate asymmetry from the current
  bootstrap handler (which prints "Bootstrap wizard failed" and returns
  `False` on any non-zero exit) — collapsing "broke" and "user declined"
  into the same silent `False` is exactly the kind of masked failure this
  migration should avoid introducing at 18 more call sites.
- **`go` toolchain missing or `dashboard/` module broken:** surfaces as the
  same `RuntimeError` path — not specially handled, since `resume doctor`
  already checks for a working Go toolchain as an environment
  precondition.

## Testing

- **Go side:** unit test `Spec`/`Result` JSON marshal/unmarshal in
  `dashboard/internal/ui/prompt` (new package housing the shared logic
  `cmd/prompt/main.go` calls into, matching the `cmd/bootstrap` /
  `internal/ui/bootstrap` split already in place). No new `huh` field
  types are introduced, so no additional rendering tests are needed beyond
  what `bootstrap`'s existing tests already cover for the theme layer.
- **Python side:** new `tests/test_charm_prompt.py` patches
  `subprocess.run` directly (the one true boundary for this module) and
  asserts the JSON-in/JSON-out contract, including the exit-130-is-None
  and malformed-JSON-raises cases.
- **`menu.py` call-site tests:** the 5 confirm sites' existing tests
  (spread across `test_menu.py`, `test_menu_update_knowledge.py`, etc.)
  move their patch target from `questionary.confirm` to
  `menu.charm_prompt.confirm`, asserting against the wrapper's plain
  `bool`/`None` return instead of a `Mock().ask()` chain.
- **Stale test fix:** `test_menu_bootstrap.py`'s
  `test_guest_mode_triggers_name_prompt_even_though_morgan_profile_exists`
  and its sibling (patching `menu.questionary.text`) get rewritten to
  patch `menu.subprocess.run` and assert against
  `dashboard/cmd/bootstrap`'s actual JSON-out contract, matching what
  `_handle_bootstrap()` really does today.
