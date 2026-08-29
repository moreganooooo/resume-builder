"""charm_prompt.py -- Python wrapper around dashboard/cmd/prompt, the
generic Go/huh prompt binary. Generalizes the subprocess+JSON pattern
dashboard/cmd/bootstrap established for the onboarding wizard so the rest
of menu.py's questionary call sites can move to Charm without a bespoke
Go binary per prompt (see
docs/superpowers/specs/2026-08-08-charm-prompt-migration-design.md).

confirm()/select()/checkbox() are all in production use now (cli_art.py's
wrappers route every interactive prompt through here outside of tests --
see cli_art.confirm/select/checkbox()). text() (added 2026-08-19) was the
last holdout: it had no Go/huh counterpart at all until then, which meant
every cli_art.text() call site rendered nothing when invoked from a
menu.py leaf action -- menu._run_with_chain() sets a DECSTBM scroll region
around the banner that questionary's renderer (prompt_toolkit) can't draw
under, while huh/Bubbletea can. See CLAUDE.md's Architecture notes for the
fuller writeup of that conflict and everywhere it turned up.

The one remaining raw-questionary holdout by design, not oversight, is
picker.py's multi-select checkbox (_paginated_checkbox) -- its cross-page
"still checked" state has no huh equivalent wired up yet, so its two call
sites (Tailor/Cover-Letter "pick specific role(s)") are opted out of the
scroll-region clamp instead (menu._run_with_chain's _skip_scroll_region).

Each function's call shape mirrors the questionary function it replaces:
select()/confirm()/checkbox()/text() all return the answer directly (no
`.ask()` chain), with None meaning the user cancelled (ESC/Ctrl-C) --
exactly what questionary's own `.ask()` returns on cancellation, so
existing `if not choice: return False` guards in menu.py need no changes
at their call sites.

Go is documented as optional (see doctor.check_go()) -- only `resume
dashboard` is supposed to require it. So every function here falls back
to an equivalent questionary prompt when `go` isn't on PATH, rather than
letting subprocess.run raise FileNotFoundError straight out to the user.
"""

import json
import os
import shutil
import subprocess

import cli_art
import questionary

_CANCEL_EXIT_CODE = 130

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DASHBOARD_DIR = os.path.join(_PROJECT_ROOT, "dashboard")
_BIN_PATH = os.path.join(_DASHBOARD_DIR, "bin", "prompt")


def _is_selectable(choice) -> bool:
    """False for a questionary.Separator or any explicitly-disabled Choice
    -- both carry a non-None .disabled (Separator defaults it to "-").
    questionary's own prompts skip these when building the option list;
    the Go huh binary has no such concept and, unfiltered, rendered a
    Separator as a real blank-label option a user could arrow onto and
    submit, returning its value (e.g. " ") straight back to a caller that
    only guards `if not choice` -- non-empty whitespace passed that guard
    and reached `_HANDLERS[" "]`, a KeyError with no indication onscreen
    of what happened beyond the menu going dead. See
    tests/test_charm_prompt.py's TestSeparatorsAreNeverSelectable."""
    return getattr(choice, "disabled", None) is None


def _option_dict(choice) -> dict:
    if isinstance(choice, dict):
        return {"label": choice["label"], "value": choice["value"]}
    if hasattr(choice, "title") and hasattr(choice, "value"):
        # Handle Choice objects that have titles as lists/styled text
        label = choice.title
        if isinstance(label, list):
            # Strip questionary color styling tuples to get raw label text
            label = "".join(item[1] for item in label if isinstance(item, tuple))
        return {"label": str(label).strip(), "value": choice.value}
    return {"label": str(choice), "value": str(choice)}


def _go_available() -> bool:
    return shutil.which("go") is not None


def _prompt_binary_is_stale() -> bool:
    """True if any Go source under dashboard/ is newer than the cached
    binary. A plain "does the binary exist" check (the previous behavior)
    left every source fix silently unapplied until someone noticed the
    running binary didn't match the code and deleted dashboard/bin/prompt
    by hand -- exactly what happened chasing the 2026-08-19 black-text-on-
    dark-terminal regression, where the theme.go/prompt.go fixes had no
    effect until the stale cached binary was manually removed."""
    bin_mtime = os.path.getmtime(_BIN_PATH)
    for root, _dirs, files in os.walk(_DASHBOARD_DIR):
        if os.sep + "bin" + os.sep in root + os.sep:
            continue
        for name in files:
            if name.endswith(".go") or name in ("go.mod", "go.sum"):
                if os.path.getmtime(os.path.join(root, name)) > bin_mtime:
                    return True
    return False


