"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

import json
import os
import random
import re
import time
import sys
import shutil

import questionary
from rich import box
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape as _escape_markup
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme as RichTheme

import followup
import jd_manager
import theme
import charm_prompt

# Overrides Rich's automatic quoted-text highlighting (its default
# "repr.str" is a dim ANSI green, distinct from -- and clashing with --
# theme.SUCCESS's brighter flat green) so any auto-highlighted quoted
# substring anywhere in this app's output stays on-palette.
console = Console(theme=RichTheme({"repr.str": theme.SUCCESS}))

SUCCESS = f"[bold {theme.SUCCESS}]{theme.colorize_icon('success')}[/bold {theme.SUCCESS}]"
ERROR = f"[bold {theme.ERROR}]{theme.colorize_icon('error')}[/bold {theme.ERROR}]"
WARNING = f"[bold {theme.WARNING}]{theme.colorize_icon('warning')}[/bold {theme.WARNING}]"
HINT = f"[bold {theme.INFO}]{theme.colorize_icon('hint')}[/bold {theme.INFO}]"

# Re-exported so menu.py/picker.py's existing `cli_art.QUESTIONARY_STYLE`
# references keep working unchanged.
QUESTIONARY_STYLE = theme.QUESTIONARY_STYLE

# Unified table header styling (used across all render_*_table functions)
TABLE_HEADER_STYLE = f"bold {theme.BRAND_ACCENT}"


