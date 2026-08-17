"""
company_research.py — Fetches a company's About/Mission/Careers pages via
plain requests/BeautifulSoup (no browser automation, no search API) for
ResumeEngine.research_company() to feed into a Gemini call.

Deliberately not an agentic/WebFetch-driven process (career-ops's
approach) -- matches the plain-scraper pattern already proven in
scan_linkedin.py, keeping Claude's role bounded to build-time work, not
runtime operation.

find_company_website() and research_company_via_search() are the exceptions
to "no search API" above -- both are real, separate Gemini calls using
Google Search grounding, used as fallbacks when no company_website is
already known from the JD source, or when the site that is known turns out
to be unscrapeable/too thin (see ResumeEngine.research_company()). Both are
kept as distinct plain-text calls (no response_schema) rather than folded
into the extraction call, since grounding tools and structured JSON output
can't be combined in a single Gemini call.
"""

import re

import requests
from bs4 import BeautifulSoup

from gemini_client import GeminiClient

CANDIDATE_PATHS = ["/about", "/about-us", "/mission", "/values", "/culture", "/team", "/careers", "/jobs"]
MIN_USEFUL_CHARS = 200
EARLY_STOP_CHARS = 1500
MAX_TOTAL_CHARS = 6000
REQUEST_TIMEOUT_SECONDS = 10

# Grounded search can surface a job board's or review site's listing
# instead of the company's own site (e.g. a LinkedIn company page ranking
# above the real domain) -- these are never a usable company_website for
# fetch_company_pages()'s About/Mission scraping, so any match is rejected.
_REJECTED_DOMAINS = (
    "linkedin.com", "indeed.com", "glassdoor.com", "google.com",
    "wikipedia.org", "crunchbase.com", "ziprecruiter.com",
)
FIND_WEBSITE_MODEL = "gemini-3.1-flash-lite"
SEARCH_RESEARCH_MODEL = "gemini-3.1-flash-lite"

# Tier 2's self-reported confidence. Anything but "high" falls through to
# Tier 3 -- many companies share a name, and a confidently-wrong writeup
# about the wrong Acme is worse than falling back to the JD's own text.
_CONFIDENCE_PATTERN = re.compile(r"^\s*CONFIDENCE:\s*(high|medium|low)\b", re.IGNORECASE)


def _candidate_urls(company_website: str) -> list:
    base = company_website.rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return [f"{base}{path}" for path in CANDIDATE_PATHS]


_BOILERPLATE_TAGS = ["script", "style", "nav", "header", "footer", "aside"]
_BOILERPLATE_SELECTORS = [
    '[class*="cookie" i]', '[id*="cookie" i]',
    '[class*="consent" i]', '[id*="consent" i]',
]


def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_BOILERPLATE_TAGS):
        tag.decompose()
    for selector in _BOILERPLATE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_company_pages(company_website: str) -> str:
    """
    Tries each candidate path in order, collecting visible text until
    EARLY_STOP_CHARS is reached or all candidates are exhausted. Returns
    combined text (capped at MAX_TOTAL_CHARS), or "" if nothing useful was
    found. Network/HTTP errors on any single candidate are caught and
    skipped -- the function moves on rather than aborting.
    """
    collected = []
    total_chars = 0

    for url in _candidate_urls(company_website):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException:
            continue
        if response.status_code != 200:
            continue

        text = _extract_visible_text(response.text)
        if not text:
            continue

        collected.append(text)
        total_chars += len(text)
        if total_chars >= EARLY_STOP_CHARS:
            break

    combined = " ".join(collected)
    return combined[:MAX_TOTAL_CHARS]


def find_company_website(company_name: str) -> str | None:
    """
    Fallback lookup for a JD source that never surfaced a company_website
    (e.g. scan_linkedin.py's JDs today -- see ResumeEngine.research_company()'s
    call site). Uses Gemini's Google Search grounding tool to find the
    company's real external site, not its own structured-extraction call --
    grounding and response_schema can't be combined in one request.
    Returns None (never raises) on no API match, a rejected domain (job
    boards/review sites -- see _REJECTED_DOMAINS), or an unparseable
    response, so a caller can always treat None as "proceed exactly as if
    this feature didn't exist."
    """
    if not company_name:
        return None

    try:
        text, _ = GeminiClient.generate(
            model=FIND_WEBSITE_MODEL,
            system_instruction=(
                "You find companies' official website homepage URLs. "
                "Reply with exactly one URL and nothing else -- no "
                "markdown, no explanation, no citation brackets."
            ),
            contents=f"What is the official website homepage URL for the company \"{company_name}\"?",
            tools=[{"google_search": {}}],
            temperature=0.0,
        )
    except Exception:
        return None

    if not text:
        return None

    match = re.search(r"https?://[^\s\"'<>\]\)]+", text)
    if not match:
        return None
    url = match.group(0).rstrip(".,;")

    if any(domain in url.lower() for domain in _REJECTED_DOMAINS):
        return None
    return url


