"""Fails if the operator's own identity is hardcoded anywhere in tests/.

This is deliberately NOT a list of one person's details. It reads the
ACTIVE profile's profile.yml at runtime and searches tests/ for those
values -- so it protects whoever is running it. If Dominick clones this
repo, sets up his own profile, and then writes a test containing his own
email address, this fails for him exactly as it would have failed for the
original author.

Why this matters beyond privacy: a test that hardcodes the operator's
details is a test that only passes on the operator's machine, or worse,
passes everywhere while silently asserting something about one particular
person's resume rather than about the pipeline. Use tests/persona.py.

Skips cleanly when there is no configured profile to compare against (a
fresh clone, CI) -- there is nothing to leak in that case.
"""

import os
import re
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(TESTS_DIR), "scripts")
sys.path.insert(0, SCRIPTS_DIR)
# tests/ itself, so `import persona` works both under `discover -s tests`
# (where tests/ is the top-level dir) and under `python -m unittest
# tests.test_no_operator_identity` (where it is not).
sys.path.insert(0, TESTS_DIR)

import profile_paths  # noqa: E402

# Files exempt from the scan, with the reason. Keep this list short and
# justified -- an entry here is a place the rule does not hold.
_EXEMPT = {
    # Asserts that a PREVIOUS user's identity does NOT leak into a new
    # profile, so it necessarily names fragments of one. Those fragments
    # are deliberately partial ("Escott", not a full address) and exist
    # only to be searched for in output that must not contain them.
    "test_bootstrap_first_run.py",
    # This file: it builds the very patterns it searches for.
    "test_no_operator_identity.py",
}

# Values too short or too common to search for without false positives.
_MIN_LEN = 5


# RFC 2606 reserved domains and the NANP 555-01xx block: set aside for
# fiction precisely so they can be used in examples and test fixtures.
_RESERVED_PATTERNS = (
    re.compile(r"@(example|invalid|test|localhost)\.(com|org|net|edu)?", re.IGNORECASE),
    re.compile(r"\b555-?01\d\d\b"),
)


def _is_reserved_fictional(value: str) -> bool:
    return any(p.search(value) for p in _RESERVED_PATTERNS)


def _operator_values() -> dict:
    """{label: value} pulled from the active profile's own profile.yml."""
    try:
        candidate = (profile_paths.profile_yaml() or {}).get("candidate") or {}
    except Exception:
        return {}

    values = {}
    for key in ("full_name", "email", "phone", "location", "linkedin"):
        raw = candidate.get(key)
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        if len(raw) < _MIN_LEN:
            continue
        if _is_reserved_fictional(raw):
            # A value from a reserved-for-fiction range (555-01xx numbers,
            # example.com addresses) cannot identify a real person, and the
            # test fixtures legitimately use those same ranges. Scanning for
            # it would flag every fixture as a leak.
            continue
        values[key] = raw
        # Also catch the bare local-part of an email -- hardcoding
        # "someone.name" is the same problem as the full address.
        if key == "email" and "@" in raw:
            local = raw.split("@", 1)[0]
            if len(local) >= _MIN_LEN:
                values["email_local"] = local
        # Deliberately NOT each name part on its own. A given name is too
        # generic to search for: the profile DIRECTORY is often named after
        # it, so "profiles/<name>/..." appears in fixture paths and in the
        # comments that explain why a given test is shaped the way it is.
        # Flagging those produced noise and pressure to delete accurate
        # documentation. The surname is caught via full_name and the email
        # local-part, which is where the identifying signal actually is.
        if key == "full_name":
            surname = raw.split()[-1] if raw.split() else ""
            if len(surname) >= _MIN_LEN and " " in raw:
                values["surname"] = surname
    return values


def _test_files():
    for name in sorted(os.listdir(TESTS_DIR)):
        if not name.endswith(".py") or name in _EXEMPT:
            continue
        yield name, os.path.join(TESTS_DIR, name)


class NoOperatorIdentityInTests(unittest.TestCase):

    def setUp(self):
        self.values = _operator_values()
        if not self.values:
            self.skipTest(
                "No configured profile to compare against -- nothing to leak."
            )

    def test_no_test_file_contains_the_operators_identity(self):
        offenders = []
        for name, path in _test_files():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                continue
            for label, value in self.values.items():
                if re.search(re.escape(value), body, re.IGNORECASE):
                    offenders.append(f"{name}: contains {label} ({value!r})")

        self.assertEqual(
            [],
            offenders,
            "The operator's own identity is hardcoded in these test files. "
            "Use tests/persona.py instead -- a test needs *an* identity, not "
            "*this* identity:\n  " + "\n  ".join(offenders),
        )


class PersonaIsActuallyNeutral(unittest.TestCase):
    """The replacement persona must not itself be someone real."""

    def test_persona_uses_reserved_fictional_phone_range(self):
        import persona

        # 555-01xx is the NANP block reserved for fiction.
        self.assertRegex(persona.PHONE, r"555-01\d\d")

    def test_persona_uses_reserved_example_domain(self):
        import persona

        # example.com/.org/.net are RFC 2606 reserved and can never be
        # registered by a real person.
        self.assertTrue(persona.EMAIL.endswith("@example.com"))

    def test_persona_location_is_geocodable(self):
        """The radius and distance tests need a real place, not a made-up
        one -- otherwise they assert against a None centroid."""
        import geo_distance
        import persona

        self.assertIsNotNone(
            geo_distance.get_city_centroid(persona.CITY, persona.STATE)
        )
        self.assertIsNotNone(
            geo_distance.get_city_centroid(persona.FAR_CITY, persona.FAR_STATE)
        )

    def test_persona_profile_name_is_not_a_real_profile(self):
        import persona

        self.assertNotIn(persona.PROFILE, profile_paths.available_profiles())


if __name__ == "__main__":
    unittest.main()