def scrub_pii(text: str) -> str:
    """Redacts candidate emails and phone numbers from tracebacks and log messages."""
    if not text:
        return ""
    clean = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', str(text))
    clean = re.sub(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[REDACTED_PHONE]', clean)
    return clean


def display_error(message: str) -> None:
    """A failure reads with real visual weight -- a bordered panel, not a
    bare icon-prefixed line. message is escaped before interpolation --
    Rich's markup parser silently drops bracketed content that happens
    to look like a style tag (e.g. a company name in brackets), rather
    than raising or rendering it literally, so caller-supplied text must
    never reach console.print unescaped."""
    body = f"[bold {theme.ERROR}]{theme.colorize_icon('error')}[/bold {theme.ERROR}] {_escape_markup(scrub_pii(message))}"
    console.print(Panel(body, border_style=theme.ERROR, box=box.ROUNDED, padding=(0, 2)))


def display_success(message: str) -> None:
    """Stays lightweight (no border) -- this is the common case and a
    bordered panel for every success would get old fast. message is
    escaped -- see display_error()'s docstring."""
    console.print(f"[bold {theme.SUCCESS}]{theme.colorize_icon('success')}[/bold {theme.SUCCESS}] {_escape_markup(message)}")


def print_literal(message: str = "") -> None:
    """Print a literal string without Rich markup parsing (shortcut used by
    callers that previously relied on `console.print(..., markup=False)`.
    Keeps `soft_wrap=True` to match previous call sites."""
    console.print(message, markup=False, soft_wrap=True)

# Raw block-letter lines, no markup -- color now comes from the diagonal
# gradient applied per-character in display_main_banner(), not a blanket
# style wrapper.
MAIN_BANNER_LINES = [
    "██████╗ ███████╗███████╗██╗   ██╗███╗   ███╗███████╗",
    "██╔══██╗██╔════╝██╔════╝██║   ██║████╗ ████║██╔════╝",
    "██████╔╝█████╗  ███████╗██║   ██║██╔████╔██║█████╗  ",
    "██╔══██╗██╔══╝  ╚════██║██║   ██║██║╚██╔╝██║██╔══╝  ",
    "██║  ██║███████╗███████║╚██████╔╝██║ ╚═╝ ██║███████╗",
    "╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝",
    "",
    "██████╗ ██╗   ██╗██╗██╗     ██████╗ ███████╗██████╗ ",
    "██╔══██╗██║   ██║██║██║     ██╔══██╗██╔════╝██╔══██╗",
    "██████╔╝██║   ██║██║██║     ██║  ██║█████╗  ██████╔╝",
    "██╔══██╗██║   ██║██║██║     ██║  ██║██╔══╝  ██╔══██╗",
    "██████╔╝╚██████╔╝██║███████╗██████╔╝███████╗██║  ██║",
    "╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝",]

SUBTITLE = "Custom Resumes & Cover Letters, Powered by Gemini\n"

# Glyphs for the banner's decorative sparkle field -- weighted toward the
# plain small dot so stars stay an accent, not the majority. Plain symbol
# glyphs only (not emoji-presentation ones like an outlined star with
# VS16) -- those commonly render double-width and would throw off a row's
# alignment relative to the others.
_SPARKLE_GLYPHS = ["·", "·", "·", "⋆", "⋆", "✦", "✧"]
_SPARKLE_DENSITY = 0.08


def _sparkle_field(rows: int, width: int) -> list:
    """A fresh random scatter (not a fixed pattern) every call -- fills
    the banner's right side out to the panel's actual inner width (see
    display_main_banner's caller), so it always reaches the border
    regardless of terminal size, and looks like a different night sky
    each launch rather than a static decal."""
    if width <= 0:
        return [""] * rows
    lines = []
    for _ in range(rows):
        row = [random.choice(_SPARKLE_GLYPHS) if random.random() < _SPARKLE_DENSITY else " " for _ in range(width)]
        lines.append("".join(row))
    return lines


def _lerp_hex(start_hex: str, end_hex: str, t: float) -> str:
    """Linearly interpolates between two '#rrggbb' colors at t in [0, 1]."""
    start_rgb = tuple(int(start_hex[i:i + 2], 16) for i in (1, 3, 5))
    end_rgb = tuple(int(end_hex[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(start_rgb[c] + (end_rgb[c] - start_rgb[c]) * t) for c in range(3))
    return f"#{mixed[0]:02x}{mixed[1]:02x}{mixed[2]:02x}"


def _gradient_grid(lines: list, start_hex: str, end_hex: str) -> list:
    """Returns a per-character color grid (list of list of hex strings,
    parallel to `lines`) -- a diagonal sweep from start_hex (top-left) to
    end_hex (bottom-right), keyed by (row + col) / (max_row + max_col)."""
    max_row = max(len(lines) - 1, 1)
    max_col = max((len(line) for line in lines), default=1)
    max_col = max(max_col - 1, 1)
    denom = max_row + max_col

    grid = []
    for row, line in enumerate(lines):
        grid.append([_lerp_hex(start_hex, end_hex, (row + col) / denom) for col in range(len(line))])
    return grid


def _render_grid(lines: list, grid: list, threshold: int = None) -> Text:
    """Builds one multi-line Rich Text from lines/grid. threshold is the
    max (row + col) diagonal index to reveal; None reveals everything."""
    text = Text()
    for row, line in enumerate(lines):
        for col, ch in enumerate(line):
            if threshold is not None and (row + col) > threshold:
                text.append(" ")
            else:
                text.append(ch, style=grid[row][col])
        text.append("\n")
    return text


def _reveal_banner(lines: list, grid: list, render_frame) -> None:
    """Drives a rich.live.Live diagonal-wipe reveal. render_frame(threshold)
    returns the Rich renderable for a given frame (threshold=None means
    fully revealed). Falls back to a single fully-revealed print when
    stdout isn't a real terminal (piped output, non-interactive contexts,
    tests) -- Live's redraws don't compose safely with non-TTY output --
    or when RESUME_BUILDER_MOTION=reduced, the same opt-out (and env var
    name) dashboard/main.go's reducedMotion() already offers for the Go
    side's screen-transition animation."""
    if not console.is_terminal or os.environ.get("RESUME_BUILDER_MOTION") == "reduced":
        console.print(render_frame(None))
        return

    max_row = max(len(lines) - 1, 1)
    max_col = max((len(line) for line in lines), default=1)
    max_col = max(max_col - 1, 1)
    max_threshold = max_row + max_col

    frame_count = 30
    total_seconds = 1.6
    with Live(console=console, refresh_per_second=30, transient=False) as live:
        for frame in range(frame_count + 1):
            threshold = round(max_threshold * frame / frame_count)
            live.update(render_frame(threshold))
            time.sleep(total_seconds / frame_count)


def _stats_line_text() -> str:
    """Real, live data -- no new persistence. pending count comes from
    jd_manager.get_pending_jds(); tailored count comes from the append-only
    tracker CSV, NOT from jds/completed/'s file count -- archive_jd() moves
    files out of that directory, which would make an "All-Time" total go
    down. This walks the whole JD corpus, so it is expensive: call it once
    and reuse the string, never once per animation frame."""
    pending = len(jd_manager.get_pending_jds())
    tailored = jd_manager.count_completed_resumes()
    return f"{pending} Roles Currently Awaiting Resume Creation · {tailored} Resumes Customized All-Time"


def display_main_banner(reveal: bool = True) -> None:
    # Sparkles ride the same diagonal gradient/reveal as the letters
    # themselves (composed onto each line before the grid is built, not
    # rendered separately) so they wipe in together as one coherent piece
    # instead of the letters finishing and sparkles popping in after.
    #
    # Fills all the way to the panel's inner right edge: the panel has no
    # explicit width (so it stretches to console.width), box.DOUBLE costs
    # 1 column of border on each side, and padding=(1, 2) costs 2 more on
    # each side -- 6 columns of overhead total.
    gap = "   "
    banner_width = max((len(line) for line in MAIN_BANNER_LINES), default=0)
    sparkle_width = console.width - 6 - banner_width - len(gap)
    sparkle_lines = _sparkle_field(len(MAIN_BANNER_LINES), sparkle_width)
    decorated_lines = [
        line + gap + sparkles
        for line, sparkles in zip(MAIN_BANNER_LINES, sparkle_lines)
    ]
    grid = _gradient_grid(decorated_lines, theme.BRAND, theme.BRAND_ACCENT)
    # Hoisted out of render_frame deliberately: the stats are constant for the
    # length of the animation, but calling this per-frame walked the entire JD
    # corpus 31 times and turned a 1.6s reveal into ~27s -- the first thing
    # every user ever experiences. Compute once, close over the string.
    stats_line = _stats_line_text()

    def render_frame(threshold):
        body = _render_grid(decorated_lines, grid, threshold=threshold)
        body.append(SUBTITLE, style="bold")
        body.append(stats_line, style=theme.INFO)
        return Panel(body, border_style=theme.BRAND, box=box.DOUBLE, padding=(1, 2))

    if not reveal or not console.is_terminal or os.environ.get("RESUME_BUILDER_MOTION") == "reduced":
        console.print(render_frame(None))
        return

    _reveal_banner(decorated_lines, grid, render_frame)


def display_stats_line() -> None:
    console.print(_stats_line_text(), style=theme.INFO)


TIPS = [
    "Want the AI to sound like you? Drop past cover letters, personal bios, or emails into source_documents/ — our engine extracts and clones your unique tone and style automatically!",
    "What is a 'Bullet Bank'? It is your living achievement inventory. Curate your accomplishments there, and the AI will auto-select and adapt the best matches for each job description!",
    "To target your job search, customize your active search keywords inside your profile's search_queries.json file directly in-app or in your editor.",
    "Did you know? Logging into LinkedIn or JobRight in Google Chrome lets our scanner fetch session cookies automatically on macOS — no manual copy-pasting required!",
    "Running low on time? Try 'Express Setup (Auto-pilot)' — it ingests your source files, constructs your bullet bank, and builds a customized resume in a single click!",
    "Have a specific edit in mind? Use 'Polish Resume or Cover Letter' to conversationally ask the AI for exact visual, wording, or structure tweaks.",
    "Landed an interview? Update your status in the Applications Tracker to unlock achievements and watch your funnel conversion rate rise!"
]


def display_tip() -> None:
    """Boxed and shown last in the launch sequence -- reads as a distinct
    callout rather than blending into the stats line above it."""
    console.print()  # Blank line before tip for separation
    tip = random.choice(TIPS)
    console.print(Panel(
        f"{theme.colorize_icon('hint')}  Did you know? {tip}",
        border_style=theme.BRAND_ACCENT, box=box.ROUNDED, padding=(0, 2),
    ))


def display_exit_footer() -> None:
    """Closing flourish shown once, at session exit -- bookends
    display_main_banner()'s launch treatment (same BRAND/BRAND_ACCENT
    gradient pairing and sparkle motif from the banner's own decoration,
    just condensed to one line instead of a 13-row block)."""
    console.print()
    console.rule(
        f"[{theme.BRAND_ACCENT}]✦[/{theme.BRAND_ACCENT}]  "
        f"[dim]resume-builder[/dim]  "
        f"[{theme.BRAND_ACCENT}]✦[/{theme.BRAND_ACCENT}]",
        style=theme.BRAND,
    )


def display_breadcrumb() -> None:
    """Replaces a full banner repaint on menu loop-back -- one line, not
    another full-width panel every time an action finishes."""
    console.print()  # Blank line before breadcrumb for separation
    console.rule(f"[bold {theme.BRAND}]›[/bold {theme.BRAND}] resume-builder", style="dim", align="left")


def display_whats_next_panel() -> None:
    console.print(f"\n[bold {theme.BRAND}]What's next?[/bold {theme.BRAND}]")


def display_bootstrap_intro(doc_count: int) -> None:
    body = (
        f"Here's what's about to happen:\n\n"
        f"I'll read through your {doc_count} document(s) and pull out real "
        f"achievements, figure out which company each one belongs to, tag "
        f"them by skill area, then run them through a quality-check, "
        f"cleanup, and rewrite pipeline so you end up with a polished "
        f"bullet bank.\n\n"
        f"Two of these steps make real API calls and can take a few "
        f"minutes — I'll let you know before each one."
    )
    console.print(Panel(body, title="New User Bootstrap", border_style=theme.SUCCESS, box=box.ROUNDED, padding=(1, 2)))


# Same four tiers as orchestrator.FitEvaluationSchema's `recommendation`
# Literal -- sourced from theme.py so this table and picker.py's checkbox
# list are provably one palette, not two hand-maintained copies. "Skip"
# is intentionally not dimmed here (it was previously "red dim" in this
# file only) -- unified to match picker.py's plain-hex treatment.
_RECOMMENDATION_COLORS = theme.RECOMMENDATION_COLORS


def display_banner(subtitle: str = "") -> None:
    """Direct single-command invocations (e.g. `resume tailor file.json`)
    get the same lightweight rule-line treatment as menu loop-backs
    (display_breadcrumb()) rather than a full boxed panel -- consistent
    with "don't repaint a whole banner for one action", and theme.BRAND
    instead of a hardcoded "cyan"."""
    title = f"[bold {theme.BRAND}]›[/bold {theme.BRAND}] resume-builder"
    if subtitle:
        title += f" [dim]— {subtitle}[/dim]"
    console.rule(title, style="dim", align="left")


def _short_why(why: str, max_len: int = 70) -> str:
    """Truncates evaluate_fit()'s full 2-4 sentence `why` to a single
    short descriptor for compact table display -- the full text is still
    persisted in full (jd_manager.save_evaluation()) for anyone who wants
    to read the whole rationale, this is just the at-a-glance version."""
    why = (why or "").strip()
    if not why:
        return "-"
    first_sentence = why.split(". ")[0].rstrip(".")
    if len(first_sentence) <= max_len:
        return first_sentence
    return first_sentence[:max_len].rstrip() + "..."


# Mirrors orchestrator.STALE_POSTING_THRESHOLD_DAYS -- kept as a plain
# constant here rather than importing orchestrator (a heavy module with
# its own Gemini client dependency) into this presentation layer just
# for one number.
_POSTING_AGE_STALE_DAYS = 7
_POSTING_AGE_VERY_STALE_DAYS = 21


def _posting_age_cell(days: int | None) -> str:
    """Icon+colored "Nd" cell for how long a posting's been up -- green
    within the not-yet-penalized window, amber into the scoring-penalty
    range, red well past it. "-" when no post date or scan-discovery
    fallback was available at all (see
    jd_manager.compute_posting_age_days()).

    The icon is not decoration. This was the one cell in this module
    signalling by color alone, which is invisible to a colorblind user
    and to anyone piping output somewhere unstyled -- everywhere else
    pairs color with a glyph via theme.colorize_icon(). Pairing it here
    makes freshness readable from the glyph with the color removed."""
    if days is None:
        return "-"
    if days <= _POSTING_AGE_STALE_DAYS:
        color, icon_name = theme.SUCCESS, "success"
    elif days <= _POSTING_AGE_VERY_STALE_DAYS:
        color, icon_name = theme.WARNING, "warning"
    else:
        color, icon_name = theme.ERROR, "error"
    return f"[{color}]{theme.ICONS[icon_name]} {days}d[/{color}]"


def _fit_odds_cell(score: float | None) -> str:
    """Colored Fit/Odds cell, reusing the same four-tier vocabulary as
    _RECOMMENDATION_COLORS (SUCCESS/BRAND/WARNING/ERROR) rather than
    inventing a fresh scale -- so a 4.5 Fit score reads as the same kind
    of "good" as a "Strong pursue" recommendation. "hint" is BRAND-colored
    (see theme._ICON_COLORS), which is what makes it the right icon for
    the vocabulary's second tier -- there's no dedicated "good but not
    great" icon name in theme.py, so this reuses one that already
    resolves to the right color.

    Pairs color with an icon (not color alone) for the same reason
    _posting_age_cell does: color-only signaling is invisible to a
    colorblind user and to anything piping this output unstyled.

    "-" for missing/None -- fit_score/interview_odds_score were added to
    the evaluation dict after older evaluations were already persisted,
    so a pre-existing JD's JSON may not have them yet."""
    if score is None:
        return "-"
    if score >= 4.0:
        color, icon_name = theme.SUCCESS, "success"
    elif score >= 3.0:
        color, icon_name = theme.BRAND, "hint"
    elif score >= 2.0:
        color, icon_name = theme.WARNING, "warning"
    else:
        color, icon_name = theme.ERROR, "error"
    return f"[{color}]{theme.ICONS[icon_name]} {score:.1f}[/{color}]"


def render_fit_table(results: list, start_index: int = 1, title: str | None = None) -> None:
    """Renders batch_evaluate.evaluate_all_pending()'s result list -- or a
    page-sized slice of it -- as a Rich Table, colored by recommendation
    tier (modeled on job_automater's display_job_table(), cli.py:73-142).
    results is expected pre-sorted (evaluate_all_pending() already sorts
    best-first, errors-last). start_index numbers the "#" column from an
    arbitrary offset so a paginated caller (picker.pick_and_process())
    can show true positions (51, 52, ...) instead of every page
    restarting at 1. title overrides the panel's title -- defaults to a
    plain count for non-paginated callers. The "Why" column is a short
    excerpt, not the model's full reasoning -- lets a lower-scored-but-
    higher-priority role get spot-checked at a glance instead of needing
    to open its JD JSON to see why it scored the way it did.

    Columns are explicitly sized/bounded for the same reason
    render_pipeline_table's are (see that function's own B22 comment):
    seven columns with no sizing meant Rich divided any width deficit
    evenly across all of them, squeezing/truncating header text itself on
    an ordinary 80-100 column terminal. Title is the one `ratio` column so
    it absorbs whatever's left; Why -- a short excerpt, least essential at
    a glance -- drops entirely below _NARROW_TERMINAL_COLUMNS rather than
    shrinking everything else past legibility.

    Fit and Odds are the two layers that feed Score alongside Practical
    Pursue (orchestrator.COMPOSITE_SCORE_WEIGHTS -- 40/40/20), broken out
    as their own columns so a strong-fit/weak-odds role no longer looks
    identical to the reverse just because their blended Score matches.
    Score stays and stays the sort key -- these are additive context, not
    a replacement. Practical Pursue is deliberately NOT broken out here
    (keeps the table narrow); render_comparison_table already shows all
    three layers in full for anyone who wants that."""
    narrow = console.width < _NARROW_TERMINAL_COLUMNS
    show_score_detail = console.width >= _FIT_SCORE_DETAIL_COLUMNS
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE, expand=True)
    table.add_column("#", justify="right", style="dim", width=4, no_wrap=True)
    table.add_column("Score", justify="right", width=7, no_wrap=True)
    if show_score_detail:
        table.add_column("Fit", justify="right", width=6, no_wrap=True)
        table.add_column("Odds", justify="right", width=6, no_wrap=True)
    table.add_column("Recommendation", min_width=9, no_wrap=True, overflow="ellipsis")
    # max_width caps Company at a real company name's length -- without
    # one, a column with only min_width auto-grows on its longest cell,
    # and it was winning that fight against Score/Recommendation's own
    # fixed widths on ordinary terminals, cutting the score value itself.
    table.add_column("Company", min_width=10, max_width=22, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", ratio=1, min_width=25, no_wrap=True, overflow="ellipsis")
    table.add_column("Posted", justify="right", width=8, no_wrap=True)
    if not narrow:
        table.add_column("Why", width=40, no_wrap=True, overflow="ellipsis")

    for i, r in enumerate(results, start_index):
        if r["error"]:
            row = [str(i), f"[{theme.ERROR}]ERROR[/{theme.ERROR}]"]
            if show_score_detail:
                row += ["-", "-"]
            row += ["-", r["company_name"], r["job_title"], "-"]
            if not narrow:
                row.append("-")
            table.add_row(*row)
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], theme.MUTED)
        row = [
            str(i),
            f"[{color}]{r['composite_score']:.2f}/5[/{color}]",
            f"[{color}]{r['recommendation']}[/{color}]",
            r["company_name"],
            r["job_title"],
            _posting_age_cell(r.get("posting_age_days")),
        ]
        if show_score_detail:
            row.insert(2, _fit_odds_cell(r.get("fit_score")))
            row.insert(3, _fit_odds_cell(r.get("interview_odds_score")))
        if not narrow:
            row.append(_short_why(r.get("why")))
        table.add_row(*row)

    legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in _RECOMMENDATION_COLORS.items())
    console.print()
    console.print(Panel(
        table, title=title or f"{len(results)} JD(s) evaluated", subtitle=legend,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))
    console.print()


