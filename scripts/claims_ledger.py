"""
claims_ledger.py — One list of topics and phrases this candidate must never
claim, shared by every step that writes or judges resume text: the builder
prompt, the static prefix the critique/apply/audit calls read, and
validate_resume's soft check. Lives in profile.yml's claims_ledger: section.

Exists because the ban list used to reach only the final regex rewrite
(auto_fix_banned_claims): the critique never saw it, so it recommended
"customer health scoring" for a lifecycle JD and protected the sentence
as a distinctive moment. A ban the model never reads can't be followed.
"""

import re

import profile_paths

_SECTIONS = (("SUMMARY_TEXT", "Summary"), ("WHY_TEXT", "Why"))


def load(profile_data: dict | None = None) -> dict:
    """Returns {"topics": [(name, regex, instead)], "phrases": [(text, regex)]}.
    Malformed entries are skipped, not fatal -- a typo in profile.yml must
    not stop a build."""
    if profile_data is None:
        try:
            profile_data = profile_paths.profile_yaml()
        except Exception:
            profile_data = {}
    raw = (profile_data or {}).get("claims_ledger") or {}
    topics, phrases = [], []
    for entry in raw.get("banned_topics") or []:
        try:
            topics.append(
                (
                    entry["name"],
                    re.compile(entry["pattern"], re.I),
                    entry.get("instead", ""),
                )
            )
        except (KeyError, TypeError, re.error):
            continue
    for entry in raw.get("banned_phrases") or []:
        try:
            phrases.append((entry["text"], re.compile(entry["pattern"], re.I)))
        except (KeyError, TypeError, re.error):
            continue
    notes = [str(n) for n in raw.get("notes") or [] if n]
    anchors = {k: str(v) for k, v in (raw.get("anchors") or {}).items() if v}
    return {"topics": topics, "phrases": phrases, "notes": notes, "anchors": anchors}


def prompt_block(ledger: dict) -> str:
    """The "never claim" block every prompt gets. Empty when no ledger."""
    if not ledger["topics"] and not ledger["phrases"]:
        return ""
    lines = [
        "=== CLAIMS LEDGER (never claim these, even when the JD asks for them) ===",
        "The candidate has no evidence for the topics below. Do not write them into "
        "any section, do not recommend adding them, and do not treat a sentence "
        "containing them as a strength. When the JD asks for one, use the honest "
        "substitute or leave the gap.",
    ]
    for name, _rx, instead in ledger["topics"]:
        lines.append(f"- {name}" + (f" -> instead: {instead}" if instead else ""))
    if ledger["phrases"]:
        lines.append(
            "Never use these phrases: "
            + ", ".join(f'"{t}"' for t, _ in ledger["phrases"])
        )
    lines.extend(ledger.get("notes") or [])
    return "\n".join(lines)


def find_in_text(text: str, ledger: dict) -> list[tuple[str, str]]:
    """(matched text, what to use instead) for every ledger hit in `text`."""
    hits = []
    for _name, rx, instead in ledger["topics"]:
        for m in rx.finditer(text or ""):
            hits.append((m.group(0), instead))
    for _text, rx in ledger["phrases"]:
        for m in rx.finditer(text or ""):
            hits.append((m.group(0), ""))
    return hits


def check_resume(resume_data: dict, ledger: dict | None = None) -> list[str]:
    """Soft violations ("Claims ledger: ...") for every hit in Summary, Why,
    EXPERIENCE bullets, and SKILLS -- each names the section, the exact
    text, and the substitute, so the retry loop knows what to change."""
    ledger = ledger if ledger is not None else load()
    if not ledger["topics"] and not ledger["phrases"]:
        return []
    places: list[tuple[str, str]] = [
        (label, resume_data.get(key) or "") for key, label in _SECTIONS
    ]
    for job in resume_data.get("EXPERIENCE") or []:
        for bullet in job.get("achievements") or []:
            places.append((f"{job.get('company', '?')} bullet", bullet))
    for item in _skills_items(resume_data.get("SKILLS")):
        places.append(("Skills", item))
    violations = []
    for label, text in places:
        for matched, instead in find_in_text(text, ledger):
            fix = (
                f" Use {instead} instead, or remove the clause."
                if instead
                else " Reword or remove it."
            )
            violations.append(
                f"Claims ledger: {label} claims {matched!r}, which the candidate has no "
                f"evidence for: {_snippet(text)!r}.{fix}"
            )
    return violations


