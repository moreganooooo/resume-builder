"""Salary Negotiation & Counter-Offer Strategy Tree Module.

Generates market-calibrated counter-offer decision trees, negotiation email scripts,
and leverage playbooks for job offers.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def build_negotiation_strategy(
    offer_base: int,
    target_base: int,
    company: str,
    role: str,
    equity: Optional[int] = 0,
    competing_offers: Optional[int] = 0,
) -> Dict[str, Any]:
    """Calculates negotiation leverage and counter-offer targets."""
    delta = target_base - offer_base
    pct_gap = (delta / offer_base * 100.0) if offer_base > 0 else 0.0

    if pct_gap <= 0:
        recommended_counter = int(target_base * 1.05)
        strategy = "Strong Position: Offer meets base target. Counter on equity, signing bonus, or title advancement."
    elif pct_gap <= 15:
        recommended_counter = target_base + int(delta * 0.25)
        strategy = "Close Gap: Standard negotiation window. Request target base while anchoring with quantified market data."
    else:
        recommended_counter = target_base
        strategy = "Substantial Gap: High-leverage negotiation required. Anchor firmly to target base or bridge with guaranteed first-year signing bonus."

    if competing_offers and competing_offers > 0:
        strategy += f" Leveraged by {competing_offers} competing active process(es)."

    # Draft counter email
    email_script = (
        f"Dear Hiring Team at {company},\n\n"
        f"Thank you so much for extending the offer to join {company} as {role}. "
        f"I am genuinely thrilled about the team's mission and the impact we can make together.\n\n"
        f"Based on my recent market benchmarks, scope of leadership, and the immediate value I will bring "
        f"to the organization, I would be enthusiastic to sign immediately if we can align on a base compensation of "
        f"${recommended_counter:,}.\n\n"
        f"I look forward to discussing how we can make this work!\n\n"
        f"Best regards,\n[Candidate Name]"
    )

    return {
        "company": company,
        "role": role,
        "initial_offer": offer_base,
        "target_base": target_base,
        "recommended_counter": recommended_counter,
        "equity": equity,
        "strategy": strategy,
        "email_script": email_script,
    }


def generate_negotiation_guide_markdown(strategy_data: Dict[str, Any]) -> str:
    """Renders a complete negotiation guide in Markdown format."""
    lines = [
        f"# ▣ Compensation Negotiation Playbook: {strategy_data['role']} @ {strategy_data['company']}",
        "",
        "## ▤ 1. Compensation Breakdown & Targets",
        f"- **Initial Offer Base:** `${strategy_data['initial_offer']:,}`",
        f"- **Candidate Target Base:** `${strategy_data['target_base']:,}`",
        f"- **Recommended Counter-Anchor:** `${strategy_data['recommended_counter']:,}`",
        "",
        "## ⌖ 2. Strategic Posture & Plan",
        f"> {strategy_data['strategy']}",
        "",
        "## ✉ 3. Ready-to-Send Counter-Offer Email Script",
        "```text",
        strategy_data["email_script"],
        "```",
        "",
    ]
    return "\n".join(lines)


def write_negotiation_playbook(strategy_data: Dict[str, Any], output_path: str) -> str:
    """Writes negotiation playbook markdown file to disk."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    content = generate_negotiation_guide_markdown(strategy_data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER SALARY NEGOTIATION PLAYBOOK ENGINE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    sample = build_negotiation_strategy(
        offer_base=160000,
        target_base=180000,
        company="Example Corp",
        role="Senior Software Engineer",
        equity=50000,
        competing_offers=1,
    )
    print(f"  \033[1mRole:\033[0m {sample['role']} @ {sample['company']}")
    print(
        f"  \033[1mInitial Offer:\033[0m \033[38;2;255;123;153m${sample['initial_offer']:,}\033[0m"
    )
    print(
        f"  \033[1mTarget Base:\033[0m   \033[38;2;0;164;255m${sample['target_base']:,}\033[0m"
    )
    print(
        f"  \033[1mCounter Anchor:\033[0m\033[1m\033[38;2;18;199;143m ${sample['recommended_counter']:,}\033[0m"
    )
    print(
        f"  \033[1mStrategy:\033[0m       \033[38;2;245;239;52m{sample['strategy']}\033[0m\n"
    )


if __name__ == "__main__":
    main()