def _liveness_cell(liveness: dict | None) -> str:
    if not liveness or not liveness.get("checked_at"):
        return "-"
    date = liveness["checked_at"][:10]
    result = liveness.get("result", "")
    color = {"active": theme.SUCCESS, "likely_active": theme.SUCCESS, "expired": theme.ERROR}.get(result, theme.WARNING)
    return f"[{color}]{result or '?'}[/{color}] ({date})"


_FOLLOWUP_COLORS = {"overdue": theme.ERROR, "cold": theme.MUTED, "waiting": theme.SUCCESS}


def _followup_cell(application: dict | None) -> str:
    if not application:
        return "-"
    status = application.get("status", "?")
    urgency = followup.compute_urgency(application)
    if not urgency:
        return status
    color = _FOLLOWUP_COLORS.get(urgency, theme.MUTED)
    return f"{status} [{color}]({urgency})[/{color}]"


_NARROW_TERMINAL_COLUMNS = 110

# Fit/Odds break the composite Score into its two primary layers, which is
# genuinely useful but costs ~13 columns. They are ADDITIVE detail, so they
# are the first thing dropped when space is tight -- the pre-existing
# columns (Recommendation, Status, Last Liveness, Follow-up) carry
# information a user acts on directly and must not lose room to them.
# Thresholds differ because the two tables carry different column sets:
# the fit table's free-text "Why" needs room to stay readable, and the
# pipeline table additionally carries Status/Liveness/Follow-up.
_FIT_SCORE_DETAIL_COLUMNS = 130
_PIPELINE_SCORE_DETAIL_COLUMNS = 150


