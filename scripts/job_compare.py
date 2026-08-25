"""
job_compare.py — Side-by-side Job & Application Package Comparison Mode.

Compares two target job postings side-by-side across match fit score, compensation,
ATS keyword overlap, required skills diff, tailored bullet alignment, and strategic ROI.
"""

import json
import os
import re
import sys
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import cli_art
import db
import picker
import profile_paths
import theme
import vector_store
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def load_job_target(target: str, profile: str = None) -> dict[str, Any] | None:
    """Loads job dictionary from file path, DB job_id, or fuzzy name search."""
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            with open(target, "r", encoding="utf-8") as f:
                return {"raw_text": f.read(), "title": os.path.basename(target)}

    # Search in SQLite db
    name = profile or profile_paths.active_profile()
    conn = db.get_db(name)
    try:
        row = conn.execute(
            "SELECT id, title, company, location, status, final_score, metadata_json, raw_text "
            "FROM jobs WHERE id = ? OR company LIKE ? OR title LIKE ? LIMIT 1;",
            (target, f"%{target}%", f"%{target}%"),
        ).fetchone()
        if row:
            meta = {}
            if row[6]:
                try:
                    meta = json.loads(row[6])
                except Exception:
                    pass

            skills = meta.get("hard_skills") or []
            return {
                "id": row[0],
                "job_id": row[0],
                "title": row[1] or "Unknown Title",
                "company": row[2] or "Unknown Company",
                "platform": meta.get("platform") or "direct",
                "status": row[4] or "discovered",
                "fit_score": int(row[5] or 0),
                "location": row[3] or meta.get("location") or "Remote",
                "work_style": meta.get("work_style") or "Remote",
                "salary_min": meta.get("salary_min"),
                "salary_max": meta.get("salary_max"),
                "salary_raw": meta.get("salary_raw") or "Not specified",
                "why_fit": meta.get("why_fit") or "",
                "why_not_fit": meta.get("why_not_fit") or "",
                "hard_skills": skills,
                "raw_text": row[7] or "",
            }
    finally:
        conn.close()

    # Fallback to picker JSON scan
    evaluated = picker.list_all_evaluated_jds()
    for j in evaluated:
        if (
            str(j.get("id")) == str(target)
            or str(j.get("source_job_id")) == str(target)
            or target.lower() in str(j.get("company", "")).lower()
            or target.lower() in str(j.get("title", "")).lower()
        ):
            return j

    return None


def compare_jobs(
    job_a: dict[str, Any], job_b: dict[str, Any], profile: str = None
) -> dict[str, Any]:
    """Computes side-by-side comparison metrics between two job postings."""
    skills_a = set(s.lower() for s in (job_a.get("hard_skills") or []))
    skills_b = set(s.lower() for s in (job_b.get("hard_skills") or []))

    # If skills list is empty, extract rough keywords from raw_text or title
    if not skills_a and job_a.get("raw_text"):
        skills_a = set(
            re.findall(r"\b[A-Za-z]{3,}\b", job_a["raw_text"][:1000].lower())
        )
    if not skills_b and job_b.get("raw_text"):
        skills_b = set(
            re.findall(r"\b[A-Za-z]{3,}\b", job_b["raw_text"][:1000].lower())
        )

    common_skills = sorted(list(skills_a & skills_b))
    unique_a = sorted(list(skills_a - skills_b))
    unique_b = sorted(list(skills_b - skills_a))

    score_a = job_a.get("fit_score", 0) or 0
    score_b = job_b.get("fit_score", 0) or 0

    # RAG top matches for each
    query_a = f"{job_a.get('title', '')} {job_a.get('company', '')}"
    query_b = f"{job_b.get('title', '')} {job_b.get('company', '')}"

    rag_a = vector_store.search_bullet_bank(query_a, top_k=2, profile=profile)
    rag_b = vector_store.search_bullet_bank(query_b, top_k=2, profile=profile)

    # Decision verdict
    if score_a > score_b:
        verdict = f"[bold {theme.SUCCESS}]{job_a.get('company')} ({job_a.get('title')})[/] offers higher fit score (+{score_a - score_b} pts)."
    elif score_b > score_a:
        verdict = f"[bold {theme.SUCCESS}]{job_b.get('company')} ({job_b.get('title')})[/] offers higher fit score (+{score_b - score_a} pts)."
    else:
        verdict = "Both roles have tied fit scores. Prioritize based on compensation band and company alignment."

    return {
        "job_a": job_a,
        "job_b": job_b,
        "score_a": score_a,
        "score_b": score_b,
        "common_skills": common_skills,
        "unique_a": unique_a,
        "unique_b": unique_b,
        "rag_a": rag_a,
        "rag_b": rag_b,
        "verdict": verdict,
    }


