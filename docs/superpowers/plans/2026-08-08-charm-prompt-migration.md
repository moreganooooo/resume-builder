# Charm Prompt Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a generic Go/`huh` prompt binary + Python wrapper that generalizes `dashboard/cmd/bootstrap`'s subprocess+JSON pattern, and convert `scripts/menu.py`'s 5 `confirm()` call sites to use it.

**Architecture:** `dashboard/cmd/prompt` reads a JSON spec (passed as a CLI argument, not stdin — `huh` needs real stdin for keystrokes) describing a `select`/`confirm`/`checkbox` prompt, renders it via `huh`, and writes the answer as JSON to stdout. `scripts/charm_prompt.py` wraps it with `select()`/`confirm()`/`checkbox()` functions matching `questionary`'s call shape. Cancellation (ESC/Ctrl-C) maps to exit code 130 → Python `None`; any other failure raises `RuntimeError`.

**Tech Stack:** Go 1.24 (`charmbracelet/huh` v0.4.1, already a dependency), Python 3.10+ (`subprocess`, stdlib `unittest`).

## Global Constraints

- `go run` only — never `go build`. No compiled binary lands in the repo (existing project rule, see CLAUDE.md).
- Python 3.10+ syntax throughout (`str | None`, not `Optional[str]`).
- Cancellation exit code is `130` (matches shell SIGINT convention), reserved and must not collide with any other exit path.
- This plan converts `confirm()` call sites only. `select()`/`checkbox()` get Go rendering support (for future call sites) but no `menu.py` call site is converted to them in this plan.
- **Deviation from the approved spec:** icon-colored options (spec Goal 3) are deliberately NOT implemented here — no `Icon` field on `Option`, no theme lookup. No `select()`/`checkbox()` call site is converted in this plan to exercise or test it, and `dashboard/internal/theme`'s `Icons` struct only has two icon names (`Evaluate`, `Utility`) today — nowhere near the set `menu.py`'s main menu actually uses (`new_user`, `bullet_bank`, `discovery`, `build`, `utility`, `hint`, ...). Building icon resolution now would be untested, speculative code. It belongs in whichever future plan first converts an icon-bearing `select()` site, alongside expanding the Go icon set to match.
- No field-level validators in the JSON spec — none of the 5 `confirm()` sites need them.
- Tests patch `menu.charm_prompt.confirm` (or `.select`/`.checkbox`), not `subprocess.run` directly, at every `menu.py` call site — `charm_prompt.py`'s own subprocess boundary is tested once, in `tests/test_charm_prompt.py`.

---

### Task 1: Go prompt package (`dashboard/internal/ui/prompt`)

**Files:**
- Create: `dashboard/internal/ui/prompt/prompt.go`
- Test: `dashboard/internal/ui/prompt/prompt_test.go`

**Interfaces:**
- Consumes: `theme.Theme` (existing, `dashboard/internal/theme`), specifically `theme.NewTheme(string) Theme` and `Theme.HuhTheme() huh.Theme`.
- Produces: `prompt.Spec` (JSON-decodable), `prompt.Result` (JSON-encodable), `prompt.Run(theme.Theme, Spec) (Result, error)` — consumed by Task 2's `main.go`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/internal/ui/prompt/prompt_test.go`:

