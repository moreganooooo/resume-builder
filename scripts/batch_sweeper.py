"""
batch_sweeper.py — High-Throughput Async Batch Sweeper.

Sweeps pending jobs in data.db through prefilters and zero-cost heuristics
(salary extraction, ghost job scoring, dealbreakers) in fast concurrent batches.
"""

from __future__ import annotations

import concurrent.futures
import os
import sqlite3
from typing import Any, Dict, List

import db
import job_eval_heuristics
import prefilter
import profile_paths


def sweep_job_record(
    job: Dict[str, Any], filters: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Evaluates a single job record through zero-cost pre-flight gates."""
    raw_text = job.get("raw_text") or job.get("description") or ""
    title = job.get("title") or ""
    company = job.get("company") or ""

    # Gate 1: Deal-breaker pre-filter
    passed, reasons = prefilter.evaluate_preflight_gate(raw_text, deal_breakers=filters)

    # Gate 2: Fast heuristics
    salary_data = job_eval_heuristics.extract_salary_range(raw_text)
    ghost_prob = job_eval_heuristics.compute_ghost_job_probability(
        raw_text, posting_age_days=10
    )
    visa_sponsorship = job_eval_heuristics.classify_visa_sponsorship(raw_text)

    status = "skip" if not passed else "ready_for_eval"

    return {
        "id": job.get("id"),
        "title": title,
        "company": company,
        "passed_prefilter": passed,
        "deal_breakers": reasons,
        "salary_range": salary_data,
        "ghost_probability": ghost_prob,
        "visa_sponsored": 1 if visa_sponsorship == "available" else 0,
        "status": status,
    }


def sweep_pending_jobs(
    jobs: List[Dict[str, Any]],
    max_workers: int = 4,
    filters: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Runs concurrent zero-cost sweeping over a list of job dicts."""
    if not jobs:
        return []

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(sweep_job_record, job, filters) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return results


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER HIGH-THROUGHPUT BATCH SWEEPER\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(
        "  \033[1m\033[38;2;0;164;255mEngine:\033[0m \033[1m\033[38;2;18;199;143mConcurrent Multi-Threaded Zero-Cost Gate Sweeper\033[0m"
    )
    print(
        "  \033[38;2;163;163;163mEvaluates blacklist, dealbreakers, and ghost job patterns before LLM calls.\033[0m\n"
    )


if __name__ == "__main__":
    main()
