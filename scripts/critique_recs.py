"""
critique_recs.py — Turns the critique's structured recommendations
({section, target_text, action, evidence}) into the plain strings the
apply step has always consumed, and drops the ones that can't be an
honest edit to this resume.

Exists because free-text recommendations routinely asked for things a
resume edit can't deliver -- "prepare to discuss renewals in the
interview", "add customer health scoring experience" -- and the apply
model, told to apply them, invented the claim. Code decides here, not
the model:

- target_text not in the resume  -> dropped (the edit has nothing to edit)
- "add" with no evidence          -> gaps (an ask, not an edit)
- claims-ledger or gap-list hit   -> gaps
- interview/prep/cover-letter     -> interview_notes

Old checkpoints and tests hand in plain strings; those pass through the
ledger and interview filters only (no target/evidence to check).
"""

import re

import claims_ledger

_NON_RESUME_RE = re.compile(
    r"\b(interview|prep(?:are|aration)?|cover letter|continue to|networking|"
    r"practice (?:your|answering)|talking points?|be ready to)\b",
    re.I,
)
_TARGETED_ACTIONS = ("rewrite", "remove", "move", "replace", "shorten", "reorder")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip().lower()


def resume_text(resume_data: dict) -> str:
    """Every string in the resume, flattened -- what target_text must match."""
    parts: list[str] = []

    def walk(node):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                if not str(k).startswith("_"):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(resume_data)
    return _norm(" \n ".join(parts))


def to_text(item) -> str:
    """The string form the apply step and resume_report read."""
    if not isinstance(item, dict):
        return str(item)
    action = str(item.get("action") or "").strip()
    if action.endswith("?"):
        # Questions route to `resume polish` by their trailing "?".
        return action
    text = f"{item.get('section') or 'Resume'}: {action}"
    if item.get("target_text"):
        text += f' (target: "{item["target_text"]}")'
    if item.get("evidence"):
        text += f" Evidence: {item['evidence']}"
    return text


def _verb(action: str) -> str:
    words = action.strip().lower().split()
    return words[0] if words else ""


def sort_recommendations(
    recs, resume_data: dict, ledger: dict | None = None, unsupported_asks=None
) -> dict:
    """Returns {"recommendations": [str], "interview_notes": [str],
    "gaps": [str], "dropped": [str]}."""
    ledger = ledger if ledger is not None else claims_ledger.load()
    asks = [a.lower() for a in (unsupported_asks or []) if a]
    doc = resume_text(resume_data)
    out: dict[str, list[str]] = {
        "recommendations": [],
        "interview_notes": [],
        "gaps": [],
        "dropped": [],
    }
    for item in recs or []:
        text = to_text(item)
        claim_text = (
            f"{item.get('action', '')} {item.get('evidence', '')}"
            if isinstance(item, dict)
            else text
        )
        if _NON_RESUME_RE.search(claim_text):
            out["interview_notes"].append(text)
            continue
        if claims_ledger.find_in_text(claim_text, ledger) or any(
            a in claim_text.lower() for a in asks
        ):
            out["gaps"].append(text)
            continue
        if isinstance(item, dict):
            action = str(item.get("action") or "")
            target = _norm(item.get("target_text") or "")
            verb = _verb(action)
            if target and target not in doc:
                out["dropped"].append(text)
                continue
            if verb in _TARGETED_ACTIONS and not target:
                out["dropped"].append(text)
                continue
            if verb == "add" and not str(item.get("evidence") or "").strip():
                out["gaps"].append(text)
                continue
        out["recommendations"].append(text)
    return out
