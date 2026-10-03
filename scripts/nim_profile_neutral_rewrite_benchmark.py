#!/usr/bin/env python3
"""Profile-neutral, evidence-first NVIDIA rewrite benchmark.

Compares only the two demonstrated rewrite candidates:
  - NVIDIA Nemotron 3.5 Lightning 30B: thinking off, temperature 0.4
  - Meta Muse Glimmer 30B: reasoning off, temperature 0.95, top-p 1.0

It is read-only. It never changes the bullet bank, profile, JD files, or DB.
Every raw model result and every evidence/guard finding is saved under
scratch/nim-results/.

Safety features beyond the existing production rewrite guard:
  - skips blank/NaN role-company rows instead of benchmarking unscoped context
  - canonicalizes employer aliases for grouping and evidence lookup
  - independently verifies every output number against role-scoped evidence
  - records named-tool terms unsupported by role-scoped evidence
  - flags potential unsupported elaboration for human review rather than
    silently treating deterministic-guard acceptance as proof of truth
  - repeats an explicit no-number/no-tool instruction after a repeat offense

Examples:
  RESUME_PROFILE=morgan python scripts/nim_profile_neutral_rewrite_benchmark.py
  RESUME_PROFILE=dominick python scripts/nim_profile_neutral_rewrite_benchmark.py --n 24
  RESUME_PROFILE=morgan python scripts/nim_profile_neutral_rewrite_benchmark.py --n 30 --models lightning
"""

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import pandas as pd  # noqa: E402
import rewrite_bullets as rb  # noqa: E402

LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
MUSE = "meta/muse-glimmer-30b"

MODEL_VARIANTS: dict[str, dict[str, Any]] = {
    "lightning": {
        "model": LIGHTNING,
        "temperature": 0.4,
        "max_tokens": 1200,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    },
    "muse": {
        "model": MUSE,
        "temperature": 0.95,
        "top_p": 1.0,
        "reasoning_effort": "none",
        "max_tokens": 1200,
    },
}

# Profile-neutral generic normalizer plus a small known alias family found by
# this benchmark. Add a repeatable --alias canonical=variant for new profiles.
KNOWN_ALIASES = {
    "mlqrotech": "miqrotech",
    "miqrotech": "miqrotech",
    "miqrotechinc": "miqrotech",
}
LEGAL_SUFFIXES = re.compile(
    r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|co|company)\b", re.I
)
NUMBER_RE = re.compile(r"(?<![A-Za-z])\$?\d[\d,.]*\s*(?:%|[kKmMbB]|\+)?")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:[-/][A-Z0-9]+)*\b")

# These terms are not automatically rejected. They are high-value audit hints:
# if they appear in a rewrite but not in role evidence, a human should inspect
# the claim before trusting the result.
TOOLISH_TERMS = frozenset(
    {
        "aws",
        "azure",
        "gcp",
        "glue",
        "sagemaker",
        "s3",
        "rds",
        "snowflake",
        "databricks",
        "python",
        "sql",
        "spacy",
        "nlp",
        "tensorflow",
        "pytorch",
        "tableau",
        "power bi",
        "salesforce",
        "hubspot",
        "marketo",
        "etl",
        "api",
    }
)
OUTCOME_CUES = re.compile(
    r"\b(improv(?:e|ed|ing)|reduc(?:e|ed|ing)|increase(?:e|ed|ing)|"
    r"enabl(?:e|ed|ing)|accelerat(?:e|ed|ing)|driv(?:e|en|ing)|"
    r"support(?:ed|ing)|deliver(?:ed|ing)|result(?:ed|ing)|leading to)\b",
    re.I,
)


