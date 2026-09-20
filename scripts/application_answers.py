"""Job-scoped application-answer engine and one-turn NDJSON CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import answer_questions
import jd_manager
import profile_paths
from answer_grounding import Violation, check_answer


MAX_PROMPT_CHARS = 60_000
MODEL = "gemini-3.5-flash-lite"


@dataclass
class Evidence:
    text: str = ""
    bullets: list[str] = field(default_factory=list)
    stories: list[str] = field(default_factory=list)


@dataclass
class AnswerContext:
    job_id: str
    title: str
    company: str
    jd_text: str
    evaluation_summary: str = ""
    research_summary: str = ""
    research_source: str = ""
    voice_anchors: str = ""
    compensation_context: str = ""
    roster: list[str] = field(default_factory=list)


@dataclass
class AnswerResult:
    text: str
    kind: answer_questions.QuestionKind
    warnings: list[Violation] = field(default_factory=list)
    blocked: bool = False


def _trim(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    head = limit // 2
    return text[:head] + "\n...[trimmed]...\n" + text[-(limit - head - 19):]


def _payload(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def context_cache_path(job_id: str, jd_text: str = "") -> str:
    digest = hashlib.sha256(jd_text.encode("utf-8")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"resume-answer-context-{job_id}-{digest}.json")


def build_context(job: str) -> AnswerContext:
    with __import__("jd_source").resolved_jd(job) as (path, _database_backed):
        payload = _payload(path)
        jd_text = jd_manager.read_jd_text(path)
        evaluation = jd_manager.read_evaluation(path) or {}
        research = jd_manager.read_research(path) or {}
        title = payload.get("job_title") or payload.get("title") or ""
        company = payload.get("company_name") or payload.get("company") or ""
        if not research:
            try:
                from orchestrator import ResumeEngine

                research = ResumeEngine().research_company(payload, jd_text) or {}
            except (ImportError, OSError, ValueError):
                research = {}
        research_summary = _trim(
            "\n".join(
                str(x)
                for x in (
                    research.get("company_facts", []),
                    research.get("notable_highlights", []),
                    research.get("vocabulary_substitutions", []),
                )
            ),
            2500,
        )
        voice = ""
        voice_path = os.path.join(profile_paths.kb_dir(), "voice-anchors.md")
        try:
            voice = _trim(Path(voice_path).read_text(encoding="utf-8"), 2000)
        except OSError:
            pass
        compensation = ""
        try:
            from orchestrator import build_compensation_context

            compensation = build_compensation_context(jd_text)
        except (ImportError, OSError, ValueError):
            pass
        profile = profile_paths.profile_yaml() or {}
        roster = [
            str(role.get("company") or role)
            for role in (profile.get("roles") or [])
            if isinstance(role, (dict, str))
        ]
        evaluation_summary = _trim(
            json.dumps(
                {
                    key: evaluation.get(key)
                    for key in (
                        "strengths",
                        "capability_gaps",
                        "experience_blockers",
                        "recruiter_read",
                        "hard_blockers",
                    )
                    if evaluation.get(key)
                },
                ensure_ascii=False,
            ),
            1500,
        )
        return AnswerContext(
            job_id=payload.get("id") or job,
            title=title,
            company=company,
            jd_text=_trim(jd_text, 12000),
            evaluation_summary=evaluation_summary,
            research_summary=research_summary,
            research_source=str(research.get("_research_source") or ""),
            voice_anchors=voice,
            compensation_context=_trim(compensation, 1500),
            roster=roster,
        )


def evidence_for(context: AnswerContext, question: str, kind: answer_questions.QuestionKind) -> Evidence:
    try:
        from vector_store import search_bullet_bank

        rows = search_bullet_bank(question, top_k=8)
        bullets = [row[0] for row in rows]
    except (ImportError, OSError, ValueError):
        bullets = []
    return Evidence(text="\n".join(bullets), bullets=bullets)


def render_prompt(context, evidence, history, question, kind, char_limit=None) -> str:
    turns = history[-6:] if history else []
    conversation = "\n".join(
        f"{turn.get('role', 'user').upper()}: {turn.get('text', '')}" for turn in turns
    )
    limit_rule = f"Maximum length: {char_limit} characters." if char_limit else "No character limit was supplied."
    prompt = f"""You are the candidate, writing a truthful application answer with a hiring recruiter's eye.

