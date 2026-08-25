"""
platform_analytics.py — Source-Platform, Company Concentration, and Scatter Analytics.

Computes:
1. Source-platform breakdown (which job boards/ATS produce high-scoring roles)
2. Company frequency / concentration (surfacing staffing agencies & top employers)
3. Score-vs-coverage scatter (mapping high-fit / low-coverage bullet bank gaps)
4. Bullet-bank coverage heatmap (category supply vs JD skill demand)
"""

import json
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional

import db
import profile_paths

# Known staffing and recruitment agencies
STAFFING_AGENCY_PATTERNS = [
    r"\bcybercoders\b",
    r"\bapex\s+systems\b",
    r"\bapex\s+staffing\b",
    r"\bteksystems\b",
    r"\binsight\s+global\b",
    r"\brobert\s+half\b",
    r"\baddison\s+group\b",
    r"\bharnham\b",
    r"\bkforce\b",
    r"\bmodis\b",
    r"\brandstad\b",
    r"\ballegis\b",
    r"\bkelly\s+services\b",
    r"\bmanpower\b",
    r"\baerotek\b",
    r"\bbeacon\s+hill\b",
    r"\blucas\s+group\b",
    r"\bmotion\s+recruitment\b",
    r"\bjudge\s+group\b",
    r"\bcreative\s+circle\b",
    r"\bmondo\b",
    r"\bjobot\b",
    r"\bstaffing\b",
    r"\brecruiting\b",
    r"\brecruitment\b",
    r"\btalent\s+solutions\b",
    r"\bsearch\s+partners\b",
    r"\bheadhunters\b",
    r"\bpersonnel\b",
]

PLATFORM_CANONICAL_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "jobright": "Jobright",
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "workday": "Workday",
    "remoteok": "RemoteOK",
    "himalayas": "Himalayas",
    "wellfound": "Wellfound",
    "ziprecruiter": "ZipRecruiter",
    "glassdoor": "Glassdoor",
    "adzuna": "Adzuna",
    "jooble": "Jooble",
    "smartrecruiters": "SmartRecruiters",
    "icims": "iCIMS",
}


def normalize_platform_name(raw_platform: Optional[str]) -> str:
    """Normalizes raw platform keys to user-friendly canonical names."""
    if not raw_platform or not raw_platform.strip():
        return "Direct / Unknown"

    cleaned = raw_platform.strip().lower()
    if cleaned.startswith("custom_"):
        return cleaned.replace("custom_", "").replace("_", " ").title()

    return PLATFORM_CANONICAL_NAMES.get(cleaned, cleaned.replace("_", " ").title())


def is_staffing_agency(company_name: str) -> bool:
    """Detects whether a company name matches known staffing agencies or recruiter patterns."""
    if not company_name:
        return False
    lower = company_name.lower()
    return any(re.search(pat, lower) for pat in STAFFING_AGENCY_PATTERNS)


def _get_active_conn(
    profile: Optional[str] = None, conn: Optional[sqlite3.Connection] = None
):
    if conn is not None:
        return conn, False
    return db.get_db(profile), True