def render_pipeline_table(rows: list, start_index: int = 1, title: str | None = None) -> None:
    """Renders picker.list_all_evaluated_jds()'s row list -- or a
    page-sized slice of it -- as a bordered table (the "blue box" browse
    view). start_index numbers the "#" column from an arbitrary offset
    so a paginated caller (picker.browse_and_select_jds()) can show true
    positions (51, 52, ...) instead of every page restarting at 1. title
    overrides the panel's title -- defaults to a plain count for
    non-paginated callers.

    Nine columns with no explicit sizing used to mean Rich divided any
    width deficit evenly across all of them, eating the header text itself
    below ~120 columns ("Recom…", "Compa…", "Liven…") -- 80 and 100 are
    ordinary terminal widths, not edge cases (B22). Fixed widths on the
    short columns (#/Score/Posted/Status) protect their headers; Title
    gets the one `ratio` column so it absorbs whatever's left; Last
    Liveness/Follow-up -- the two least essential at a glance -- drop
    entirely below _NARROW_TERMINAL_COLUMNS rather than shrinking
    everything else past legibility.

    Fit and Odds break the blended Score out into its two primary layers
    (see render_fit_table's docstring for the full rationale) -- kept
    visible even on a narrow terminal since they're additive context for
    Score itself, unlike Liveness/Follow-up which are their own separate
    concern."""
    narrow = console.width < _NARROW_TERMINAL_COLUMNS
    show_score_detail = console.width >= _PIPELINE_SCORE_DETAIL_COLUMNS
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE, expand=True)
    table.add_column("#", justify="right", style="dim", width=3, no_wrap=True)
    table.add_column("Score", justify="right", width=6, no_wrap=True)
    if show_score_detail:
        table.add_column("Fit", justify="right", width=6, no_wrap=True)
        table.add_column("Odds", justify="right", width=6, no_wrap=True)
    table.add_column("Recommendation", min_width=9, no_wrap=True, overflow="ellipsis")
    # See render_fit_table's own comment on why Company needs a max_width.
    table.add_column("Company", min_width=10, max_width=22, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", ratio=1, min_width=25, no_wrap=True, overflow="ellipsis")
    table.add_column("Posted", justify="right", width=8, no_wrap=True)
    table.add_column("Status", width=10, no_wrap=True, overflow="ellipsis")
    if not narrow:
        table.add_column("Last Liveness", width=22, no_wrap=True, overflow="ellipsis")
        # 20 fits the longest real cell ("Interview (waiting)") without
        # truncating the urgency word itself -- that's the part that
        # actually matters at a glance, unlike Last Liveness's date.
        table.add_column("Follow-up", width=20, no_wrap=True, overflow="ellipsis")

    for i, r in enumerate(rows, start_index):
        evaluation = r["evaluation"]
        color = _RECOMMENDATION_COLORS.get(evaluation.get("recommendation"), theme.MUTED)
        cells = [
            str(i),
            f"[{color}]{evaluation.get('composite_score', 0):.2f}/5[/{color}]",
            f"[{color}]{evaluation.get('recommendation')}[/{color}]",
            r["company"] or "?",
            r["title"] or "?",
            _posting_age_cell(evaluation.get("posting_age_days")),
            r["status"],
        ]
        if show_score_detail:
            cells.insert(2, _fit_odds_cell(evaluation.get("fit_score")))
            cells.insert(3, _fit_odds_cell(evaluation.get("interview_odds_score")))
        if not narrow:
            cells.append(_liveness_cell(r.get("liveness")))
            cells.append(_followup_cell(r.get("application")))
        table.add_row(*cells)

    subtitle = (
        "[dim]Last Liveness/Follow-up hidden below ~110 columns -- widen your terminal to see them[/dim]"
        if narrow else None
    )
    console.print()
    console.print(Panel(
        table, title=title or f"{len(rows)} evaluated JD(s)", subtitle=subtitle,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))
    console.print()


def render_picker_header(title: str, columns: list, legend: str | None = None) -> None:
    """The purple bounding-box header for picker.py's merged table/
    checkbox pickers -- title, column labels, and the recommendation-tier
    legend, but deliberately NO data rows. Before this, picker.py drew
    every JD twice: once as an inert Rich table row here, a second time
    immediately below as the actual selectable questionary checkbox row
    -- visually two stacked lists showing the same data, only the second
    one interactive. The real rows now render only once, as the checkbox
    choices themselves, formatted to line up under this header by using
    the exact same `columns` widths (see picker.py's row formatters) --
    Rich's own dynamic Table layout can't be reused for that half since
    the row data renders through questionary/prompt_toolkit, a separate
    engine with no shared column model.

    columns is a list of (label, width, justify) tuples, justify being
    "left" or "right"."""
    header = Text()
    for label, width, justify in columns:
        cell = label.rjust(width) if justify == "right" else label.ljust(width)
        header.append(cell + "  ", style=TABLE_HEADER_STYLE)
    console.print(Panel(header, title=title, subtitle=legend, border_style=theme.BRAND, box=box.ROUNDED, padding=(0, 1)))


def render_picker_instructions() -> None:
    """A compact, high-contrast callout for the two keys that actually
    drive every checkbox picker in this program -- SPACE to toggle a
    row, ENTER to confirm. Previously this lived only as a few words
    inside the checkbox's own plain-text prompt header, easy to miss
    entirely (this bit even the program's own author, who forgot the
    picker needed a space-bar toggle rather than acting on Enter alone).
    Styled like a Charm/Crush-style popup: a small bordered box in the
    brand accent color, printed once above the first page of any picker."""
    body = (
        f"[bold {theme.BRAND_ACCENT}]SPACE[/bold {theme.BRAND_ACCENT}] toggle a row    "
        f"[bold {theme.BRAND_ACCENT}]ENTER[/bold {theme.BRAND_ACCENT}] confirm & continue    "
        f"[dim]↑↓ move  •  / filter[/dim]"
    )
    console.print(Panel(body, border_style=theme.BRAND_ACCENT, box=box.ROUNDED, padding=(0, 2)))


def render_polish_table(rows: list, start_index: int = 1, title: str | None = None) -> None:
    """Renders polish.pick_polish_target()'s candidate list -- or a
    page-sized slice of it -- as a bordered table (the same "blue box"
    style as render_pipeline_table()/render_fit_table(), for visual
    consistency across every large picker in this program). Each row is
    {"path": ..., "label": "Resume" or "Cover Letter"} -- doc-type
    detection stays in polish.py to avoid a cli_art<->polish import
    cycle. start_index/title behave exactly like
    render_pipeline_table()'s."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Type")
    table.add_column("Filename")
    table.add_column("Modified", justify="right")

    for i, r in enumerate(rows, start_index):
        modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(r["path"])))
        table.add_row(str(i), r["label"], os.path.basename(r["path"]), modified)

    console.print(Panel(
        table, title=title or f"{len(rows)} document(s)", border_style=theme.BRAND, box=box.ROUNDED,
    ))


# (subscore dict key, display label) grouped by layer, so the
# comparison table can show a section header per layer instead of one
# flat list of 18 dimensions with no indication of what they mean.
_FIT_DIMENSION_GROUPS = [
    ("Fit", "fit_subscores", {
        "functional_alignment": "Functional", "north_star_alignment": "North Star",
        "level_plausibility": "Level Fit", "work_style_sustainability": "Sustainability",
        "tools_process_overlap": "Tools",
    }),
    ("Interview odds", "interview_odds_subscores", {
        "title_continuity": "Title Continuity", "evidence_match": "Evidence Match",
        "domain_credibility": "Domain Cred.", "recruiter_legibility": "Recruiter Legibility",
        "narrative_burden": "Narrative Burden", "funnel_friction": "Funnel Friction",
    }),
    ("Practical pursue", "practical_pursue_subscores", {
        "remote_quality": "Remote", "compensation_viability": "Comp", "growth_value": "Growth",
        "time_to_offer": "Speed", "company_reputation": "Reputation",
        "cultural_signals": "Culture", "posting_legitimacy_score": "Legitimacy",
    }),
]


def render_comparison_table(rows: list) -> None:
    """Side-by-side comparison of 2+ already-evaluated JDs (the "Multi-job
    comparison mode" backlog item) -- one column per JD, one row per
    dimension grouped under its layer (fit / interview odds / practical
    pursue), so a strength/weakness pattern is visible at a glance rather
    than needing to hold several single-JD views in your head."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("")
    for r in rows:
        table.add_column(f"{r['company'] or '?'}\n{r['title'] or '?'}")

    def _row(label: str, values: list) -> None:
        table.add_row(label, *[str(v) for v in values])

    _row("Score", [f"{r['evaluation'].get('composite_score', 0):.2f}/5" for r in rows])
    _row("Recommendation", [
        f"[{_RECOMMENDATION_COLORS.get(r['evaluation'].get('recommendation'), 'white')}]"
        f"{r['evaluation'].get('recommendation')}[/{_RECOMMENDATION_COLORS.get(r['evaluation'].get('recommendation'), 'white')}]"
        for r in rows
    ])
    _row("Archetype", [r["evaluation"].get("archetype") or "-" for r in rows])
    _row("Posted", [_posting_age_cell(r["evaluation"].get("posting_age_days")) for r in rows])

    for group_label, subscores_key, labels in _FIT_DIMENSION_GROUPS:
        table.add_section()
        _row(f"[bold]{group_label}[/bold]", ["" for _ in rows])
        for dim, label in labels.items():
            _row(label, [r["evaluation"].get(subscores_key, {}).get(dim, "-") for r in rows])

    console.print(Panel(
        table, title=f"Comparing {len(rows)} JD(s)", border_style=theme.BRAND, box=box.ROUNDED,
    ))


_STAGE_STATUS_COLORS = {"Up to date": theme.SUCCESS, "Stale": theme.WARNING, "In progress": theme.INFO}


def render_bullet_bank_status(stage_rows: list, maintenance_rows: list, title: str = "Bullet Bank Pipeline Status",
                              show_numbers: bool = True) -> None:
    """stage_rows: (number, label, status, detail) tuples, in pipeline
    order. maintenance_rows: (label, detail) tuples for the non-sequential
    triage/retire scripts. title is overridable so bootstrap_menu.py can
    reuse this exact table shape for onboarding-phase status instead of
    carrying its own near-identical render function.

    show_numbers=False drops the "#" column, for callers whose rows are a
    linear checklist rather than a numbered pipeline. bootstrap_menu.py's
    onboarding table is the reason it exists: its first two steps are
    numbered 0 and 0.5 internally (they were inserted ahead of an existing
    1-6 pipeline), and "Stage 0.5" on a first-time user's very first screen
    is dev-sequencing leaking into the product. Renumbering them 1-8 there
    was the other option, but that would permanently disagree with the
    Bullet Bank menu's own 1-6 for the same stages. Dropping the column
    sidesteps both: row order already carries the sequence, and the Status
    column already says where you are. Callers still pass the number in
    each tuple -- it's simply not rendered."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    if show_numbers:
        table.add_column("#", justify="right", style="dim")
    table.add_column("Stage")
    table.add_column("Status")

    for number, label, status, detail in stage_rows:
        color = _STAGE_STATUS_COLORS.get(status)
        status_text = f"[{color}]{status}[/{color}]" if color else f"[dim]{status}[/dim]"
        if detail:
            status_text += f" ({detail})"
        row = (label, status_text) if not show_numbers else (str(number), label, status_text)
        table.add_row(*row)

    for label, detail in maintenance_rows:
        table.add_row(*((label, detail) if not show_numbers else ("-", label, detail)))

    console.print()
    console.print(Panel(table, title=title, border_style=theme.BRAND, box=box.ROUNDED))
    console.print()


def render_scan_report(source_results: list, total_written: int) -> None:
    """Renders scan.run_scan()'s per-source results -- one row per source
    in a summary table, then the actual new postings grouped under a
    themed divider per source. Deliberately doesn't print an
    "already known" line per skipped posting the way the old plain-print
    version did (noisy after the first run of the day, tens/hundreds of
    lines for zero new information) -- just a Skipped count in the
    summary table; anything genuinely new is what earns a visible line.
    source_results: [{"source", "fetched", "written", "skipped",
    "dropped_expired", "new_jobs": [{"company", "title"}], "warnings":
    [{"provider_id", "kind", "reason", "count"}], "error": str|None}, ...].
    "dropped_expired" is optional (only present when scan.run_scan()'s
    verify pass actually ran) -- a real Playwright check caught the
    posting as already-dead before it ever became a visible hit, distinct
    from "skipped" (already-known, not re-checked at all). "warnings" is
    pre-grouped by scan._summarize_warnings() (provider_id/kind/reason,
    most-frequent-first) -- e.g. workday HTTP 404s x44 renders as one row
    here, not 44 raw WARNING:root: lines the way the old plain-logging
    version did."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Source")
    table.add_column("Fetched", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Expired", justify="right")
    table.add_column("Issues", justify="right")

    for r in source_results:
        if r.get("error"):
            table.add_row(r["source"], "-", "-", "-", "-", "-", style=theme.ERROR)
            continue
        new_count = r["written"]
        new_style = theme.SUCCESS if new_count else "dim"
        dropped = r.get("dropped_expired", 0)
        dropped_style = theme.WARNING if dropped else "dim"
        issue_count = sum(w["count"] for w in r.get("warnings", []))
        issue_style = theme.WARNING if issue_count else "dim"
        table.add_row(
            r["source"], str(r["fetched"]),
            f"[{new_style}]{new_count}[/{new_style}]", str(r["skipped"]),
            f"[{dropped_style}]{dropped}[/{dropped_style}]",
            f"[{issue_style}]{issue_count}[/{issue_style}]",
        )

    console.print()
    console.print(Panel(
        table, title="Scan Results", border_style=theme.BRAND, box=box.ROUNDED,
        subtitle=f"{total_written} new JD(s) written to jds/",
    ))
    console.print()

    for r in source_results:
        if not r.get("new_jobs"):
            continue
        console.print()
        console.rule(f"[bold {theme.BRAND}]{r['source']}[/bold {theme.BRAND}] — {len(r['new_jobs'])} new", style="dim", align="left")
        for job in r["new_jobs"]:
            console.print(f"  {theme.colorize_icon('success')} [bold]{job['company']}[/bold] — {job['title']}")

    _render_scan_warnings(source_results)


_WARNING_KIND_LABELS = {
    "provider_failed": "listing fetch failed",
    "posting_text_failed": "description fetch failed",
    # From run_provider.mjs's JSON error envelope (B27) -- a specific reason
    # instead of the generic "listing fetch failed" above.
    "auth": "auth failed",
    "quota": "quota exhausted",
    "network": "network error",
    "config": "misconfigured",
    # From scan_boards.py's own description-quality check (B36).
    "thin_description": "thin description",
}


def _render_scan_warnings(source_results: list) -> None:
    """One grouped table across every source with issues -- see
    render_scan_report()'s docstring for why grouping matters here."""
    rows = [
        (r["source"], w["provider_id"] or "-", _WARNING_KIND_LABELS.get(w["kind"], w["kind"]), w["reason"], w["count"])
        for r in source_results for w in r.get("warnings", [])
    ]
    if not rows:
        return

    console.print()
    console.rule(f"[bold {theme.WARNING}]{theme.colorize_icon('warning')} Issues[/bold {theme.WARNING}]", style="dim", align="left")
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Source")
    table.add_column("Provider")
    table.add_column("Stage")
    table.add_column("Reason")
    table.add_column("Count", justify="right")
    for source, provider_id, stage, reason, count in rows:
        table.add_row(source, provider_id, stage, reason, f"[{theme.WARNING}]{count}[/{theme.WARNING}]")
    console.print(table)


# Single source of truth for the shortcuts cheat sheet -- both `resume
# help` (scripts/resume-cli.sh, which shells out to `python scripts/cli.py
# help`) and the interactive menu's Help entry render this same list, so
# there's exactly one place to update instead of two copies drifting apart.
HELP_ENTRIES = [
    ("resume", "launch the interactive menu"),
    ("resume bootstrap", "new-user setup: ingest documents, draft your profile, build the bullet bank"),
    ("resume activate", "cd into the project and activate the venv (stays active in this shell)"),
    ("resume cd", "just cd into the project"),
    ("resume run", "tailor+render every pending JD in jds/ (batch mode)"),
    ("resume run jds/x.txt", "tailor+render one specific JD file"),
    ("resume run --pick", "interactively select which pending JD(s) to tailor"),
    ("resume coverletter jds/x.txt", "generate + render a cover letter for one JD"),
    ("resume coverletter --pick", "interactively select which pending JD(s) to generate a cover letter for"),
    ("resume evaluate jds/x.txt", "score a JD's fit (go/no-go) without building a resume"),
    ("resume evaluate", "score every pending JD at once"),
    ("resume scan", "pull new postings into jds/ (verifies each is actually live via headless browser by default)"),
    ("resume scan --source jobright", "pull from just one source (jobright, linkedin, boards, ats)"),
    ("resume scan --no-verify", "skip the liveness check on new postings (faster, but stale listings may slip through)"),
    ("resume liveness", "check every pending JD's posting URL, move expired ones out"),
    ("resume polish", "interactively polish an already-generated resume/cover letter"),
    ("resume test", "run the full test suite (compact: dots + summary)"),
    ("resume test -v", "same, but lists every test by name"),
    ("resume test -vv", "same, but shows the app's own logging too"),
    ("resume doctor", "check dependencies/assets/config, then run the test suite"),
    ("resume doctor --skip-tests", "same, but skip the (slower) test-suite run"),
]


def display_playbook() -> None:
    """Renders the simple, compassionate 3-Step Job Search Playbook for ADHD job-seekers."""
    content = Text()
    content.append("🎯 STEP 1: Find & Pick High-Fit Roles\n", style=f"bold {theme.BRAND}")
    content.append("   • Run 'Find Jobs' -> 'Scan for New Jobs' (or paste a job link directly).\n", style=theme.MUTED)
    content.append("   • The AI scores fit automatically so you never waste energy on low-odds roles.\n\n", style=theme.MUTED)

    content.append("🚀 STEP 2: 1-Click Tailor & Build\n", style=f"bold {theme.SUCCESS}")
    content.append("   • Select 'Build Documents' -> 'Build Full Application Package'.\n", style=theme.MUTED)
    content.append("   • Generates an ATS-optimized PDF resume and tailored cover letter in seconds.\n\n", style=theme.MUTED)

    content.append("💼 STEP 3: Apply & Track Effortlessly\n", style=f"bold {theme.BRAND_ACCENT}")
    content.append("   • Open 'Track & Follow Up' -> 'Career Dashboard' to review and submit.\n", style=theme.MUTED)
    content.append("   • Keep track of applications, interview dates, and reminders without stress.\n", style=theme.MUTED)

    panel = Panel(
        content,
        title=f"[bold {theme.BRAND}]✦ 3-STEP JOB HUNT PLAYBOOK ✦[/bold {theme.BRAND}]",
        title_align="center",
        border_style=theme.BRAND,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def display_help() -> None:
    display_playbook()
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Command")
    table.add_column("What it does")
    for command, description in HELP_ENTRIES:
        table.add_row(command, description)
    console.print(Panel(table, title="resume-builder shortcuts", border_style=theme.BRAND, box=box.ROUNDED))



def display_applications_tracker(content: str) -> None:
    """Renders data/applications.md's raw markdown content directly in the
    terminal via Rich's built-in Markdown renderer -- the table and each
    row's clickable "[Apply](source_url)" link render as-is, no custom
    parsing needed since the file is already valid GFM markdown."""
    console.print(Markdown(content))


def render_doctor_report(checks: list, test_result: tuple | None = None) -> None:
    """checks: doctor.run_checks()'s result list. test_result: doctor.run_
    test_suite()'s (passed, summary) tuple, or None if the test-suite step
    was skipped/declined. Ends with a plain-English "N passed, M problems
    found" line and a one-line suggested fix per failing check, so nothing
    requires opening a JSON blob to act on."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    failed = []
    for c in checks:
        icon = f"[{theme.SUCCESS}]{theme.colorize_icon('success')}[/{theme.SUCCESS}]" if c["passed"] else f"[{theme.ERROR}]{theme.colorize_icon('error')}[/{theme.ERROR}]"
        table.add_row(c["name"], icon, c["detail"])
        if not c["passed"]:
            failed.append(c)

    console.print()
    console.print(Panel(table, title="Doctor Checks", border_style=theme.BRAND, box=box.ROUNDED))
    console.print()

    if test_result is not None:
        test_passed, test_summary = test_result
        icon = SUCCESS if test_passed else ERROR
        console.print(f"\n{icon} Test suite: {test_summary}")

    if failed:
        console.print(f"\n[bold {theme.ERROR}]{len(failed)} problem(s) found:[/bold {theme.ERROR}]")
        for c in failed:
            console.print(f"  {theme.colorize_icon('warning')} {c['name']}: {c['fix']}")
    else:
        console.print(f"\n{SUCCESS} All checks passed.")

def cli_info(message: str) -> None:
    """Print an informational message with hint icon. message is
    escaped -- see display_error()'s docstring."""
    console.print(f"{HINT} {_escape_markup(message)}", soft_wrap=True)

def cli_warning(message: str) -> None:
    """Print a warning message with warning icon. message is escaped --
    see display_error()'s docstring."""
    console.print(f"{WARNING} {_escape_markup(message)}", soft_wrap=True)

def cli_error(message: str) -> None:
    """Print an error message using display_error for consistency."""
    display_error(message)

def cli_success(message: str) -> None:
    """Print a success message with success icon. message is escaped --
    see display_error()'s docstring."""
    console.print(f"{SUCCESS} {_escape_markup(message)}", soft_wrap=True)


# =====================================================================
# House rule 1: output verbosity
# ---------------------------------------------------------------------
# A design audit found the core engine (orchestrator.py) printing cache
# hit/miss, per-tier character counts, model identifiers and rule-file
# names on every ordinary run -- engineer-facing telemetry shipped to a
# self-described non-technical audience. Rather than delete it (it's
# genuinely useful while iterating on prompts), output is now tiered.
#
# Three levels, because the middle one earns its place: cache hit/miss is
# cheap to read and meaningful even to a non-engineer ("this was free"),
# whereas char counts and model internals are not.
#
#   QUIET   -- errors, warnings and final results only.
#   NORMAL  -- the above, plus step labels and cache hit/miss. (default)
#   VERBOSE -- everything, including tier sizes, token math, model IDs
#              and which rule files were applied.
#
# Precedence: an explicit set_verbosity() call (i.e. a --quiet/--verbose
# CLI flag) beats the RESUME_BUILDER_VERBOSITY env var, which beats the
# NORMAL default. The env var is what makes this usable day-to-day --
# `RESUME_BUILDER_VERBOSITY=verbose resume run` needs no flag plumbing
# through the menu layer, which never passes argv at all.
# =====================================================================

QUIET = 0
NORMAL = 1
VERBOSE = 2

_VERBOSITY_ENV = "RESUME_BUILDER_VERBOSITY"
_LEVEL_BY_NAME = {
    "quiet": QUIET, "0": QUIET,
    "normal": NORMAL, "1": NORMAL,
    "verbose": VERBOSE, "2": VERBOSE, "debug": VERBOSE,
}
# None means "not yet resolved"; resolution is lazy so importing cli_art
# never reads the environment at import time (tests set the env var after
# import all the time).
_verbosity: int | None = None


def set_verbosity(level: int | str | None) -> None:
    """Pin the output level explicitly, overriding the environment.

    Accepts an int constant or a name ("quiet"/"normal"/"verbose").
    Passing None resets to unresolved, so the env var wins again -- which
    is what argparse should hand us when neither flag was given."""
    global _verbosity
    if level is None:
        _verbosity = None
        return
    if isinstance(level, str):
        level = _LEVEL_BY_NAME.get(level.strip().lower(), NORMAL)
    _verbosity = max(QUIET, min(VERBOSE, int(level)))


def verbosity() -> int:
    """Current output level, resolving from the environment on first use."""
    global _verbosity
    if _verbosity is None:
        raw = os.environ.get(_VERBOSITY_ENV, "").strip().lower()
        _verbosity = _LEVEL_BY_NAME.get(raw, NORMAL)
    return _verbosity


def at_level(level: int) -> bool:
    """True when output at `level` should be shown. Use this to guard an
    expensive f-string or a multi-line block, rather than building the
    string and throwing it away inside detail()."""
    return verbosity() >= level


def detail(message: str, level: int = VERBOSE, **print_kwargs) -> None:
    """Print implementation detail, suppressed unless the output level is
    high enough. Styled MUTED so that even when it IS shown it reads as
    secondary to the step labels around it.

    Default level is VERBOSE -- the stricter of the two -- so that an
    un-annotated call site stays hidden from ordinary users. Pass
    level=NORMAL only for the small set of internals a job seeker can
    actually act on (cache hit/miss being the motivating case)."""
    if not at_level(level):
        return
    print_kwargs.setdefault("style", theme.MUTED)
    print_kwargs.setdefault("soft_wrap", True)
    console.print(message, **print_kwargs)


# =====================================================================
# House rule 2: no raw exception text reaches the user
# ---------------------------------------------------------------------
# doctor.py's check/detail/fix convention is the best error UX in this
# codebase -- every failure carries a concrete one-line remedy. This
# generalizes that shape so any caller gets it for free.
#
# The classifier is deliberately ordered most-specific-first and falls
# through to a generic message, so an unrecognized exception degrades to
# "something went wrong, here's the technical detail" rather than
# vanishing. Raw text is never dropped -- it moves to a dimmed second
# line under a plain-English first line.
# =====================================================================

# (exception type, substring to look for in str(exc) or "" for any) ->
# (plain-English explanation, concrete fix)
# Substring matching is lowercased on both sides.
_ERROR_SIGNATURES: list[tuple[type, str, str, str]] = [
    (FileNotFoundError, "", "A file this step needed isn't there.",
     "Run `resume doctor` -- it checks for every file the pipeline expects."),
    (PermissionError, "", "This machine wouldn't let the app read or write that file.",
     "Check the file isn't open in another program, then try again."),
    (json.JSONDecodeError, "", "A saved data file is corrupted and couldn't be read.",
     "Delete the file named below and let it rebuild, or restore it from a backup."),
    (UnicodeDecodeError, "", "A file contains characters that couldn't be read as text.",
     "Re-save the file as UTF-8 and try again."),
    (TimeoutError, "", "The request took too long and gave up.",
     "Check your internet connection and try again -- this is usually temporary."),
    # --- Below: signatures taken from the real failure text, produced by
    # --- actually triggering each one rather than guessing at wording.
    # --- The substrings are the stable part of each message; the variable
    # --- parts (paths, counts, row numbers) are deliberately not matched.
    #
    # Playwright, browsers never installed / installed somewhere else.
    # Real text: "browserType.launch: Executable doesn't exist at
    # /.../chrome-headless-shell" followed by an ASCII box telling you to
    # run `npx playwright install`.
    (Exception, "executable doesn't exist",
     "The headless browser that turns your resume into a PDF isn't installed.",
     "Run `npm install && npx playwright install chromium` in the project folder."),
    # The macOS 12 trap this project is pinned around (see CLAUDE.md):
    # Playwright >= 1.62 dropped macOS 12, so an unpinned upgrade makes
    # every render die here. Worth its own message because the fix is the
    # opposite of the obvious one -- downgrade, don't reinstall.
    (Exception, "does not support chromium on mac",
     "The installed Playwright version is too new for this machine's macOS.",
     "Pin playwright to exactly 1.61.1 in package.json (not ^1.61.1), then re-run `npm install`."),
    (Exception, "cannot find module",
     "A required Node package isn't installed.",
     "Run `npm install` in the project folder."),
    (Exception, "command not found: node",
     "Node.js isn't installed, or isn't on this shell's PATH.",
     "Install Node, then run `resume doctor` to confirm it's visible."),
    # The Go toolchain is the one dependency the rest of this project does
    # NOT need -- only the dashboard and the new-user setup wizard shell out
    # to it. So "go: command not found" is both likely on a fresh machine
    # and completely opaque if shown raw.
    (Exception, "command not found: go",
     "The setup wizard and dashboard need the Go toolchain, which isn't installed.",
     "Install Go (https://go.dev/dl/), then try again -- nothing else in this app needs it."),
    (Exception, "go: no such file or directory",
     "The setup wizard and dashboard need the Go toolchain, which isn't installed.",
     "Install Go (https://go.dev/dl/), then try again -- nothing else in this app needs it."),
    # pandas CSV failures. Real text, in order:
    #   ParserError:    "Error tokenizing data. C error: Expected 2 fields
    #                    in line 3, saw 5"
    #   ParserError:    "Error tokenizing data. C error: EOF inside string
    #                    starting at row 1"
    #   EmptyDataError: "No columns to parse from file"
    # Both ParserError and EmptyDataError subclass ValueError, so they're
    # matched on message text rather than type.
    (Exception, "eof inside string",
     "A saved spreadsheet has a quote that's opened but never closed, so the rest of the file can't be read.",
     "Open the file listed below in a spreadsheet app, fix the stray quote mark, and save it again as CSV."),
    (Exception, "error tokenizing data",
     "A saved spreadsheet has a row with the wrong number of columns.",
     "Open the file listed below in a spreadsheet app -- the error names the bad row -- then save it again as CSV."),
    (Exception, "no columns to parse",
     "A saved spreadsheet is completely empty.",
     "Restore it from a backup, or re-run the bullet-bank setup step to rebuild it."),
    # gemini_client.SustainedFailureError's own message text.
    (Exception, "sustained quota issue",
     "Gemini refused several requests in a row, which usually means the API key is out of quota.",
     "Swap GEMINI_API_KEY in your profile's .env for one with quota left, or wait for the window to reset."),

    # --- GENERIC NETWORK / API SIGNATURES MUST STAY LAST ---------------
    # First match wins, so broad needles have to sit below narrow ones.
    # This is not theoretical: "sustained quota issue" above contains the
    # word "quota", so while the generic "quota" entry sat higher in this
    # list, SustainedFailureError matched it and told the user to "wait
    # for the quota to reset" -- when the actual remedy is to swap the
    # API key. Anything added below this line is a fallback, not a
    # signature; add new specific cases ABOVE this comment.
    # tests/test_cli_art_errors.py pins the two collisions that matter.
    (Exception, "api key", "The Gemini API key is missing or wasn't accepted.",
     "Add a valid GEMINI_API_KEY to your profile's .env file, then run `resume doctor`."),
    (Exception, "quota", "You've hit the Gemini API's usage limit for now.",
     "Wait for the quota to reset, or switch to a different model tier."),
    (Exception, "rate limit", "Requests are going out faster than the API allows.",
     "Wait a minute and run it again -- an interrupted run resumes from its checkpoint."),
    (Exception, "429", "Requests are going out faster than the API allows.",
     "Wait a minute and run it again -- an interrupted run resumes from its checkpoint."),
    (Exception, "connection", "Couldn't reach the service over the network.",
     "Check your internet connection, then try again."),
    (Exception, "timed out", "The request took too long and gave up.",
     "Check your internet connection and try again -- this is usually temporary."),
    (Exception, "ssl", "A secure connection to the service couldn't be established.",
     "Check whether a VPN or corporate proxy is intercepting traffic."),
]

_GENERIC_EXPLANATION = (
    "Something went wrong that this app doesn't have a specific explanation for."
)


def _classify(text: str, exc: BaseException | None = None) -> tuple[str, str | None]:
    """Shared matcher behind describe_error() and describe_stderr().

    Two callers with different amounts of information:
      - describe_error() has a real exception, so type-anchored signatures
        (FileNotFoundError, PermissionError, ...) are eligible.
      - describe_stderr() has only captured text from a subprocess, where
        there is no Python exception to type-check. Type-anchored
        signatures are skipped entirely there rather than being matched
        loosely, so a bare `except`-style catch-all can't fire on a
        substring it was never meant to own."""
    lowered = (text or "").lower()
    for exc_type, needle, explanation, fix in _ERROR_SIGNATURES:
        if exc is not None:
            if not isinstance(exc, exc_type):
                continue
        elif exc_type is not Exception or not needle:
            continue
        if needle and needle not in lowered:
            continue
        return explanation, fix
    return _GENERIC_EXPLANATION, None


def describe_error(exc: BaseException, context: str) -> tuple[str, str | None]:
    """Classify an exception into (plain-English explanation, fix or None).

    `context` is what the app was trying to do, phrased as a noun phrase
    -- "saving your tailored resume", "checking whether the posting is
    still live". It leads the message, so the user learns what broke
    before they learn how."""
    return _classify(str(exc), exc)


def describe_stderr(text: str) -> tuple[str, str | None]:
    """Classify captured subprocess stderr into (explanation, fix or None).

    The exception-based path can't cover the failures that matter most
    here: generate-pdf.mjs and check-liveness.mjs are Node subprocesses,
    so a missing Chromium or a missing npm package arrives as a non-zero
    return code plus stderr text, never as a Python exception. Those
    call sites used to print that stderr verbatim -- which is how a
    Playwright ASCII-art box ends up on a job seeker's screen."""
    return _classify(text, None)


def friendly_subprocess_error(stderr: str, context: str, fix: str | None = None) -> None:
    """Report a failed subprocess in plain language, raw output demoted.

    The `returncode != 0` counterpart to friendly_error()."""
    explanation, suggested_fix = describe_stderr(stderr)
    display_error(f"Couldn't finish {context}. {explanation}")
    if fix or suggested_fix:
        console.print(f"   {theme.colorize_icon('hint')} {fix or suggested_fix}", soft_wrap=True)
    raw = (stderr or "").strip()
    if raw:
        # markup=False and MUTED for the same reasons friendly_error()
        # uses them: subprocess output routinely contains brackets Rich
        # would try to parse, and box-drawing art that shouldn't compete
        # with the plain sentence above it.
        for line in raw.splitlines():
            if line.strip():
                console.print(f"   {line}", style=theme.MUTED, markup=False, soft_wrap=True)


def friendly_error(exc: BaseException, context: str, fix: str | None = None) -> None:
    """Report an exception in plain language, with the raw text demoted to
    a dimmed detail line rather than deleted.

    Follows doctor.py's what/why/fix shape. Pass `fix` to override the
    classifier's suggestion when the call site knows better."""
    explanation, suggested_fix = describe_error(exc, context)
    display_error(f"Couldn't finish {context}. {explanation}")
    if fix or suggested_fix:
        console.print(f"   {theme.colorize_icon('hint')} {fix or suggested_fix}", soft_wrap=True)
    raw = str(exc).strip()
    if raw:
        # markup=False: exception text routinely contains square brackets
        # (list reprs, log prefixes) that Rich would try to parse as tags.
        console.print(f"   {type(exc).__name__}: {raw}", style=theme.MUTED,
                      markup=False, soft_wrap=True)


def friendly_warning(exc: BaseException, context: str, consequence: str) -> None:
    """The non-fatal sibling of friendly_error, for the `except` blocks
    that fall back to a default instead of aborting.

    `consequence` states what the user is getting INSTEAD -- the thing
    that was actually missing from the swallowed-exception sites this was
    built for, where users saw "0 existing rows" with no way to know that
    came from a parse failure rather than reality."""
    cli_warning(f"Couldn't finish {context} -- {consequence}")
    raw = str(exc).strip()
    if raw and at_level(NORMAL):
        console.print(f"   {type(exc).__name__}: {raw}", style=theme.MUTED,
                      markup=False, soft_wrap=True)


# =====================================================================
# House rule 3: one confirm-gate policy
# ---------------------------------------------------------------------
# The audit found cost-gated Gemini calls confirming properly while
# destructive-but-free actions (archive_jd, application-status changes)
# committed instantly. The blind spot was "free == safe", which isn't
# true when the cost is the user's own data. These wrappers also bake in
# QUESTIONARY_STYLE, which was previously repeated at 18 call sites.
# =====================================================================

def select(message: str, choices, **kwargs):
    """questionary.select() with this app's style applied, or upgraded to Charm."""
    import sys
    if "unittest" in sys.modules:
        kwargs.setdefault("style", QUESTIONARY_STYLE)
        return questionary.select(message, choices=choices, **kwargs).ask()
    return charm_prompt.select(message, choices, default=kwargs.get("default"))


def confirm(message: str, default: bool = False, **kwargs) -> bool:
    """questionary.confirm() with this app's style applied, or upgraded to Charm.

    Returns False (not None) when the user aborts with Ctrl-C, so callers
    can treat the answer as a plain bool without re-introducing the
    Ctrl-C-fallthrough bug class documented in menu.py:151-217."""
    import sys
    if "unittest" in sys.modules:
        kwargs.setdefault("style", QUESTIONARY_STYLE)
        answer = questionary.confirm(message, default=default, **kwargs).ask()
        return bool(answer)
    answer = charm_prompt.confirm(message, default=default)
    return bool(answer)


def text(message: str, **kwargs):
    """questionary.text() with this app's style applied."""
    kwargs.setdefault("style", QUESTIONARY_STYLE)
    return questionary.text(message, **kwargs).ask()


def checkbox(message: str, choices, **kwargs):
    """questionary.checkbox() with this app's style applied, or upgraded to Charm."""
    import sys
    if "unittest" in sys.modules:
        kwargs.setdefault("style", QUESTIONARY_STYLE)
        return questionary.checkbox(message, choices=choices, **kwargs).ask()
    return charm_prompt.checkbox(message, choices)


def confirm_destructive(action: str, target: str, default: bool = False) -> bool:
    """The single gate for actions that change or discard the user's own
    data without costing money -- archiving a posting, overwriting a
    saved document, changing an application's status.

    `action` is an imperative verb phrase ("Archive", "Overwrite",
    "Mark as rejected"); `target` names the specific thing. Defaults to
    No, because the whole point is that a stray Enter shouldn't be
    destructive."""
    console.print(
        f"{WARNING} [bold]{action}[/bold] {target}?", soft_wrap=True)
    return confirm("   Are you sure?", default=default)


def print_subprocess_output(text: str) -> None:
    """Renders output captured from a Node-side subprocess
    (generate-pdf.mjs, check-liveness.mjs) that has no color output of
    its own -- both already resolve RESUME_BUILDER_ICONS for their own
    icons (see generate-pdf.mjs's B45 comment), but printing their text
    raw and unstyled drops the CLI out of its Charmtone palette for
    exactly those lines, sandwiched between fully-colored status lines
    just before and after. Dims each non-blank line to theme.MUTED
    instead -- distinct from, but still part of, the same palette as its
    neighbors. style= (not markup) applies the color, so this stays safe
    against literal '[' / ']' in the subprocess's own text."""
    for line in text.splitlines():
        if line.strip():
            console.print(line, style=theme.MUTED, markup=False, soft_wrap=True)


def new_progress(**kwargs) -> Progress:
    """Rich Progress bar pre-configured with resume-builder's standard
    spinner+description+bar+percentage columns, themed via `console` --
    the same construction cli.py's batch tailor command uses. Any batch
    operation processing a known number of items should build its
    progress bar through this instead of re-declaring the column set, so
    every progress bar in the program looks identical. Usage:

        with cli_art.new_progress() as progress:
            task = progress.add_task(f"[bold {theme.BRAND}]...", total=n)
            for item in items:
                progress.update(task, description="...")
                ...
                progress.advance(task)
    """
    return Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {theme.BRAND_ACCENT}"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=40,  # Chunky, wide bar
            complete_style=f"bold {theme.SUCCESS}",  # Mint green for completed portion
            finished_style=f"bold {theme.BRAND}",  # Purple when fully complete
        ),
        TaskProgressColumn(),
        console=console,
        **kwargs,
    )


class ScanActivity:
    """Context-managed live activity display for a multi-source scan or
    verify pass: one pinned, live-updating tally line (a themed
    rich.Progress spinner task) plus a permanent, themed step-log of
    completed items printed above it. Progress is built on Live and
    supports printing permanent lines through its own .console while a
    task stays live -- that's what gives this its two-part shape,
    matching Crush's step-log-plus-status-line pattern rather than an
    animated percentage bar (most of these sources never know a grand
    total up front). See new_scan_activity()."""

    def __init__(self, **progress_kwargs):
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots", style=f"bold {theme.BRAND_ACCENT}"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            **progress_kwargs,
        )
        self._task_id = None
        self._counts: dict = {}
        self._eta_total = None
        self._eta_done = 0
        self._eta_start = None

    def __enter__(self) -> "ScanActivity":
        self._progress.__enter__()
        self._task_id = self._progress.add_task(
            f"[bold {theme.BRAND}]Scanning[/bold {theme.BRAND}]", total=None,
        )
        return self

    def __exit__(self, *exc_info) -> None:
        self._progress.__exit__(*exc_info)

    def start_source(self, total: int, label: str = "Checking") -> None:
        """Resets the running ETA tracker for the next source's items --
        same averaging math scan_boards.ProgressReporter used to own.
        A source with no known total up front (e.g. JobRight's
        open-ended pagination) simply never calls this, and step()
        prints with no ETA suffix."""
        self._eta_total = total
        self._eta_done = 0
        self._eta_start = time.time()

    def step(self, icon_name: str, source: str, message: str, preserve_markup: bool = False) -> None:
        """Print one permanent themed line: icon, source label,
        message, plus a running ETA suffix once start_source() has
        been called and at least one prior step() has run.

        preserve_markup=True allows Rich markup in the message without
        escaping (use for pre-formatted styled messages)."""
        eta = ""
        if self._eta_total is not None:
            self._eta_done += 1
            if self._eta_done > 1:
                avg = (time.time() - self._eta_start) / self._eta_done
                remaining = avg * (self._eta_total - self._eta_done)
                eta = f" (~{_format_scan_eta(remaining)} remaining)"
        icon = theme.colorize_icon(icon_name)
        message_part = message if preserve_markup else _escape_markup(message)
        self._progress.console.print(
            f"  {icon} [bold]{_escape_markup(source)}[/bold] {message_part}{eta}", soft_wrap=True,
        )

    def tally(self, **counts: int) -> None:
        """Update the pinned line's description from named counts,
        cumulative across calls, e.g. tally(fetched=12) then
        tally(written=9) -> 'Scanning · Fetched 12 · Written 9'. Count
        names deliberately match scan.py's existing per-source result
        dict keys (fetched/written/skipped) rather than inventing
        synonyms."""
        self._counts.update(counts)
        description = f"[bold {theme.BRAND}]Scanning[/bold {theme.BRAND}]"
        if self._counts:
            parts = " · ".join(f"{key.capitalize()} {value}" for key, value in self._counts.items())
            description += f" · {parts}"
        self._progress.update(self._task_id, description=description)


