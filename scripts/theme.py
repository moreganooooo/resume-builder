"""theme.py -- single source of truth for resume-builder's CLI visual
system: color tokens, icon glyphs (Nerd Font by default, plain Unicode
fallback), and the shared questionary.Style. cli_art.py and picker.py both
build their own constants from this module instead of defining their own
copies -- see docs/superpowers/specs/2026-07-14-cli-ux-redesign-design.md.
"""

import os

from questionary import Style

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
    "success": "",     # nf-fa-check
    "error": "",       # nf-fa-times
    "warning": "",     # nf-fa-exclamation_triangle
    "hint": "",        # nf-fa-lightbulb_o
    "discovery": "",   # nf-fa-search
    "evaluate": "",    # nf-fa-bar_chart
    "build": "",       # nf-fa-wrench
    "utility": "",     # nf-fa-cog
}

# Plain Unicode fallback -- renders correctly with no special font. See
# README's "Fonts"/Setup notes for how to opt in via RESUME_BUILDER_ICONS.
_UNICODE_ICONS = {
    "success": "✓",       # ✓
    "error": "✗",         # ✗
    "warning": "⚠",       # ⚠
    "hint": "\U0001F4A1",      # 💡
    "discovery": "\U0001F50D",  # 🔍
    "evaluate": "\U0001F4CA",   # 📊
    "build": "\U0001F6E0",      # 🛠
    "utility": "⚙",        # ⚙
}

# Nerd Font is the default -- set RESUME_BUILDER_ICONS=unicode (exact,
# case-sensitive match) to fall back to the plain-Unicode set. Any other
# or unset value fails toward the enhanced default, not toward breakage --
# a typo'd env var shouldn't silently degrade someone who does have a
# Nerd Font active.
ICONS = _UNICODE_ICONS if os.environ.get("RESUME_BUILDER_ICONS") == "unicode" else _NERD_ICONS

QUESTIONARY_STYLE = Style([
    ("qmark", f"fg:{BRAND_ACCENT} bold"),
    ("question", "bold"),
    ("answer", f"fg:{INFO} bold"),
    ("pointer", f"fg:{BRAND_ACCENT} bold"),
    ("highlighted", f"fg:{BRAND_ACCENT} bold"),
    ("selected", f"fg:{SUCCESS}"),
    ("separator", "fg:#cc5454"),
    ("new_user", f"fg:{SUCCESS} bold"),
    ("instruction", ""),
    ("text", ""),
])
