"""charm_prompt.py -- Python wrapper around dashboard/cmd/prompt, the
generic Go/huh prompt binary. Generalizes the subprocess+JSON pattern
dashboard/cmd/bootstrap established for the onboarding wizard so the rest
of menu.py's questionary call sites can move to Charm without a bespoke
Go binary per prompt (see
docs/superpowers/specs/2026-08-08-charm-prompt-migration-design.md).

select()/checkbox() have no production call sites yet -- deliberately, per
that spec's own Non-Goals: only confirm()'s 5 call sites were converted to
"prove the pattern end-to-end" before the remaining 13 select()/checkbox()
sites in menu.py (including the icon-heavy main menu). Converting those is
explicitly deferred as "straightforward mechanical follow-up," not
abandoned -- this isn't stale code, it's finished infrastructure ahead of
its call sites. Both functions are exercised directly by
tests/test_charm_prompt.py.

Each function's call shape mirrors the questionary function it replaces:
select()/confirm()/checkbox() all return the answer directly (no `.ask()`
chain), with None meaning the user cancelled (ESC/Ctrl-C) -- exactly what
questionary's own `.ask()` returns on cancellation, so existing
`if not choice: return False` guards in menu.py need no changes at their
call sites.

Go is documented as optional (see doctor.check_go()) -- only `resume
dashboard` is supposed to require it. So every function here falls back
to an equivalent questionary prompt when `go` isn't on PATH, rather than
letting subprocess.run raise FileNotFoundError straight out to the user.
"""

import json
import os
import shutil
import subprocess

import questionary

import cli_art

_CANCEL_EXIT_CODE = 130

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _option_dict(choice) -> dict:
    if isinstance(choice, dict):
        return {"label": choice["label"], "value": choice["value"]}
    return {"label": choice.title, "value": choice.value}


def _go_available() -> bool:
    return shutil.which("go") is not None


def _run_prompt(spec: dict):
    # No spinner/status line wraps this call, deliberately: stdout/stderr
    # are captured here so this function can read back the form's final
    # JSON answer, yet the huh form still renders live and reads real
    # keystrokes -- meaning it takes over the terminal by some path other
    # than the captured stdout/stderr this function sees. A Rich Live/
    # status spinner writes to that same terminal on its own timer;
    # racing it against however the form takes over risks corrupting the
    # handoff (two things drawing over each other), for a delay that's a
    # couple of seconds on `go run`'s cold build cache and sub-second
    # otherwise. Not worth that risk to a working interactive path for a
    # cold-start-only cosmetic gap; revisit only if this is actually
    # reported as sluggish.
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


def _warn_and_degrade(e: Exception) -> None:
    # A non-zero/non-130 exit from the Go prompt binary is a real bug in
    # dashboard/cmd/prompt, not just "Go missing" -- previously this
    # propagated as an unhandled RuntimeError straight out of every menu.py
    # call site. Degrading to questionary (rather than crashing) keeps the
    # menu usable; the warning still surfaces that something's wrong.
    cli_art.cli_warning(f"Charm prompt failed, falling back to plain prompt: {e}")


def confirm(message: str, default: bool = True) -> bool | None:
    if not _go_available():
        return questionary.confirm(message, default=default, style=cli_art.QUESTIONARY_STYLE).ask()
    try:
        data = _run_prompt({"type": "confirm", "message": message, "default": default})
    except RuntimeError as e:
        _warn_and_degrade(e)
        return questionary.confirm(message, default=default, style=cli_art.QUESTIONARY_STYLE).ask()
    if data is None:
        return None
    return data["confirmed"]


def select(message: str, choices: list, default: str | None = None) -> str | None:
    if not _go_available():
        return questionary.select(
            message, choices=choices, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    spec = {"type": "select", "message": message, "options": [_option_dict(c) for c in choices]}
    if default is not None:
        spec["default_value"] = default
    try:
        data = _run_prompt(spec)
    except RuntimeError as e:
        _warn_and_degrade(e)
        return questionary.select(
            message, choices=choices, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    if data is None:
        return None
    return data["value"]


def checkbox(message: str, choices: list) -> list | None:
    if not _go_available():
        return questionary.checkbox(message, choices=choices, style=cli_art.QUESTIONARY_STYLE).ask()
    spec = {"type": "checkbox", "message": message, "options": [_option_dict(c) for c in choices]}
    try:
        data = _run_prompt(spec)
    except RuntimeError as e:
        _warn_and_degrade(e)
        return questionary.checkbox(message, choices=choices, style=cli_art.QUESTIONARY_STYLE).ask()
    if data is None:
        return None
    return data.get("values", [])
