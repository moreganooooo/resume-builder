"""email_matcher.py -- matches a classified email to a specific saved role
and proposes an application-status change.

inbox_sync answers "is this job mail, and what kind". This answers the
harder question: WHICH of the saved roles it refers to, and whether we
are confident enough to write anything down.

Company alone is not enough. A staffing agency sends many rejections for
many different roles, and matching on company would attach a "Graphic
Designer" rejection to a "Copywriter" application. So the company only
selects the candidate set; the role title, the dates, and the current
status decide between them.

Where the role hides depends on the intent, which is the single most
useful pattern in the corpus:

    rejections / status updates -> role is in the SUBJECT
        "Update on your application for Digital Marketing Coordinator"
    application confirmations   -> role is in the BODY
        subject: "Thank you for your application to Aquent | Skill"
        body:    "Thank you for your interest in the Copywriter position"

Nothing here writes by itself. plan_updates() returns proposals with a
confidence and a human-readable reason; apply_updates() is a separate
call, and anything below AUTO_APPLY has to be confirmed by a person.
Getting this wrong silently marks a live application as rejected, which
is worse than doing nothing.
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

import jd_manager
import jd_source

# Role sits in the subject for anything reporting ON an application.
ROLE_IN_SUBJECT = re.compile(
    r"(?:update on your application for|thank you for your interest in|"
    r"regarding your application for|your application for|"
    r"application for|not moving forward with|"
    r"interview (?:invitation|request) for|phone screen for|"
    r"schedule (?:an )?interview for|application (?:update|status) for)"
    r"[:\s]+(.+?)(?:\s+(?:at|with)\s+|\s*[|–—-]\s*|$)",
    re.I,
)

# Role sits in the body for confirmations, which greet the company in the
# subject and name the role inside.
ROLE_IN_BODY = re.compile(
    r"(?:for your interest in the|your interest in the|"
    r"your application for the|application for the|"
    r"applying (?:for|to) the|applied (?:for|to) the|"
    r"position of|role of)\s+(.+?)\s+(?:position|role|opening|job)\b",
    re.I,
)

# Fallback: "... the Copywriter position ..." with no lead-in phrase.
ROLE_BEFORE_NOUN = re.compile(
    r"\bthe\s+([A-Z][A-Za-z0-9/&()\-\s]{2,60}?)\s+(?:position|role|opening)\b"
)

# Noise that clings to an extracted title.
ROLE_TRIM = re.compile(
    r"\b(position|role|opening|job|opportunity|at|with|for)\b\s*$", re.I
)

# Seniority and employment-type words that vary between how a job is
# posted and how a rejection refers to it. Dropped before comparison so
# "Sr. Content Strategist" and "Content Strategist" are the same role.
ROLE_STOPWORDS = {
    "sr",
    "senior",
    "jr",
    "junior",
    "lead",
    "staff",
    "principal",
    "i",
    "ii",
    "iii",
    "remote",
    "hybrid",
    "onsite",
    "contract",
    "contractor",
    "fulltime",
    "parttime",
    "temporary",
    "temp",
    "permanent",
    "the",
    "a",
    "an",
}

# Intent -> the application status it implies. Keys are inbox_sync's
# intents; values must be members of jd_manager.APPLICATION_STATUSES.
STATUS_MAP = {
    "acknowledgment": "Applied",
    "rejection": "Rejected",
    "interview": "Interview",
    "offer": "Offer",
}

# Statuses that already represent a later or terminal point in the funnel.
# A stray "we received your application" arriving after an interview must
# not drag the record backwards.
STATUS_RANK = {
    "Applied": 1,
    "Responded": 2,
    "Interview": 3,
    "Offer": 4,
    "Rejected": 5,
    "Withdrawn": 5,
}

AUTO_APPLY = 0.85
CONFIRM = 0.60


# Requisition ids a job board staples onto a title: "[AQ-12521]",
# "(REQ 4471)", "#26-07112". Pure noise for comparison -- the same role
# is posted with one and referred to without it. A parenthetical WITHOUT
# a digit is left alone, because "(Commercial B2B)" genuinely
# distinguishes two different roles at the same company.
ROLE_BRACKETED = re.compile(r"\[[^\]]*\]|\([^)]*\)")
ROLE_HASH_ID = re.compile(r"#\s*[\w-]*\d[\w-]*")


def _looks_like_req_id(chunk: str) -> bool:
    """True for "[AQ-12521]" or "(REQ 4471)", false for "(Commercial B2B)".

    Tested on the digit RATIO, not on containing a digit: "B2B" has a
    digit but is part of the role's actual name, and stripping it merged
    two genuinely different Aquent postings into one.
    """
    letters_digits = re.sub(r"[^A-Za-z0-9]", "", chunk)
    if not letters_digits:
        return True
    digits = sum(c.isdigit() for c in letters_digits)
    return digits / len(letters_digits) >= 0.4


def normalize_role(role: str) -> str:
    """Comparable form of a job title: lowercased, punctuation stripped,
    requisition ids and seniority/employment-type words removed."""
    role = ROLE_BRACKETED.sub(
        lambda m: " " if _looks_like_req_id(m.group(0)) else m.group(0), role or ""
    )
    role = ROLE_HASH_ID.sub(" ", role)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", role.lower())
    words = [w for w in cleaned.split() if w not in ROLE_STOPWORDS]
    return " ".join(words)


def extract_role(subject: str, body: str, intent: str = "") -> Optional[str]:
    """Best-effort job title from an email, or None.

    Tries the location the intent predicts first, then the other, because
    the convention is strong but not universal.
    """
    subject = subject or ""
    body = body or ""

    body_first = intent in ("acknowledgment", "application")
    if body_first:
        attempts = [
            (ROLE_IN_BODY, body),
            (ROLE_BEFORE_NOUN, body),
            (ROLE_IN_SUBJECT, subject),
        ]
    else:
        attempts = [
            (ROLE_IN_SUBJECT, subject),
            (ROLE_IN_BODY, body),
            (ROLE_BEFORE_NOUN, body),
        ]

    for pattern, text in attempts:
        match = pattern.search(text or "")
        if not match:
            continue
        role = ROLE_TRIM.sub("", match.group(1)).strip(" -:|–—")
        # A "role" of one short word is almost always a mis-capture.
        if role and len(role) > 2 and normalize_role(role):
            return role
    return None


def role_similarity(left: str, right: str) -> float:
    """0..1 similarity between two job titles, after normalization."""
    a, b = normalize_role(left), normalize_role(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    a_words, b_words = set(a.split()), set(b.split())
    overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    # Word overlap catches reordering ("Marketing Content" vs "Content
    # Marketing"); the sequence ratio catches near-spellings. Take the
    # kinder of the two rather than averaging, so one strong signal is
    # enough.
    return max(overlap, sequence)


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def score_match(email: Dict[str, Any], job: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Confidence that `email` refers to `job`, with the reasons why.

    Company is assumed to already match -- it selects the candidate set,
    it does not discriminate within it.
    """
    reasons: List[str] = []
    score = 0.4  # same company, established by the caller
    reasons.append("same company")

    email_role = email.get("role")
    job_role = job.get("title") or ""

    if email_role and job_role:
        similarity = role_similarity(email_role, job_role)
        if similarity >= 0.95:
            score += 0.45
            reasons.append(f"role matches exactly ({job_role})")
        elif similarity >= 0.7:
            score += 0.3
            reasons.append(f"role is close ({email_role} ~ {job_role})")
        elif similarity >= 0.4:
            score += 0.1
            reasons.append("role partly overlaps")
        else:
            # A clear role on both sides that disagrees is evidence
            # AGAINST this pairing, not merely absent evidence -- this is
            # what stops a "Graphic Designer" rejection landing on a
            # "Copywriter" application.
            score -= 0.35
            reasons.append(f"role conflicts ({email_role} vs {job_role})")
    elif not email_role:
        reasons.append("no role found in the email")

    email_date = _parse_date(email.get("date"))
    applied_at = _parse_date((job.get("application") or {}).get("applied_at"))
    if email_date and applied_at:
        days = abs((email_date - applied_at.replace(tzinfo=email_date.tzinfo)).days)
        if days <= 7:
            score += 0.15
            reasons.append(f"{days}d after applying")
        elif days <= 30:
            score += 0.1
            reasons.append(f"{days}d after applying")
        elif days <= 90:
            score += 0.05
            reasons.append(f"{days}d after applying")
        else:
            reasons.append(f"{days}d apart")

    intent = email.get("intent")
    status = (job.get("application") or {}).get("status")
    if intent in ("rejection", "interview", "offer") and status == "Applied":
        score += 0.05
        reasons.append("job is awaiting a reply")

    return max(0.0, min(score, 1.0)), reasons


