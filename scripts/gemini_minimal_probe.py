#!/usr/bin/env python3
"""
Minimal direct Gemini/Gemma health probe.

This intentionally bypasses resume-builder's normal client, context cache,
schemas, tools, retry logic, vector store, and full prompts. It tests whether
the selected Gemini API model can answer a tiny standalone request.
"""

import os
import sys
import time

import profile_paths
import requests
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=True)

DEFAULT_MODEL = "gemini-3.1-flash-lite"
MODEL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL

KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not KEY:
    raise SystemExit(
        "No Gemini key found.\n"
        f"Checked active profile .env: {profile_paths.env_path()}\n"
        "Expected GEMINI_API_KEY or GOOGLE_API_KEY."
    )

url = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)

payload = {
    "contents": [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Reply with exactly this text and nothing else: "
                        "gemini probe ok"
                    )
                }
            ],
        }
    ],
    "generationConfig": {
        "temperature": 0,
        "maxOutputTokens": 20,
        "thinkingConfig": {
            "thinkingLevel": "minimal",
        },
    },
}

print()
print("═" * 72)
print("Gemini/Gemma Minimal Health Probe")
print("═" * 72)
print(f"Profile: {profile_paths.active_profile()}")
print(f"Model:   {MODEL}")
print(f"Key:     loaded ({KEY[-4:]})")
print(f"URL:     {url}")
print("═" * 72)
print()

for attempt in range(1, 6):
    started = time.perf_counter()

    try:
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        elapsed = time.perf_counter() - started
        print(
            f"[{attempt}/5] TRANSPORT ERROR in {elapsed:.1f}s — "
            f"{type(exc).__name__}: {exc}"
        )
        if attempt < 5:
            print("         Waiting 20 seconds before the next probe...")
            time.sleep(20)
        continue

    elapsed = time.perf_counter() - started
    print(f"[{attempt}/5] HTTP {response.status_code} in {elapsed:.1f}s")

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            print(
                f"         ERROR: HTTP 200 but body was not JSON: {response.text[:500]!r}"
            )
        else:
            candidate = data.get("candidates", [{}])[0]
            finish_reason = candidate.get("finishReason")
            parts = candidate.get("content", {}).get("parts", [])

            text = "".join(
                part.get("text", "") for part in parts if not part.get("thought")
            ).strip()

            thought_parts = sum(1 for part in parts if part.get("thought"))
            usage = data.get("usageMetadata", {})

            print(f"         Finish reason: {finish_reason!r}")
            print(
                f"         Parts: {len(parts)} total "
                f"({thought_parts} thought, {len(parts) - thought_parts} answer)"
            )
            print(f"         Response: {text!r}")

            if usage:
                print(
                    "         Usage: "
                    f"prompt={usage.get('promptTokenCount', '?')} | "
                    f"output={usage.get('candidatesTokenCount', '?')} | "
                    f"total={usage.get('totalTokenCount', '?')}"
                )

            if not text:
                print(
                    "         WARNING: HTTP 200 returned, but no non-thought text was found."
                )
                print(f"         Raw candidate: {candidate!r}")

    else:
        print(f"         Body: {response.text[:1000]}")

    if attempt < 5:
        print("         Waiting 20 seconds before the next probe...")
        time.sleep(20)

print()
print("═" * 72)
print("Probe complete.")
print("═" * 72)
