#!/usr/bin/env python3
"""Diagnostic script to test menu prompts with Dom's profile."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["RESUME_PROFILE"] = "dom"

import charm_prompt
import cli_art

print("=== Testing Dom's profile menu interactions ===\n")

# Test 1: Try charm_prompt.select directly
print("Test 1: charm_prompt.select()")
try:
    result = charm_prompt.select(
        "Which option?",
        choices=[
            {"label": "Option A", "value": "a"},
            {"label": "Option B", "value": "b"},
        ],
    )
    print(f"Result: {result}")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")

# Test 2: Try cli_art.select (which wraps charm_prompt)
print("\nTest 2: cli_art.select()")
try:
    result = cli_art.select(
        "Which option?",
        choices=[
            {"label": "Option A", "value": "a"},
            {"label": "Option B", "value": "b"},
        ],
    )
    print(f"Result: {result}")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")

# Test 3: Check Go binary directly
print("\nTest 3: Go binary status")
import shutil

print(f"Go available: {shutil.which('go') is not None}")
prompt_bin = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard",
    "bin",
    "prompt",
)
print(f"Prompt binary exists: {os.path.exists(prompt_bin)}")
print(f"Prompt binary executable: {os.access(prompt_bin, os.X_OK)}")

# Test 4: Check if binary is stale
print("\nTest 4: Binary staleness")
if charm_prompt._prompt_binary_is_stale():
    print("WARNING: Prompt binary is stale!")
else:
    print("Prompt binary is up to date")

print("\nDone!")