=== JOB DESCRIPTION ===
{context.jd_text}
=== RECRUITER ASSESSMENT ===
{context.evaluation_summary}
=== COMPANY ===
{context.research_summary}
=== CANDIDATE EVIDENCE ===
{evidence.text}
=== VOICE ===
{context.voice_anchors}
=== RULES ===
Use only facts in the evidence above. Never invent numbers, employers, tools, titles, or outcomes.
Answer the question directly. For compensation, use only the stated posting context and say when pay is unstated.
Question kind: {kind.value}. {limit_rule}
=== CONVERSATION ===
{conversation}
NEW QUESTION: {question}
"""
    return _trim(prompt, MAX_PROMPT_CHARS)


def _generate(prompt: str) -> str:
    from gemini_client import GeminiClient

    result = GeminiClient.generate(
        model=MODEL,
        system_instruction="You write concise, truthful application answers.",
        contents=prompt,
    )
    if isinstance(result, tuple):
        return str(result[0] or "")
    return str(result or "")


def answer(job: str, question: str, history=(), char_limit=None) -> AnswerResult:
    context = build_context(job)
    kind = answer_questions.classify_question(question)
    profile = profile_paths.profile_yaml() or {}
    blocked = answer_questions.sensitive_response(kind, profile)
    if blocked is not None:
        return AnswerResult(blocked, kind, blocked=True)
    evidence = evidence_for(context, question, kind)
    prompt = render_prompt(context, evidence, history, question, kind, char_limit)
    text = _generate(prompt)
    warnings = check_answer(text, context, evidence, char_limit, question)
    hard = [warning for warning in warnings if not warning.soft]
    if hard:
        retry_prompt = (
            prompt
            + "\nRETRY REQUIREMENT: Correct these deterministic issues without "
            "inventing replacement facts:\n"
            + "\n".join(f"- {warning.detail}" for warning in hard)
        )
        retry_text = _generate(retry_prompt)
        retry_warnings = check_answer(
            retry_text, context, evidence, char_limit, question
        )
        if len([warning for warning in retry_warnings if not warning.soft]) < len(hard):
            text, warnings = retry_text, retry_warnings
    return AnswerResult(text, kind, warnings)


def _save_turn(
    job: str,
    question: str,
    kind,
    text: str,
    warnings,
    char_limit=None,
    role: str = "assistant",
) -> None:
    """Merge one answer turn into the job transcript without leaking metadata."""
    with __import__("jd_source").resolved_jd(job) as (path, _database_backed):
        saved = jd_manager.read_application_answers(path) or {"items": []}
        items = saved.get("items") if isinstance(saved, dict) else []
        items = items if isinstance(items, list) else []
        item = next((item for item in items if item.get("question") == question), None)
        if item is None:
            item = {
                "id": str(uuid.uuid4()),
                "question": question,
                "kind": kind.value,
                "char_limit": char_limit,
                "final": "",
                "history": [],
            }
            items.append(item)
        item.setdefault("history", []).append(
            {
                "role": role,
                "text": text,
                "warnings": [warning.__dict__ for warning in warnings],
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        jd_manager.save_application_answers(path, {"items": items})


def _event(event_type: str, **payload) -> None:
    print(json.dumps({"type": event_type, **payload}, ensure_ascii=False))


def _turn(request: dict) -> None:
    _event("status", message="Building grounded answer context")
    try:
        _save_turn(
            request["job"],
            request["question"],
            answer_questions.classify_question(request["question"]),
            request["question"],
            [],
            request.get("char_limit"),
            role="user",
        )
        result = answer(
            request["job"],
            request["question"],
            request.get("history") or (),
            request.get("char_limit"),
        )
        _save_turn(
            request["job"],
            request["question"],
            result.kind,
            result.text,
            result.warnings,
            request.get("char_limit"),
        )
        _event(
            "answer",
            text=result.text,
            kind=result.kind.value,
            blocked=result.blocked,
            warnings=[v.__dict__ for v in result.warnings],
        )
    except LookupError as exc:
        _event("error", code="context_error", message=str(exc))
    except Exception as exc:
        _event("error", code="internal", message=str(exc))


def _finalize(job: str, item_index: int, library: bool = False) -> None:
    with __import__("jd_source").resolved_jd(job) as (path, _):
        saved = jd_manager.read_application_answers(path) or {"items": []}
        items = saved.get("items") or []
        if item_index < 0 or item_index >= len(items):
            raise IndexError(f"answer item {item_index} does not exist")
        item = items[item_index]
        answers = [turn for turn in item.get("history", []) if turn.get("role") == "assistant"]
        if not answers:
            raise ValueError("cannot finalize an item without an assistant answer")
        item["final"] = answers[-1].get("text") or ""
        jd_manager.save_application_answers(path, {"items": items})
        if library:
            # Deliberately no automatic library write: generated text remains
            # job-scoped until a future explicit curation flow is implemented.
            _event("status", message="Saved as final; answer library remains unchanged")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("turn", "load", "finalize"))
    parser.add_argument("--job")
    parser.add_argument("--item", type=int, default=0)
    parser.add_argument("--library", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "turn":
        request = json.load(sys.stdin)
        _turn(request)
    elif args.command == "load":
        with __import__("jd_source").resolved_jd(args.job) as (path, _):
            _event("answers", answers=jd_manager.read_application_answers(path))
    else:
        _finalize(args.job, args.item, args.library)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