def best_match(
    email: Dict[str, Any], candidates: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], float, List[str]]:
    """Highest-scoring candidate for this email.

    A near-tie is deliberately penalized: if two saved roles at the same
    company score within 0.1 of each other, nothing distinguishes them and
    a confident write would be a coin flip.
    """
    if not candidates:
        return None, 0.0, ["no saved role at this company"]

    scored = [(job,) + score_match(email, job) for job in candidates]
    scored.sort(key=lambda item: item[1], reverse=True)

    job, score, reasons = scored[0]
    if len(scored) > 1 and scored[1][1] >= score - 0.1:
        score = min(score, CONFIRM - 0.01)
        reasons.append(
            f"ambiguous: {len(scored)} roles at this company score alike"
        )
    return job, score, reasons


def resolve_status(intent: str, current: Optional[str]) -> Optional[str]:
    """The status this intent implies, or None to leave the record alone.

    Never moves an application backwards. A delayed "we received your
    application" must not undo a recorded interview, and nothing reopens
    a Rejected or Withdrawn record.
    """
    proposed = STATUS_MAP.get(intent)
    if not proposed:
        return None
    if not current:
        return proposed
    if STATUS_RANK.get(current, 0) >= STATUS_RANK.get(proposed, 0):
        return None
    return proposed


