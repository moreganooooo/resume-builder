"""Interview Preparation & STAR Story Synthesizer Module.

Synthesizes bullet bank achievements and JD requirements into structured
STAR (Situation, Task, Action, Result) talking points and technical deep-dive dossiers.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


def synthesize_star_story(bullet_dict: Dict[str, Any]) -> Dict[str, str]:
    """Expands a single metric/bullet into a structured STAR interview story."""
    text = bullet_dict.get(
        "bullet", bullet_dict.get("final_bullet", bullet_dict.get("text", ""))
    )
    company = bullet_dict.get("company", "Company")
    metrics = bullet_dict.get("metrics", "")

    return {
        "title": f"Project at {company}",
        "situation": f"While serving at {company}, the organization needed to improve performance and operational efficiency.",
        "task": f"Took ownership of designing and executing the solution: {text}",
        "action": f"Led the technical implementation, collaborating with cross-functional stakeholders and standardizing best practices.",
        "result": f"Achieved measurable impact: {metrics or 'Successfully delivered on-time with zero regressions and improved team throughput.'}",
        "core_bullet": text,
    }


def generate_interview_prep_dossier(
    job_title: str,
    company: str,
    bullets: List[Dict[str, Any]],
    target_skills: List[str],
) -> str:
    """Renders a comprehensive interview prep guide in Markdown format."""
    lines = [
        f"# ◉ Interview Preparation Dossier: {job_title} @ {company}",
        "",
        "## ⌖ 1. Target Core Competencies & Skills",
    ]

    for skill in target_skills[:8]:
        lines.append(f"- ▸ **{skill}**")

    lines.extend(
        [
            "",
            "## ★ 2. Structured STAR Behavioral Stories (Situation-Task-Action-Result)",
            "",
        ]
    )

    for i, b in enumerate(bullets[:5], 1):
        star = synthesize_star_story(b)
        lines.extend(
            [
                f"### Story #{i}: {star['title']}",
                f"> **Summary:** *{star['core_bullet']}*",
                "",
                f"- **Situation:** {star['situation']}",
                f"- **Task:** {star['task']}",
                f"- **Action:** {star['action']}",
                f"- **Result:** {star['result']}",
                "",
            ]
        )

    lines.extend(
        [
            "## ✦ 3. High-Impact Reverse-Interview Questions for the Hiring Team",
            f"1. *'What are the most critical milestones you want this {job_title} to achieve in the first 90 days?'*",
            "2. *'How does your engineering team balance rapid feature delivery with architectural technical debt?'*",
            "3. *'What distinguishes someone who is merely good in this role from someone who is truly exceptional?'*",
            "",
        ]
    )

    return "\n".join(lines)


def write_interview_prep_file(
    job_title: str,
    company: str,
    bullets: List[Dict[str, Any]],
    target_skills: List[str],
    output_path: str,
) -> str:
    """Writes the interview prep dossier to disk."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    content = generate_interview_prep_dossier(
        job_title, company, bullets, target_skills
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER INTERVIEW PREP & STAR DOSSIER GENERATOR\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(
        "  \033[1m\033[38;2;0;164;255mGenerates structured talking points and behavioral stories:\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Situation-Task-Action-Result (STAR) Synthesizer\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Core Competency & Skill Gap Analysis\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Reverse-Interview Question Playbooks\033[0m\n"
    )


if __name__ == "__main__":
    main()
