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

import datetime
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

import profile_paths
import requests
from atomic_write import atomic_write
from bs4 import BeautifulSoup
from gemini_client import GeminiClient

CANDIDATE_PATHS = [
    "/about",
    "/about-us",
    "/company",
    "/our-story",
    "/who-we-are",
    "/mission",
    "/values",
    "/culture",
    "/team",
    "/careers",
    "/jobs",
    # The homepage itself, last: plenty of small/local employers have no
    # About page at all, and their homepage is the only prose they publish.
    # Only reached when every page above came up short of EARLY_STOP_CHARS.
    "",
]
MIN_USEFUL_CHARS = 200
EARLY_STOP_CHARS = 1500
MAX_TOTAL_CHARS = 6000
REQUEST_TIMEOUT_SECONDS = 10

# A browser User-Agent: the requests default ("python-requests/x") is
# refused outright by a large share of company sites (Cloudflare and most
# WAFs 403 it), which silently sent those companies to the weaker tiers.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Grounded search can surface a job board's or review site's listing
# instead of the company's own site (e.g. a LinkedIn company page ranking
# above the real domain) -- these are never a usable company_website for
# fetch_company_pages()'s About/Mission scraping, so any match is rejected.
_REJECTED_DOMAINS = (
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "google.com",
    "wikipedia.org",
    "crunchbase.com",
    "ziprecruiter.com",
    # ATS hosts: a board is the company's job list, not its About page.
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "icims.com",
    "smartrecruiters.com",
    "bamboohr.com",
    "jobvite.com",
    "rippling.com",
    # Social/directory listings: what grounded search tends to surface for
    # small local employers instead of their own site.
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "yelp.com",
    "bbb.org",
    "zoominfo.com",
    "mapquest.com",
    # Business directories and contact-data sites: they rank highly for a
    # small company's name and are never the company itself (a live
    # DuckDuckGo sample returned bizapedia.com and seamless.ai as the top
    # "site" for 2 of 10 employers).
    "bizapedia.com",
    "seamless.ai",
    "rocketreach.co",
    "apollo.io",
    "dnb.com",
    "opencorporates.com",
    "manta.com",
    "buzzfile.com",
    "signalhire.com",
    "lusha.com",
    "owler.com",
    "cbinsights.com",
    "pitchbook.com",
    "craft.co",
    "comparably.com",
    "builtin.com",
    "wellfound.com",
    "trustpilot.com",
    "bloomberg.com",
    "yellowpages.com",
)


def is_usable_company_site(url: str) -> bool:
    """False for job boards, ATS hosts, and social/directory sites -- none is
    ever the company's own About/Mission pages. Matched on the host SUFFIX,
    not a substring of the URL: a substring check would let "x.com" reject
    fedex.com and box.com."""
    raw = (url or "").strip()
    if not raw:
        return False
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    host = (urlparse(raw).hostname or "").lower()
    if not host:
        return False
    return not any(host == d or host.endswith("." + d) for d in _REJECTED_DOMAINS)


# Gemma, not Gemini 3: Google Search grounding quota is per model FAMILY on
# the free tier, and it is ZERO for every Gemini 3 model (so these calls
# 429'd every time on gemini-3.1-flash-lite) while the Gemma 4 models sit in
# the "Default" group at 1.5K grounded requests/day. The 2.0/2.5 families
# also have grounding quota but answer 404 to new projects. Verified live
# 2026-09-13: gemma-4-31b-it returned the right site with groundingMetadata
# present. Gemma 500s intermittently; generate()'s retries absorb that.
FIND_WEBSITE_MODEL = "gemma-4-31b-it"
SEARCH_RESEARCH_MODEL = "gemma-4-31b-it"

# Tier 2's self-reported confidence. Anything but "high" falls through to
# Tier 3 -- many companies share a name, and a confidently-wrong writeup
# about the wrong Acme is worse than falling back to the JD's own text.
_CONFIDENCE_PATTERN = re.compile(
    r"^\s*CONFIDENCE:\s*(high|medium|low)\b", re.IGNORECASE
)


def _candidate_urls(company_website: str) -> list:
    # Origin only. A JD's company_website or a search hit is often a deep
    # link (acme.com/careers/123), and appending /about to that produced
    # acme.com/careers/123/about -- a 404 on every single candidate.
    raw = company_website.strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else raw.rstrip("/")
    return [f"{base}{path}" for path in CANDIDATE_PATHS]


_BOILERPLATE_TAGS = ["script", "style", "nav", "header", "footer", "aside"]
_BOILERPLATE_SELECTORS = [
    '[class*="cookie" i]',
    '[id*="cookie" i]',
    '[class*="consent" i]',
    '[id*="consent" i]',
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


_RENDER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "render-page-text.mjs"
)
RENDER_TIMEOUT_SECONDS = 60
_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"


