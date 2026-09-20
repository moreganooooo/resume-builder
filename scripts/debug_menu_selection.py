#!/usr/bin/env python3
"""Debug script to see what happens when a menu selection is made on Dom's profile."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["RESUME_PROFILE"] = "dom"

print("=" * 60)
print("DEBUG: Menu Selection Test for Dom Profile")
print("=" * 60)

import charm_prompt
import cli_art

# Test 1: Import and get choices
print("\n[1] Getting menu choices...")
try:
    from menu import _menu_choices

    choices = _menu_choices()
    print(f"    ✓ Got {len(choices)} choices")
    for i, c in enumerate(choices[:5]):
        label = getattr(c, "title", c.get("label", c) if isinstance(c, dict) else c)
        print(f"      {i}: {label}")
except Exception as e:
    print(f"    ✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 2: Try charm_prompt directly
print("\n[2] Testing charm_prompt.select() directly...")
try:
    print("    Calling charm_prompt.select()...")
    result = charm_prompt.select(
        "Test prompt (should see this):", choices=["Option A", "Option B", "Option C"]
    )
    print(f"    Result type: {type(result)}")
    print(f"    Result value: {repr(result)}")
    print(f"    Result is None: {result is None}")
    print(f"    Result bool: {bool(result)}")
except Exception as e:
    print(f"    ✗ Exception: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()

# Test 3: Try cli_art.select
print("\n[3] Testing cli_art.select()...")
try:
    print("    Calling cli_art.select()...")
    result = cli_art.select(
        "Test prompt #2 (should see this):",
        choices=["Option A", "Option B", "Option C"],
    )
    print(f"    Result type: {type(result)}")
    print(f"    Result value: {repr(result)}")
    print(f"    Result is None: {result is None}")
    print(f"    Result bool: {bool(result)}")
except Exception as e:
    print(f"    ✗ Exception: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 60)
print("Debug test complete")
print("=" * 60)
