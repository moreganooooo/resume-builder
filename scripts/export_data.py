"""Data Lake Exporter Module.

Exports SQLite jobs and application history records to JSONL, CSV, and Parquet
formats for analytics and reporting.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


def fetch_all_jobs(
    conn_or_path: sqlite3.Connection | str,
) -> List[Dict[str, Any]]:
    """Fetches all jobs from SQLite database as list of dictionaries."""
    if isinstance(conn_or_path, str):
        if not os.path.exists(conn_or_path):
            return []
        conn = sqlite3.connect(conn_or_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        should_close = True
    else:
        conn = conn_or_path
        conn.row_factory = sqlite3.Row
        should_close = False

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        if should_close:
            conn.close()


def export_jobs_jsonl(jobs: List[Dict[str, Any]], output_path: str) -> str:
    """Exports list of jobs to a JSON Lines (.jsonl) file."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for job in jobs:
            f.write(json.dumps(job, default=str) + "\n")
    return output_path


def export_jobs_csv(jobs: List[Dict[str, Any]], output_path: str) -> str:
    """Exports list of jobs to a CSV file."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if not jobs:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return output_path

    fieldnames = list(jobs[0].keys())
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            writer.writerow(job)
    return output_path


def export_jobs_parquet(jobs: List[Dict[str, Any]], output_path: str) -> Optional[str]:
    """Exports list of jobs to Parquet format if pyarrow or duckdb is available."""
    if not jobs:
        return None
    try:
        import pandas as pd  # pylint: disable=import-outside-toplevel

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        df = pd.DataFrame(jobs)
        df.to_parquet(output_path, index=False)
        return output_path
    except ImportError:
        # Fallback to jsonl if pandas/pyarrow not installed in environment
        return None


def export_data_lake(
    conn_or_path: sqlite3.Connection | str, output_dir: str
) -> Dict[str, str]:
    """Exports database jobs into all supported data lake formats."""
    os.makedirs(output_dir, exist_ok=True)
    jobs = fetch_all_jobs(conn_or_path)

    results = {}
    jsonl_file = os.path.join(output_dir, "jobs_datalake.jsonl")
    csv_file = os.path.join(output_dir, "jobs_datalake.csv")

    export_jobs_jsonl(jobs, jsonl_file)
    results["jsonl"] = jsonl_file

    export_jobs_csv(jobs, csv_file)
    results["csv"] = csv_file

    parquet_file = os.path.join(output_dir, "jobs_datalake.parquet")
    pq_res = export_jobs_parquet(jobs, parquet_file)
    if pq_res:
        results["parquet"] = pq_res

    return results


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER MULTI-FORMAT DATA LAKE EXPORTER\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    db_path = os.path.join("output", "morgan", "data.db")
    if not os.path.exists(db_path):
        db_path = "data.db"
    out_dir = os.path.join("output", "morgan", "datalake")
    res = export_pipeline_datalake(db_path, out_dir)
    for fmt, path in res.items():
        print(
            f"  \033[1m\033[38;2;18;199;143m✓ {fmt.upper():<8}\033[0m \033[38;2;163;163;163m→\033[0m \033[38;2;0;164;255m{path}\033[0m"
        )
    print("")


if __name__ == "__main__":
    main()