def fetch_rendered_text(urls: list) -> dict:
    """{url: visible text} for each URL, rendered in headless Chromium via
    render-page-text.mjs -- the fallback for JavaScript-only sites, whose
    plain HTML is an empty shell. Returns {} on any failure (no Node, no
    Playwright browser, timeout) and never raises. Also {} under unittest
    unless RESUME_ALLOW_TEST_NETWORK is set: a real browser session is
    network I/O the suite must never start on its own (the same rule as
    websearch_ddg.search() and the liveness sweep)."""
    if not urls:
        return {}
    if "unittest" in sys.modules and not os.environ.get(_TEST_NETWORK_ENV):
        return {}
    try:
        result = subprocess.run(
            ["node", _RENDER_SCRIPT, *urls],
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


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
    host_unreachable = False

    for url in _candidate_urls(company_website):
        try:
            response = requests.get(
                url, timeout=REQUEST_TIMEOUT_SECONDS, headers=_HEADERS
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # The HOST is unreachable, not just this page -- trying the
            # remaining candidates would only add a timeout each (up to two
            # minutes of dead air on a dead domain) for the same result.
            host_unreachable = True
            break
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
    if len(combined) < MIN_USEFUL_CHARS and not host_unreachable:
        # The site answered but served (almost) no text -- the signature of
        # a JavaScript-rendered site, whose HTML is an empty shell until a
        # browser runs it. Render just its About page and homepage; a dead
        # host is skipped, since a browser would only time out as well.
        urls = _candidate_urls(company_website)
        rendered = fetch_rendered_text([urls[0], urls[-1]])
        extra = " ".join(
            re.sub(r"\s+", " ", text).strip() for text in rendered.values() if text
        )
        combined = f"{combined} {extra}".strip()
    return combined[:MAX_TOTAL_CHARS]


_LEGAL_WORDS = {
    "inc",
    "llc",
    "ltd",
    "limited",
    "co",
    "corp",
    "corporation",
    "company",
    "the",
    "plc",
    "lp",
    "llp",
}


def _normalized_words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def _compact_name(company_name: str) -> str:
    return "".join(
        w for w in _normalized_words(company_name).split() if w not in _LEGAL_WORDS
    )


# Second-level labels under a country code ("acme.co.uk"), so the site root
# keeps three labels there instead of two.
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu"}
# Words a company commonly wraps around its own name in its domain.
_HOST_AFFIXES = (
    "the",
    "get",
    "try",
    "join",
    "my",
    "go",
    "hq",
    "app",
    "use",
    "hello",
    "team",
    "usa",
    "us",
    "inc",
    "group",
    "careers",
    "jobs",
    "s",
)


def _registrable_labels(url: str) -> list:
    """Host labels trimmed to the registrable domain: ui.elevenlabs.io ->
    [elevenlabs, io]; acme.co.uk keeps three."""
    labels = [l for l in _host_of(url).split(".") if l]
    if len(labels) > 2:
        keep = 3 if labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2 else 2
        labels = labels[-keep:]
    return labels


def _site_root(url: str) -> str:
    """The company's main site for a matched result: subdomains dropped
    (ui.elevenlabs.io and id.tripleten.com were matched live -- a design
    system and a login page), except "www", which some sites require."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    root = ".".join(_registrable_labels(url))
    www = (parsed.hostname or "").lower().startswith("www.")
    return f"{parsed.scheme or 'https'}://{'www.' if www else ''}{root}"


def _host_names_company(url: str, compact: str) -> bool:
    """True when the domain's main label IS the company name, optionally
    wrapped in one common affix (theladders.com, manpowergroupusa.com).
    Plain containment was too loose: live, "Skill" matched gskill.com
    (G.Skill), "Sona" sonagrouptours.com and "KOPA" m-kopa.com."""
    labels = _registrable_labels(url)
    if not labels:
        return False
    label = re.sub(r"[^a-z0-9]", "", labels[0])
    if label == compact:
        return True
    return any(label in (a + compact, compact + a) for a in _HOST_AFFIXES)


def _looks_like_the_company(result: dict, company_name: str) -> bool:
    """Whether one search result is plausibly the company's OWN site.

    Researching the wrong company is worse than researching none -- the
    JD-text tier is always there -- so only strong evidence is accepted:
    the domain's main label IS the name (acorns.com, theladders.com -- see
    _host_names_company), or a HOMEPAGE whose title opens with the name
    (adr.org for "American Arbitration Association"). A directory's deep
    link titled with the name (somedirectory.com/company/acme-roofing)
    fails both."""
    url = (result.get("url") or "").strip()
    if not is_usable_company_site(url):
        return False
    compact = _compact_name(company_name)
    if len(compact) < 4:
        return False
    if _host_names_company(url, compact):
        return True
    # Title evidence counts only for a MULTI-WORD name, and only on a whole-
    # word boundary. A single generic word is not evidence of which company
    # this is: live, "Skill" matched a homepage titled "Skillsoft ..." (a
    # raw startswith) and "Sona" one titled "Sona Group Tours". One-word
    # names still match by domain above; otherwise they fall through to the
    # grounded search in find_company_website().
    name = _normalized_words(company_name)
    if len(name.split()) < 2:
        return False
    title = _normalized_words(result.get("title"))
    path = urlparse(url if "://" in url else f"https://{url}").path
    return path in ("", "/") and (title == name or title.startswith(name + " "))


def _find_website_via_search_engine(company_name: str) -> str | None:
    """Free website lookup via DuckDuckGo (websearch_ddg), tried before the
    grounded Gemma lookup below: it costs no quota at all, and on the live
    corpus it found 30 of 44 sites on its own (2026-09-13). Returns the
    company's site root (see _site_root), or None."""
    import websearch_ddg

    for result in websearch_ddg.search(
        f'"{company_name}" official website', max_results=8
    ):
        if _looks_like_the_company(result, company_name):
            return _site_root(result["url"])
    return None


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

    # Free and quota-less first; the grounded Gemini call only helps on a
    # project whose tier grants search grounding (see the helper's docstring).
    found = _find_website_via_search_engine(company_name)
    if found:
        return found

    try:
        text, _ = GeminiClient.generate(
            model=FIND_WEBSITE_MODEL,
            system_instruction=(
                "You find companies' official website homepage URLs. "
                "Reply with exactly one URL and nothing else -- no "
                "markdown, no explanation, no citation brackets."
            ),
            contents=f'What is the official website homepage URL for the company "{company_name}"?',
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

    if not is_usable_company_site(url):
        return None
    return url


def research_company_via_search(
    company_name: str, context_hint: str = ""
) -> str | None:
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

    hint = (
        f"\n\nContext from the job posting (use this to disambiguate same-named companies): {context_hint}"
        if context_hint
        else ""
    )

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
            contents=f'Research the company "{company_name}".{hint}',
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

    body = text[match.end() :].strip()
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


def apply_vocabulary_substitutions_to_resume(
    resume_data: dict, substitutions: list
) -> dict:
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
            (
                apply_vocabulary_substitutions(bullet, substitutions)
                if isinstance(bullet, str)
                else bullet
            )
            for bullet in achievements
        ]

    return resume_data


# --- Per-company cache ------------------------------------------------------
# Research describes the COMPANY, not the role, so two roles at one employer
# should not each pay for a site scrape plus a Gemini extraction (and, for
# LinkedIn-sourced roles, a grounded website search too). Only the
# company-level tiers (website, search) are cached: the JD-text tier is
# derived from one posting and would leak that posting into another's.
CACHE_TTL_DAYS = 90
_CACHE_FILENAME = "company_research_cache.json"


def _cache_path() -> str:
    return os.path.join(profile_paths.data_dir(), _CACHE_FILENAME)


def _cache_disabled() -> bool:
    """Fail closed under tests that have not isolated the profile -- the
    same guard db.upsert_job uses. Reading the developer's real cache would
    make research tests nondeterministic; writing it would pollute it."""
    try:
        import db

        return db._is_unisolated_test_write()
    except Exception:
        return "unittest" in sys.modules


def _company_key(company_name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (company_name or "").lower()).split())