def _missing_role(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.lower() in {"nan", "none", "null", "unknown", "n/a"}


def _normalize_key(value: str) -> str:
    text = LEGAL_SUFFIXES.sub("", value.lower())
    return re.sub(r"[^a-z0-9]+", "", text)


def _parse_aliases(values: list[str]) -> dict[str, str]:
    aliases = dict(KNOWN_ALIASES)
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid --alias {value!r}; use canonical=variant.")
        canonical, variant = (part.strip() for part in value.split("=", 1))
        if not canonical or not variant:
            raise SystemExit(f"Invalid --alias {value!r}; use canonical=variant.")
        aliases[_normalize_key(variant)] = _normalize_key(canonical)
    return aliases


def canonical_role(raw_role: str, aliases: dict[str, str]) -> str:
    key = _normalize_key(raw_role)
    return aliases.get(key, key)


def _numbers(text: str) -> set[str]:
    return {
        match.group(0).lower().replace(" ", "") for match in NUMBER_RE.finditer(text)
    }


def _evidence_variants(
    kb: Any, raw_role: str, canonical: str, tags: str
) -> tuple[str, str]:
    """Build evidence from the literal role and canonical alias without guessing."""
    roles = [raw_role]
    if canonical and canonical != _normalize_key(raw_role):
        roles.append(canonical)

    contexts: list[str] = []
    segments: list[str] = []
    for role in roles:
        try:
            contexts.append(kb.company_scoped_context(role, tags) or "")
        except Exception:
            pass
        try:
            segments.append(kb.context_block_for_bullet(role, tags) or "")
        except Exception:
            pass

    def unique(parts: list[str]) -> str:
        return "\n\n".join(dict.fromkeys(part for part in parts if part.strip()))

    return unique(contexts), unique(segments)


def _tool_audit(rewrite: str, evidence: str) -> list[str]:
    low_evidence = evidence.lower()
    hits: list[str] = []
    for term in TOOLISH_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", rewrite, re.I) and not re.search(
            rf"\b{re.escape(term)}\b", low_evidence, re.I
        ):
            hits.append(term)
    return sorted(hits)


def _elaboration_flags(source: str, rewrite: str, evidence: str) -> list[str]:
    """Conservative manual-review flags, not automatic truth claims.

    A rewrite can legitimately paraphrase evidence, so this does not reject
    ordinary new wording. It flags specific, outcome-shaped elaboration that
    cannot be found in the source/evidence text for human review.
    """
    flags: list[str] = []
    source_and_evidence = f"{source}\n{evidence}".lower()
    rewrite_low = rewrite.lower()

    for acronym in sorted(set(ACRONYM_RE.findall(rewrite))):
        if acronym.lower() not in source_and_evidence:
            flags.append(f"unsupported acronym/domain term: {acronym}")

    if OUTCOME_CUES.search(rewrite) and not OUTCOME_CUES.search(source):
        # Outcome language may still be supported by the role context. Flag
        # only when several content words after a cue are novel to evidence.
        cue_tail = re.split(OUTCOME_CUES, rewrite_low, maxsplit=1)[-1]
        evidence_words = set(re.findall(r"[a-z]{4,}", source_and_evidence))
        novel = [
            word
            for word in re.findall(r"[a-z]{5,}", cue_tail)
            if word not in evidence_words
        ]
        novel = list(dict.fromkeys(novel))[:6]
        if len(novel) >= 3:
            flags.append("outcome/elaboration has novel terms: " + ", ".join(novel))

    return flags


def _strict_audit(source: str, rewrite: str, evidence: str) -> dict[str, Any]:
    evidence_numbers = _numbers(evidence)
    output_numbers = _numbers(rewrite)
    unsupported_numbers = sorted(output_numbers - evidence_numbers)
    unsupported_tools = _tool_audit(rewrite, evidence)
    elaboration = _elaboration_flags(source, rewrite, evidence)
    return {
        "unsupported_numbers": unsupported_numbers,
        "unsupported_tools": unsupported_tools,
        "elaboration_flags": elaboration,
        "strict_auto_pass": not unsupported_numbers
        and not unsupported_tools
        and not elaboration,
    }


def _prompt_only_messages(
    messages: list[dict[str, Any]], schema: dict[str, Any]
) -> list[dict[str, Any]]:
    copied = [dict(message) for message in messages]
    instruction = (
        "Reply with ONLY valid JSON matching this schema, without markdown:\n"
        + json.dumps(schema)
    )
    if copied and copied[-1].get("role") == "user":
        copied[-1]["content"] = f"{copied[-1].get('content', '')}\n\n{instruction}"
    else:
        copied.append({"role": "user", "content": instruction})
    return copied


