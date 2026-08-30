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

# Semantic color tokens -- hex, not named ANSI colors. Named colors get
# remapped by whatever terminal theme is active; this project has already
# hit that in practice (see README's "Colors" section: `cyan` washed out
# to near-invisible gray on a dark-teal theme).
#
# Sourced from Charmtone (github.com/charmbracelet/x/exp/charmtone), the
# Charm ecosystem's own branded palette (as used by crush) -- picked for
# CharmtonePantera's semantic roles: primary/accent/success/error/
# warning/info. Every value must clear 4.5:1 WCAG AA contrast against the
# dashboard's two actual backgrounds -- Base (#1e1e2e) *and* Surface
# (#313244, the lighter "elevated panel" tone header/status/error bars
# render on top of) -- this bit us twice now: BRAND_ACCENT was #673ab7 at
# 2.27:1 before B23 lightened it to #b39ddb, and ERROR was only ever
# checked against Base (5.40:1 there) -- Surface, being lighter, is the
# tighter constraint for light-on-dark text and ERROR measured just
# 4.14:1 against it, failing AA on the dashboard's own error banner
# (internal/ui/screens/jobs.go's renderActionError) under this exact
# theme. Two of Charmtone's own picks failed the original Base-only check
# -- Charple (BRAND's "primary", 3.29:1) and Sriracha (ERROR, 4.30:1) --
# so BRAND uses Charmtone's Hazy and ERROR uses a lightened Charmtone
# Coral instead, both from the same purple/red family but lighter. All six
# below clear >=4.5:1 (most with a real ~5:1+ margin, not sitting right on
# the line) against both Base and Surface.
BRAND = "#8B75FF"  # Charmtone Hazy (Charple substitute, contrast fix)
BRAND_ACCENT = "#FF60FF"  # Charmtone Dolly
SUCCESS = "#12C78F"  # Charmtone Guac
ERROR = "#FF7B99"  # Charmtone Coral, lightened (Sriracha substitute, contrast fix: 4.14:1 -> 5.12:1 on Surface)
WARNING = "#F5EF34"  # Charmtone Mustard
INFO = "#00A4FF"  # Charmtone Malibu
MUTED = "#A3A3A3"  # lightened neutral gray -- #888888 only cleared 4.63:1 on Base
# but just 3.55:1 on Surface (fails AA's 4.5:1 floor, same bug class BRAND_ACCENT and
# ERROR hit above); #A3A3A3 clears ~6.5:1 on Base and ~5.0:1 on Surface.

# Dashboard-only decorative accents -- no CLI semantic role of their own
# (Rich/questionary never render these), they exist purely so the
# dashboard's 8-slot Catppuccin-shaped accent struct (Blue/Mauve/Green/
# Yellow/Sky/Peach/Red/Pink) has 8 actually-distinct colors instead of
# reusing two of the six above. See sync_dashboard_theme.py.
PEACH = "#FF985A"  # Charmtone Tang
PINK = "#FF84FF"  # Charmtone Blush
MAUVE = "#cba6f7"  # Catppuccin Mauve
LAVENDER = "#b4befe"  # Catppuccin Lavender
BLUE = "#89b4fa"  # Catppuccin Blue
SKY = "#89dceb"  # Catppuccin Sky

THINKING_GRADIENT_COLORS = [PEACH, PINK, MAUVE, LAVENDER, BLUE, SKY]


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
    "prev": "",  # nf-fa-chevron_left
    "next": "",  # nf-fa-chevron_right
    "back": "",  # nf-fa-chevron_left
    "exit": "",  # nf-fa-power_off
    "location": "",  # nf-fa-map_marker -- place/commute
    "filter": "",  # nf-fa-filter -- exclusion gates (language, travel)
}