def render_job_comparison(comp: dict[str, Any], console: Console = None) -> None:
    """Renders side-by-side comparison table to terminal."""
    c = console or cli_art.console
    a = comp["job_a"]
    b = comp["job_b"]

    c.print()
    c.print(
        Panel(
            f"[bold {theme.BRAND}]SIDE-BY-SIDE JOB & APPLICATION PACKAGE COMPARISON[/]\n"
            f"[dim]Comparing:[/] [bold]{a.get('company')} — {a.get('title')}[/] [dim]VS[/] [bold]{b.get('company')} — {b.get('title')}[/]",
            border_style=theme.BRAND,
            padding=(0, 2),
        )
    )

    table = Table(
        box=None,
        show_header=True,
        header_style=f"bold {theme.MUTED}",
        pad_edge=False,
    )
    table.add_column("Dimension", style="bold", width=20)
    table.add_column(
        f"Option A: {a.get('company', 'Job A')[:22]}", style="dim", width=34
    )
    table.add_column(
        f"Option B: {b.get('company', 'Job B')[:22]}", style="dim", width=34
    )

    # Title & Role
    table.add_row("Title", a.get("title", "—")[:32], b.get("title", "—")[:32])

    # Fit Score
    sa_style = theme.SUCCESS if comp["score_a"] >= 80 else theme.WARNING
    sb_style = theme.SUCCESS if comp["score_b"] >= 80 else theme.WARNING
    table.add_row(
        "Fit Score",
        f"[{sa_style}]{comp['score_a']}/100[/{sa_style}]",
        f"[{sb_style}]{comp['score_b']}/100[/{sb_style}]",
    )

    # Location & Work Style
    table.add_row(
        "Location / Style",
        f"{a.get('location', '—')} ({a.get('work_style', '—')})",
        f"{b.get('location', '—')} ({b.get('work_style', '—')})",
    )

    # Compensation
    table.add_row(
        "Compensation",
        str(a.get("salary_raw") or "Not listed"),
        str(b.get("salary_raw") or "Not listed"),
    )

    # Platform / Source
    table.add_row(
        "Source Platform",
        str(a.get("platform") or "Direct"),
        str(b.get("platform") or "Direct"),
    )

    # Skills Unique
    ua_str = ", ".join(comp["unique_a"][:4]) if comp["unique_a"] else "None"
    ub_str = ", ".join(comp["unique_b"][:4]) if comp["unique_b"] else "None"
    table.add_row("Distinct Skills", ua_str, ub_str)

    # Top Tailored Bullet Match
    ba = comp["rag_a"][0][0][:45] + "..." if comp["rag_a"] else "—"
    bb = comp["rag_b"][0][0][:45] + "..." if comp["rag_b"] else "—"
    table.add_row("Top Bullet Match", ba, bb)

    c.print(table)
    c.print()

    # Common Skills & Verdict
    if comp["common_skills"]:
        c.print(
            f"[bold {theme.BRAND_ACCENT}]🔗 Shared Required Competencies ({len(comp['common_skills'])}):[/] "
            + ", ".join(comp["common_skills"][:8])
        )
    c.print()
    c.print(
        Panel(
            f"🎯 [bold]Comparative Verdict:[/] {comp['verdict']}",
            border_style=theme.SUCCESS,
            padding=(0, 2),
        )
    )
    c.print()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        ja = load_job_target(sys.argv[1])
        jb = load_job_target(sys.argv[2])
        if ja and jb:
            res = compare_jobs(ja, jb)
            render_job_comparison(res)
        else:
            print("Could not locate both job targets.")
    else:
        print("Usage: python scripts/job_compare.py <target_a> <target_b>")
