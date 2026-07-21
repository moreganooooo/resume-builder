"""
company_research.py — Fetches a company's About/Mission/Careers pages via
plain requests/BeautifulSoup (no browser automation, no search API) for
ResumeEngine.research_company() to feed into a Gemini call.

Deliberately not an agentic/WebFetch-driven process (career-ops's
approach) -- matches the plain-scraper pattern already proven in
scan_linkedin.py, keeping Claude's role bounded to build-time work, not
runtime operation.

find_company_website() is the one exception to "no search API" above --
it's a real, separate Gemini call using Google Search grounding, used
only as a fallback when no company_website is already known from the JD
source (see ResumeEngine.research_company()). Kept as a distinct
plain-text call (no response_schema) rather than folded into the
scraped-page extraction call, since grounding tools and structured JSON
output can't be combined in a single Gemini call.
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


def _candidate_urls(company_website: str) -> list:
    base = company_website.rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return [f"{base}{path}" for path in CANDIDATE_PATHS]


def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
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