# Plain Unicode fallback -- renders correctly with no special font. See
# README's "Fonts"/Setup notes for how to opt in via RESUME_BUILDER_ICONS.
#
# Every glyph here must be TEXT presentation, never emoji. Emoji (any
# codepoint with Emoji_Presentation=Yes) render as full-color double-width
# glyphs regardless of ANSI foreground: they break Rich's column-width
# math, which assumes single-width, and they ignore the theme palette
# entirely. This dict has drifted back to emoji twice now -- most recently
# in a0eabe8e, which left this very comment describing a replacement it
# had undone -- so test_theme.py asserts the property directly rather
# than trusting review.
#
# Prefer East_Asian_Width=Neutral codepoints. The three A (ambiguous)
# glyphs below -- resume's ▶, evaluate's ▤, bullet_bank's ◈ -- can measure
# wide under some CJK font configurations; they are kept because they are
# the legible picks for their slots and this project ships a Latin locale.
_UNICODE_ICONS = {
    "success": "✓",  # U+2713 check mark
    "error": "✗",  # U+2717 ballot x
    "warning": "⚠",  # U+26A0 warning sign
    "hint": "✦",  # U+2726 four-pointed star
    "discovery": "⌖",  # U+2316 position indicator (was the magnifier emoji)
    "evaluate": "▤",  # U+25A4 square with horizontal fill (was the bar-chart emoji)
    "build": "⚒",  # U+2692 hammer and pick -- construct (was the gear, now on "utility")
    "utility": "⚙",  # U+2699 gear -- settings (was the hammer-and-wrench emoji)
    "bullet_bank": "◈",  # U+25C8 diamond in diamond (was the gem emoji)
    "skip": "⊘",  # U+2298 circled division slash
    "save": "⭳",  # U+2B73 arrow to bar (was the floppy-disk emoji)
    "resume": "▶",  # U+25B6 play triangle
    "complete": "✓",  # U+2713 check mark, consistent with success
    "gem": "✦",  # U+2726 four-pointed star
    "location": "⌂",  # U+2302 house -- place/commute (never the pin emoji)
    "filter": "▽",  # U+25BD white down triangle -- a funnel, i.e. exclusion
    "prev": "❮",  # U+276E angle quote left
    "next": "❯",  # U+276F angle quote right
    "back": "❮",  # U+276E angle quote left, same as prev
    "exit": "⏻",  # U+23FB power symbol
}


def _resolve_icon_set_name() -> str:
    if os.environ.get("RESUME_BUILDER_ICONS") == "unicode":
        return "unicode"
    if os.environ.get("RESUME_BUILDER_ICONS") == "nerd":
        return "nerd"
    try:
        import ui_config

        persisted = ui_config.get_icon_set()
    except (ImportError, AttributeError, OSError, ValueError):
        persisted = None
    if persisted in ("unicode", "nerd"):
        return persisted
    if sys.stdin.isatty():
        return "nerd"
    return "unicode"


_ICON_SET_NAME = _resolve_icon_set_name()
ICONS = _UNICODE_ICONS if _ICON_SET_NAME == "unicode" else _NERD_ICONS


def icon_set_name() -> str:
    """Returns the resolved icon-set name ('nerd' or 'unicode'). Meant to be
    passed as RESUME_BUILDER_ICONS into the environment of a JS-side
    subprocess that prints its own icons directly (generate-pdf.mjs,
    check-liveness.mjs) -- there's no shared theming layer across the JS/
    Python boundary, so without this those scripts only ever see an
    explicit shell-level override, never this process's resolved
    preference (an interactive answer persisted via ui_config.py, or the
    isatty-based default) (B45)."""
    return _ICON_SET_NAME


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
    "success": SUCCESS,  # green
    "error": ERROR,  # red
    "warning": WARNING,  # gold
    "hint": BRAND,  # blue
    "discovery": INFO,  # light blue
    "evaluate": BRAND_ACCENT,  # purple
    "build": SUCCESS,  # green
    "utility": BRAND_ACCENT,  # purple
    "bullet_bank": BRAND,  # blue
    "skip": ERROR,  # red
    "save": SUCCESS,  # green
    "resume": BRAND_ACCENT,  # purple
    "complete": SUCCESS,  # green
    "gem": WARNING,  # gold
    "location": INFO,  # light blue
    "filter": INFO,  # light blue -- same family as location, a sibling gate
    "prev": BRAND_ACCENT,  # purple, matches existing pagination style
    "next": BRAND_ACCENT,  # purple, matches existing pagination style
    "back": BRAND_ACCENT,  # purple, matches existing pagination style
    "exit": ERROR,  # red -- distinct from "utility" (Settings & Upkeep) it used to share
}


def colorize_icon(name: str) -> str:
    """Return icon with Rich color markup ([hex]icon[/hex]).

    Only renders correctly when passed to a rich.console.Console.print()
    call -- plain print() does not interpret Rich markup and will show the
    brackets as literal text. Every script in this codebase routes its
    icon-bearing output through cli_art.console (the one shared Console
    instance) rather than the plain print() builtin, so this is always
    the right call."""
    if name not in ICONS:
        return name
    icon = ICONS[name]
    color = _ICON_COLORS.get(name)
    if color:
        return f"[{color}]{icon}[/{color}]"
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


QUESTIONARY_STYLE = Style(
    [
        ("qmark", f"fg:{BRAND_ACCENT} bold"),
        ("question", "bold"),
        ("answer", f"fg:{INFO} bold"),
        ("pointer", f"fg:{BRAND_ACCENT} bold"),
        ("highlighted", f"fg:{BRAND_ACCENT} bold"),
        ("selected", f"fg:{SUCCESS}"),
        ("separator", f"fg:{INFO} bold"),
        ("new_user", f"fg:{SUCCESS} bold"),
        ("exit_flourish", f"fg:{BRAND_ACCENT} bold"),
        ("instruction", ""),
        ("text", ""),
        ("description", f"fg:{MUTED} italic"),
    ]
)