```go
package prompt

import (
	"encoding/json"
	"testing"
)

func TestSpecUnmarshal_Confirm(t *testing.T) {
	raw := `{"type":"confirm","message":"Ready?","default":true}`
	var spec Spec
	if err := json.Unmarshal([]byte(raw), &spec); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if spec.Type != "confirm" {
		t.Errorf("Type = %q, want %q", spec.Type, "confirm")
	}
	if spec.Message != "Ready?" {
		t.Errorf("Message = %q, want %q", spec.Message, "Ready?")
	}
	if !spec.Default {
		t.Errorf("Default = false, want true")
	}
}

func TestSpecUnmarshal_SelectWithOptions(t *testing.T) {
	raw := `{"type":"select","message":"Pick one","options":[{"label":"A","value":"a"},{"label":"B","value":"b"}],"default_value":"b"}`
	var spec Spec
	if err := json.Unmarshal([]byte(raw), &spec); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if len(spec.Options) != 2 {
		t.Fatalf("len(Options) = %d, want 2", len(spec.Options))
	}
	if spec.Options[0].Label != "A" || spec.Options[0].Value != "a" {
		t.Errorf("Options[0] = %+v, want {A a}", spec.Options[0])
	}
	if spec.DefaultValue != "b" {
		t.Errorf("DefaultValue = %q, want %q", spec.DefaultValue, "b")
	}
}

func TestResultMarshal_Confirm(t *testing.T) {
	answer := true
	result := Result{Confirmed: &answer}
	out, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if string(out) != `{"confirmed":true}` {
		t.Errorf("Marshal = %s, want %s", out, `{"confirmed":true}`)
	}
}

func TestResultMarshal_Select(t *testing.T) {
	result := Result{Value: "b"}
	out, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if string(out) != `{"value":"b"}` {
		t.Errorf("Marshal = %s, want %s", out, `{"value":"b"}`)
	}
}

func TestResultMarshal_Checkbox(t *testing.T) {
	result := Result{Values: []string{"bullets", "profile"}}
	out, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if string(out) != `{"values":["bullets","profile"]}` {
		t.Errorf("Marshal = %s, want %s", out, `{"values":["bullets","profile"]}`)
	}
}

func TestRun_UnknownTypeErrors(t *testing.T) {
	_, err := Run(theme.Theme{}, Spec{Type: "bogus"})
	if err == nil {
		t.Fatal("expected an error for an unknown prompt type, got nil")
	}
}
```

Note: `TestRun_UnknownTypeErrors` needs `"github.com/moreganooooo/resume-builder/dashboard/internal/theme"` imported — add it to the test file's import block alongside `encoding/json` and `testing`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && go test ./internal/ui/prompt/...`
Expected: FAIL — `prompt.go` doesn't exist yet, so this won't even compile (`undefined: Spec`, `undefined: Result`, `undefined: Run`).

- [ ] **Step 3: Write the implementation**

Create `dashboard/internal/ui/prompt/prompt.go`:

```go
// Package prompt renders a single interactive prompt (select, confirm, or
// checkbox) from a JSON spec and returns the answer. Generalizes the
// one-off dashboard/cmd/bootstrap pattern (a bespoke Go/huh binary per
// prompt) into a single reusable binary driven by data instead of code,
// so scripts/menu.py's remaining questionary call sites can move to Charm
// without a new Go binary per prompt.
package prompt

import (
	"fmt"

	"github.com/charmbracelet/huh"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// Option is one selectable item in a select or checkbox prompt.
type Option struct {
	Label string `json:"label"`
	Value string `json:"value"`
}

// Spec describes the prompt to render, decoded from the CLI argument JSON.
// Default is used by "confirm"; DefaultValue is used by "select" -- kept
// as separate fields since they're different JSON types, not a shared
// "default" key.
type Spec struct {
	Type         string   `json:"type"` // "select", "confirm", or "checkbox"
	Message      string   `json:"message"`
	Options      []Option `json:"options,omitempty"`
	Default      bool     `json:"default,omitempty"`
	DefaultValue string   `json:"default_value,omitempty"`
}

// Result is the answer, encoded to stdout JSON. Exactly one field is set,
// matching Spec.Type: Confirmed for "confirm", Value for "select", Values
// for "checkbox".
type Result struct {
	Value     string   `json:"value,omitempty"`
	Values    []string `json:"values,omitempty"`
	Confirmed *bool    `json:"confirmed,omitempty"`
}

// Run renders the prompt described by spec using the given theme and
// returns the answer. On cancellation (ESC/Ctrl-C), the returned error
// wraps huh.ErrUserAborted -- dashboard/cmd/prompt/main.go checks for it
// with errors.Is to map it to a distinct exit code.
func Run(t theme.Theme, spec Spec) (Result, error) {
	switch spec.Type {
	case "confirm":
		return runConfirm(t, spec)
	case "select":
		return runSelect(t, spec)
	case "checkbox":
		return runCheckbox(t, spec)
	default:
		return Result{}, fmt.Errorf("unknown prompt type %q", spec.Type)
	}
}

func runConfirm(t theme.Theme, spec Spec) (Result, error) {
	answer := spec.Default
	field := huh.NewConfirm().
		Title(spec.Message).
		Value(&answer)
	form := huh.NewForm(huh.NewGroup(field)).Theme(t.HuhTheme())
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Confirmed: &answer}, nil
}

func runSelect(t theme.Theme, spec Spec) (Result, error) {
	answer := spec.DefaultValue
	opts := make([]huh.Option[string], len(spec.Options))
	for i, o := range spec.Options {
		opts[i] = huh.NewOption(o.Label, o.Value)
	}
	field := huh.NewSelect[string]().
		Title(spec.Message).
		Options(opts...).
		Value(&answer)
	form := huh.NewForm(huh.NewGroup(field)).Theme(t.HuhTheme())
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Value: answer}, nil
}

func runCheckbox(t theme.Theme, spec Spec) (Result, error) {
	var answer []string
	opts := make([]huh.Option[string], len(spec.Options))
	for i, o := range spec.Options {
		opts[i] = huh.NewOption(o.Label, o.Value)
	}
	field := huh.NewMultiSelect[string]().
		Title(spec.Message).
		Options(opts...).
		Value(&answer)
	form := huh.NewForm(huh.NewGroup(field)).Theme(t.HuhTheme())
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	if answer == nil {
		answer = []string{}
	}
	return Result{Values: answer}, nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && go test ./internal/ui/prompt/...`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/ui/prompt/prompt.go dashboard/internal/ui/prompt/prompt_test.go
