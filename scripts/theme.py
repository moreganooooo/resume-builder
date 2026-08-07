"""theme.py -- single source of truth for resume-builder's CLI visual
system: color tokens, icon glyphs (Nerd Font by default, plain Unicode
fallback), and the shared questionary.Style. cli_art.py and picker.py both
build their own constants from this module instead of defining their own
copies -- see docs/superpowers/specs/2026-07-14-cli-ux-redesign-design.md.
"""

import os
import sys

from questionary import Style
from rich.console import Console
from rich.style import Style as RichStyle

# Semantic color tokens -- hex, not named ANSI colors. Named colors get
# remapped by whatever terminal theme is active; this project has already
# hit that in practice (see README's "Colors" section: `cyan` washed out
# to near-invisible gray on a dark-teal theme).
# BRAND_ACCENT was #673ab7 (2.27:1 against a dark terminal background --
# the lowest-contrast color in the whole palette, and the one driving the
# questionary selection pointer/highlighted row plus every table header).
# Lightened to clear 4.5:1 AA on dark (8.77:1 against black) -- see B23.
BRAND = "#4dabf7"
BRAND_ACCENT = "#b39ddb"
SUCCESS = "#4caf50"
ERROR = "#c96a6a"
WARNING = "#f5c542"
INFO = "#2196f3"
MUTED = "#888888"

# Values match orchestrator.FitEvaluationSchema's `recommendation` Literal
# exactly: "Strong pursue", "Selective pursue", "Low-priority pursue", "Skip".
RECOMMENDATION_COLORS = {
    "Strong pursue": SUCCESS,
    "Selective pursue": BRAND,
    "Low-priority pursue": WARNING,
    "Skip": ERROR,
}

# questionary Choice-title style strings for the same four tiers. "Skip"
# stays unbolded (deliberately de-emphasized); the other three are bold.
RECOMMENDATION_STYLES = {
    "Strong pursue": f"fg:{SUCCESS} bold",
    "Selective pursue": f"fg:{BRAND} bold",
    "Low-priority pursue": f"fg:{WARNING} bold",
    "Skip": f"fg:{ERROR}",
}

# Font Awesome glyphs (Private Use Area code points Nerd Fonts patch in
# verbatim under the nf-fa-* names) -- this is the default experience.
_NERD_ICONS = {
    "success": "",  # nf-fa-check
    "error": "",  # nf-fa-times
    "warning": "",  # nf-fa-exclamation_triangle
    "hint": "",  # nf-fa-lightbulb_o
    "discovery": "",  # nf-fa-search
    "evaluate": "",  # nf-fa-bar_chart
    "build": "",  # nf-fa-wrench
    "utility": "",  # nf-fa-cog
    "bullet_bank": "",  # nf-fa-database
    "skip": "",  # nf-fa-ban
    "save": "",  # nf-fa-save
    "resume": "",  # nf-fa-play
    "complete": "",  # nf-fa-check_circle
    "gem": "",  # nf-fa-diamond
}

# Plain Unicode fallback -- renders correctly with no special font. See
# README's "Fonts"/Setup notes for how to opt in via RESUME_BUILDER_ICONS.
#
# B22/P1F7: four of the original picks here (evaluate/build/skip/save) are
# real emoji with Emoji_Presentation=Yes -- terminals render those as
# full-color, double-width glyphs regardless of ANSI foreground, which
# both breaks Rich's column-width math (it assumes single-width) and
# ignores the theme entirely. Replaced with plain ASCII, which is
# guaranteed single-width and colorless-by-default in every terminal/font,
# same safety class as warning/utility's ⚠/⚙ (Emoji_Presentation=No,
# render as narrow text glyphs, not touched here since they're already
# fine). hint/discovery/resume/gem's diamond/circle/triangle glyphs are
# ambiguous-width (not emoji, but can measure wide under some CJK-font
# configurations) -- also moved to ASCII rather than relying on locale.
_UNICODE_ICONS = {
    "success": "✓",  # ✓
    "error": "✗",  # ✗
    "warning": "⚠",  # ⚠
    "hint": "!",  # note/FYI (was ◆, ambiguous-width)
    "discovery": "?",  # search/explore (was ◎, ambiguous-width)
    "evaluate": "%",  # score/metrics (was 📊, double-width emoji)
    "build": "+",  # action/construct (was ⚡, double-width emoji)
    "utility": "⚙",  # gear (settings/tools)
    "bullet_bank": "□",  # box (storage/database)
    "skip": "-",  # excluded/rejection (was 🚫, double-width emoji)
    "save": "s",  # save/archive (was 💾, double-width emoji)
    "resume": ">",  # play/continue (was ▶, ambiguous-width)
    "complete": "✓",  # checkmark (done, consistent with success)
    "gem": "*",  # quality/priority (was ◆, ambiguous-width)
}