def _structured_call(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Avoid private helper-name/version drift; use two safe local routes."""
    routes = [
        (
            "response_format.json_schema",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "rewrite",
                        "schema": schema,
                        "strict": True,
                    },
                }
            },
            messages,
        ),
        ("prompt_only", {}, _prompt_only_messages(messages, schema)),
    ]
    failures: list[dict[str, str]] = []
    for mode, additions, route_messages in routes:
        call_kwargs = dict(kwargs)
        call_kwargs.update(additions)
        result = nim._call(client, model, route_messages, **call_kwargs)
        result["mode"] = mode
        if result["ok"]:
            result["prior_route_failures"] = failures
            return result
        failures.append({"mode": mode, "error": result.get("error", "")[:200]})
    result["prior_route_failures"] = failures
    return result


def _sample(
    df: pd.DataFrame, n: int, aliases: dict[str, str]
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    skipped: list[dict[str, str]] = []
    valid_rows = []
    for _, row in df.iterrows():
        role = row.get("Role / Company", "")
        if _missing_role(role):
            skipped.append(
                {
                    "bullet": str(row.get("Bullet Point", ""))[:120],
                    "reason": "blank/nan role-company",
                }
            )
            continue
        valid_rows.append(row)
    clean = pd.DataFrame(valid_rows)
    if clean.empty:
        raise SystemExit(
            "No benchmarkable rows: every Role / Company value is blank/nan."
        )

    keep = clean[clean["rewrite_status"] == "KEEP"]
    manual = clean[clean["rewrite_status"] == "MANUAL"].head(min(4, n))
    wanted_keep = max(0, n - len(manual))
    step = max(1, len(keep) // max(1, wanted_keep))
    sample = pd.concat([keep.iloc[::step].head(wanted_keep), manual]).head(n)
    return sample, skipped


def _warmup(client: Any, model: str) -> dict[str, Any]:
    result = nim.stage_ping(client, model)
    status = "ok" if result["ok"] else "FAILED"
    print(f" warmup {status} in {result['seconds']}s ({result.get('diagnosis', '')})")
    return result


def _run_variant(
    client: Any,
    variant_name: str,
    cfg: dict[str, Any],
    sample: pd.DataFrame,
    aliases: dict[str, str],
) -> dict[str, Any]:
    print(f"\n=== {variant_name}: {cfg['model']} ===")
    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, _ = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()
    rows = []

    for _, row in sample.iterrows():
        source = str(row["Bullet Point"]).strip()
        raw_role = str(row.get("Role / Company", "")).strip()
        canonical = canonical_role(raw_role, aliases)
        tags = str(row.get("Tags", ""))
        weaknesses = str(row.get("weaknesses", ""))
        company_context, segment_context = _evidence_variants(
            kb, raw_role, canonical, tags
        )
        evidence = f"{source}\n{company_context}\n{segment_context}"
        attempts = []
        final_text = ""
        final_reason = None
        final_audit: dict[str, Any] = {}

        for attempt_no in range(1, rb.MAX_ATTEMPTS + 1):
            repeat_ban = ""
            if final_reason and (
                "number" in final_reason[0].lower() or "tool" in final_reason[0].lower()
            ):
                repeat_ban = (
                    "\n\nCRITICAL RETRY CONSTRAINT: The prior answer introduced unsupported numeric or tool claims. "
                    "Do not use any new number, percentage, count, money amount, named tool, platform, domain, "
                    "or technical system unless it appears literally in the supplied evidence."
                )
            prompt = rb.build_rewrite_prompt(
                bullet=source,
                tags=tags,
                weaknesses=weaknesses + repeat_ban,
                kb_context=segment_context,
                attempt=attempt_no,
            )
            result = _structured_call(
                client,
                cfg["model"],
                [
                    {"role": "system", "content": rewrite_system},
                    {"role": "user", "content": prompt},
                ],
                schema,
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
                **({"top_p": cfg["top_p"]} if cfg.get("top_p") is not None else {}),
                **(
                    {"reasoning_effort": cfg["reasoning_effort"]}
                    if cfg.get("reasoning_effort")
                    else {}
                ),
                **({"extra_body": cfg["extra_body"]} if cfg.get("extra_body") else {}),
            )
            log = {
                "attempt": attempt_no,
                "ok": result["ok"],
                "seconds": result["seconds"],
                "mode": result.get("mode"),
            }
            attempts.append(log)
            if not result["ok"]:
                log["error"] = result.get("error")
                break
            try:
                final_text = str(
                    json.loads(result["text"]).get("rewritten_bullet", "")
                ).strip()
            except json.JSONDecodeError:
                final_text = ""
            production_reason = (
                rb._rejection_reason(final_text, evidence, raw_role, kb)
                if final_text
                else None
            )
            strict = _strict_audit(source, final_text, evidence)
            if strict["unsupported_numbers"]:
                final_reason = (
                    "Strict evidence audit: unsupported numbers "
                    + ", ".join(strict["unsupported_numbers"]),
                    "",
                )
            elif strict["unsupported_tools"]:
                final_reason = (
                    "Strict evidence audit: unsupported tools "
                    + ", ".join(strict["unsupported_tools"]),
                    "",
                )
            elif production_reason:
                final_reason = production_reason
            else:
                final_reason = None
            final_audit = strict
            log.update(
                {
                    "rewritten": final_text,
                    "production_rejection": (
                        production_reason[0] if production_reason is not None else None
                    ),
                    "strict_auto_pass": strict["strict_auto_pass"],
                    "elaboration_flags": strict["elaboration_flags"],
                    "rejected": (final_reason[0] if final_reason is not None else None),
                }
            )
            if final_text and not final_reason:
                break
            weaknesses = (
                production_reason[1]
                if production_reason is not None
                else "Return a grounded rewrite using only literal evidence."
            )

        record = {
            "raw_role": raw_role,
            "canonical_role": canonical,
            "source": source,
            "tags": tags,
            "attempts": attempts,
            "final_text": final_text,
            "final_rejection": final_reason[0] if final_reason else None,
            "strict_audit": final_audit,
        }
        rows.append(record)
        outcome = "AUTO-PASS" if final_text and not final_reason else "REJECT/REVIEW"
        print(
            f" {canonical[:26]:26} | attempts={len(attempts)} | {outcome} | flags={len(final_audit.get('elaboration_flags', []))}"
        )

    return {"variant": variant_name, "settings": cfg, "rows": rows}


def _summarize(result: dict[str, Any]) -> dict[str, int]:
    rows = result["rows"]
    return {
        "rows": len(rows),
        "auto_pass": sum(
            1 for row in rows if row["final_text"] and not row["final_rejection"]
        ),
        "final_reject": sum(1 for row in rows if row["final_rejection"]),
        "api_failure": sum(
            1 for row in rows if row["attempts"] and not row["attempts"][-1]["ok"]
        ),
        "elaboration_flags": sum(
            len(row["strict_audit"].get("elaboration_flags", [])) for row in rows
        ),
        "avg_attempts_x10": (
            round(10 * sum(len(row["attempts"]) for row in rows) / len(rows))
            if rows
            else 0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=24, help="total sampled valid rows")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=tuple(MODEL_VARIANTS),
        default=("lightning", "muse"),
    )
    parser.add_argument(
        "--alias", action="append", default=[], help="canonical=variant; repeatable"
    )
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()

    aliases = _parse_aliases(args.alias)
    client = nim._client()
    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    sample, skipped = _sample(df, args.n, aliases)
    print(
        f"\nProfile: {os.environ.get('RESUME_PROFILE', '(default)')} | valid sample: {len(sample)} | skipped unscoped rows: {len(skipped)}"
    )

    output: dict[str, Any] = {"skipped_unscoped_rows": skipped, "runs": []}
    for name in args.models:
        cfg = MODEL_VARIANTS[name]
        if not args.no_warmup:
            print(f"\nWarm-up: {cfg['model']}")
            _warmup(client, cfg["model"])
        run = _run_variant(client, name, cfg, sample, aliases)
        run["summary"] = _summarize(run)
        output["runs"].append(run)
        print(f" summary: {run['summary']}")

    stage = f"profile_neutral_rewrite_{datetime.now():%Y-%m-%d_%H%M%S}"
    path = nim._save("profile-neutral-rewrite", stage, {"ok": True, **output})
    print(f"\nSaved complete results: {os.path.relpath(path, nim.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