git commit -m "feat(dashboard): add generic prompt package for select/confirm/checkbox"
```

---

### Task 2: Go prompt CLI binary (`dashboard/cmd/prompt`)

**Files:**
- Create: `dashboard/cmd/prompt/main.go`

**Interfaces:**
- Consumes: `prompt.Spec`, `prompt.Result`, `prompt.Run` (Task 1). `theme.NewTheme("")` (existing).
- Produces: a CLI contract — `go run ./dashboard/cmd/prompt '<json spec>'` writes one line of JSON to stdout and exits 0 on submit, exits 130 on cancel with empty stdout, exits 1 with a stderr message on any other error. This exact contract is what Task 3's `scripts/charm_prompt.py` depends on.

This binary is interactive (renders a real `huh` form to the terminal), so it can't be covered by `go test` — verify it manually.

- [ ] **Step 1: Write the implementation**

Create `dashboard/cmd/prompt/main.go`:

```go
// Command prompt renders a single interactive prompt (select, confirm, or
// checkbox) described by a JSON spec passed as the program's one CLI
// argument, and writes the answer as JSON to stdout. The spec travels as
// an argument rather than stdin because huh's form needs real stdin for
// keystrokes -- piping the spec through stdin would consume the same
// channel a live terminal session needs.
//
// Generalizes dashboard/cmd/bootstrap's one-off pattern so
// scripts/charm_prompt.py can invoke this same binary for every
// questionary call site being migrated in scripts/menu.py, instead of a
// new Go binary per prompt.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"

	"github.com/charmbracelet/huh"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/prompt"
)

// cancelExitCode matches the shell SIGINT convention (128 + SIGINT's 2),
// distinguishing "user backed out" from any other failure so
// scripts/charm_prompt.py can map it to None instead of raising.
const cancelExitCode = 130

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "prompt: expected exactly one argument, a JSON prompt spec")
		os.Exit(1)
	}

	var spec prompt.Spec
	if err := json.Unmarshal([]byte(os.Args[1]), &spec); err != nil {
		fmt.Fprintf(os.Stderr, "prompt: invalid spec JSON: %v\n", err)
		os.Exit(1)
	}

	t := theme.NewTheme("")
	result, err := prompt.Run(t, spec)
	if err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			os.Exit(cancelExitCode)
		}
		fmt.Fprintf(os.Stderr, "prompt: %v\n", err)
		os.Exit(1)
	}

	out, err := json.Marshal(result)
	if err != nil {
		fmt.Fprintf(os.Stderr, "prompt: failed to encode result: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(out))
}
```

- [ ] **Step 2: Manually verify the submit path**

Run from the project root:

```bash
go run ./dashboard/cmd/prompt '{"type":"confirm","message":"Test?","default":true}'
```

Press `Enter` to accept the default. Expected: the form clears, stdout prints exactly `{"confirmed":true}`, and `echo $?` reports `0`.

- [ ] **Step 3: Manually verify the cancellation path**

Run the same command again, then press `Esc` (or `Ctrl+C`) instead of submitting.

```bash
go run ./dashboard/cmd/prompt '{"type":"confirm","message":"Test?","default":true}'
echo "exit code: $?"
```

Expected: no stdout output, `exit code: 130`.

- [ ] **Step 4: Manually verify a select prompt**

```bash
go run ./dashboard/cmd/prompt '{"type":"select","message":"Pick one","options":[{"label":"Alpha","value":"a"},{"label":"Beta","value":"b"}],"default_value":"b"}'
```

Expected: an interactive list with "Beta" pre-highlighted; submitting without moving the cursor prints `{"value":"b"}`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/cmd/prompt/main.go
git commit -m "feat(dashboard): add generic prompt CLI binary"
```

---

### Task 3: Python wrapper (`scripts/charm_prompt.py`)

**Files:**
- Create: `scripts/charm_prompt.py`
- Test: `tests/test_charm_prompt.py`

**Interfaces:**
- Consumes: the `dashboard/cmd/prompt` CLI contract from Task 2 (invoked via `subprocess.run`, spec as CLI arg, JSON on stdout, exit code 130 = cancel).
- Produces: `charm_prompt.confirm(message: str, default: bool = True) -> bool | None`, `charm_prompt.select(message: str, choices: list, default: str | None = None) -> str | None`, `charm_prompt.checkbox(message: str, choices: list) -> list | None` — consumed by Tasks 4-8's `menu.py` conversions. `choices` accepts either `{"label", "value"}` dicts or objects with `.label`/`.value` attributes (matches `questionary.Choice`'s shape, though `questionary.Choice` actually uses `.title`/`.value` — see the `_option_dict` helper below for the exact attribute names it reads).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_charm_prompt.py`:

```python
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import charm_prompt  # noqa: E402