def compute_source_platform_breakdown(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Aggregates jobs by source platform with role counts, average scores,

    score-tier distributions, and top matching roles.
    """
    c, should_close = _get_active_conn(profile, conn)
    try:
        rows = c.execute(
            """
            SELECT id, title, company, status, capability_score, recruiter_score, final_score, metadata_json
            FROM jobs
            """
        ).fetchall()

        if not rows:
            return []

        platforms: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "platform": "",
                "total_roles": 0,
                "evaluated_roles": 0,
                "scores": [],
                "bands": {
                    "tier_4_5_plus": 0,
                    "tier_4_0_to_4_4": 0,
                    "tier_3_5_to_3_9": 0,
                    "tier_sub_3_5": 0,
                },
                "top_role": None,
            }
        )

        for row in rows:
            meta = {}
            if row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                except Exception:
                    meta = {}

            raw_platform = (
                meta.get("source_platform")
                or meta.get("platform")
                or meta.get("source")
                or meta.get("board")
                or ""
            )
            platform_name = normalize_platform_name(raw_platform)

            entry = platforms[platform_name]
            entry["platform"] = platform_name
            entry["total_roles"] += 1

            # Extract score
            score = row["final_score"]
            if score is None and isinstance(meta.get("_evaluation"), dict):
                score = meta["_evaluation"].get("composite_score")

            if score is not None:
                try:
                    s_val = float(score)
                    entry["scores"].append(s_val)
                    entry["evaluated_roles"] += 1

                    if s_val >= 4.5:
                        entry["bands"]["tier_4_5_plus"] += 1
                    elif s_val >= 4.0:
                        entry["bands"]["tier_4_0_to_4_4"] += 1
                    elif s_val >= 3.5:
                        entry["bands"]["tier_3_5_to_3_9"] += 1
                    else:
                        entry["bands"]["tier_sub_3_5"] += 1

                    if entry["top_role"] is None or s_val > entry["top_role"]["score"]:
                        entry["top_role"] = {
                            "id": row["id"],
                            "title": row["title"],
                            "company": row["company"],
                            "score": round(s_val, 2),
                        }
                except (ValueError, TypeError):
                    pass

        result = []
        for p_name, data in platforms.items():
            avg = (
                round(sum(data["scores"]) / len(data["scores"]), 2)
                if data["scores"]
                else 0.0
            )
            result.append(
                {
                    "platform": p_name,
                    "total_roles": data["total_roles"],
                    "evaluated_roles": data["evaluated_roles"],
                    "avg_score": avg,
                    "bands": data["bands"],
                    "top_role": data["top_role"],
                }
            )

        # Sort primarily by evaluated_roles / total_roles descending, then avg_score
        result.sort(key=lambda x: (x["total_roles"], x["avg_score"]), reverse=True)
        return result
    finally:
        if should_close:
            c.close()


def compute_company_concentration(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    top_n: int = 25,
) -> List[Dict[str, Any]]:
    """Aggregates jobs by employer, identifying company frequency,

    average fit score, and flagging staffing agencies.
    """
    c, should_close = _get_active_conn(profile, conn)
    try:
        rows = c.execute(
            """
            SELECT id, title, company, status, capability_score, recruiter_score, final_score, metadata_json
            FROM jobs
            """
        ).fetchall()

        if not rows:
            return []

        companies: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "company": "",
                "total_roles": 0,
                "evaluated_roles": 0,
                "scores": [],
                "roles": [],
            }
        )

        for row in rows:
            raw_comp = row["company"] or "Unknown Company"
            comp_name = raw_comp.strip()

            entry = companies[comp_name]
            entry["company"] = comp_name
            entry["total_roles"] += 1
            entry["roles"].append(row["title"])

            score = row["final_score"]
            if score is None and row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                    if isinstance(meta.get("_evaluation"), dict):
                        score = meta["_evaluation"].get("composite_score")
                except Exception:
                    pass

            if score is not None:
                try:
                    s_val = float(score)
                    entry["scores"].append(s_val)
                    entry["evaluated_roles"] += 1
                except (ValueError, TypeError):
                    pass

        result = []
        for c_name, data in companies.items():
            avg = (
                round(sum(data["scores"]) / len(data["scores"]), 2)
                if data["scores"]
                else 0.0
            )
            is_agency = is_staffing_agency(c_name)
            result.append(
                {
                    "company": c_name,
                    "total_roles": data["total_roles"],
                    "evaluated_roles": data["evaluated_roles"],
                    "avg_score": avg,
                    "is_agency": is_agency,
                    "roles": data["roles"][:5],  # top 5 sample roles
                }
            )

        result.sort(key=lambda x: (x["total_roles"], x["avg_score"]), reverse=True)
        return result[:top_n]
    finally:
        if should_close:
            c.close()


def compute_score_vs_coverage_scatter(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Extracts (composite_score, coverage_score) coordinate points for evaluated roles

    and classifies each role into actionable quadrants:
    - high_score_low_coverage: High Fit (>=4.0), Low Coverage (<70%) -> "Write Bullets Next"
    - high_score_high_coverage: High Fit (>=4.0), High Coverage (>=70%) -> "Ready to Apply"
    - low_score_high_coverage: Lower Fit (<4.0), High Coverage (>=70%) -> "Over-Covered"
    - low_score_low_coverage: Lower Fit (<4.0), Low Coverage (<70%) -> "Low Priority"
    """
    c, should_close = _get_active_conn(profile, conn)
    try:
        rows = c.execute(
            """
            SELECT id, title, company, status, final_score, metadata_json
            FROM jobs
            """
        ).fetchall()

        points = []
        quadrants: Dict[str, List[Dict[str, Any]]] = {
            "high_score_low_coverage": [],
            "high_score_high_coverage": [],
            "low_score_high_coverage": [],
            "low_score_low_coverage": [],
        }

        for row in rows:
            meta = {}
            if row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                except Exception:
                    meta = {}

            score = row["final_score"]
            if score is None and isinstance(meta.get("_evaluation"), dict):
                score = meta["_evaluation"].get("composite_score")

            cov_score = None
            if "_coverage" in meta and isinstance(meta["_coverage"], dict):
                cov_score = meta["_coverage"].get("coverage_score") or meta[
                    "_coverage"
                ].get("total_pct")
            elif "coverage" in meta and isinstance(meta["coverage"], dict):
                cov_score = meta["coverage"].get("percentage") or meta["coverage"].get(
                    "score"
                )
            elif "coverage_score" in meta:
                cov_score = meta["coverage_score"]
            elif isinstance(meta.get("_evaluation"), dict):
                ev = meta["_evaluation"]
                iodds = ev.get("interview_odds_subscores", {})
                if "evidence_match" in iodds and iodds["evidence_match"] is not None:
                    try:
                        # Convert 1-5 evidence match subscore to percentage (20% - 100%)
                        cov_score = (float(iodds["evidence_match"]) / 5.0) * 100.0
                    except (ValueError, TypeError):
                        pass

            if score is None or cov_score is None:
                continue

            try:
                s_val = round(float(score), 2)
                c_val = round(float(cov_score), 1)

                if s_val >= 4.0 and c_val < 70.0:
                    quadrant = "high_score_low_coverage"
                elif s_val >= 4.0 and c_val >= 70.0:
                    quadrant = "high_score_high_coverage"
                elif s_val < 4.0 and c_val >= 70.0:
                    quadrant = "low_score_high_coverage"
                else:
                    quadrant = "low_score_low_coverage"

                point = {
                    "id": row["id"],
                    "title": row["title"],
                    "company": row["company"],
                    "score": s_val,
                    "coverage": c_val,
                    "quadrant": quadrant,
                }
                points.append(point)
                quadrants[quadrant].append(point)
            except (ValueError, TypeError):
                continue

        return {
            "points": points,
            "quadrants": quadrants,
            "total_points": len(points),
        }
    finally:
        if should_close:
            c.close()


def compute_bullet_bank_heatmap(
    profile: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Cross-analyzes bullet bank categories against skill demand in evaluated jobs."""
    import re

    c, should_close = _get_active_conn(profile, conn)
    try:
        # 1. Bullet bank category counts from DB
        bb_rows = c.execute(
            """
            SELECT category, COUNT(*) as count
            FROM bullet_bank
            WHERE audit_status = 'CLEAN'
            GROUP BY category
            """
        ).fetchall()

        bullet_counts: Dict[str, int] = defaultdict(int)
        for r in bb_rows:
            cat = r["category"]
            if cat and cat != "Uncategorized":
                bullet_counts[cat.lower().strip()] += r["count"]

        # Fallback/enrich from bullet-bank-keepers.csv tags if DB is untagged
        kb_csv = os.path.join(profile_paths.kb_dir(profile), "bullet-bank-keepers.csv")
        if not bullet_counts and os.path.exists(kb_csv):
            try:
                import pandas as pd

                df = pd.read_csv(kb_csv)
                tag_col = (
                    "Tags"
                    if "Tags" in df.columns
                    else "tags" if "tags" in df.columns else None
                )
                if tag_col:
                    for tags in df[tag_col].dropna():
                        found = re.findall(r"\[(.*?)\]", str(tags))
                        for t in found:
                            bullet_counts[t.lower().strip()] += 1
            except Exception:
                pass

        if not bullet_counts and bb_rows:
            bullet_counts["Uncategorized"] = sum(r["count"] for r in bb_rows)

        # 2. Extract job demand across high-scoring jobs
        job_rows = c.execute(
            """
            SELECT id, title, final_score, metadata_json
            FROM jobs
            WHERE final_score >= 3.5 OR final_score IS NULL
            """
        ).fetchall()

        demand_counts: Dict[str, int] = defaultdict(int)
        tag_patterns = {
            "ops": r"\b(ops|operations|operational|workflow|systems|process)\b",
            "content": r"\b(content|copywriting|editorial|publishing|creator)\b",
            "mgmt": r"\b(manager|management|lead|director|head|leadership)\b",
            "brand": r"\b(brand|branding|creative|identity)\b",
            "email": r"\b(email|lifecycle|retention|crm|hubspot|marketo|klaviyo)\b",
            "generalist": r"\b(generalist|hybrid|cross-functional|growth)\b",
            "design": r"\b(design|figma|visual|ui|ux|graphic)\b",
            "writing": r"\b(writer|writing|author|technical writing|copywriter)\b",
            "enablement": r"\b(enablement|onboarding|training|coaching|sales enablement)\b",
        }

        for row in job_rows:
            if not row["metadata_json"]:
                continue
            try:
                meta = json.loads(row["metadata_json"])
                skills = meta.get("skills") or []
                if isinstance(skills, list):
                    for sk in skills:
                        name = (
                            (sk["name"] if isinstance(sk, dict) else str(sk))
                            .lower()
                            .strip()
                        )
                        demand_counts[name] += 1

                ev = meta.get("_evaluation", {})
                text = f"{row['title']} {ev.get('archetype', '')} {ev.get('why', '')}".lower()
                for tag, pattern in tag_patterns.items():
                    if re.search(pattern, text):
                        demand_counts[tag] += 1
            except Exception:
                pass

        categories = []
        all_keys = set(bullet_counts.keys()).union(set(demand_counts.keys()))
        for key in sorted(all_keys):
            supply = bullet_counts.get(key, 0)
            demand = demand_counts.get(key, 0)
            categories.append(
                {
                    "name": key,
                    "bullets_in_bank": supply,
                    "job_demand_count": demand,
                    "status": "surplus" if supply >= demand else "deficit",
                }
            )

        # Sort categories by job demand descending
        categories.sort(
            key=lambda x: (x["job_demand_count"], x["bullets_in_bank"]), reverse=True
        )

        return {
            "categories": categories,
            "total_bullets": sum(bullet_counts.values()),
            "total_demand_skills": len(demand_counts),
        }
    finally:
        if should_close:
            c.close()
