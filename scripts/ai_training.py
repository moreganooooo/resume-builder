"""Detects AI-training gig postings: contract work producing training and
evaluation data for AI labs ("AI Trainer", "evaluate AI-generated
responses", "$40/hour -- Domain Expert").

These are real, paid, and often a strong skills match, so the evaluator
scores many of them at the top of a pipeline -- where they crowd out
permanent roles. This module only LABELS them; the dashboard offers an
opt-in view filter. Nothing here changes a score or drops a posting.

Measured against both profiles' pending corpora (2026-09-23) before
choosing the rules, and the shape of the rules is what that showed:

* ``employment_type`` is no signal -- Green Key's "AI Trainer" is tagged
  Full-time. Green Key itself is a general staffing agency (its "Data
  Scientist" posting is an ordinary role), so it is not a platform here.
* Single keywords are noise. "RLHF", "annotation", "LLM evaluation" and
  "training data" appear as SKILLS in real engineering roles (ElevenLabs,
  Deepgram, Fetch, Angi, SentiLink) and must not flag them. Nor does
  "improve AI": "build and improve AI voice agents" is engineering.
* The postings that are AI-training work describe the WORK itself in a
  handful of distinctive phrasings ("evaluate AI model outputs", "AI
  training projects", "partnering with a leading AI lab"), or carry a
  gig-shaped title ("AI Trainer", "... - $60/hour").

So a posting is flagged by any one of: a known AI-training platform as
employer, a gig-shaped title, or a work phrase. Each returns the evidence
that fired, so a wrong label is easy to see and correct.
"""

import re

# Companies whose business IS supplying human training/evaluation data to
# AI labs. Matched on the normalized employer name, whole-word.
PLATFORMS = (
    "24-mag",
    "alignerr",
    "codefeast",
    "crossing hurdles",
    "dataannotation",
    "data annotation tech",
    "deccan ai",
    "handshake ai",
    "invisible technologies",
    "mercor",
    "micro1",
    "outlier",
    "scale ai",
    "remotasks",
    "toloka",
    "turing",
    "weekday ai",
    "yo ai labs",
)

_TITLE_PATTERNS = (
    r"\bai (trainer|tutor|rater|evaluator|model trainer|data trainer)\b",
    r"\b(model|data|llm) trainer\b",
    r"\btrain(ing)? (ai|llms?|models)\b",
    r"\b(ai|llm|model) (evaluation|response) (specialist|expert|writer)\b",
    r"\bdomain expert\b",
    r"\btalent network\b",
    r"\bprompt (writer|engineer(ing)? contractor)\b",
    # A pay rate in the TITLE is how gig marketplaces list: "Data
    # Scientist - $75/hour". Employers put pay in the body.
    r"\$\s?\d[\d,.]*\s?(k\s?)?(/|per\s)\s?(hr|hour)\b",
)

_BODY_PATTERNS = (
    r"\bai training (sprint|project|work|task)s?\b",
    r"\b(evaluate|review|rate|rank|assess)(s|ing)? (and improve )?(the )?"
    r"(quality of )?ai[- ](generated|model) (responses|outputs?|answers)\b",
    r"\bevaluate (ai|llm|model) (model )?outputs?\b",
    # "train", not "improve": "build and improve AI voice agents" is an
    # ordinary engineering role (Angi), as is "improve AI application
    # quality" (Day & Zimmermann).
    r"\b(help )?train (their |its |our )?(latest )?(ai|llms?|large language models?|"
    r"language models?|frontier models|ai models)\b",
    r"\b(partner(ing|s)?|working) with (a |one of the )?(leading|top|world'?s leading) "
    r"(foundational )?ai (lab|labs|companies|research)",
    r"\bexpert-level prompts\b",
    r"\bprompts?, datasets?,? and reference solutions\b",
    r"\bnetwork of experienced [\w ]{3,40} for (potential )?future projects\b",
    r"\bhuman (feedback|data) for (ai|llm|frontier)",
    r"\bwrite (and|&) (evaluate|review) (responses|answers) (to|for) (ai|llm)",
)

_TITLE_RES = tuple(re.compile(p, re.I) for p in _TITLE_PATTERNS)
_BODY_RES = tuple(re.compile(p, re.I) for p in _BODY_PATTERNS)
_PLATFORM_RES = tuple(
    re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", re.I)
    for name in PLATFORMS
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("’", "'")).strip()


def classify(title: str, company: str, description: str) -> list[str]:
    """The evidence that this is an AI-training gig, or [] when it is not.

    Each item names what fired, e.g. ``platform: micro1``, ``title: AI
    Trainer``, ``body: evaluate AI model outputs``."""
    evidence = []
    company_n = _normalize(company)
    for name, pattern in zip(PLATFORMS, _PLATFORM_RES):
        if pattern.search(company_n):
            evidence.append(f"platform: {name}")
            break
    title_n = _normalize(title)
    for pattern in _TITLE_RES:
        match = pattern.search(title_n)
        if match:
            evidence.append(f"title: {match.group(0)}")
            break
    body_n = _normalize(description)
    for pattern in _BODY_RES:
        match = pattern.search(body_n)
        if match:
            evidence.append(f"body: {match.group(0)}")
            break
    return evidence


def is_ai_training(title: str, company: str, description: str) -> bool:
    """True when any rule in classify() fires."""
    return bool(classify(title, company, description))