def _format_scan_eta(seconds: float) -> str:
    """Same duration formatting scan_boards._format_duration used to
    own (Ns / NmNNs / NhNNm) -- moved here since ETA math now lives on
    ScanActivity instead of the retired ProgressReporter."""
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def new_scan_activity(**kwargs) -> ScanActivity:
    """Themed live activity display for a multi-source scan or verify
    pass: a pinned, live-updating tally line plus a permanent step-log
    of completed items underneath it. Usage:

        with cli_art.new_scan_activity() as activity:
            activity.start_source(len(jobs), label="Checking")
            for job in jobs:
                activity.step("success", "ATS", f"{job['title']} @ {job['company']}")
            activity.tally(fetched=len(jobs))
    """
    return ScanActivity(**kwargs)


def format_job_found_message(job_title: str, company_name: str, separator: str = "@") -> str:
    """Format a styled job discovery message with Rich markup:
    - Role title: colored in SUCCESS (mint-green)
    - Separator and company: gray/muted
    - Format: Found "Job Title" @ Company"""
    return f"[dim]Found[/dim] \"[{theme.SUCCESS}]{_escape_markup(job_title)}[/{theme.SUCCESS}]\" {separator} [dim]{_escape_markup(company_name)}[/dim]"


def format_board_name(board_name: str) -> str:
    """Format a board/source name with styling: info color.
    Used for: ATS providers, public job boards."""
    return f"[{theme.INFO}]{_escape_markup(board_name)}[/{theme.INFO}]"


