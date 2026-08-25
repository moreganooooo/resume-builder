"""strategy_radar.py — Application Strategy Radar & Situation Room Coaching Module.

Analyzes job postings against candidate profile capabilities to provide:
1. ATS platform classification & document layout recommendations.
2. Seniority & archetype alignment (IC vs Management, CRM, Content, GTM).
3. Situation Room tactical playbooks (Overqualification defusal, gap framing, agency vs direct).
4. Automated evidence cluster & story hook recommendations from evidence-guide.csv.
5. Batch market radar analytics across the evaluated JD database.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import cli_art
import profile_paths
import theme
import vector_store

# ATS Platform Signatures & Parsing Rules
ATS_SIGNATURES = {
    "workday": {
        "patterns": [r"myworkdayjobs\.com", r"workday", r"wd\d+\.myworkday"],
        "name": "Workday",
        "doc_format": "DOCX (Plain-Text Structured) or Single-Column PDF",
        "ats_parsing_risk": "High (Rigid parser, sensitive to multi-column layouts)",
        "recommendation": "Use standard section headers. Avoid tables or complex grids. Keep bullet formatting clean.",
    },
    "taleo": {
        "patterns": [r"taleo\.net", r"taleo"],
        "name": "Oracle Taleo",
        "doc_format": "DOCX or Single-Column Clean PDF",
        "ats_parsing_risk": "High (Legacy ATS parser)",
        "recommendation": "Stick to standard chronological format. Explicitly match top hard skill keywords.",
    },
    "icims": {
        "patterns": [r"icims\.com", r"icims"],
        "name": "iCIMS",
        "doc_format": "Standard PDF / DOCX",
        "ats_parsing_risk": "Medium-High",
        "recommendation": "Ensure exact job title keywords appear in summary and earliest work experience.",
    },
    "greenhouse": {
        "patterns": [r"greenhouse\.io", r"boards\.greenhouse\.io", r"grnh\.se"],
        "name": "Greenhouse",
        "doc_format": "Typst Modern PDF (Standard 1-2 Page)",
        "ats_parsing_risk": "Low (Modern OCR & HTML preview)",
        "recommendation": "Strong visual hierarchy and crisp typography are highlighted. Human recruiters review in-app.",
    },
    "lever": {
        "patterns": [r"lever\.co", r"jobs\.lever\.co"],
        "name": "Lever",
        "doc_format": "Typst Modern PDF (Standard 1-2 Page)",
        "ats_parsing_risk": "Low (Modern OCR parser)",
        "recommendation": "Direct candidate profile view. Emphasize punchy metric bullets and portfolio links.",
    },
    "ashby": {
        "patterns": [r"ashbyhq\.com", r"jobs\.ashbyhq\.com"],
        "name": "Ashby",
        "doc_format": "Typst Modern PDF / Markdown-friendly",
        "ats_parsing_risk": "Low (Modern developer-centric ATS)",
        "recommendation": "Include live links to portfolio, GitHub, or case studies. Focus on direct impact metrics.",
    },
    "jobright": {
        "patterns": [r"jobright\.ai"],
        "name": "Jobright Aggregator",
        "doc_format": "Direct ATS Link / Typst PDF",
        "ats_parsing_risk": "Varies by destination ATS",
        "recommendation": "Trace destination ATS before applying to calibrate document formatting.",
    },
}

# Role Archetypes & Keywords
ARCHETYPES = {
    "CRM & Lifecycle Marketing": [
        "crm",
        "lifecycle",
        "retention",
        "email marketing",
        "hubspot",
        "salesforce",
        "marketo",
        "braze",
        "klaviyo",
        "campaign operations",
        "customer journey",
    ],
    "Content & Brand Strategy": [
        "content",
        "copywriter",
        "brand",
        "editorial",
        "storytelling",
        "messaging",
        "creative strategist",
        "content marketing",
        "social media",
        "communications",
    ],
    "GTM & Sales Enablement": [
        "enablement",
        "sdr",
        "bdr",
        "sales operations",
        "outreach.io",
        "pipeline",
        "sales playbooks",
        "prospecting",
        "training",
        "field enablement",
    ],
    "Marketing Generalist & Operations": [
        "generalist",
        "marketing manager",
        "marketing associate",
        "digital marketing",
        "growth",
        "campaign coordinator",
        "events",
        "ops",
        "project manager",
    ],
}


def detect_ats_platform(url: str, text: str = "") -> Dict[str, str]:
    """Detects ATS platform from job URL or text."""
    combined = f"{url} {text}".lower()
    for key, spec in ATS_SIGNATURES.items():
        for pat in spec["patterns"]:
            if re.search(pat, combined, re.IGNORECASE):
                return {
                    "platform_key": key,
                    "platform_name": spec["name"],
                    "recommended_format": spec["doc_format"],
                    "parsing_risk": spec["ats_parsing_risk"],
                    "advice": spec["recommendation"],
                }
    return {
        "platform_key": "direct",
        "platform_name": "Direct / Custom ATS",
        "recommended_format": "Typst Modern PDF (Clean Chronological)",
        "parsing_risk": "Low-Medium",
        "advice": "Standard professional typography and clear keyword alignment.",
    }


def classify_role_archetype(title: str, jd_text: str = "") -> Tuple[str, str]:
    """Classifies job title and text into core archetype and seniority level."""
    t_lower = title.lower()
    combined = f"{title} {jd_text}".lower()

    # Seniority
    if any(
        w in t_lower for w in ["director", "head of", "vp", "vice president", "chief"]
    ):
        seniority = "Director / Executive"
    elif any(w in t_lower for w in ["manager", "lead", "principal", "supervisor"]):
        seniority = "Lead / Manager"
    elif any(w in t_lower for w in ["senior", "sr.", "sr ", "iii", "iv"]):
        seniority = "Senior IC"
    elif any(
        w in t_lower for w in ["junior", "jr.", "entry", "associate", "coordinator"]
    ):
        seniority = "Associate / Coordinator"
    else:
        seniority = "Individual Contributor (IC)"

    # Archetype scoring
    scores: Dict[str, int] = collections.defaultdict(int)
    for arch, kws in ARCHETYPES.items():
        for kw in kws:
            if kw in t_lower:
                scores[arch] += 5
            if kw in combined:
                scores[arch] += 1

    best_arch = (
        max(scores.items(), key=lambda x: x[1])[0]
        if scores
        else "Marketing Generalist & Operations"
    )
    return best_arch, seniority


def select_situation_playbooks(
    title: str,
    jd_text: str,
    seniority: str,
    is_agency: bool,
    profile_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Selects tactical coaching playbooks based on role nuances."""
    playbooks = []

    # 1. Overqualification / IC Preference Playbook
    if (
        seniority in ["Lead / Manager", "Director / Executive"]
        or "manage" in title.lower()
    ):
        playbooks.append(
            {
                "title": "Tactical Playbook: Hands-On IC Refocus",
                "trigger": f"Role is flagged as '{seniority}', but target focus is High-Craft Individual Contributor.",
                "coaching": (
                    "Frame past management as an advantage for cross-functional collaboration and systems building, "
                    "while clearly asserting enthusiasm for direct tactical execution: 'I want an IC role where the writing, "
                    "systems, and strategy work are the job itself, not a side responsibility.'"
                ),
                "story_anchor": "Dedicated IC Focus & Hands-On Technical Execution",
            }
        )

    # 2. Agency vs Direct Employer Playbook
    if is_agency:
        playbooks.append(
            {
                "title": "Tactical Playbook: High-Volume Staffing Agency Navigation",
                "trigger": "Posting is managed by a staffing/recruiting agency rather than direct hiring team.",
                "coaching": (
                    "Agency recruiters filter heavily for literal keyword matches and immediate placement readiness. "
                    "Ensure hard skills (Salesforce, Outreach, CRM, Copywriting) appear verbatim in the top third of Page 1. "
                    "Highlight 2x Top Seller and rapid ramp velocity."
                ),
                "story_anchor": "Sales Velocity & Rapid Leadership Promotion",
            }
        )
    else:
        playbooks.append(
            {
                "title": "Tactical Playbook: Direct Brand Alignment & Culture Fit",
                "trigger": "Direct employer posting with high brand value.",
                "coaching": (
                    "Lead with genuine brand connection and values alignment. Connect the company's mission with "
                    "tangible past impact (e.g. tree planting, animal welfare broadcast PR, or organic community growth)."
                ),
                "story_anchor": "Professional Trust & Talent Retention",
            }
        )

    # 3. Creative & Systems Dual-Threat
    if any(
        kw in jd_text.lower()
        for kw in ["analytical", "metrics", "data", "reporting", "roi"]
    ):
        playbooks.append(
            {
                "title": "Tactical Playbook: Creative + Analytical Dual-Threat",
                "trigger": "JD emphasizes both creative concepting and quantitative reporting/metrics.",
                "coaching": (
                    "Emphasize the rare combination: author of campaigns with 95% open / 54% reply rates WHO ALSO "
                    "builds custom Salesforce dashboards and Handlebars conditional logic. 'Brings structure to creative work "
                    "and energy to technical systems.'"
                ),
                "story_anchor": "Agency Foundations & Creative Rigor",
            }
        )

    return playbooks


