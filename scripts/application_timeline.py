import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import cli_art
import db
import profile_paths
import theme
from platform_analytics import STAFFING_AGENCY_PATTERNS


class TimelineMilestone:
    def __init__(
        self,
        event_type: str,
        timestamp: str,
        title: str,
        detail: str = "",
        status_badge: str = "INFO",
    ):
        self.event_type = event_type
        self.timestamp = timestamp
        self.title = title
        self.detail = detail
        self.status_badge = status_badge

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "title": self.title,
            "detail": self.detail,
            "status_badge": self.status_badge,
        }


def _parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(ts_str.split(".")[0], fmt)
        except ValueError:
            pass
    return None


def get_single_application_timeline(
    job_id_or_query: str, profile: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Reconstructs the full lifecycle timeline for a specific job."""
    conn = db.get_db(profile)
    try:
        # Search by ID or company/title query
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE id = ? OR id LIKE ? OR company LIKE ? OR title LIKE ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (
                job_id_or_query,
                f"%{job_id_or_query}%",
                f"%{job_id_or_query}%",
                f"%{job_id_or_query}%",
            ),
        ).fetchone()

        if not row:
            return None

        job_dict = dict(row)
        job_id = job_dict["id"]

        # Fetch application_log events
        app_rows = conn.execute(
            "SELECT * FROM application_log WHERE job_id = ? OR (company = ? AND role = ?) ORDER BY applied_at ASC",
            (job_id, job_dict["company"], job_dict["title"]),
        ).fetchall()

        # Fetch verification audits
        audit_rows = conn.execute(
            "SELECT * FROM verification_audit_log WHERE job_id = ? ORDER BY reviewed_at ASC",
            (job_id,),
        ).fetchall()

        # Fetch contacts
        contact_rows = conn.execute(
            "SELECT * FROM contacts WHERE company = ? ORDER BY created_at ASC",
            (job_dict["company"],),
        ).fetchall()

    finally:
        conn.close()

    milestones: List[TimelineMilestone] = []

    # 1. Milestone: Scraped / Discovered
    created_at = job_dict.get("created_at") or ""
    source_info = ""
    try:
        meta = json.loads(job_dict.get("metadata_json") or "{}")
        if meta.get("platform"):
            source_info = f" (via {meta['platform']})"
    except Exception:
        pass

    milestones.append(
        TimelineMilestone(
            event_type="DISCOVERED",
            timestamp=created_at,
            title=f"Job Discovered & Ingested{source_info}",
            detail=f"{job_dict['title']} at {job_dict['company']} (Location: {job_dict.get('location') or 'Remote'})",
            status_badge="INFO",
        )
    )

    # 2. Milestone: Evaluated
    score = job_dict.get("final_score")
    if score is not None and score > 0:
        cap = job_dict.get("capability_score") or 0.0
        rec = job_dict.get("recruiter_score") or 0.0
        score_badge = (
            "SUCCESS" if score >= 80 else ("WARNING" if score >= 65 else "INFO")
        )
        milestones.append(
            TimelineMilestone(
                event_type="EVALUATED",
                timestamp=job_dict.get("updated_at") or created_at,
                title=f"Evaluated Fit Score: {score:.1f}%",
                detail=f"Capability Match: {cap:.1f}% │ Recruiter Fit: {rec:.1f}%",
                status_badge=score_badge,
            )
        )

    # 3. Check Filesystem Artifacts (Tailored PDF / JSON)
    prof_name = profile or profile_paths.active_profile()
    root = profile_paths.PROJECT_ROOT
    pdf_path = os.path.join(root, "output", prof_name, "pdf", f"{job_id}_Resume.pdf")
    cl_path = os.path.join(
        root, "output", prof_name, "pdf", f"{job_id}_Cover_Letter.pdf"
    )
    json_path = os.path.join(root, "output", prof_name, "json", f"{job_id}.json")

    tailored_dt = None
    if os.path.isfile(pdf_path) or os.path.isfile(json_path):
        target_f = pdf_path if os.path.isfile(pdf_path) else json_path
        mtime = os.path.getmtime(target_f)
        tailored_dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        doc_types = ["Tailored Resume"]
        if os.path.isfile(cl_path):
            doc_types.append("Targeted Cover Letter")
        milestones.append(
            TimelineMilestone(
                event_type="TAILORED",
                timestamp=tailored_dt,
                title=f"Documents Compiled ({' + '.join(doc_types)})",
                detail=f"Rendered to {os.path.relpath(pdf_path, root) if os.path.isfile(pdf_path) else os.path.relpath(json_path, root)}",
                status_badge="SUCCESS",
            )
        )

    # 4. Milestone: Audited
    for a in audit_rows:
        milestones.append(
            TimelineMilestone(
                event_type="AUDITED",
                timestamp=a["reviewed_at"] or "",
                title=f"Human Verification Audit: {a['reviewer_action']}",
                detail=f"Sign-off Hash: {a['candidate_signoff_hash'] or 'N/A'} │ {a['notes'] or ''}",
                status_badge=(
                    "SUCCESS" if a["reviewer_action"] == "APPROVED" else "WARNING"
                ),
            )
        )

    # 5. Milestone: Application Submissions
    for app in app_rows:
        milestones.append(
            TimelineMilestone(
                event_type="APPLIED",
                timestamp=app["applied_at"] or "",
                title=f"Application Submitted (Status: {app['status'].upper()})",
                detail=f"Company: {app['company']} │ Notes: {app['notes'] or 'Direct Submission'}",
                status_badge="SUCCESS",
            )
        )
        if app["responded_at"]:
            milestones.append(
                TimelineMilestone(
                    event_type="RESPONDED",
                    timestamp=app["responded_at"],
                    title=f"Employer Response Received ({app['status'].upper()})",
                    detail=f"Notes: {app['notes'] or 'Status updated via email sync'}",
                    status_badge=(
                        "SUCCESS"
                        if app["status"] in ("interview", "offer")
                        else "WARNING"
                    ),
                )
            )

    # 6. Current Status Milestone if not yet captured
    st = (job_dict.get("status") or "pending").lower()
    if st in ("interview", "offer", "rejected", "discarded", "expired"):
        milestones.append(
            TimelineMilestone(
                event_type=st.upper(),
                timestamp=job_dict.get("updated_at") or "",
                title=f"Current Lifecycle Stage: {st.upper()}",
                detail=f"Deal-breakers / Notes: {job_dict.get('deal_breakers') or 'None'}",
                status_badge=(
                    "SUCCESS"
                    if st in ("interview", "offer")
                    else ("ERROR" if st == "rejected" else "INFO")
                ),
            )
        )

    # Sort milestones chronologically
    def _sort_key(m: TimelineMilestone):
        dt = _parse_timestamp(m.timestamp)
        return dt or datetime.min

    milestones.sort(key=_sort_key)

    contacts_summary = [
        {
            "name": c["name"],
            "title": c["title"] or "Recruiter",
            "email": c["email"] or "",
            "linkedin": c["linkedin_url"] or "",
        }
        for c in contact_rows
    ]

    return {
        "job_id": job_id,
        "title": job_dict["title"],
        "company": job_dict["company"],
        "location": job_dict.get("location") or "Remote",
        "status": job_dict.get("status") or "pending",
        "score": score,
        "created_at": created_at,
        "milestones": [m.to_dict() for m in milestones],
        "contacts": contacts_summary,
    }


def get_agency_relationships(
    profile: Optional[str] = None, agency_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Aggregates all job postings and recruiter contacts grouped by staffing agencies."""
    conn = db.get_db(profile)
    try:
        jobs = [
            dict(r)
            for r in conn.execute("SELECT * FROM jobs ORDER BY company ASC").fetchall()
        ]
        contacts = [dict(r) for r in conn.execute("SELECT * FROM contacts").fetchall()]
        apps = [
            dict(r) for r in conn.execute("SELECT * FROM application_log").fetchall()
        ]
    finally:
        conn.close()

    contacts_by_company = {}
    for c in contacts:
        comp_key = (c["company"] or "").lower().strip()
        contacts_by_company.setdefault(comp_key, []).append(c)

    apps_by_company = {}
    for a in apps:
        comp_key = (a["company"] or "").lower().strip()
        apps_by_company.setdefault(comp_key, []).append(a)

    # Compile regex pattern for agencies
    agency_re = re.compile("|".join(STAFFING_AGENCY_PATTERNS), re.IGNORECASE)

    agency_map: Dict[str, Dict[str, Any]] = {}

    for j in jobs:
        company = (j.get("company") or "Unknown").strip()
        comp_lower = company.lower()

        is_agency = bool(agency_re.search(comp_lower))
        if not is_agency:
            continue

        if agency_filter and agency_filter.lower() not in comp_lower:
            continue

        if comp_lower not in agency_map:
            agency_map[comp_lower] = {
                "agency_name": company,
                "total_roles": 0,
                "roles": [],
                "statuses": {},
                "scores": [],
                "contacts": contacts_by_company.get(comp_lower, []),
                "applications": apps_by_company.get(comp_lower, []),
            }

        data = agency_map[comp_lower]
        data["total_roles"] += 1
        st = (j.get("status") or "pending").lower()
        data["statuses"][st] = data["statuses"].get(st, 0) + 1
        score = j.get("final_score")
        if score is not None:
            data["scores"].append(score)

        data["roles"].append(
            {
                "id": j["id"],
                "title": j["title"],
                "status": st,
                "score": score,
                "created_at": j.get("created_at") or "",
            }
        )

    results = []
    for comp_lower, data in agency_map.items():
        scores = data["scores"]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        ghost_count = data["statuses"].get("expired", 0) + data["statuses"].get(
            "discarded", 0
        )
        ghost_rate = (
            (ghost_count / data["total_roles"] * 100.0)
            if data["total_roles"] > 0
            else 0.0
        )

        results.append(
            {
                "agency_name": data["agency_name"],
                "total_roles": data["total_roles"],
                "avg_score": avg_score,
                "ghost_rate": ghost_rate,
                "statuses": data["statuses"],
                "roles": sorted(
                    data["roles"], key=lambda x: x.get("created_at", ""), reverse=True
                ),
                "contacts": data["contacts"],
                "applications_count": len(data["applications"]),
            }
        )

    results.sort(key=lambda x: x["total_roles"], reverse=True)
    return results


def render_application_timeline_terminal(timeline_data: Dict[str, Any]) -> None:
    """Renders a single-application interactive milestone ladder in terminal."""
    from rich.panel import Panel
    from rich.table import Table

    cli_art.console.print()
    cli_art.console.print(
        f"[{theme.BRAND}]✦ Application Lifecycle Timeline: [bold]{timeline_data['title']}[/bold] @ {timeline_data['company']}[/]"
    )
    cli_art.console.print(
        f"[{theme.MUTED}]Job ID: {timeline_data['job_id']} │ Location: {timeline_data['location']} │ Current Status: [{theme.SUCCESS}]{timeline_data['status'].upper()}[/{theme.SUCCESS}][/{theme.MUTED}]"
    )
    cli_art.console.print()

    milestones = timeline_data.get("milestones", [])
    first_dt = None
    if milestones:
        first_dt = _parse_timestamp(milestones[0]["timestamp"])

    ladder_lines = []
    for i, m in enumerate(milestones):
        dt = _parse_timestamp(m["timestamp"])
        delta_str = "+0.0d"
        if dt and first_dt:
            delta_days = (dt - first_dt).total_seconds() / 86400.0
            delta_str = f"+{delta_days:.1f}d"

        badge_color = theme.INFO
        if m["status_badge"] == "SUCCESS":
            badge_color = theme.SUCCESS
        elif m["status_badge"] == "WARNING":
            badge_color = theme.WARNING
        elif m["status_badge"] == "ERROR":
            badge_color = theme.ERROR

        connector = "│\n" if i < len(milestones) - 1 else ""
        node = f"[{badge_color}]● [bold]{m['event_type']}[/bold][/{badge_color}]  [{theme.MUTED}]({m['timestamp']}  |  {delta_str})[/{theme.MUTED}]\n  [{theme.BRAND}]↳ {m['title']}[/{theme.BRAND}]\n  [{theme.MUTED}]{m['detail']}[/{theme.MUTED}]\n{connector}"
        ladder_lines.append(node)

    cli_art.console.print(
        Panel(
            "".join(ladder_lines),
            title=f"[bold {theme.BRAND}]Lifecycle Progression Ladder[/bold {theme.BRAND}]",
            border_style=theme.BRAND,
            expand=False,
        )
    )

    contacts = timeline_data.get("contacts", [])
    if contacts:
        cli_art.console.print()
        tbl = Table(
            show_header=True,
            header_style=f"bold {theme.BRAND}",
            title="Associated Recruiter & Hiring Contacts",
            title_style=theme.BRAND_ACCENT,
            border_style=theme.BRAND,
        )
        tbl.add_column("Contact Name", style="bold")
        tbl.add_column("Title / Role", style="dim")
        tbl.add_column("Email")
        tbl.add_column("LinkedIn")
        for c in contacts:
            tbl.add_row(
                c["name"], c["title"], c["email"] or "N/A", c["linkedin"] or "N/A"
            )
        cli_art.console.print(tbl)
    cli_art.console.print()


def render_agency_view_terminal(agencies: List[Dict[str, Any]]) -> None:
    """Renders the multi-role agency relationship matrix in terminal."""
    from rich.panel import Panel
    from rich.table import Table

    if not agencies:
        cli_art.console.print(
            f"[{theme.WARNING}]No staffing agency relationships detected in database.[/{theme.WARNING}]"
        )
        return

    cli_art.console.print()
    cli_art.console.print(
        f"[{theme.BRAND}]✦ Multi-Role Agency Relationship Matrix ({len(agencies)} Staffing Agencies Detected)[/]"
    )
    cli_art.console.print()

    tbl = Table(
        show_header=True,
        header_style=f"bold {theme.BRAND}",
        title="[bold]Agency Pipeline & Ghost Rate Analysis[/bold]",
        title_style=theme.BRAND_ACCENT,
        border_style=theme.BRAND,
    )
    tbl.add_column("Agency Name", style="bold", width=26)
    tbl.add_column("Roles", justify="right", width=8)
    tbl.add_column("Avg Fit", justify="right", width=10)
    tbl.add_column("Ghost Rate", justify="right", width=12)
    tbl.add_column("Applied", justify="right", width=10)
    tbl.add_column("Status Breakdown", style="dim")

    for a in agencies:
        st_breakdown = ", ".join(f"{k}:{v}" for k, v in a["statuses"].items())
        ghost_color = (
            theme.SUCCESS
            if a["ghost_rate"] < 25
            else (theme.WARNING if a["ghost_rate"] < 60 else theme.ERROR)
        )
        tbl.add_row(
            a["agency_name"],
            str(a["total_roles"]),
            f"{a['avg_score']:.1f}%",
            f"[{ghost_color}]{a['ghost_rate']:.1f}%[/{ghost_color}]",
            str(a["applications_count"]),
            st_breakdown,
        )

    cli_art.console.print(tbl)
    cli_art.console.print()