def format_jd_label(company_name: str, job_title: str) -> str:
    """Format a JD label with styled title and company.
    Format: Company — Title (with title in SUCCESS color, separator/company muted)."""
    return f"[dim]{_escape_markup(company_name)} —[/dim] [{theme.SUCCESS}]{_escape_markup(job_title)}[/{theme.SUCCESS}]"


def render_rewrite_queue_table(rows: list, title: str) -> None:
    """Themed table for a ranked list of queued-for-rewrite bullets --
    audit_keepers.py's Top-10-worst preview. Each row:
    {"rank", "source", "composite", "manager_test", "bullet"}. Bullet
    text and source are escaped (see display_error()'s docstring) since
    Table cells parse markup exactly like console.print does -- a
    bullet or provider-id containing a stray "[" would otherwise be
    silently dropped the same way a plain console.print call would."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("#", justify="right")
    table.add_column("Source")
    table.add_column("Composite", justify="right")
    table.add_column("Manager Test")
    table.add_column("Bullet")
    for row in rows:
        table.add_row(
            str(row["rank"]),
            _escape_markup(str(row["source"])),
            f"{row['composite']:.0f}",
            str(row["manager_test"]),
            f"{_escape_markup(row['bullet'])}...",
        )
    console.print(Panel(table, title=title, border_style=theme.BRAND, box=box.ROUNDED, padding=(0, 1)))


def render_triage_summary_table(counts: dict) -> None:
    """Themed summary for triage_needs_review.py's routing pass --
    replaces five flat 'KEEP -> N' lines with one small table matching
    render_bullet_bank_status()'s visual language."""
    table = Table(box=box.SIMPLE_HEAD, show_header=False)
    table.add_column("Outcome")
    table.add_column("Count", justify="right")
    table.add_row(f"[{theme.SUCCESS}]KEEP[/{theme.SUCCESS}]", str(counts.get("keep", 0)))
    table.add_row(f"[{theme.WARNING}]REWRITE[/{theme.WARNING}]", str(counts.get("rewrite", 0)))
    table.add_row(f"[{theme.ERROR}]RETIRE[/{theme.ERROR}]", str(counts.get("retire", 0)))
    table.add_row("DUPLICATE (already in keeper bank, skipped)", str(counts.get("duplicate", 0)))
    table.add_row("Leftover (needs human)", str(counts.get("leftover", 0)))
    console.print(Panel(table, title="Triage Results", border_style=theme.BRAND, box=box.ROUNDED, padding=(0, 1)))