def analyze_job_strategy(
    job_data: Dict[str, Any],
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a complete Strategy Radar report for a specific job."""
    title = job_data.get("title") or job_data.get("role") or "Unknown Role"
    company = job_data.get("company") or "Unknown Company"
    url = job_data.get("url") or job_data.get("link") or ""
    jd_text = (
        job_data.get("description")
        or job_data.get("raw_text")
        or job_data.get("text")
        or ""
    )

    # Agency check
    is_agency = False
    notes = job_data.get("notes") or ""
    agency_keywords = [
        "staffing",
        "recruiting",
        "talent",
        "search partners",
        "apex systems",
        "teksystems",
        "robert half",
        "insight global",
    ]
    if any(kw in company.lower() or kw in notes.lower() for kw in agency_keywords):
        is_agency = True

    # ATS & Archetype
    ats_info = detect_ats_platform(url, jd_text)
    archetype, seniority = classify_role_archetype(title, jd_text)

    # Situation Playbooks
    playbooks = select_situation_playbooks(title, jd_text, seniority, is_agency)

    # Evidence Guide Semantic Retrieval
    search_query = f"{title} {archetype} {jd_text[:500]}"
    evidence_matches = vector_store.search_evidence_guide(
        search_query, top_k=3, profile=profile
    )

    # Bullet Bank Semantic Retrieval
    bullet_matches = vector_store.search_bullet_bank(search_query, top_k=3)

    return {
        "title": title,
        "company": company,
        "url": url,
        "is_agency": is_agency,
        "ats": ats_info,
        "archetype": archetype,
        "seniority": seniority,
        "playbooks": playbooks,
        "evidence_recommendations": evidence_matches,
        "bullet_recommendations": bullet_matches,
    }


def render_strategy_radar_hud(report: Dict[str, Any]) -> None:
    """Renders the Strategy Radar report into a rich terminal HUD."""
    from rich.panel import Panel
    from rich.table import Table

    cli_art.console.print()
    cli_art.console.print(
        Panel(
            f"[bold {theme.BRAND}]APPLICATION STRATEGY RADAR & SITUATION ROOM[/]\n"
            f"[dim]Role:[/] [bold]{report['title']}[/]  [dim]•[/]  "
            f"[dim]Company:[/] [bold]{report['company']}[/]  "
            f"({'[yellow]Agency/Staffing[/]' if report['is_agency'] else '[green]Direct Employer[/]'})",
            border_style=theme.BRAND,
            padding=(0, 2),
        )
    )

    # Overview Table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("Key", style="dim")
    t.add_column("Value", style="bold")

    t.add_row("Core Archetype:", f"[{theme.BRAND_ACCENT}]{report['archetype']}[/]")
    t.add_row("Seniority Tier:", report["seniority"])
    t.add_row(
        "Target ATS:",
        f"{report['ats']['platform_name']} ({report['ats']['parsing_risk']})",
    )
    t.add_row("Layout Delivery:", report["ats"]["recommended_format"])
    t.add_row("ATS Parsing Rule:", f"[dim italic]{report['ats']['advice']}[/]")

    cli_art.console.print(
        Panel(
            t,
            title="[bold]Strategic Profile & Delivery Parameters[/]",
            border_style="dim",
        )
    )

    # Situation Playbooks
    if report["playbooks"]:
        cli_art.console.print()
        cli_art.console.print(
            f"[bold {theme.BRAND_ACCENT}]⚡ Situation Room Tactical Playbooks[/]"
        )
        for pb in report["playbooks"]:
            cli_art.console.print(
                Panel(
                    f"[bold yellow]Trigger:[/] {pb['trigger']}\n\n"
                    f"[bold cyan]Tactical Coaching:[/] {pb['coaching']}\n\n"
                    f"[bold green]Suggested Narrative Anchor:[/] [italic]{pb['story_anchor']}[/]",
                    title=f"[bold]{pb['title']}[/]",
                    border_style="yellow",
                    padding=(0, 1),
                )
            )

    # Recommended Evidence Clusters
    if report.get("evidence_recommendations"):
        cli_art.console.print()
        cli_art.console.print(
            f"[bold {theme.BRAND}]📖 Top Evidence Clusters for Cover Letter & Why Narrative[/]"
        )
        for ev in report["evidence_recommendations"]:
            name = ev.get("cluster") or ev.get("Evidence Cluster") or "Evidence Cluster"
            metric = ev.get("metric") or ev.get("Best Metric") or "N/A"
            quote = ev.get("quote") or ev.get("Best Detail / Quote") or ""
            score = ev.get("score", 0.0)
            cli_art.console.print(
                f"  • [bold {theme.BRAND_ACCENT}]{name}[/] (Score: {score:.2f})\n"
                f"    [green]Key Metric:[/] {metric}\n"
                f'    [dim italic]"{quote[:180]}..."[/]\n'
            )

    # Recommended Bullet Bank Proof
    if report.get("bullet_recommendations"):
        cli_art.console.print(
            f"[bold {theme.BRAND}]🎯 Recommended Bullet Bank Anchors[/]"
        )
        for b in report["bullet_recommendations"]:
            bullet_text = b[0]
            role = b[1]
            sim = b[3]
            cli_art.console.print(
                f"  • [dim][{role}][/] {bullet_text} [cyan]({sim:.2f})[/]"
            )

    cli_art.console.print()
