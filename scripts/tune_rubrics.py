#!/usr/bin/env python3
"""
tune_rubrics.py — Closed-loop telemetry and dynamic rubric tuning.

Correlates real-world interview progression/outcomes tracked in applications.md
with the resume composite scores and evaluation metadata under jds/. Calculates
data-driven scoring thresholds and automatically updates ats_match.yaml.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

# Secure sibling imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.append(str(SCRIPT_DIR))

import cli_art
import theme


def load_applications(md_path: Path) -> list:
    """Parses applications.md into structured dicts."""
    apps = []
    if not md_path.is_file():
        return apps
    try:
        with md_path.open("r", encoding="utf-8") as f:
            lines = [ln.rstrip() for ln in f.readlines()]
    except Exception as e:
        cli_art.cli_warning(f"Could not read {md_path}: {e}")
        return apps

    # Skip header lines
    for line in lines[2:]:
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 10:
            continue
        # Columns: #, Date, Company, Role, Score, Status, PDF, Link, Report, Notes
        _, date, company, role, score, status, _, _, _, _ = parts
        
        # Clean score (e.g., '4.50/5' -> 4.50)
        score_val = None
        score_clean = score.split("/")[0].strip()
        if score_clean and score_clean != "NA" and score_clean != "—":
            try:
                score_val = float(score_clean)
            except ValueError:
                pass

        apps.append({
            "date": date,
            "company": company,
            "role": role,
            "score": score_val,
            "status": status,
        })
    return apps


def find_jd_payload(jds_dir: Path, company: str, role: str) -> dict | None:
    """Finds the corresponding job JSON in jds/ based on company and role match."""
    # Normalize names to lowercase alphanumeric for robust matching
    def norm(s):
        return re.sub(r"\W+", "", s.lower())

    comp_norm = norm(company)
    role_norm = norm(role)

    for jf in jds_dir.glob("*.json"):
        try:
            with jf.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}  # safe_load handles JSON too
            c = norm(data.get("company", ""))
            r = norm(data.get("role", ""))
            if (comp_norm in c or c in comp_norm) and (role_norm in r or r in role_norm):
                return data
        except Exception:
            continue
    return None


def calculate_optimal_thresholds(apps: list) -> dict:
    """
    Computes statistical correlation and recommended thresholds.
    Maps 5-point composite scores back to 100-point ATS scales (score * 20).
    """
    success_statuses = {"interview", "offer", "active", "negotiation"}
    unsuccess_statuses = {"rejected", "archived", "withdrawn"}

    success_scores = []
    unsuccess_scores = []

    for app in apps:
        if app["score"] is None:
            continue
        status_low = app["status"].lower()
        if status_low in success_statuses:
            success_scores.append(app["score"] * 20.0)  # Convert 5-point scale to 100-point scale
        elif status_low in unsuccess_statuses:
            unsuccess_scores.append(app["score"] * 20.0)

    # Defaults from ats_match.yaml if no outcome data is present yet
    recommendations = {
        "excellent_match": 85,
        "good_match": 70,
        "weak_match": 50,
        "success_count": len(success_scores),
        "unsuccess_count": len(unsuccess_scores),
    }

    if success_scores:
        s_avg = sum(success_scores) / len(success_scores)
        # Excellent is centered slightly above average success to represent a premium candidate tier
        recommendations["excellent_match"] = int(min(max(s_avg + 2, 60), 98))
    
    if unsuccess_scores:
        u_avg = sum(unsuccess_scores) / len(unsuccess_scores)
        # Good match threshold sits between successful and unsuccessful average
        if success_scores:
            s_avg = sum(success_scores) / len(success_scores)
            recommendations["good_match"] = int(min(max((s_avg + u_avg) / 2.0, 50), 90))
        else:
            recommendations["good_match"] = int(min(max(u_avg + 5, 45), 85))
        
        recommendations["weak_match"] = int(min(max(u_avg - 5, 30), 75))

    return recommendations


def update_ats_match_yaml(yaml_path: Path, thresholds: dict) -> bool:
    """Updates thresholds in ats_match.yaml while preserving formatting and comments."""
    if not yaml_path.is_file():
        cli_art.console.print(f"  {cli_art.ERROR} {yaml_path} not found.")
        return False
    try:
        content = yaml_path.read_text(encoding="utf-8")
        
        # Regex replacement to preserve all surrounding whitespace, structures, and comments
        patterns = [
            (r"(excellent_match:\s*)\d+", f"\\g<1>{thresholds['excellent_match']}"),
            (r"(good_match:\s*)\d+", f"\\g<1>{thresholds['good_match']}"),
            (r"(weak_match:\s*)\d+", f"\\g<1>{thresholds['weak_match']}"),
        ]
        
        updated = content
        for pat, repl in patterns:
            updated = re.sub(pat, repl, updated)

        if updated == content:
            cli_art.console.print(f"  {theme.colorize_icon('info')} No threshold adjustments needed in config.")
            return True

        # Atomic write to prevent zero-byte truncation
        tmp_path = yaml_path.with_suffix(".tmp")
        tmp_path.write_text(updated, encoding="utf-8")
        os.replace(tmp_path, yaml_path)
        cli_art.console.print(f"  {theme.colorize_icon('success')} Successfully auto-tuned {yaml_path.name} based on outcomes!")
        return True
    except Exception as e:
        cli_art.console.print(f"  {cli_art.ERROR} Failed to update yaml file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Closed-loop telemetry and dynamic rubric tuning.")
    parser.add_argument("--profile", default="morgan", help="Profile to tune rubrics for")
    parser.add_argument("--apply", action="store_true", help="Apply tuned thresholds directly to ats_match.yaml")
    args = parser.parse_args()

    profile = args.profile
    md_path = PROJECT_ROOT / "data" / profile / "applications.md"
    jds_dir = PROJECT_ROOT / "jds" / profile
    yaml_path = PROJECT_ROOT / "resume-engine" / "scoring" / "ats_match.yaml"

    cli_art.console.print(f"\n[bold]{theme.colorize_icon('sync')} Running Closed-Loop Telemetry Tuning for: [dim]{profile}[/dim][/bold]\n")

    if not md_path.is_file():
        cli_art.console.print(f"  {cli_art.WARNING} applications.md not found for profile: {profile}. No outcome telemetry available.")
        sys.exit(0)

    apps = load_applications(md_path)
    if not apps:
        cli_art.console.print(f"  {cli_art.WARNING} No application entries found in applications.md.")
        sys.exit(0)

    rec = calculate_optimal_thresholds(apps)

    cli_art.console.print(f"  [bold]Telemetry Statistics:[/bold]")
    cli_art.console.print(f"    - Total Logged Applications: {len(apps)}")
    cli_art.console.print(f"    - Progression to Interview+ (Success): {rec['success_count']} entries")
    cli_art.console.print(f"    - Rejections/Archived (Unsuccess): {rec['unsuccess_count']} entries")

    # Display comparison
    cli_art.console.print(f"\n  [bold]Recommended vs. Current Thresholds:[/bold]")
    
    # Read current values
    current_exc, current_good, current_weak = 85, 70, 50
    if yaml_path.is_file():
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
                t = y.get("thresholds", {})
                current_exc = t.get("excellent_match", current_exc)
                current_good = t.get("good_match", current_good)
                current_weak = t.get("weak_match", current_weak)
        except Exception:
            pass

    cli_art.console.print(f"    - [bold]Excellent Match:[/bold] {current_exc} → [green]{rec['excellent_match']}[/green] (Ready to apply)")
    cli_art.console.print(f"    - [bold]Good Match:[/bold]      {current_good} → [green]{rec['good_match']}[/green] (Needs tailoring)")
    cli_art.console.print(f"    - [bold]Weak Match:[/bold]      {current_weak} → [green]{rec['weak_match']}[/green] (Missing competencies)")

    if args.apply:
        cli_art.console.print(f"\n  [bold]Applying thresholds...[/bold]")
        update_ats_match_yaml(yaml_path, rec)
    else:
        cli_art.console.print(f"\n  [dim]Run with [bold]--apply[/bold] to write these data-driven recommendations back to {yaml_path.name}.[/dim]\n")


if __name__ == "__main__":
    main()