def research_company_via_search(company_name: str, context_hint: str = "") -> str | None:
    """
    Tier 2 of ResumeEngine.research_company()'s fallback chain: when no
    company website is known or scrapeable, ask Gemini (with Google Search
    grounding) to describe the company's tone, values, and language
    directly.

    Like find_company_website(), this is a plain-text call with no
    response_schema -- grounding and structured output can't be combined
    in one request. Its output is fed to the same research_company.md
    extraction call the scraped-page path uses, so there's exactly one
    place that produces CompanyResearchSchema.

    The model self-reports confidence on a leading `CONFIDENCE:` line, and
    only "high" is trusted; anything else (including a missing or
    unparseable line) returns None so the caller falls through to Tier 3.
    Returns None on any failure and never raises.
    """
    if not company_name:
        return None

    hint = f"\n\nContext from the job posting (use this to disambiguate same-named companies): {context_hint}" if context_hint else ""

    try:
        text, _ = GeminiClient.generate(
            model=SEARCH_RESEARCH_MODEL,
            system_instruction=(
                "You research companies' public voice and values. Your first "
                "line must be exactly 'CONFIDENCE: high', 'CONFIDENCE: medium', "
                "or 'CONFIDENCE: low' -- reporting how certain you are that "
                "you found the specific company asked about, not how much you "
                "found. Say 'high' only when the identifying details you found "
                "clearly match the company described. Many companies share a "
                "name; if you cannot tell which one this is, say 'low'. After "
                "that line, describe in plain prose: what the company does, "
                "their stated mission and values, the tone of their public "
                "writing, and any distinctive words they use for everyday "
                "things (for example calling customers 'guests'). Use only "
                "what you actually found -- never fill gaps with plausible "
                "guesses."
            ),
            contents=f"Research the company \"{company_name}\".{hint}",
            tools=[{"google_search": {}}],
            temperature=0.0,
        )
    except Exception:
        return None

    if not text:
        return None

    match = _CONFIDENCE_PATTERN.match(text)
    if not match or match.group(1).lower() != "high":
        return None

    body = text[match.end():].strip()
    return body or None


def _is_word_char(char: str) -> bool:
    """Matches regex \\w: alphanumerics plus underscore."""
    return char.isalnum() or char == "_"


def _match_case(source: str, replacement: str) -> str:
    """Makes `replacement` echo `source`'s capitalization, so substituting
    mid-sentence vs. sentence-initial vs. all-caps text all read naturally.

    The >1-letter guard on the all-caps branch is load-bearing: str.isupper()
    is True for "C++" (one cased char, no lowercase), which would turn a
    "C++ -> Cpp" pair into "CPP".
    """
    if source.isupper() and sum(c.isalpha() for c in source) > 1:
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_vocabulary_substitutions(text: str, substitutions: list) -> str:
    """
    Swaps a generic noun for a company's own preferred term (e.g.
    "customers" -> "guests") in already-written text.

    Deliberately deterministic rather than an LLM rewrite: this runs over
    resume bullets, which are pre-audited verified text ("bullet bank is
    LEGO not prose inspiration", style_rules.yaml:19). A regex substitution
    can only change the target noun -- it structurally cannot alter a
    metric, a verb, or a claim, which an LLM asked to "mirror company
    vocabulary" absolutely could. See
    docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md.

    Word-boundary matched and case-preserving. Malformed pairs are skipped
    rather than raised on -- these terms come from a model, not a human.
    """
    if not text or not substitutions:
        return text

    for pair in substitutions:
        if not isinstance(pair, dict):
            continue
        generic = (pair.get("generic_term") or "").strip()
        preferred = (pair.get("company_term") or "").strip()
        if not generic or not preferred:
            continue
        # re.escape keeps a term like "C++" literal rather than a broken
        # pattern. \b only asserts a word/non-word transition, so it can't be
        # used on an edge that isn't a word char -- \bC\+\+\b never matches
        # "C++ tooling" (both '+' and ' ' are non-word). Each end therefore
        # picks \b or a lookaround depending on the term's own edge character.
        left = r"\b" if _is_word_char(generic[0]) else r"(?<!\w)"
        right = r"\b" if _is_word_char(generic[-1]) else r"(?!\w)"
        pattern = re.compile(rf"{left}{re.escape(generic)}{right}", re.IGNORECASE)
        text = pattern.sub(lambda m, p=preferred: _match_case(m.group(0), p), text)

    return text


def apply_vocabulary_substitutions_to_resume(resume_data: dict, substitutions: list) -> dict:
    """
    Applies apply_vocabulary_substitutions() to every Work Experience
    bullet in a built resume dict, in place, returning the same dict.

    Bullets only -- not SUMMARY or the Why section (both are model-written
    with the vocabulary already in their prompt context) and not Skills
    (category and tool names are precise technical terms, not
    customer-facing prose). Defensive about shape because it runs on
    model-generated JSON.
    """
    if not substitutions or not isinstance(resume_data, dict):
        return resume_data

    for role in resume_data.get("EXPERIENCE") or []:
        if not isinstance(role, dict):
            continue
        achievements = role.get("achievements")
        if not isinstance(achievements, list):
            continue
        role["achievements"] = [
            apply_vocabulary_substitutions(bullet, substitutions) if isinstance(bullet, str) else bullet
            for bullet in achievements
        ]

    return resume_data
