"""
scan_stream.py — Live Scan Stream & NDJSON Event Monitor for Resume-Builder.

Features:
1. Standardized NDJSON event emission for batch scans, scrapers, and evaluators.
2. Supports stdout, file logging, or dedicated file descriptors (e.g. RESUME_EVENT_STREAM=3).
3. Rich Live interactive terminal monitor for viewing real-time pipeline events.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, TextIO

import cli_art
import theme
from pydantic import BaseModel, Field


class ScanEvent(BaseModel):
    event_type: str  # scan_start, job_discovered, job_deduped, job_evaluating, job_evaluated, job_filtered, scan_progress, scan_complete, error
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    job_id: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


def _dump_event(event: ScanEvent) -> Dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return event.dict()


class ScanStreamEmitter:
    """Emits newline-delimited JSON (NDJSON) events to an output stream."""

    def __init__(
        self, target_stream: Optional[TextIO] = None, fd: Optional[int] = None
    ):
        self._fd_file: Optional[TextIO] = None
        if fd is not None:
            self._fd_file = os.fdopen(fd, "w", buffering=1, encoding="utf-8")
            self.stream = self._fd_file
        elif target_stream is not None:
            self.stream = target_stream
        elif "RESUME_EVENT_STREAM" in os.environ:
            try:
                env_fd = int(os.environ["RESUME_EVENT_STREAM"])
                self._fd_file = os.fdopen(env_fd, "w", buffering=1, encoding="utf-8")
                self.stream = self._fd_file
            except Exception:
                self.stream = sys.stdout
        else:
            self.stream = sys.stdout

    def emit(self, event: ScanEvent) -> None:
        """Serializes event and writes one line of NDJSON."""
        line = json.dumps(_dump_event(event), ensure_ascii=False)
        try:
            self.stream.write(line + "\n")
            self.stream.flush()
        except Exception:
            pass

    def emit_event(
        self,
        event_type: str,
        message: str,
        job_id: Optional[str] = None,
        title: Optional[str] = None,
        company: Optional[str] = None,
        score: Optional[float] = None,
        source: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ScanEvent:
        ev = ScanEvent(
            event_type=event_type,
            message=message,
            job_id=job_id,
            title=title,
            company=company,
            score=score,
            source=source,
            details=details or {},
        )
        self.emit(ev)
        return ev

    def close(self) -> None:
        if self._fd_file:
            try:
                self._fd_file.close()
            except Exception:
                pass


def parse_ndjson_line(line: str) -> Optional[ScanEvent]:
    """Parses a single line of NDJSON into a ScanEvent."""
    clean = line.strip()
    if not clean:
        return None
    try:
        data = json.loads(clean)
        return ScanEvent(**data)
    except Exception:
        return None


class ScanMonitorState:
    def __init__(self):
        self.discovered = 0
        self.deduped = 0
        self.evaluating = 0
        self.evaluated = 0
        self.high_fit = 0  # score >= 80
        self.filtered = 0
        self.errors = 0
        self.recent_events: List[ScanEvent] = []
        self.max_events = 12
        self.is_complete = False

    def update(self, event: ScanEvent) -> None:
        self.recent_events.append(event)
        if len(self.recent_events) > self.max_events:
            self.recent_events.pop(0)

        et = event.event_type
        if et == "job_discovered":
            self.discovered += 1
        elif et == "job_deduped":
            self.deduped += 1
        elif et == "job_evaluating":
            self.evaluating += 1
        elif et == "job_evaluated":
            self.evaluated += 1
            if event.score and event.score >= 80:
                self.high_fit += 1
        elif et == "job_filtered":
            self.filtered += 1
        elif et == "error":
            self.errors += 1
        elif et == "scan_complete":
            self.is_complete = True


def render_monitor_view(state: ScanMonitorState):
    """Renders the Rich layout for the Live scan monitor."""
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.table import Table

    # Metrics HUD
    stat_tbl = Table.grid(padding=(0, 2))
    stat_tbl.add_column("Stat", justify="right")
    stat_tbl.add_column("Val", justify="left")

    c_discovered = f"[{theme.BRAND}]{state.discovered}[/{theme.BRAND}]"
    c_evaluated = f"[{theme.INFO}]{state.evaluated}[/{theme.INFO}]"
    c_high = f"[{theme.SUCCESS}]{state.high_fit}[/{theme.SUCCESS}]"
    c_deduped = f"[{theme.MUTED}]{state.deduped}[/{theme.MUTED}]"
    c_filtered = f"[{theme.WARNING}]{state.filtered}[/{theme.WARNING}]"
    c_errors = f"[{theme.ERROR}]{state.errors}[/{theme.ERROR}]"

    summary_text = (
        f"✦ [bold {theme.BRAND}]Discovered:[/] {c_discovered}  │  "
        f"[bold {theme.INFO}]Evaluated:[/] {c_evaluated}  │  "
        f"[bold {theme.SUCCESS}]High Fit (≥80%):[/] {c_high}  │  "
        f"[bold {theme.MUTED}]Deduped:[/] {c_deduped}  │  "
        f"[bold {theme.WARNING}]Filtered:[/] {c_filtered}  │  "
        f"[bold {theme.ERROR}]Errors:[/] {c_errors}"
    )

    # Activity Feed Table
    event_tbl = Table(
        show_header=True,
        header_style=f"bold {theme.BRAND}",
        title="Live Pipeline Stream Events",
        title_style=theme.BRAND_ACCENT,
        border_style=theme.BRAND,
        expand=True,
    )
    event_tbl.add_column("Time", width=10, style="dim")
    event_tbl.add_column("Type", width=16)
    event_tbl.add_column("Target Role / Company", width=34)
    event_tbl.add_column("Fit Score", justify="right", width=10)
    event_tbl.add_column("Message")

    for ev in state.recent_events:
        ts_short = (
            ev.timestamp.split("T")[-1].split(".")[0]
            if "T" in ev.timestamp
            else ev.timestamp[-8:]
        )
        et = ev.event_type

        badge_color = theme.INFO
        if et == "job_evaluated":
            badge_color = theme.SUCCESS if (ev.score and ev.score >= 80) else theme.INFO
        elif et in ("job_filtered", "job_deduped"):
            badge_color = theme.MUTED
        elif et == "error":
            badge_color = theme.ERROR
        elif et == "scan_complete":
            badge_color = theme.SUCCESS

        score_str = f"{ev.score:.1f}%" if ev.score is not None else "-"
        target_str = (
            f"{ev.title or ''} @ {ev.company or ''}"
            if (ev.title or ev.company)
            else "-"
        )

        event_tbl.add_row(
            ts_short,
            f"[{badge_color}]{et}[/{badge_color}]",
            target_str,
            score_str,
            ev.message,
        )

    status_footer = (
        f"[{theme.SUCCESS}]● Stream Active & Ingesting Events[/{theme.SUCCESS}]"
        if not state.is_complete
        else f"[{theme.BRAND}]✓ Scan Completed Successfully[/{theme.BRAND}]"
    )

    panel_content = f"{summary_text}\n\n" f"{event_tbl}\n\n" f"{status_footer}"

    return Panel(
        panel_content,
        title=f"[bold {theme.BRAND}]Resume Builder — Live Scan Stream Monitor[/bold {theme.BRAND}]",
        border_style=theme.BRAND,
    )


def run_live_monitor(stream: Iterator[str]) -> None:
    """Consumes lines of NDJSON and displays live terminal HUD."""
    from rich.live import Live

    state = ScanMonitorState()

    with Live(
        render_monitor_view(state), refresh_per_second=4, console=cli_art.console
    ) as live:
        for line in stream:
            ev = parse_ndjson_line(line)
            if ev:
                state.update(ev)
                live.update(render_monitor_view(state))
            if state.is_complete:
                break