def display_compact_banner(action_title: str) -> None:
    """Prints a beautiful, ultra-compact 1-line header for active script runs,
    preserving terminal height for script output while maintaining product branding.
    """
    panel_content = Text()
    panel_content.append("✦ ", style=theme.BRAND_ACCENT)
    panel_content.append(make_gradient_text("💎 RESUME BUILDER ", theme.BRAND, theme.BRAND_ACCENT))
    panel_content.append("│ ", style=theme.MUTED)
    panel_content.append(make_gradient_text(action_title.upper(), theme.INFO, theme.SUCCESS))
    panel_content.append(" │ ", style=theme.MUTED)
    panel_content.append("Active Script Execution Mode", style=theme.MUTED)
    panel_content.append(" ✦", style=theme.BRAND_ACCENT)
    
    panel = Panel(
        panel_content,
        border_style=theme.BRAND,
        box=box.ROUNDED,
        padding=(0, 2),
        width=console.width
    )
    console.print(panel)
    console.print()


def thinking_status(message: str):
    """Shifting Gradient-Wave loader for Gemini 'Thinking' state.
    Cycles Peach, Pink, Mauve, and Blue dynamically with sparkling flourishes.
    """
    import threading
    import contextlib
    
    # Catppuccin Peach, Pink, Mauve, Lavender, Blue, Sky tokens from theme.py
    colors = theme.THINKING_GRADIENT_COLORS
    stop_event = threading.Event()
    
    status = console.status(
        f"[bold {theme.BRAND}]Thinking[/bold {theme.BRAND}] · {message}",
        spinner="dots",
        spinner_style=f"bold {theme.BRAND_ACCENT}"
    )
    
    def update_gradient():
        idx = 0
        while not stop_event.is_set():
            color = colors[idx % len(colors)]
            c2 = colors[(idx + 1) % len(colors)]
            c3 = colors[(idx + 2) % len(colors)]
            
            sparkles_left = f"[{color}]✦[/] [{c2}]✧[/] [{c3}]✦[/]"
            sparkles_right = f"[{c3}]✦[/] [{c2}]✧[/] [{color}]✦[/]"
            
            # Shifting wave text
            text = f"{sparkles_left} [bold {color}]Thinking[/] · [{theme.INFO}]{message}[/] {sparkles_right}"
            status.update(text, spinner="dots", spinner_style=f"bold {color}")
            idx += 1
            time.sleep(0.12)
            
    status.start()
    t = threading.Thread(target=update_gradient, daemon=True)
    t.start()
    
    @contextlib.contextmanager
    def _runner():
        try:
            yield status
        finally:
            stop_event.set()
            t.join(timeout=0.2)
            status.stop()
            
    return _runner()


