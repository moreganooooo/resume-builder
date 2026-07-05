"""
company_research.py — Fetches a company's About/Mission/Careers pages via
plain requests/BeautifulSoup (no browser automation, no search API) for
ResumeEngine.research_company() to feed into a Gemini call.

Deliberately not an agentic/WebFetch-driven process (career-ops's
approach) -- matches the plain-scraper pattern already proven in
scan_linkedin.py, keeping Claude's role bounded to build-time work, not
runtime operation.
"""

import re

import requests
from bs4 import BeautifulSoup

CANDIDATE_PATHS = ["/about", "/about-us", "/mission", "/values", "/culture", "/team", "/careers", "/jobs"]
MIN_USEFUL_CHARS = 200
EARLY_STOP_CHARS = 1500
MAX_TOTAL_CHARS = 6000
REQUEST_TIMEOUT_SECONDS = 10


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
