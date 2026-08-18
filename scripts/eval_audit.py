"""Evaluation Audit Trail Generator Module.

Generates human-readable, explainable scoring audit trails for job evaluations.
"""

from __future__ import annotations

import os
from typing import Any, Dict


def generate_evaluation_audit_markdown(
    job_data: Dict[str, Any], evaluation: Dict[str, Any]
) -> str:
    """Renders a comprehensive, explainable evaluation audit markdown report."""
    title = job_data.get("title", "Unknown Role")
    company = job_data.get("company", "Unknown Company")
    score = evaluation.get("composite_score", evaluation.get("score", "N/A"))
    tier = evaluation.get("tier", "N/A")
    odds = evaluation.get("interview_odds", evaluation.get("odds", "N/A"))

    capability_score = evaluation.get("capability_score", "N/A")
    recruiter_friction = evaluation.get("recruiter_friction", "N/A")

    pros = evaluation.get("pros", [])
    cons = evaluation.get("cons", [])
    missing_skills = evaluation.get("missing_skills", evaluation.get("skill_gaps", []))
    tailoring_tips = evaluation.get("tailoring_tips", [])

    lines = [
        f"# 🎯 Evaluation Audit Trail: {title} @ {company}",
        "",
        f"- **Composite Fit Score:** `{score}` / 100 ({tier})",
        f"- **Empirical Interview Odds:** `{odds}`",
        f"- **Functional Capability Sub-Score:** `{capability_score}` / 100",
        f"- **Recruiter Friction Index:** `{recruiter_friction}` / 100",
        "",
        "---",
        "",
        "## 💡 Scoring Rationale & Evidence",
        "",
        "### Key Alignments & Strengths",
    ]

    if pros:
        for p in pros:
            lines.append(f"- ✅ {p}")
    else:
        lines.append("- *No specific standout strengths recorded.*")

    lines.extend(["", "### Friction Points & Risk Factors"])
    if cons:
        for c in cons:
            lines.append(f"- ⚠️ {c}")
    else:
        lines.append("- *No significant friction points detected.*")

    lines.extend(["", "### Missing Skills & Keyword Gaps"])
    if missing_skills:
        for s in missing_skills:
            lines.append(f"- ❌ `{s}`")
    else:
        lines.append("- *No critical missing skills.*")

    if tailoring_tips:
        lines.extend(["", "## 🛠 Recommended Tailoring Strategy"])
        for tip in tailoring_tips:
            lines.append(f"1. {tip}")

    lines.append("")
    return "\n".join(lines)


def write_evaluation_audit(
    job_data: Dict[str, Any], evaluation: Dict[str, Any], output_path: str
) -> str:
    """Writes the evaluation audit trail markdown file to disk."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    content = generate_evaluation_audit_markdown(job_data, evaluation)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER EVALUATION AUDIT TRAIL ENGINE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(
        "  \033[1m\033[38;2;0;164;255mGenerates explainable audit logs across 4 score pillars:\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Composite Fit Score & Tier Classification\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Functional Capability & Recruiter Friction Indexes\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Missing Skills Breakdown & Tailoring Action Items\033[0m\n"
    )


if __name__ == "__main__":
    main()