class TestConfirm(unittest.TestCase):

    @patch("charm_prompt.subprocess.run")
    def test_true_answer_builds_correct_spec_and_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"confirmed": True}), stderr="")

        result = charm_prompt.confirm("Ready?", default=True)

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], "./dashboard/cmd/prompt")
        spec = json.loads(args[3])
        self.assertEqual(spec, {"type": "confirm", "message": "Ready?", "default": True})

    @patch("charm_prompt.subprocess.run")
    def test_false_answer(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"confirmed": False}), stderr="")
        result = charm_prompt.confirm("Ready?", default=True)
        self.assertFalse(result)

    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.confirm("Ready?")
        self.assertIsNone(result)

    @patch("charm_prompt.subprocess.run")
    def test_nonzero_exit_raises_with_stderr(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
        with self.assertRaises(RuntimeError) as ctx:
            charm_prompt.confirm("Ready?")
        self.assertIn("boom", str(ctx.exception))

    @patch("charm_prompt.subprocess.run")
    def test_malformed_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        with self.assertRaises(RuntimeError):
            charm_prompt.confirm("Ready?")


class TestSelect(unittest.TestCase):

    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_value(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"value": "b"}), stderr="")
        result = charm_prompt.select("Pick one", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])
        self.assertEqual(result, "b")

    @patch("charm_prompt.subprocess.run")
    def test_default_is_passed_through_as_default_value(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"value": "b"}), stderr="")
        charm_prompt.select("Pick one", [{"label": "B", "value": "b"}], default="b")
        args = mock_run.call_args[0][0]
        spec = json.loads(args[3])
        self.assertEqual(spec["default_value"], "b")

    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.select("Pick one", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


class TestCheckbox(unittest.TestCase):

    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_values(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"values": ["a", "b"]}), stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])
        self.assertEqual(result, ["a", "b"])

    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_charm_prompt -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'charm_prompt'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/charm_prompt.py`:

```python
"""charm_prompt.py -- Python wrapper around dashboard/cmd/prompt, the
generic Go/huh prompt binary. Generalizes the subprocess+JSON pattern
dashboard/cmd/bootstrap established for the onboarding wizard so the rest
of menu.py's questionary call sites can move to Charm without a bespoke
Go binary per prompt (see
docs/superpowers/specs/2026-08-08-charm-prompt-migration-design.md).

Each function's call shape mirrors the questionary function it replaces:
select()/confirm()/checkbox() all return the answer directly (no `.ask()`
chain), with None meaning the user cancelled (ESC/Ctrl-C) -- exactly what
questionary's own `.ask()` returns on cancellation, so existing
`if not choice: return False` guards in menu.py need no changes at their
call sites.
"""

import json
import os
import subprocess

_CANCEL_EXIT_CODE = 130

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _option_dict(choice) -> dict:
    if isinstance(choice, dict):
        return {"label": choice["label"], "value": choice["value"]}
    return {"label": choice.title, "value": choice.value}


