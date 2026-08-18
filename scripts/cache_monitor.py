"""
cache_monitor.py -- Explicit Context Caching Token Efficiency & Cost Monitor.

Tracks prompt token caching performance, hit rates, and estimated cost savings
for LLM calls with static rules/system prompt prefix caching.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def calculate_cache_efficiency(
    total_prompt_tokens: int,
    cached_prompt_tokens: int,
    price_per_million_cached: float = 0.075,
    price_per_million_uncached: float = 0.30,
) -> Dict[str, Any]:
    """
    Calculates cache hit percentage and estimated financial savings.
    Default pricing based on Gemini 2.5 Flash / Flash-Lite cached vs standard rates.
    """
    if total_prompt_tokens <= 0:
        return {
            "total_prompt_tokens": 0,
            "cached_prompt_tokens": 0,
            "cache_hit_rate": 0.0,
            "uncached_cost_usd": 0.0,
            "actual_cost_usd": 0.0,
            "savings_usd": 0.0,
            "savings_percentage": 0.0,
        }

    uncached_tokens = max(0, total_prompt_tokens - cached_prompt_tokens)
    hit_rate = (cached_prompt_tokens / total_prompt_tokens) * 100.0

    # Theoretical cost if nothing was cached
    full_uncached_cost = (
        total_prompt_tokens / 1_000_000.0
    ) * price_per_million_uncached

    # Actual cost with cache discount
    actual_cost = (cached_prompt_tokens / 1_000_000.0) * price_per_million_cached + (
        uncached_tokens / 1_000_000.0
    ) * price_per_million_uncached
    savings = max(0.0, full_uncached_cost - actual_cost)
    savings_pct = (
        (savings / full_uncached_cost * 100.0) if full_uncached_cost > 0 else 0.0
    )

    return {
        "total_prompt_tokens": total_prompt_tokens,
        "cached_prompt_tokens": cached_prompt_tokens,
        "cache_hit_rate": round(hit_rate, 2),
        "uncached_cost_usd": round(full_uncached_cost, 6),
        "actual_cost_usd": round(actual_cost, 6),
        "savings_usd": round(savings, 6),
        "savings_percentage": round(savings_pct, 2),
    }


def format_cache_report(stats: Dict[str, Any]) -> str:
    """Formats human-readable terminal output for token cache statistics."""
    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        "║          GEMINI CONTEXT CACHE EFFICIENCY MONITOR         ║",
        "╠══════════════════════════════════════════════════════════╣",
        f"║  Total Prompt Tokens:     {stats['total_prompt_tokens']:>12,}           ║",
        f"║  Cached Prompt Tokens:    {stats['cached_prompt_tokens']:>12,}           ║",
        f"║  Cache Hit Rate:          {stats['cache_hit_rate']:>11.1f}%           ║",
        "╠══════════════════════════════════════════════════════════╣",
        f"║  Standard Cost (Uncached): ${stats['uncached_cost_usd']:>10.4f}           ║",
        f"║  Actual Effective Cost:    ${stats['actual_cost_usd']:>10.4f}           ║",
        f"║  Total Savings:            ${stats['savings_usd']:>10.4f} ({stats['savings_percentage']:>4.1f}%)   ║",
        "╚══════════════════════════════════════════════════════════╝",
    ]
    return "\n".join(lines)


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER CONTEXT CACHE & TOKEN MONITOR\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    sample_stats = calculate_cache_efficiency(
        total_prompt_tokens=150000,
        cached_prompt_tokens=100000,
    )
    print(format_cache_report(sample_stats))
    print("")


if __name__ == "__main__":
    main()
