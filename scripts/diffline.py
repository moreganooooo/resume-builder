"""diffline.py -- the CLI half of docs/DesignSystem/components/data/DiffLine.

A rewrite is the product's core value, and until now the user never saw it:
`rewrite_bullets.py` printed only the NEW bullet, so the one thing worth
judging -- what changed, and why -- was never on screen.

The spec's rules, and why each one is here rather than being a preference:

* The SIGN COLUMN is always present ("+", "-", " ", "|"), on every line
  including unchanged ones. That is what keeps the lines aligned, and it is
  what makes the diff survive being copied out of the terminal into a plain
  text email, where the colors do not travel.
* Color is therefore never the only signal. A red/green-blind reader and a
  screen reader both get the signs.
* Removed text is NOT struck through. Strikethrough renders unreliably
  across terminals, and where it does render it makes the original hard to
  read -- which is precisely the text the user needs in order to judge the
  rewrite.
* A rewrite is ONE decision, not two, so `render_rewrite()` emits the
  paired "-"/"+" adjacent with the model's own reasoning as a "note" line
  under them, rather than leaving the two halves to drift apart on screen.
* Word-level emphasis is BOLD, never a background fill: filled spans read
  as redaction rather than as attention.

Colors come from theme.py's tokens, so this agrees with every other CLI
surface. Output is Rich markup and must be printed through
`cli_art.console`, like every other icon-bearing line in this codebase.
"""

import difflib
from typing import Iterable, Sequence

import theme
from rich.markup import escape

# The sign column, per the spec. "note" is the Mauve rule under a pair; the
# spec draws it with a heavy vertical bar, the same glyph the dashboard's
# ClusterTree and select field use for "this is the line you are on".
SIGNS = {"add": "+", "remove": "-", "same": " ", "note": "┃"}

COLORS = {
    "add": theme.SUCCESS,
    "remove": theme.ERROR,
    "same": theme.MUTED,
    "note": theme.MAUVE,
}


def _emphasize(text: str, emphasis: Iterable[str]) -> str:
    """Bold each emphasis substring inside already-escaped markup."""
    out = escape(text)
    for phrase in sorted({p for p in emphasis if p.strip()}, key=len, reverse=True):
        marked = escape(phrase)
        if marked and marked in out:
            out = out.replace(marked, f"[bold]{marked}[/bold]")
    return out


def render_line(kind: str, text: str, emphasis: Sequence[str] = ()) -> str:
    """One diff line as Rich markup: sign, a space, then the text."""
    if kind not in SIGNS:
        kind = "same"
    color = COLORS[kind]
    body = _emphasize(text, emphasis)
    return f"[{color}]{SIGNS[kind]}[/{color}] [{color}]{body}[/{color}]"


def changed_words(before: str, after: str) -> list[str]:
    """Words present in `after` but not in `before`, for word-level bolding.

    Only the added side is emphasized. Bolding both sides would mark most
    of a substantially rewritten bullet, which is the same as marking none
    of it.
    """
    old = before.split()
    new = after.split()
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    words: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            words.extend(new[j1:j2])
    return [w for w in words if len(w) > 2]


def render_rewrite(before: str, after: str, reasoning: str = "") -> list[str]:
    """The paired before/after view, plus the model's reasoning as a note.

    Returns Rich-markup lines. Nothing is truncated: the whole point of
    showing the pair is that the user can read both and judge the trade,
    and a truncated bullet cannot be judged.
    """
    lines = [
        render_line("remove", before),
        render_line("add", after, emphasis=changed_words(before, after)),
    ]
    if reasoning.strip():
        lines.append(render_line("note", reasoning.strip()))
    return lines