def _run_prompt(spec: dict):
    result = subprocess.run(
        ["go", "run", "./dashboard/cmd/prompt", json.dumps(spec)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == _CANCEL_EXIT_CODE:
        return None
    if result.returncode != 0:
        raise RuntimeError(f"charm_prompt failed (exit {result.returncode}): {result.stderr.strip()}")
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"charm_prompt returned invalid JSON: {result.stdout!r}") from e


def confirm(message: str, default: bool = True) -> bool | None:
    data = _run_prompt({"type": "confirm", "message": message, "default": default})
    if data is None:
        return None
    return data["confirmed"]


def select(message: str, choices: list, default: str | None = None) -> str | None:
    spec = {"type": "select", "message": message, "options": [_option_dict(c) for c in choices]}
    if default is not None:
        spec["default_value"] = default
    data = _run_prompt(spec)
    if data is None:
        return None
    return data["value"]


def checkbox(message: str, choices: list) -> list | None:
    spec = {"type": "checkbox", "message": message, "options": [_option_dict(c) for c in choices]}
    data = _run_prompt(spec)
    if data is None:
        return None
    return data.get("values", [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_charm_prompt -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/charm_prompt.py tests/test_charm_prompt.py
git commit -m "feat: add charm_prompt.py wrapper around the Go prompt binary"
```

---

### Task 4: Convert `_handle_update_knowledge`'s confirm

**Files:**
- Modify: `scripts/menu.py:302-304` (the `proceed = questionary.confirm(...)` call), plus the top-level import block (`scripts/menu.py:16-40`)
- Test: `tests/test_menu_update_knowledge.py:87-188`

**Interfaces:**
- Consumes: `charm_prompt.confirm(message: str, default: bool = True) -> bool | None` (Task 3).

- [ ] **Step 1: Update the failing tests first**

In `tests/test_menu_update_knowledge.py`, there are 4 tests patching `menu.questionary.confirm`. Change each `@patch("menu.questionary.confirm")` to `@patch("menu.charm_prompt.confirm")`, and change each `mock_confirm.return_value.ask.return_value = True`/`False` to `mock_confirm.return_value = True`/`False` (dropping the `.ask` chain, since `charm_prompt.confirm` returns the answer directly). Apply this to:

- `test_both_selected_runs_scope_both` (line 97, 108): `mock_confirm.return_value.ask.return_value = True` → `mock_confirm.return_value = True`
- `test_only_bullets_selected_runs_scope_bullets` (line 120, 131): same change
- `test_only_profile_selected_runs_scope_profile` (line 141, 152): same change
- `test_declining_final_confirm_returns_false_without_running` (line 175, 185): `mock_confirm.return_value.ask.return_value = False` → `mock_confirm.return_value = False`

(`test_nothing_checked_returns_false_without_running` doesn't patch `confirm` at all — leave it untouched, it returns before reaching the confirm call.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu_update_knowledge -v`
Expected: the 4 updated tests FAIL — `menu.py` still calls `questionary.confirm`, so patching `menu.charm_prompt.confirm` has no effect and the real (unmocked in this context) `questionary.confirm(...).ask()` blocks or errors without a TTY.

- [ ] **Step 3: Convert the call site**

In `scripts/menu.py`, add the import alongside the existing ones (after `import theme` around line 40):

```python
import charm_prompt
```

Then replace (around line 302):

```python
    proceed = questionary.confirm(
        f"Ready to process {len(files)} document(s)?", default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

with:

```python
    proceed = charm_prompt.confirm(
        f"Ready to process {len(files)} document(s)?", default=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu_update_knowledge -v`
Expected: PASS (all 5 tests in the file).

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu_update_knowledge.py
git commit -m "refactor: migrate update-knowledge confirm prompt to charm_prompt"
```

---

### Task 5: Convert `_handle_draft_followup`'s confirm

**Files:**
- Modify: `scripts/menu.py:507-509`
- Test: `tests/test_menu.py:583-677`

**Interfaces:**
- Consumes: `charm_prompt.confirm` (Task 3).

- [ ] **Step 1: Update the failing tests first**

In `tests/test_menu.py`, 5 tests in the draft-followup section patch `menu.questionary.confirm`. For each, change `@patch("menu.questionary.confirm")` → `@patch("menu.charm_prompt.confirm")` and `mock_confirm.return_value.ask.return_value = X` → `mock_confirm.return_value = X`:

- `test_no_contacts_drafts_a_generic_message_without_a_prompt` (line 583, 586)
- `test_single_contact_drafts_without_a_selection_prompt` (line 599, 604)
- `test_multiple_contacts_prompts_and_allows_generic_address` (line 617, 625)
- `test_confirming_sent_logs_the_followup` (line 652, 655)
- `test_declining_sent_does_not_log_the_followup` (line 667, 670)

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k DraftFollowup`
Expected: the 5 updated tests FAIL for the same reason as Task 4 Step 2.

- [ ] **Step 3: Convert the call site**

In `scripts/menu.py`, replace (around line 507):

```python
    sent = questionary.confirm(
        "Did you send this?", default=False, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

with:

```python
    sent = charm_prompt.confirm("Did you send this?", default=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k DraftFollowup`
Expected: PASS (all tests in the `TestHandleDraftFollowup`-equivalent section).

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "refactor: migrate draft-followup confirm prompt to charm_prompt"
```

---

### Task 6: Convert `_handle_run_doctor`'s confirm

**Files:**
- Modify: `scripts/menu.py:664-666`
- Test: `tests/test_menu.py:757-780`

**Interfaces:**
- Consumes: `charm_prompt.confirm` (Task 3).

- [ ] **Step 1: Update the failing tests first**

In `tests/test_menu.py`'s `TestHandleRunDoctor` class:

- `test_runs_test_suite_when_confirmed` (line 763, 765): `@patch("menu.questionary.confirm")` → `@patch("menu.charm_prompt.confirm")`; `mock_confirm.return_value.ask.return_value = True` → `mock_confirm.return_value = True`
- `test_skips_test_suite_when_declined` (line 775, 777): same pattern with `False`

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k TestHandleRunDoctor`
Expected: FAIL, same reason as prior tasks.

- [ ] **Step 3: Convert the call site**

In `scripts/menu.py`, replace (around line 664):

```python
    run_tests = questionary.confirm(
        "Also run the full test suite? (slower, ~20s)", default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

with:

```python
    run_tests = charm_prompt.confirm(
        "Also run the full test suite? (slower, ~20s)", default=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k TestHandleRunDoctor`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "refactor: migrate run-doctor confirm prompt to charm_prompt"
```

---

### Task 7: Convert `_prompt_for_update`'s confirm

**Files:**
- Modify: `scripts/menu.py:743-747`
- Test: `tests/test_menu.py:832-865`

**Interfaces:**
- Consumes: `charm_prompt.confirm` (Task 3).

- [ ] **Step 1: Update the failing tests first**

In `tests/test_menu.py`'s `TestPromptForUpdate` class:

- `test_pulls_when_confirmed` (line 850, 852): `@patch("menu.questionary.confirm")` → `@patch("menu.charm_prompt.confirm")`; `mock_confirm.return_value.ask.return_value = True` → `mock_confirm.return_value = True`
- `test_does_not_pull_when_declined` (line 860, 862): same pattern with `False`

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k TestPromptForUpdate`
Expected: FAIL, same reason as prior tasks.

- [ ] **Step 3: Convert the call site**

In `scripts/menu.py`, replace (around line 743):

```python
    update = questionary.confirm(
        "Pull the latest changes from GitHub?",
        default=False,
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

with:

```python
    update = charm_prompt.confirm(
        "Pull the latest changes from GitHub?",
        default=False,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k TestPromptForUpdate`
Expected: PASS (4 tests in the class).

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "refactor: migrate update-check confirm prompt to charm_prompt"
```

---

### Task 8: Convert `_handle_check_updates`'s confirm

**Files:**
- Modify: `scripts/menu.py:770-774`
- Test: `tests/test_menu.py:867-903`

**Interfaces:**
- Consumes: `charm_prompt.confirm` (Task 3).

- [ ] **Step 1: Update the failing tests first**

In `tests/test_menu.py`'s `TestHandleCheckUpdates` class:

- `test_returns_true_on_confirmed_successful_pull` (line 883, 885): `@patch("menu.questionary.confirm")` → `@patch("menu.charm_prompt.confirm")`; `mock_confirm.return_value.ask.return_value = True` → `mock_confirm.return_value = True`
- `test_returns_false_on_failed_pull` (line 891, 893): same pattern with `True` (this test confirms the pull but the pull itself fails)
- `test_does_not_pull_when_declined` (line 899, 901): same pattern with `False`

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k TestHandleCheckUpdates`
Expected: FAIL, same reason as prior tasks.

- [ ] **Step 3: Convert the call site**

In `scripts/menu.py`, replace (around line 770):

```python
        update = questionary.confirm(
            "Pull the latest changes?",
            default=True,
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
```

with:

```python
        update = charm_prompt.confirm(
            "Pull the latest changes?",
            default=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu -v -k TestHandleCheckUpdates`
Expected: PASS (5 tests in the class).

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "refactor: migrate check-updates confirm prompt to charm_prompt"
```

---

### Task 9: Restore the existing-profile skip in `_handle_bootstrap`

**Files:**
- Modify: `scripts/menu.py:231-254`
- Modify: `tests/test_menu_bootstrap.py`

**Interfaces:**
- Consumes: `_profile_is_set_up()` (existing, `scripts/menu.py:210-228`, unchanged).

This is a pre-existing bug independent of the `charm_prompt` migration: `_handle_bootstrap()` currently shells out to the Go onboarding wizard unconditionally, every time, even for an already-set-up, non-guest profile (e.g. Morgan's own daily use). The original behavior — skip straight to `bootstrap_menu.run_bootstrap_menu()` unless the profile is new or `RESUME_GUEST_MODE` is set — needs restoring around the Go-wizard subprocess call. Verified before this task: running `python -m unittest tests.test_menu_bootstrap -v` today takes ~12.5s (it's making real `go run` subprocess calls) and 2 of 6 tests fail outright.

- [ ] **Step 1: Update the failing tests first**

Rewrite `tests/test_menu_bootstrap.py`'s `TestHandleBootstrapDelegatesToSubmenu` and `TestHandleBootstrapNewProfileTrigger` classes. Add `import json` to the top of the file alongside the existing `import os`, `import sys`, `import unittest` block.

Replace the `TestHandleBootstrapDelegatesToSubmenu` class body with:

```python
class TestHandleBootstrapDelegatesToSubmenu(unittest.TestCase):
    """_handle_bootstrap() skips straight to the resumable submenu
    (bootstrap_menu.py) for an already-existing, non-guest profile -- it
    does not re-run the onboarding wizard every time."""

    @patch("menu.subprocess.run")
    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=True)
    @patch("menu._profile_is_set_up", return_value=True)
    def test_delegates_to_bootstrap_menu_and_returns_its_result(self, mock_is_set_up, mock_run_menu, mock_subprocess):
        os.environ.pop("RESUME_GUEST_MODE", None)
        result = menu._handle_bootstrap()
        mock_run_menu.assert_called_once()
        mock_subprocess.assert_not_called()
        self.assertTrue(result)

    @patch("menu.subprocess.run")
    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu._profile_is_set_up", return_value=True)
    def test_returns_false_when_submenu_reports_nothing_happened(self, mock_is_set_up, mock_run_menu, mock_subprocess):
        os.environ.pop("RESUME_GUEST_MODE", None)
        result = menu._handle_bootstrap()
        self.assertFalse(result)
        mock_subprocess.assert_not_called()
```

Replace `TestHandleBootstrapNewProfileTrigger`'s two test methods (keep `setUp`/`tearDown` as-is) with:

```python
    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu.subprocess.run")
    def test_guest_mode_triggers_wizard_even_though_morgan_profile_exists(self, mock_subprocess_run, mock_run_menu):
        # Deliberately does NOT mock bootstrap_bullet_bank.create_new_profile
        # -- letting this run for real is a more honest test of the actual
        # bug (does a real profile directory get created, not just a mocked
        # call). run_bootstrap_menu() itself is mocked -- its own behavior
        # once a profile is active is covered by test_bootstrap_menu.py.
        os.environ["RESUME_GUEST_MODE"] = "1"
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"profile_name": self.test_profile_name}), stderr="",
        )

        menu._handle_bootstrap()

        mock_subprocess_run.assert_called_once()
        self.assertEqual(os.environ.get("RESUME_PROFILE"), self.test_profile_name)
        import profile_paths
        self.assertTrue(os.path.isdir(profile_paths.kb_dir(self.test_profile_name)))
        for label, path in profile_paths.sync_roots(self.test_profile_name):
            self.assertTrue(os.path.isdir(path), f"sync root {label!r} was not created: {path}")

    @patch("menu.bootstrap_menu.run_bootstrap_menu", return_value=False)
    @patch("menu.bootstrap_bullet_bank.create_new_profile")
    @patch("menu.subprocess.run")
    @patch("menu._profile_is_set_up", return_value=True)
    def test_no_guest_mode_and_existing_profile_skips_the_wizard(
        self, mock_is_set_up, mock_subprocess_run, mock_create_profile, mock_run_menu,
    ):
        # RESUME_GUEST_MODE unset, profile already set up -> should NOT
        # shell out to the Go wizard (this is the normal, unchanged
        # Morgan-daily-use path, and the exact regression this task fixes).
        os.environ.pop("RESUME_GUEST_MODE", None)

        menu._handle_bootstrap()

        mock_subprocess_run.assert_not_called()
        mock_create_profile.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu_bootstrap -v`
Expected: FAIL — `_handle_bootstrap()` still shells out unconditionally, so `mock_subprocess.assert_not_called()` fails in the first three rewritten tests, and the fourth's `mock_subprocess_run.assert_called_once()` may pass by coincidence but the others won't.

- [ ] **Step 3: Restore the guard in `_handle_bootstrap`**

In `scripts/menu.py`, replace the current `_handle_bootstrap()` body (lines 231-254):

```python
def _handle_bootstrap() -> bool:
    import profile_paths, subprocess, json
    # Run the Go wizard binary that presents the new‑user onboarding UI.
    # We execute it from the project root so the relative import works.
    result = subprocess.run(
        ["go", "run", "./dashboard/cmd/bootstrap"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        cli_art.console.print("[red]Bootstrap wizard failed[/]")
        return False
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        cli_art.console.print("[red]Failed to parse wizard output[/]")
        return False
    name = data.get("profile_name")
    if name:
        bootstrap_bullet_bank.create_new_profile(name)
        profile_paths.set_active_profile(name)
    # Continue with the existing detailed bootstrap menu (phase selection, etc.)
    return bootstrap_menu.run_bootstrap_menu()
```

with:

```python
def _handle_bootstrap() -> bool:
    import profile_paths

    is_existing = _profile_is_set_up()

    if not is_existing or os.environ.get("RESUME_GUEST_MODE"):
        # Run the Go wizard binary that presents the new-user onboarding
        # UI. We execute it from the project root so the relative import
        # works. subprocess/json are already imported at module level.
        result = subprocess.run(
            ["go", "run", "./dashboard/cmd/bootstrap"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            cli_art.console.print("[red]Bootstrap wizard failed[/]")
            return False
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            cli_art.console.print("[red]Failed to parse wizard output[/]")
            return False
        name = data.get("profile_name")
        if name:
            bootstrap_bullet_bank.create_new_profile(name)
            profile_paths.set_active_profile(name)

    # Continue with the existing detailed bootstrap menu (phase selection, etc.)
    return bootstrap_menu.run_bootstrap_menu()
```

(`subprocess` and `json` are already imported at module scope in `scripts/menu.py:18,16` — the redundant local `import ... subprocess, json` is dropped along with this change.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_menu_bootstrap -v`
Expected: PASS (6 tests), and the run completes in well under a second (no more real `go run` subprocess calls hiding in the test suite).

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu_bootstrap.py
git commit -m "fix: restore existing-profile skip in _handle_bootstrap, fix stale tests"
```

---

### Task 10: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `source .venv/bin/activate && python -m unittest discover -s tests -v 2>&1 | tail -60`
Expected: all tests pass, no `questionary.confirm`-related failures, and no test takes multiple seconds (confirming no test is silently shelling out to a real `go run` process).

- [ ] **Step 2: Run the full Go test suite**

Run: `cd dashboard && go test ./...`
Expected: all packages pass, including the new `internal/ui/prompt` package from Task 1.

- [ ] **Step 3: Confirm no remaining `questionary.confirm` call sites in `menu.py`**

Run: `grep -n "questionary.confirm" scripts/menu.py`
Expected: no output — all 5 `confirm()` sites were converted in Tasks 4-8.

- [ ] **Step 4: Manual smoke test of one real flow**

Run: `resume run` is not appropriate here (that's the batch pipeline, not the menu) — instead run the interactive menu directly and exercise `_handle_check_updates` (Maintenance → Check for GitHub Updates), since it's a low-risk, side-effect-light confirm site to click through by hand:

```bash
source .venv/bin/activate
python scripts/menu.py 2>&1 | head -5  # sanity: menu.py isn't directly executable as __main__; instead run:
resume  # launches the real interactive menu via cli.py
```

Navigate: Maintenance → Check for GitHub Updates. If updates are available, confirm the styled `huh` confirm prompt renders (not the old `questionary` list-style prompt) and both Yes/No paths behave as expected.

No commit for this task — it's verification only.