def _compile_prompt_if_needed() -> str | None:
    """Compiles the Go prompt binary if missing or stale (see
    _prompt_binary_is_stale), returning the path to the compiled binary.
    If compilation fails or Go is missing, returns None."""
    if not _go_available():
        return None

    if os.path.exists(_BIN_PATH) and not _prompt_binary_is_stale():
        return _BIN_PATH

    os.makedirs(os.path.dirname(_BIN_PATH), exist_ok=True)
    try:
        subprocess.run(
            ["go", "build", "-o", _BIN_PATH, "./cmd/prompt"],
            cwd=_DASHBOARD_DIR,
            check=True,
            capture_output=True,
        )
        return _BIN_PATH
    except Exception:
        return None


def _flush_stdin() -> None:
    """Discards any keystrokes already buffered on stdin before a raw-mode
    subprocess starts reading it.

    Matters whenever two prompts fire back-to-back in one screen (e.g.
    stale_sweep's backfill offer immediately followed by its archive
    confirm) -- Bubbletea reads raw input the instant it takes over the
    tty, so an Enter the user pressed a beat too early (while the first
    subprocess was still tearing down, or during the plain print() lines
    between the two prompts) gets consumed as this form's first
    keystroke instead of theirs, submitting on the default answer before
    they see the question. Single-prompt screens never hit this, which
    is why it went unnoticed until backfill started actually succeeding
    (see stale_sweep.backfill_discovery_dates()) and its confirm+confirm
    sequence started running for real instead of erroring out first."""
    try:
        import sys
        import termios

        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        # Not a POSIX tty (Windows, piped stdin, a test harness) -- nothing
        # to flush, and this must never be the reason a prompt fails.
        pass


def _run_prompt(spec: dict):
    _flush_stdin()
    # Run from _DASHBOARD_DIR where go.mod is located
    bin_path = _compile_prompt_if_needed()
    if bin_path and os.path.exists(bin_path):
        cmd = [bin_path, json.dumps(spec)]
    else:
        cmd = ["go", "run", "./cmd/prompt", json.dumps(spec)]

    # stderr is left connected to our own terminal (not captured) -- huh/
    # Bubbletea render the live form there by default, and need a real tty
    # to do raw-mode drawing, which a pipe can't provide (confirmed via a
    # pty-attached test). The binary's JSON answer goes to stdout, so
    # that's the only stream we capture.
    result = subprocess.run(
        cmd,
        cwd=_DASHBOARD_DIR,
        stdout=subprocess.PIPE,
        text=True,
    )
    if result.returncode == _CANCEL_EXIT_CODE:
        return None
    if result.returncode != 0:
        # stderr isn't captured (see above) -- log.Fatalf's message already
        # printed live to the terminal, so this just carries the exit code.
        raise RuntimeError(f"charm_prompt failed (exit {result.returncode})")
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"charm_prompt returned invalid JSON: {result.stdout!r}"
        ) from e


def _warn_and_degrade(e: Exception) -> None:
    # A non-zero/non-130 exit from the Go prompt binary is a real bug in
    # dashboard/cmd/prompt, not just "Go missing" -- previously this
    # propagated as an unhandled RuntimeError straight out of every menu.py
    # call site. Degrading to questionary (rather than crashing) keeps the
    # menu usable; the warning still surfaces that something's wrong.
    cli_art.cli_warning(f"Charm prompt failed, falling back to plain prompt: {e}")


def confirm(message: str, default: bool = True) -> bool | None:
    if not _go_available():
        return questionary.confirm(
            message, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    try:
        data = _run_prompt({"type": "confirm", "message": message, "default": default})
    except RuntimeError as e:
        _warn_and_degrade(e)
        return questionary.confirm(
            message, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    if data is None:
        return None
    return data["confirmed"]


def select(message: str, choices: list, default: str | None = None):
    if not _go_available():
        return questionary.select(
            message, choices=choices, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    spec = {
        "type": "select",
        "message": message,
        "options": [_option_dict(c) for c in choices if _is_selectable(c)],
    }
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
        return questionary.checkbox(
            message, choices=choices, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    spec = {
        "type": "checkbox",
        "message": message,
        "options": [_option_dict(c) for c in choices if _is_selectable(c)],
    }
    try:
        data = _run_prompt(spec)
    except RuntimeError as e:
        _warn_and_degrade(e)
        return questionary.checkbox(
            message, choices=choices, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    if data is None:
        return None
    return data.get("values", [])


def text(message: str, default: str = "") -> str | None:
    if not _go_available():
        return questionary.text(
            message, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    spec = {"type": "text", "message": message, "default_value": default}
    try:
        data = _run_prompt(spec)
    except RuntimeError as e:
        _warn_and_degrade(e)
        return questionary.text(
            message, default=default, style=cli_art.QUESTIONARY_STYLE
        ).ask()
    if data is None:
        return None
    return data["value"]