def plan_updates(
    results: List[Dict[str, Any]], jobs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Proposed status changes for classified emails. Writes nothing.

    Each proposal carries its confidence, its reasons, and an `action` of
    auto / confirm / skip so a caller can decide how much to trust it.
    """
    by_company: Dict[str, List[Dict[str, Any]]] = {}
    for job in jobs:
        key = _company_key(job.get("company", ""))
        if key:
            by_company.setdefault(key, []).append(job)

    proposals = []
    for email in results:
        intent = email.get("intent", "")
        if intent not in STATUS_MAP:
            continue

        enriched = dict(email)
        enriched["role"] = extract_role(
            email.get("subject", ""), email.get("body", ""), intent
        )

        candidates = by_company.get(_company_key(email.get("company", "")), [])
        job, score, reasons = best_match(enriched, candidates)
        if job is None:
            continue

        current = (job.get("application") or {}).get("status")
        new_status = resolve_status(intent, current)
        if new_status is None:
            continue

        if score >= AUTO_APPLY:
            action = "auto"
        elif score >= CONFIRM:
            action = "confirm"
        else:
            action = "skip"

        proposals.append(
            {
                "job_id": job.get("path") or job.get("id"),
                "job_title": job.get("title"),
                "company": job.get("company"),
                "email_subject": email.get("subject"),
                "email_role": enriched["role"],
                "intent": intent,
                "current_status": current,
                "new_status": new_status,
                "confidence": round(score, 2),
                "action": action,
                "reasons": reasons,
            }
        )
    return proposals


def apply_updates(
    proposals: List[Dict[str, Any]], include_confirmed: bool = False
) -> int:
    """Writes the proposed statuses. Returns how many were applied.

    Only 'auto' proposals are written unless include_confirmed is set,
    which a caller passes after a person has actually reviewed them.
    """
    allowed = {"auto"} | ({"confirm"} if include_confirmed else set())
    applied = 0

    for proposal in proposals:
        if proposal["action"] not in allowed:
            continue
        job_id = proposal["job_id"]
        if not job_id:
            continue
        try:
            with jd_source.resolved_jd(job_id) as (path, _is_db):
                jd_manager.save_application_status(path, proposal["new_status"])
            applied += 1
        except (LookupError, OSError):
            continue
    return applied


def _normalize_company(name: str) -> str:
    """Same folding inbox_sync uses, kept local so this module can be
    imported without pulling in the IMAP layer."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    cleaned = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|co|company|group|holdings)\b", " ", cleaned
    )
    return " ".join(cleaned.split())


def _company_key(name: str) -> str:
    """Whitespace-free company key.

    A company name reaches us two ways -- from a saved role ("Khan
    Academy") and from a sender domain ("khanacademy.org" -> "khanacademy")
    -- and those never compare equal with spaces preserved. Every company
    lookup here keys on the collapsed form so the two agree.
    """
    return _normalize_company(name).replace(" ", "")