# Icon-set resolution, in priority order (B33):
#   1. RESUME_BUILDER_ICONS=unicode (exact, case-sensitive match) -- an
#      explicit override always wins and is never re-asked.
#   2. This profile's persisted first-launch answer (ui_config.py), if any.
#   3. A real terminal with no answer yet: default to Nerd Font (today's
#      icons) until the interactive prompt (menu._confirm_icon_set(), run
#      once at startup) asks and persists a real answer.
#   4. No terminal (piped output, CI, tests) and no answer yet: default to
#      Unicode -- deterministic and never garbled, unlike guessing at font
#      support that can't actually be probed from a TTY.
def _resolve_icon_set_name() -> str:
    if os.environ.get("RESUME_BUILDER_ICONS") == "unicode":
        return "unicode"
    try:
        import ui_config
        persisted = ui_config.get_icon_set()
    except Exception:
        persisted = None
    if persisted:
        return persisted
    if sys.stdin.isatty():
        return "nerd"
    return "unicode"


_ICON_SET_NAME = _resolve_icon_set_name()
ICONS = _UNICODE_ICONS if _ICON_SET_NAME == "unicode" else _NERD_ICONS


def set_icon_set(name: str) -> None:
    """Switches the active icon set at runtime -- called by menu.py's
    first-launch prompt right after it persists the user's answer, so the
    rest of the same session reflects the choice immediately rather than
    needing a restart. Reassigns the module-level ICONS binding in place
    (mirrors profile_paths.set_active_profile()'s "mutate, don't
    reimport" convention) so every existing `theme.colorize_icon()` etc.
    call -- which reads ICONS as a module global at call time, not at
    def time -- picks up the change immediately."""
    global ICONS, _ICON_SET_NAME
    if name not in ("nerd", "unicode"):
        raise ValueError(f"name must be 'nerd' or 'unicode', got {name!r}")
    _ICON_SET_NAME = name
    ICONS = _UNICODE_ICONS if name == "unicode" else _NERD_ICONS

# Map icon names to Rich markup colors for colorized output
_ICON_COLORS = {
    "success": SUCCESS,      # green
    "error": ERROR,          # red
    "warning": WARNING,      # gold
    "hint": BRAND,           # blue
    "discovery": INFO,       # light blue
    "evaluate": BRAND_ACCENT,# purple
    "build": SUCCESS,        # green
    "utility": BRAND_ACCENT, # purple
    "bullet_bank": BRAND,    # blue
    "skip": ERROR,           # red
    "save": SUCCESS,         # green
    "resume": BRAND_ACCENT,  # purple
    "complete": SUCCESS,     # green
    "gem": WARNING,          # gold
}

def colorize_icon(name: str) -> str:
    """Return icon with Rich color markup ([hex]icon[/hex]).

    Only renders correctly when passed to a rich.console.Console.print()
    call -- plain print() does not interpret Rich markup and will show the
    brackets as literal text. cli_art.py is the only module with an actual
    Console instance; every other script's print() statements should use
    colorize_icon_ansi() instead (see that function's docstring)."""
    if name not in ICONS:
        return name
    icon = ICONS[name]
    color = _ICON_COLORS.get(name)
    if color:
        return f"[{color}]{icon}[/{color}]"
    return icon

def colorize_icon_ansi(name: str) -> str:
    """Return icon wrapped in raw ANSI 24-bit color escape codes.

    Use this (not colorize_icon()) in any script that calls the plain
    print() builtin directly to a terminal -- a real terminal interprets
    raw ANSI escapes on its own, unlike Rich markup (which needs a Rich
    Console to parse it, and -- confirmed empirically, B46/P5#4 -- would
    silently swallow any single-word bracketed text elsewhere in the same
    message, e.g. a `[STALE]` status tag, since it looks like a valid but
    unstyled markup tag) or prompt_toolkit's renderer (which needs its own
    (style, text) tuple format -- see questionary_icon_tuple()).

    Renders via rich.style.Style rather than hand-rolled hex parsing, so
    there's exactly one place (Rich's own Style class) that turns a hex
    color into terminal escape codes, not two -- the RGB math and the
    reset sequence both come from Rich itself."""
    if name not in ICONS:
        return name
    icon = ICONS[name]
    color = _ICON_COLORS.get(name)
    if color:
        return RichStyle(color=color).render(icon, color_system="truecolor")
    return icon

def questionary_icon_tuple(name: str) -> tuple:
    """Return (style, icon) tuple for use in questionary Choice title lists.
    questionary/prompt_toolkit renders titles given as a list of
    (style, text) tuples natively -- unlike Rich markup or raw ANSI codes
    embedded in a plain string, which display as literal escape sequences
    inside prompt_toolkit's own renderer. See _CHOICES's "New User" entry
    for the pre-existing precedent of this exact pattern."""
    if name not in ICONS:
        return ("", name)
    icon = ICONS[name]
    color = _ICON_COLORS.get(name)
    style = f"fg:{color}" if color else ""
    return (style, icon)

QUESTIONARY_STYLE = Style([
    ("qmark", f"fg:{BRAND_ACCENT} bold"),
    ("question", "bold"),
    ("answer", f"fg:{INFO} bold"),
    ("pointer", f"fg:{BRAND_ACCENT} bold"),
    ("highlighted", f"fg:{BRAND_ACCENT} bold"),
    ("selected", f"fg:{SUCCESS}"),
    ("separator", f"fg:{INFO} bold"),
    ("new_user", f"fg:{SUCCESS} bold"),
    ("instruction", ""),
    ("text", ""),
    ("description", f"fg:{MUTED} italic"),
])