def anchor_for(ledger: dict, clerical: bool) -> str:
    """The Summary anchor for this build's track -- code picks it so the
    builder can't open on generic filler instead of the strongest fact."""
    return str(ledger["anchors"].get("clerical" if clerical else "sales_marketing", ""))


def anchor_block(anchor: str) -> str:
    if not anchor:
        return ""
    return (
        "=== SUMMARY ANCHOR ===\n"
        "The Summary's first or second sentence must carry this verified fact, "
        f"numbers intact (rephrasing is fine): {anchor}"
    )


def check_anchor(resume_data: dict) -> list[str]:
    """Soft "Summary anchor:" violation when none of the anchor's numbers
    reach the Summary. Reads resume_data["_summary_anchor"], set at build."""
    anchor = resume_data.get("_summary_anchor") or ""
    numbers = re.findall(r"\d[\d,.]*", anchor)
    summary = re.sub(r"<[^>]+>", "", resume_data.get("SUMMARY_TEXT") or "")
    # Whole numbers only: "$1M+" must not pass on the 1 in "10+ years".
    if not numbers or any(
        re.search(rf"(?<![\d,.]){re.escape(n)}(?![\d,])", summary) for n in numbers
    ):
        return []
    return [
        f"Summary anchor: the Summary leaves out the track's anchor fact: {anchor!r}. "
        "Work it into the first or second sentence, numbers intact."
    ]


def insert_anchor(resume_data: dict) -> bool:
    """Puts the anchor in as the Summary's second sentence when the model
    dropped its numbers. Retries reworded the fact into "beating initial
    targets" with the numbers gone, so code places it instead. True if
    the Summary changed."""
    if not check_anchor(resume_data):
        return False
    anchor = resume_data["_summary_anchor"].strip().rstrip(".") + "."
    summary = resume_data.get("SUMMARY_TEXT") or ""
    # After the first sentence; </strong> closes a bolded opener.
    m = re.search(r"[.!?](?:</strong>)?\s+", summary)
    if m:
        rest = summary[m.end() :]
        # The model's numberless rewording of the anchor reuses its subject
        # ("First outbound hire", "As the inaugural outbound hire"); replace
        # that sentence rather than repeat the fact.
        subject = " ".join(re.findall(r"[a-z]+", anchor.lower())[1:3])
        end = re.search(r"[.!?](?:\s+|$)|$", rest)
        assert end is not None  # the trailing "|$" always matches
        if subject and subject in rest[: end.start()].lower():
            rest = rest[end.end() :]
        summary = f"{summary[:m.end()]}{anchor} {rest}".rstrip()
    else:
        summary = f"{summary} {anchor}".strip()
    resume_data["SUMMARY_TEXT"] = summary
    return True


def unsupported_asks(jd_text: str, ledger: dict) -> list[tuple[str, str]]:
    """(topic, substitute) for each ledger topic this JD asks for."""
    return [
        (name, instead)
        for name, rx, instead in ledger["topics"]
        if rx.search(jd_text or "")
    ]


def asks_block(asks: list[tuple[str, str]]) -> str:
    """Names this JD's specific gaps -- a model told "this JD wants renewals;
    say retention campaigns" follows it far more often than a general ban."""
    if not asks:
        return ""
    lines = ["=== THIS JD ASKS FOR THINGS THE CANDIDATE HAS NO EVIDENCE FOR ==="]
    for name, instead in asks:
        lines.append(
            f"- {name}"
            + (
                f": use {instead} instead, or leave the gap"
                if instead
                else ": leave the gap"
            )
        )
    return "\n".join(lines)


def filter_texts(
    texts: list[str], ledger: dict | None = None
) -> tuple[list[str], list[str]]:
    """Splits texts into (clean, dropped) -- used for critique
    recommendations and protected distinctive moments."""
    ledger = ledger if ledger is not None else load()
    clean: list[str] = []
    dropped: list[str] = []
    for t in texts or []:
        (dropped if find_in_text(str(t), ledger) else clean).append(t)
    return clean, dropped


def _skills_items(skills) -> list[str]:
    if isinstance(skills, str):
        return [skills]
    items: list[str] = []
    for entry in skills or []:
        if isinstance(entry, dict):
            items.extend(str(v) for v in entry.values())
        else:
            items.append(str(entry))
    return items


def _snippet(text: str, limit: int = 160) -> str:
    text = re.sub(r"<[^>]+>", "", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
