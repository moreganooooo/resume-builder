"""
evidence_bank.py — Multi-Type Evidence Bank for Behavioral Stories & Negotiation Levers.

Provides:
1. STAR/CAR Behavioral Story Models & Storage (Situation, Task, Action, Result, Reflection)
2. Negotiation Levers & Talking Points Models & Storage (Anchors, Proof Points, Concessions)
3. Profile-scoped JSON storage with atomic writes & schema validation
4. Search, filtering, and terminal visualization HUD
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import cli_art
import profile_paths
import theme
from pydantic import BaseModel, Field


class BehavioralStory(BaseModel):
    id: str
    title: str
    archetype: str  # e.g., Leadership, ProblemSolving, Innovation, UnderPressure, Execution, Conflict
    situation: str
    task: str
    action: str
    result: str
    reflection_learning: Optional[str] = ""
    metrics: List[str] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    target_roles: List[str] = Field(default_factory=list)
    source: str = "verified_record"
    verified: bool = True
    confidence: float = 1.0


class NegotiationLever(BaseModel):
    id: str
    category: str  # e.g., Compensation, Equity, RemoteFlexibility, TitleSeniority, ScopeLeadership
    anchor_point: str
    talking_point: str
    metric_proof: str
    counter_scenario: Optional[str] = ""
    trade_off_concession: Optional[str] = ""
    source: str = "verified_record"
    priority: str = "High"  # High, Medium, Flexible


def stories_file_path(profile: Optional[str] = None) -> str:
    """Returns absolute path to behavioral_stories.json for given profile."""
    kb_dir = profile_paths.kb_dir(profile)
    return os.path.join(kb_dir, "behavioral_stories.json")


def negotiation_file_path(profile: Optional[str] = None) -> str:
    """Returns absolute path to negotiation_levers.json for given profile."""
    kb_dir = profile_paths.kb_dir(profile)
    return os.path.join(kb_dir, "negotiation_levers.json")


def load_behavioral_stories(profile: Optional[str] = None) -> List[BehavioralStory]:
    """Loads all verified STAR/CAR behavioral stories for active profile."""
    path = stories_file_path(profile)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        stories = []
        for item in data:
            stories.append(BehavioralStory(**item))
        return stories
    except Exception as e:
        cli_art.console.print(
            f"[{theme.WARNING}]⚠ Failed to load behavioral stories from {path}: {e}[/{theme.WARNING}]"
        )
        return []


def _dump_model(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def save_behavioral_stories(
    stories: List[BehavioralStory], profile: Optional[str] = None
) -> None:
    """Atomically writes behavioral stories to disk."""
    path = stories_file_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    data = [_dump_model(s) for s in stories]
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_negotiation_levers(profile: Optional[str] = None) -> List[NegotiationLever]:
    """Loads all negotiation levers for active profile."""
    path = negotiation_file_path(profile)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        levers = []
        for item in data:
            levers.append(NegotiationLever(**item))
        return levers
    except Exception as e:
        cli_art.console.print(
            f"[{theme.WARNING}]⚠ Failed to load negotiation levers from {path}: {e}[/{theme.WARNING}]"
        )
        return []


def save_negotiation_levers(
    levers: List[NegotiationLever], profile: Optional[str] = None
) -> None:
    """Atomically writes negotiation levers to disk."""
    path = negotiation_file_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    data = [_dump_model(l) for l in levers]
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def filter_stories(
    stories: List[BehavioralStory],
    archetype: Optional[str] = None,
    tag: Optional[str] = None,
    query: Optional[str] = None,
) -> List[BehavioralStory]:
    """Filters stories by archetype, tag, and lexical query."""
    results = stories
    if archetype:
        arch_norm = archetype.lower()
        results = [s for s in results if arch_norm in s.archetype.lower()]
    if tag:
        tag_norm = tag.lower()
        results = [s for s in results if any(tag_norm in t.lower() for t in s.tags)]
    if query:
        q_norm = query.lower()
        tokens = [t for t in re.split(r"\W+", q_norm) if len(t) >= 2]
        scored = []
        for s in results:
            content = f"{s.title} {s.situation} {s.task} {s.action} {s.result} {' '.join(s.tags)} {' '.join(s.tools_used)} {' '.join(s.target_roles)}".lower()
            score = sum(content.count(tok) for tok in tokens)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [s for _, s in scored]
    return results


def filter_negotiation_levers(
    levers: List[NegotiationLever],
    category: Optional[str] = None,
    query: Optional[str] = None,
) -> List[NegotiationLever]:
    """Filters negotiation levers by category and query."""
    results = levers
    if category:
        cat_norm = category.lower()
        results = [l for l in results if cat_norm in l.category.lower()]
    if query:
        q_norm = query.lower()
        tokens = [t for t in re.split(r"\W+", q_norm) if len(t) >= 2]
        scored = []
        for l in results:
            content = f"{l.category} {l.anchor_point} {l.talking_point} {l.metric_proof} {l.counter_scenario} {l.trade_off_concession}".lower()
            score = sum(content.count(tok) for tok in tokens)
            if score > 0:
                scored.append((score, l))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [l for _, l in scored]
    return results


def render_stories_terminal(stories: List[BehavioralStory]) -> None:
    """Renders STAR stories in a rich terminal view."""
    from rich.panel import Panel

    if not stories:
        cli_art.console.print(
            f"[{theme.WARNING}]No behavioral stories found matching criteria.[/{theme.WARNING}]"
        )
        return

    cli_art.console.print()
    cli_art.console.print(
        f"[{theme.BRAND}]✦ Multi-Type Evidence Bank — STAR/CAR Behavioral Stories ({len(stories)})[/]"
    )
    cli_art.console.print()

    for s in stories:
        tags_str = ", ".join(f"#{t}" for t in s.tags)
        metrics_str = " | ".join(s.metrics) if s.metrics else "N/A"
        tools_str = ", ".join(s.tools_used) if s.tools_used else "N/A"

        body = (
            f"[{theme.BRAND_ACCENT}]● ARCHETYPE:[/{theme.BRAND_ACCENT}] {s.archetype}  |  "
            f"[{theme.INFO}]● TAGS:[/{theme.INFO}] {tags_str}\n\n"
            f"[{theme.BRAND}]◈ SITUATION:[/{theme.BRAND}]\n  {s.situation}\n\n"
            f"[{theme.BRAND}]◈ TASK / CHALLENGE:[/{theme.BRAND}]\n  {s.task}\n\n"
            f"[{theme.SUCCESS}]◈ ACTION TAKEN:[/{theme.SUCCESS}]\n  {s.action}\n\n"
            f"[{theme.SUCCESS}]◈ MEASURABLE RESULT:[/{theme.SUCCESS}]\n  {s.result}\n"
        )
        if s.reflection_learning:
            body += f"\n[{theme.WARNING}]◈ REFLECTION & PRINCIPLE:[/{theme.WARNING}]\n  {s.reflection_learning}\n"

        body += (
            f"\n[{theme.MUTED}]────────────────────────────────────────────────────────────[/{theme.MUTED}]\n"
            f"[{theme.BRAND}]Metrics:[/{theme.BRAND}] {metrics_str}  │  "
            f"[{theme.BRAND}]Tools:[/{theme.BRAND}] {tools_str}  │  "
            f"[{theme.BRAND}]Source:[/{theme.BRAND}] {s.source}"
        )

        panel = Panel(
            body,
            title=f"[bold {theme.BRAND}]{s.title}[/bold {theme.BRAND}]",
            border_style=theme.BRAND,
            expand=False,
        )
        cli_art.console.print(panel)
        cli_art.console.print()


def render_negotiation_terminal(levers: List[NegotiationLever]) -> None:
    """Renders negotiation levers in a structured rich view."""
    from rich.panel import Panel

    if not levers:
        cli_art.console.print(
            f"[{theme.WARNING}]No negotiation levers found matching criteria.[/{theme.WARNING}]"
        )
        return

    cli_art.console.print()
    cli_art.console.print(
        f"[{theme.BRAND}]✦ Multi-Type Evidence Bank — Negotiation Strategy Levers ({len(levers)})[/]"
    )
    cli_art.console.print()

    for l in levers:
        body = (
            f"[{theme.BRAND_ACCENT}]● CATEGORY:[/{theme.BRAND_ACCENT}] {l.category}  |  "
            f"[{theme.WARNING}]● PRIORITY:[/{theme.WARNING}] {l.priority}\n\n"
            f"[{theme.SUCCESS}]◈ TARGET ANCHOR:[/{theme.SUCCESS}]\n  {l.anchor_point}\n\n"
            f'[{theme.BRAND}]◈ TALKING POINT (SCRIPT):[/{theme.BRAND}]\n  "{l.talking_point}"\n\n'
            f"[{theme.INFO}]◈ EMPIRICAL METRIC PROOF:[/{theme.INFO}]\n  {l.metric_proof}\n"
        )
        if l.counter_scenario:
            body += f"\n[{theme.WARNING}]◈ COUNTER-OFFER / PUSHBACK SCENARIO:[/{theme.WARNING}]\n  {l.counter_scenario}\n"
        if l.trade_off_concession:
            body += f"\n[{theme.BRAND_ACCENT}]◈ TRADE-OFF CONCESSION LEVER:[/{theme.BRAND_ACCENT}]\n  {l.trade_off_concession}\n"

        body += (
            f"\n[{theme.MUTED}]────────────────────────────────────────────────────────────[/{theme.MUTED}]\n"
            f"[{theme.BRAND}]Source:[/{theme.BRAND}] {l.source}"
        )

        panel = Panel(
            body,
            title=f"[bold {theme.BRAND}]{l.category} Lever: {l.anchor_point}[/bold {theme.BRAND}]",
            border_style=theme.BRAND_ACCENT,
            expand=False,
        )
        cli_art.console.print(panel)
        cli_art.console.print()
