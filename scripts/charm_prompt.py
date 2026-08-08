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