def display_footer_commands() -> None:
    """Draws a beautiful, unified footer command bar at the very bottom line of the terminal,
    re-using our brand sparkles and Catppuccin styles to match Crush's premium visual grade.
    """
    columns, rows = shutil.get_terminal_size()
    # Save current cursor position
    sys.stdout.write("\x1b[s")
    
    # Move cursor to the very bottom row (row = rows)
    sys.stdout.write(f"\x1b[{rows};1H")
    
    # Format a beautiful styled commands footer
    footer_text = Text()
    footer_text.append("✦ ", style=theme.BRAND_ACCENT)
    footer_text.append("↑↓ / JK", style=f"bold {theme.INFO}")
    footer_text.append(" navigate  ", style=theme.MUTED)
    footer_text.append("│  ", style=theme.MUTED)
    footer_text.append("ENTER", style=f"bold {theme.SUCCESS}")
    footer_text.append(" select  ", style=theme.MUTED)
    footer_text.append("│  ", style=theme.MUTED)
    footer_text.append("CTRL+C", style=f"bold {theme.ERROR}")
    footer_text.append(" cancel / exit ", style=theme.MUTED)
    footer_text.append(" ✦", style=theme.BRAND_ACCENT)
    
    # Clear line first
    sys.stdout.write("\x1b[2K")
    # Draw footer text
    console.print(footer_text, end="")
    
    # Restore saved cursor position
    sys.stdout.write("\x1b[u")
    sys.stdout.flush()


def display_execution_footer() -> None:
    """Draws a beautiful, static footer bar at the very bottom line of the terminal during active script execution."""
    columns, rows = shutil.get_terminal_size()
    # Save cursor position
    sys.stdout.write("\x1b[s")
    # Move cursor to the bottom row
    sys.stdout.write(f"\x1b[{rows};1H")
    # Clear line first
    sys.stdout.write("\x1b[2K")
    
    footer_text = Text()
    footer_text.append("✦ ", style=theme.BRAND_ACCENT)
    footer_text.append("CTRL+C", style=f"bold {theme.ERROR}")
    footer_text.append(" stop active script  ", style=theme.MUTED)
    footer_text.append("│  ", style=theme.MUTED)
    footer_text.append("Please wait for execution to complete...", style=theme.MUTED)
    footer_text.append(" ✦", style=theme.BRAND_ACCENT)
    
    # Draw footer text
    console.print(footer_text, end="")
    # Restore cursor position
    sys.stdout.write("\x1b[u")
    sys.stdout.flush()


def make_gradient_text(text: str, start_color: str, end_color: str, bold: bool = True) -> Text:
    """Creates a beautifully-blended linear gradient text using TrueColor RGB hex codes."""
    r1, g1, b1 = int(start_color[1:3], 16), int(start_color[3:5], 16), int(start_color[5:7], 16)
    r2, g2, b2 = int(end_color[1:3], 16), int(end_color[3:5], 16), int(end_color[5:7], 16)
    
    gradient_text = Text()
    n = len(text)
    if n <= 1:
        gradient_text.append(text, style=f"{'bold ' if bold else ''}{start_color}")
        return gradient_text
        
    for i, char in enumerate(text):
        t = i / (n - 1)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        gradient_text.append(char, style=f"{'bold ' if bold else ''}{hex_color}")
        
    return gradient_text


def display_success_celebration(title: str, subtitle: str) -> None:
    """Prints a magnificent, high-energy celebratory card to keep job seekers motivated
    and deliver that essential hit of career dopamine! Incorporates twinkling terminal animations!
    """
    import time
    import random
    
    panel_content = Text()
    panel_content.append("\n🎉 ✦ ─── HECK YEAH! ─── ✦ 🎉\n\n", style=f"bold {theme.BRAND_ACCENT}")
    panel_content.append(title.upper(), style=f"bold {theme.SUCCESS}")
    panel_content.append("\n\n", style="default")
    panel_content.append(subtitle, style=f"italic {theme.INFO}")
    panel_content.append("\n\n💡 Remember: Every tailored resume brings you one step closer to your dream gig!", style=theme.MUTED)
    panel_content.append("\nGo crush this application! 🚀\n", style=f"bold {theme.BRAND}")
    
    grad_title = make_gradient_text("🌟 ACHIEVEMENT UNLOCKED 🌟", theme.BRAND_ACCENT, theme.BRAND)
    
    panel = Panel(
        panel_content,
        border_style=theme.BRAND_ACCENT,
        box=box.DOUBLE,
        padding=(1, 4),
        title=grad_title,
        title_align="center"
    )
    
    sparkles = ["✨", "✦", "✧", "⭐", "🎉", "🔥", "💫", "💎"]
    sys.stdout.write("\x1b[?25l")  # Hide cursor
    sys.stdout.flush()
    
    try:
        for frame in range(12):
            sys.stdout.write("\x1b[2J\x1b[H")  # Clear screen
            sys.stdout.flush()
            
            console.print()
            sparkle_row_1 = "   " + " ".join(random.choices(sparkles, k=8))
            console.print(make_gradient_text(sparkle_row_1, theme.BRAND_ACCENT, theme.BRAND))
            console.print()
            console.print(panel)
            console.print()
            sparkle_row_2 = "   " + " ".join(random.choices(sparkles, k=8))
            console.print(make_gradient_text(sparkle_row_2, theme.BRAND, theme.BRAND_ACCENT))
            time.sleep(0.1)
    finally:
        sys.stdout.write("\x1b[?25h")  # Restore cursor
        sys.stdout.flush()
        
    sys.stdout.write("\x1b[2J\x1b[H")  # Clear screen
    sys.stdout.flush()
    console.print()
    console.print(panel)
    console.print()


def render_application_package_hud(package_result: dict) -> None:
    """Renders a consolidated, rich summary HUD of the generated application package."""
    if not isinstance(package_result, dict):
        return

    company_name = package_result.get("company_name") or "Unknown Company"
    job_title = package_result.get("job_title") or "Unknown Role"
    evaluation = package_result.get("evaluation") or {}
    ats_info = package_result.get("ats_classification") or {}
    output_paths = package_result.get("output_paths") or {}

    composite_score = evaluation.get("composite_score", "-")
    rec = evaluation.get("recommendation", "N/A")
    ats_provider = ats_info.get("provider_id", "Standard ATS")
    ats_tier = ats_info.get("weight_tier", "")

    hud_content = Text()
    hud_content.append("🏢 Company:  ", style="bold")
    hud_content.append(f"{company_name}\n", style=f"bold {theme.BRAND}")
    hud_content.append("💼 Role:     ", style="bold")
    hud_content.append(f"{job_title}\n", style="bold")

    if composite_score != "-" or rec != "N/A":
        hud_content.append("🎯 Fit:      ", style="bold")
        score_str = f"{composite_score}/5.0" if composite_score != "-" else ""
        hud_content.append(f"{score_str} ({rec})\n", style=f"bold {theme.SUCCESS}")

    if ats_provider or ats_tier:
        tier_str = f" ({ats_tier})" if ats_tier else ""
        hud_content.append("🤖 ATS:      ", style="bold")
        hud_content.append(f"{ats_provider}{tier_str}\n", style=f"{theme.MUTED}")

    hud_content.append("\n📄 Resume Artifacts:\n", style=f"bold {theme.BRAND_ACCENT}")
    res_pdf = output_paths.get("resume_pdf")
    res_docx = output_paths.get("resume_docx")
    if res_pdf:
        hud_content.append("   • PDF:  ", style=f"bold {theme.SUCCESS}")
        hud_content.append(f"{res_pdf}\n", style=theme.SUCCESS)
    if res_docx:
        hud_content.append("   • DOCX: ", style=f"bold {theme.SUCCESS}")
        hud_content.append(f"{res_docx}\n", style=theme.SUCCESS)

    hud_content.append("\n✉️  Cover Letter Artifacts:\n", style=f"bold {theme.BRAND_ACCENT}")
    cl_pdf = output_paths.get("coverletter_pdf")
    cl_docx = output_paths.get("coverletter_docx")
    if cl_pdf:
        hud_content.append("   • PDF:  ", style=f"bold {theme.SUCCESS}")
        hud_content.append(f"{cl_pdf}\n", style=theme.SUCCESS)
    if cl_docx:
        hud_content.append("   • DOCX: ", style=f"bold {theme.SUCCESS}")
        hud_content.append(f"{cl_docx}\n", style=theme.SUCCESS)

    hud_content.append(f"\n{theme.colorize_icon('success')} Application package logged to SQLite tracker & marked complete.\n", style=theme.MUTED)

    panel = Panel(
        hud_content,
        title=f"[bold {theme.BRAND}]🚀 APPLICATION PACKAGE COMPLETE[/bold {theme.BRAND}]",
        title_align="left",
        border_style=theme.BRAND_ACCENT,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def sparkle_banner(title: str, subtitle: str = "") -> None:
    """Renders a sparkling header with Catppuccin gradient flourishes and subtle shimmer icons."""
    content = Text()
    content.append("✦ ", style=theme.BRAND_ACCENT)
    content.append(make_gradient_text(f"✧ {title} ✧", theme.BRAND, theme.BRAND_ACCENT))
    content.append(" ✦", style=theme.BRAND_ACCENT)
    if subtitle:
        content.append(f"\n{subtitle}", style=theme.MUTED)

    panel = Panel(
        content,
        border_style=theme.BRAND,
        box=box.ROUNDED,
        padding=(0, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def render_sparkle_celebration(title: str, message: str, tips: list[str] = None) -> None:
    """Renders a high-dopamine, ADHD-friendly completion screen celebrating user progress."""
    content = Text()
    content.append("✨ ", style=theme.BRAND_ACCENT)
    content.append(make_gradient_text(title, theme.SUCCESS, theme.BRAND_ACCENT))
    content.append(" ✨\n\n", style=theme.BRAND_ACCENT)
    content.append(f"{message}\n")

    if tips:
        content.append(f"\n[{theme.BRAND_ACCENT}]What to do next:[/{theme.BRAND_ACCENT}]\n")
        for tip in tips:
            content.append(f"  • {tip}\n", style=theme.MUTED)

    panel = Panel(
        content,
        title=f"[{theme.BRAND}]✦ SUCCESS ✦[/{theme.BRAND}]",
        title_align="center",
        border_style=theme.SUCCESS,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()

