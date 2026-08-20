"""
coverletter_calibration.py — Seniority & Company Size Calibration Engine.

Determines target word budget, tone, paragraph structure, and strategic focus
for cover letters based on role seniority and company operating scale.
"""

from __future__ import annotations

import re
from typing import Any, Dict


def detect_role_seniority(title: str, jd_text: str = "") -> str:
    """
    Classifies seniority tier into 'executive', 'lead', 'senior', or 'standard'.
    """
    text = f"{title} {jd_text}".lower()

    if re.search(
        r"\b(vp|vice president|c-level|cto|cpo|head of|director|principal)\b", text
    ):
        return "executive"
    if re.search(r"\b(lead|staff|architect|manager)\b", text):
        return "lead"
    if re.search(r"\b(senior|sr\b|experienced)\b", text):
        return "senior"
    return "standard"


def detect_company_scale(company: str, jd_text: str = "") -> str:
    """
    Classifies company operating scale into 'startup', 'growth', or 'enterprise'.
    """
    text = f"{company} {jd_text}".lower()

    if re.search(
        r"\b(seed|series a|series b|early-stage|fast-growing startup|stealth)\b", text
    ):
        return "startup"
    if re.search(
        r"\b(fortune 500|global enterprise|multinational|public company|nasdaq|nyse)\b",
        text,
    ):
        return "enterprise"
    return "growth"


def get_calibration_parameters(
    title: str, company: str, jd_text: str = ""
) -> Dict[str, Any]:
    """
    Returns calibrated parameters for cover letter generation:
    - target_word_count: int
    - max_word_count: int
    - recommended_paragraphs: int
    - tone_archetype: str
    - focal_points: list of str
    """
    seniority = detect_role_seniority(title, jd_text)
    scale = detect_company_scale(company, jd_text)

    if seniority == "executive":
        return {
            "seniority": seniority,
            "scale": scale,
            "target_word_count": 180,
            "max_word_count": 220,
            "recommended_paragraphs": 2,
            "tone_archetype": "Strategic, executive peer-to-peer, high-leverage vision",
            "focal_points": [
                "Organizational transformation",
                "Business outcomes and revenue/efficiency growth",
                "Executive alignment and team scaling",
            ],
        }
    if seniority in {"lead", "senior"}:
        return {
            "seniority": seniority,
            "scale": scale,
            "target_word_count": 260,
            "max_word_count": 320,
            "recommended_paragraphs": 3,
            "tone_archetype": "High-impact technical leadership, problem-solving, craftsmanship",
            "focal_points": [
                "Architecture and system design",
                "Mentorship and velocity enhancement",
                "Proven delivery on complex initiatives",
            ],
        }
    return {
        "seniority": seniority,
        "scale": scale,
        "target_word_count": 220,
        "max_word_count": 280,
        "recommended_paragraphs": 3,
        "tone_archetype": "Energized, outcome-focused, proactive",
        "focal_points": [
            "Execution velocity and adaptability",
            "Strong fundamentals and tooling mastery",
            "Collaborative culture fit",
        ],
    }


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER COVER LETTER CALIBRATION ENGINE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    sample = get_calibration_parameters("Director of Engineering", "Stripe")
    print(f"  \033[1mRole / Company:\033[0m Director of Engineering @ Stripe")
    print(
        f"  \033[1mSeniority Tier:\033[0m \033[1m\033[38;2;255;96;255m{sample['seniority'].upper()}\033[0m"
    )
    print(
        f"  \033[1mTarget Length:\033[0m  \033[1m\033[38;2;18;199;143m{sample['target_word_count']} words\033[0m (max {sample['max_word_count']}) in {sample['recommended_paragraphs']} paragraphs"
    )
    print(
        f"  \033[1mTone Strategy:\033[0m  \033[38;2;0;164;255m{sample['tone_archetype']}\033[0m\n"
    )


if __name__ == "__main__":
    main()
