"""
Quick smoke-test: calls find_company_website() and research_company_via_search()
on a handful of companies from dom_companiestotrack.ods to verify that:

  1. Dom's GEMINI_API_KEY is live and search grounding works at all
  2. Whether gemini-2.0-flash works (vs. 404ing like it does on some projects)
  3. The Gemma 4 baseline still works as a fallback

Run from the repo root with Dom's profile active:

    RESUME_PROFILE=dominick python scripts/test_grounding_sample.py

Or via the resume shortcut:

    RESUME_PROFILE=dominick python scripts/test_grounding_sample.py

Prints results + which model tier actually answered, then exits.
Does NOT write anything to disk or touch any JD files.
"""

import os
import sys
import time

# Must be run from the repo root so imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

PROFILE = os.environ.get("RESUME_PROFILE", "dominick")
os.environ.setdefault("RESUME_PROFILE", PROFILE)

import company_research  # noqa: E402
import gemini_client  # noqa: E402
import profile_paths  # noqa: E402

SAMPLE_COMPANIES = [
    "PCB Piezotronics",
    "Stellar Technology",
    "Encorus Group",
    "Viridi",
    "LaBella Associates",
]

# Models to probe for grounding support.
# gemma-4-31b-it = known working on free tier.
# gemini-2.0-flash = has 1.5K quota shown in AI Studio but 404'd on some projects.
PROBE_MODELS = [
    ("gemma-4-31b-it", "Gemma 4 (baseline)"),
    ("gemini-2.0-flash", "Gemini 2.0 Flash"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
]

SEARCH_TOOL = [{"google_search": {}}]


def probe_model(model: str, label: str) -> None:
    """Fire one grounded call at the model, report whether it worked."""
    prompt = 'What is the official careers page URL for "PCB Piezotronics"? Reply with the URL only.'
    print(f"\n  [{label}]  model={model}")
    start = time.monotonic()
    try:
        text, meta = gemini_client.generate_grounded(
            model=model,
            prompt=prompt,
            tools=SEARCH_TOOL,
            max_retries=1,
        )
    except Exception as e:
        print(f"    ERROR: {e}")
        return
    elapsed = time.monotonic() - start
    chunks = meta.get("groundingChunks") or []
    if text is None:
        print(f"    RESULT: None (404 or quota exhausted) — {elapsed:.1f}s")
    else:
        print(f"    RESULT: {text!r}")
        print(f"    grounding chunks: {len(chunks)}  |  elapsed: {elapsed:.1f}s")
        if chunks:
            for c in chunks[:3]:
                uri = (c.get("web") or {}).get("uri", "?")
                title = (c.get("web") or {}).get("title", "?")
                print(f"      · {title[:60]}  →  {uri[:80]}")


def find_websites(companies: list[str]) -> None:
    print("\n── find_company_website() (DDG → Gemma grounding fallback) ──")
    for name in companies:
        start = time.monotonic()
        url = company_research.find_company_website(name)
        elapsed = time.monotonic() - start
        status = url if url else "(not found)"
        print(f"  {name:<30}  {status}  [{elapsed:.1f}s]")
        time.sleep(0.5)  # light pacing


def research_companies(companies: list[str]) -> None:
    print("\n── research_company_via_search() (grounded writeup) ──")
    for name in companies[:2]:  # only 2 — these are longer calls
        print(f"\n  {name}:")
        start = time.monotonic()
        result = company_research.research_company_via_search(name)
        elapsed = time.monotonic() - start
        if result:
            preview = result[:300].replace("\n", " ")
            print(f"    {preview}…  [{elapsed:.1f}s]")
        else:
            print(f"    (no result)  [{elapsed:.1f}s]")
        time.sleep(1.0)


if __name__ == "__main__":
    print(f"Profile: {profile_paths.active_profile()}")
    print(f"API keys loaded: {len(gemini_client.api_keys())}")

    # 1. Model probe — tests each model family directly.
    print("\n══ Grounding model probe (single query each) ══")
    for model, label in PROBE_MODELS:
        probe_model(model, label)
        time.sleep(1.0)

    # 2. find_company_website — exercises the DDG-first, Gemma-fallback path.
    find_websites(SAMPLE_COMPANIES)

    # 3. research_company_via_search — the heavier grounded writeup call.
    research_companies(SAMPLE_COMPANIES)

    print("\n── done ──")