def _host_of(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    host = (urlparse(raw).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _read_cache() -> dict:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_cached_research(company_name: str, company_website: str = "") -> dict | None:
    """Fresh cached research for this company, or None. A known, usable
    website whose host differs from the cached one counts as a miss: two
    different companies can share a name, and the site is the better
    identity."""
    key = _company_key(company_name)
    if not key or _cache_disabled():
        return None
    entry = _read_cache().get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("research"), dict):
        return None
    try:
        saved = datetime.datetime.fromisoformat(entry.get("saved_at") or "")
    except ValueError:
        return None
    if (datetime.datetime.now() - saved).days > CACHE_TTL_DAYS:
        return None
    known_host = (
        _host_of(company_website) if is_usable_company_site(company_website) else ""
    )
    cached_host = entry.get("website_host") or ""
    if known_host and cached_host and known_host != cached_host:
        return None
    return entry["research"]


def save_cached_research(company_name: str, research: dict, website: str = "") -> None:
    """Best-effort -- a failed cache write never fails research itself."""
    key = _company_key(company_name)
    if not key or not isinstance(research, dict) or _cache_disabled():
        return
    if research.get("_research_source") not in ("website", "search"):
        return
    cache = _read_cache()
    cache[key] = {
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "website_host": _host_of(website),
        "research": research,
    }
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with atomic_write(_cache_path(), encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except OSError:
        pass
