"""theme.py -- single source of truth for resume-builder's CLI visual
system: color tokens, icon glyphs (Nerd Font by default, plain Unicode
fallback), and the shared questionary.Style. cli_art.py and picker.py both
build their own constants from this module instead of defining their own
copies -- see docs/superpowers/specs/2026-07-14-cli-ux-redesign-design.md.
"""

import os

from questionary import Style
from rich.console import Console

# Semantic color tokens -- hex, not named ANSI colors. Named colors get
# remapped by whatever terminal theme is active; this project has already
# hit that in practice (see README's "Colors" section: `cyan` washed out
# to near-invisible gray on a dark-teal theme).
BRAND = "#4dabf7"
BRAND_ACCENT = "#673ab7"
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
_UNICODE_ICONS = {
    "success": "✓",  # ✓
    "error": "✗",  # ✗
    "warning": "⚠",  # ⚠
    "hint": "💡",  # 💡
    "discovery": "🔍",  # 🔍
    "evaluate": "📊",  # 📊
    "build": "🛠",  # 🛠
    "utility": "⚙",  # ⚙
    "bullet_bank": "🗃",  # 🗃
    "skip": "🚫",  # 🚫
    "save": "💾",  # 💾
    "resume": "▶",  # ▶
    "complete": "✅",  # ✅
    "gem": "💎",  # 💎
}

# Nerd Font is the default -- set RESUME_BUILDER_ICONS=unicode (exact,
# case-sensitive match) to fall back to the plain-Unicode set. Any other
# or unset value fails toward the enhanced default, not toward breakage --
# a typo'd env var shouldn't silently degrade someone who does have a
# Nerd Font active.
ICONS = _UNICODE_ICONS if os.environ.get("RESUME_BUILDER_ICONS") == "unicode" else _NERD_ICONS

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

def _hex_to_ansi_fg(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"\033[38;2;{r};{g};{b}m"

_ANSI_RESET = "\033[0m"

def colorize_icon_ansi(name: str) -> str:
    """Return icon wrapped in raw ANSI 24-bit color escape codes.

    Use this (not colorize_icon()) in any script that calls the plain
    print() builtin directly to a terminal -- a real terminal interprets
    raw ANSI escapes on its own, unlike Rich markup (which needs a Rich
    Console to parse it) or prompt_toolkit's renderer (which needs its
    own (style, text) tuple format -- see questionary_icon_tuple())."""
    if name not in ICONS:
        return name
    icon = ICONS[name]
    color = _ICON_COLORS.get(name)
    if color:
        return f"{_hex_to_ansi_fg(color)}{icon}{_ANSI_RESET}"
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
