# Engine/Profile Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate Morgan's personalization data and hardcoded business rules from the shared resume-tailoring engine, so a second profile (`profiles/dominick/`) can use the same pipeline without colliding with or overwriting her data.

**Architecture:** A new `scripts/profile_paths.py` module centralizes "which profile is active" (env-var driven, default `"morgan"`) and every path derived from it. Morgan's data migrates into `profiles/morgan/`. `tailor_resume.md`'s hardcoded business rules (bullet floors, protected bullets, page assignment, fixed credentials) move into `profile.yml` and get injected as a dynamic `=== ROLE RULES ===` context block at request time, mirroring the existing `situational_roles.py` pattern exactly.

**Tech Stack:** Python 3.10+, PyYAML, `importlib` (dynamic per-profile module loading), stdlib `unittest`.

## Global Constraints

- Full existing test suite (615 tests as of 2026-07-16, `python -m unittest discover -s tests`) must stay green after every task in this plan — run it at the end of every task, not just at the end of the plan.
- `RESUME_PROFILE` unset must resolve to `"morgan"` with zero behavior change from before this plan (backward compatibility is non-negotiable — Morgan uses this daily).
- `RESUME_PROFILE` set to a name with no matching `profiles/<name>/` directory must raise a clear error, never silently fall back to Morgan's data.
- Every new/modified path constant follows this repo's existing convention: a module-level constant computed once at import time (matching every existing script's `SCRIPT_DIR`/`PROJECT_ROOT` pattern) — no new configuration-file or dependency-injection mechanism.
- `jds/`, `output/`, and `data/` stay top-level directory names (matching `CLAUDE.md`'s already-documented paths and Morgan's existing muscle memory) — profile-scoping adds one path segment (`jds/<profile>/`, `output/<profile>/`, `data/<profile>/`), it does not relocate them under `profiles/<name>/`. Only `knowledge_base/`, `fixed_content.py`, and the new `situational_roles.yaml` live under `profiles/<name>/` directly, since those are genuinely per-user personalization content, not runtime/operational artifacts.
- No new third-party dependencies (per spec: no Jinja2 or other templating library — the dynamic-context-block pattern uses only stdlib string formatting).
- Reference design spec: `docs/superpowers/specs/2026-07-16-engine-profile-split-design.md` (committed at `15758012`).

---

### Task 1: `profile_paths.py` — the profile-resolution module

**Files:**
- Create: `scripts/profile_paths.py`
- Test: `tests/test_profile_paths.py`

**Interfaces:**
- Produces: `active_profile() -> str`, `profile_root(profile: str = None) -> str`, `kb_dir(profile: str = None) -> str`, `fixed_content_module(profile: str = None)`, `situational_roles_path(profile: str = None) -> str`, `jds_dir(profile: str = None) -> str`, `output_dir(profile: str = None) -> str`, `checkpoints_dir(profile: str = None) -> str`, `applications_md_path(profile: str = None) -> str`, `tracker_csv_path(profile: str = None) -> str`. All later tasks consume these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_profile_paths.py
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import profile_paths  # noqa: E402


class TestActiveProfile(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_defaults_to_morgan_when_unset(self):
        os.environ.pop("RESUME_PROFILE", None)
        self.assertEqual(profile_paths.active_profile(), "morgan")

    def test_returns_explicit_profile_when_directory_exists(self):
        os.environ["RESUME_PROFILE"] = "morgan"
        self.assertEqual(profile_paths.active_profile(), "morgan")

    def test_raises_on_unknown_profile(self):
        os.environ["RESUME_PROFILE"] = "nonexistent_profile_xyz"
        with self.assertRaises(ValueError):
            profile_paths.active_profile()


class TestPathHelpers(unittest.TestCase):

    def test_kb_dir_resolves_under_profile_root(self):
        expected = os.path.join(profile_paths.PROFILES_DIR, "morgan", "knowledge_base")
        self.assertEqual(profile_paths.kb_dir("morgan"), expected)

    def test_jds_dir_resolves_under_top_level_jds(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "jds", "morgan")
        self.assertEqual(profile_paths.jds_dir("morgan"), expected)

    def test_output_dir_resolves_under_top_level_output(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "output", "morgan")
        self.assertEqual(profile_paths.output_dir("morgan"), expected)

    def test_checkpoints_dir_nests_under_output_dir(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "output", "morgan", "checkpoints")
        self.assertEqual(profile_paths.checkpoints_dir("morgan"), expected)

    def test_applications_md_path_resolves_under_top_level_data(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "data", "morgan", "applications.md")
        self.assertEqual(profile_paths.applications_md_path("morgan"), expected)

    def test_tracker_csv_path_lives_inside_jds_dir(self):
        expected = os.path.join(profile_paths.PROJECT_ROOT, "jds", "morgan", "jd_tracker_log.csv")
        self.assertEqual(profile_paths.tracker_csv_path("morgan"), expected)

    def test_situational_roles_path_resolves_under_profile_root(self):
        expected = os.path.join(profile_paths.PROFILES_DIR, "morgan", "situational_roles.yaml")
        self.assertEqual(profile_paths.situational_roles_path("morgan"), expected)


class TestFixedContentModule(unittest.TestCase):

    def test_raises_import_error_for_missing_fixed_content(self):
        with self.assertRaises(ImportError):
            profile_paths.fixed_content_module("nonexistent_profile_xyz")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_profile_paths -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'profile_paths'`

- [ ] **Step 3: Write `scripts/profile_paths.py`**

```python
"""profile_paths.py — the single source of truth for "which profile is
active" and every filesystem path derived from it. Every script that used
to hand-roll its own PROJECT_ROOT/resume-engine/knowledge_base (or
PROJECT_ROOT/jds, PROJECT_ROOT/output, PROJECT_ROOT/data) path routes
through here instead, so profiles/<name>/ becomes the one place a
profile's personalization data lives, and jds/<name>/, output/<name>/,
data/<name>/ become the one place a profile's operational data lives --
with zero risk of two profiles colliding in the same checkout.

RESUME_PROFILE unset defaults to "morgan" (backward compatible with every
existing workflow). RESUME_PROFILE set to a name with no matching
profiles/<name>/ directory is a hard failure, not a silent fallback --
silently reading the wrong profile's data on a typo is exactly the bug
this module exists to prevent.
"""

import importlib.util
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PROFILES_DIR = os.path.join(PROJECT_ROOT, "profiles")


def active_profile() -> str:
    name = os.environ.get("RESUME_PROFILE")
    if name is None:
        return "morgan"
    if not os.path.isdir(os.path.join(PROFILES_DIR, name)):
        raise ValueError(
            f"RESUME_PROFILE is set to {name!r}, but profiles/{name}/ does not exist. "
            "Check for a typo, or create it via the bootstrap 'New Profile' flow."
        )
    return name


def profile_root(profile: str = None) -> str:
    return os.path.join(PROFILES_DIR, profile or active_profile())


def kb_dir(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "knowledge_base")


def situational_roles_path(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "situational_roles.yaml")


def fixed_content_module(profile: str = None):
    """Dynamically imports profiles/<profile>/fixed_content.py and returns
    the loaded module object -- the per-profile replacement for a static
    `import fixed_content`."""
    name = profile or active_profile()
    path = os.path.join(profile_root(name), "fixed_content.py")
    if not os.path.exists(path):
        raise ImportError(
            f"profiles/{name}/fixed_content.py not found -- has this profile been bootstrapped?"
        )
    spec = importlib.util.spec_from_file_location(f"fixed_content_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jds_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "jds", profile or active_profile())


def output_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "output", profile or active_profile())


def checkpoints_dir(profile: str = None) -> str:
    return os.path.join(output_dir(profile), "checkpoints")


def applications_md_path(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "data", profile or active_profile(), "applications.md")


def tracker_csv_path(profile: str = None) -> str:
    return os.path.join(jds_dir(profile), "jd_tracker_log.csv")
```

- [ ] **Step 4: `mkdir -p profiles/morgan` so `active_profile()`'s default resolves successfully**

Run: `mkdir -p /Users/morganescott/resume-builder/profiles/morgan`

(Task 2 populates this directory for real; this step just needs it to exist so `active_profile()` and the tests above pass — an empty directory is enough for `os.path.isdir()` to succeed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_profile_paths -v`
Expected: `OK` — all tests pass.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK` (615+ tests)

- [ ] **Step 7: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/profile_paths.py tests/test_profile_paths.py profiles/morgan/.gitkeep 2>/dev/null || git add scripts/profile_paths.py tests/test_profile_paths.py
git commit -m "Add profile_paths.py: centralized profile-resolution module

Single source of truth for RESUME_PROFILE resolution and every path
derived from it -- foundational for the engine/profile split, unwired
from any other script yet."
```

---

### Task 2: Migrate Morgan's data into `profiles/morgan/`

**Files:**
- Move: `resume-engine/knowledge_base/` → `profiles/morgan/knowledge_base/`
- Move: `scripts/fixed_content.py` → `profiles/morgan/fixed_content.py`
- Create: `profiles/morgan/situational_roles.yaml` (extracted from `scripts/situational_roles.py`'s current `SITUATIONAL_ROLES` dict)

**Interfaces:**
- Consumes: nothing (pure data migration)
- Produces: `profiles/morgan/knowledge_base/*`, `profiles/morgan/fixed_content.py`, `profiles/morgan/situational_roles.yaml` — every later task's file-path constants point here.

This task is a pure data move — no test-driven code changes yet. Verification is by direct filesystem/git assertion, not pytest, since there's no new logic to unit-test here (Task 3 onward wires scripts to actually *use* these new locations, and that's where behavior gets tested).

- [ ] **Step 1: Move `knowledge_base/` and `fixed_content.py` with git, preserving history**

```bash
cd /Users/morganescott/resume-builder
git mv resume-engine/knowledge_base profiles/morgan/knowledge_base
git mv scripts/fixed_content.py profiles/morgan/fixed_content.py
```

- [ ] **Step 2: Verify the moves were tracked as renames, not add+delete**

Run: `git status --short`
Expected: lines beginning `R  ` (rename) for every moved file, e.g. `R  resume-engine/knowledge_base/profile.yml -> profiles/morgan/knowledge_base/profile.yml` and `R  scripts/fixed_content.py -> profiles/morgan/fixed_content.py`. No `D`/`A` pairs for the same file.

- [ ] **Step 3: Extract `SITUATIONAL_ROLES` into `profiles/morgan/situational_roles.yaml`**

```yaml
situational_min_bullets: 2
roles:
  - display_name: "Humane Society of Greater Kansas City"
    bank_tag: "Humane Society of Greater Kansas City"
    trigger_keywords: ["animal welfare", "animal shelter", "animal rescue", "humane society", "veterinary"]
  - display_name: "Unisource Document Products"
    bank_tag: "Unisource Document Products"
    trigger_keywords: ["print production", "document management", "print services", "document solutions"]
  - display_name: "Kansas Colloquies"
    bank_tag: "Kansas Colloquies"
    trigger_keywords: ["journalism", "newspaper", "editorial", "\\breporter\\b", "news writing"]
  - display_name: "KU Payroll Office"
    bank_tag: "Payroll"
    trigger_keywords: ["payroll processing", "payroll administration", "\\bpayroll\\b"]
  - display_name: "DeJoy, Knauff & Blood"
    bank_tag: "DeJoy"
    trigger_keywords: ["tax preparation", "tax compliance", "bookkeeping", "\\baudit\\b", "accounting clerk"]
  - display_name: "USitek"
    bank_tag: "USitek"
    admin_keywords: ["clerical", "administrative support", "administrative assistant"]
    design_keywords: ["graphic design"]
```

Write this to `/Users/morganescott/resume-builder/profiles/morgan/situational_roles.yaml`.

- [ ] **Step 4: Verify the YAML parses and matches the original dict's shape**

Run:
```bash
cd /Users/morganescott/resume-builder && source .venv/bin/activate
python3 -c "
import yaml
with open('profiles/morgan/situational_roles.yaml') as f:
    data = yaml.safe_load(f)
assert data['situational_min_bullets'] == 2
assert len(data['roles']) == 6
assert data['roles'][0]['display_name'] == 'Humane Society of Greater Kansas City'
assert data['roles'][-1]['admin_keywords'] == ['clerical', 'administrative support', 'administrative assistant']
print('OK')
"
```
Expected: `OK`

- [ ] **Step 5: Run the full suite — expect failures, this is a checkpoint not a gate**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: **FAILURES** — every script still hardcodes the old `resume-engine/knowledge_base` and `scripts/fixed_content.py` paths (Tasks 3-6 fix this). Do not be alarmed; this is expected mid-migration state. Do not skip ahead — confirm the failures are exclusively `ModuleNotFoundError`/`FileNotFoundError` pointing at the old paths, not something else.

- [ ] **Step 6: Commit**

```bash
cd /Users/morganescott/resume-builder
git add profiles/morgan/situational_roles.yaml
git commit -m "Migrate Morgan's knowledge_base/ and fixed_content.py into profiles/morgan/

git mv preserves history. Extracts situational_roles.py's hardcoded
SITUATIONAL_ROLES dict into profiles/morgan/situational_roles.yaml as
data. The full test suite is expected to fail until Tasks 3-9 wire
every script through profile_paths.py -- this is a deliberate
checkpoint, not a shippable state on its own."
```

---

### Task 3: Wire `jd_manager.py` through `profile_paths` (jds/output/tracker scoping)

**Files:**
- Modify: `scripts/jd_manager.py:16-23` (path constants), `scripts/jd_manager.py:245` (`APPLICATIONS_MD`)
- Test: `tests/test_jd_manager.py` (add cases)

**Interfaces:**
- Consumes: `profile_paths.jds_dir()`, `profile_paths.checkpoints_dir()`, `profile_paths.applications_md_path()`, `profile_paths.tracker_csv_path()` (Task 1)
- Produces: `jd_manager.JDS_DIR`, `jd_manager.COMPLETED_DIR`, `jd_manager.EXPIRED_DIR`, `jd_manager.CHECKPOINTS_DIR`, `jd_manager.TRACKER_CSV`, `jd_manager.APPLICATIONS_MD` — all now profile-scoped constants that Tasks 5+ and the existing orchestrator/menu code already import unchanged (same names, same usage sites, only their *value* changes).

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_jd_manager.py
class TestProfileScopedPaths(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = "morgan"

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_jds_dir_is_profile_scoped(self):
        import importlib
        importlib.reload(jd_manager)
        self.assertTrue(jd_manager.JDS_DIR.endswith(os.path.join("jds", "morgan")))

    def test_applications_md_is_profile_scoped(self):
        import importlib
        importlib.reload(jd_manager)
        self.assertTrue(jd_manager.APPLICATIONS_MD.endswith(os.path.join("data", "morgan", "applications.md")))

    def test_tracker_csv_is_profile_scoped(self):
        import importlib
        importlib.reload(jd_manager)
        self.assertTrue(jd_manager.TRACKER_CSV.endswith(os.path.join("jds", "morgan", "jd_tracker_log.csv")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_jd_manager.TestProfileScopedPaths -v`
Expected: FAIL — `AssertionError` (paths still point at the old top-level `jds/`/`data/` locations, no `morgan` segment).

- [ ] **Step 3: Modify `scripts/jd_manager.py`'s path constants**

Replace lines 16-23:
```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

JDS_DIR = os.path.join(PROJECT_ROOT, "jds")
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
EXPIRED_DIR = os.path.join(JDS_DIR, "expired")
CHECKPOINTS_DIR = os.path.join(PROJECT_ROOT, "output", "checkpoints")
TRACKER_CSV = os.path.join(JDS_DIR, "jd_tracker_log.csv")
```
with:
```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

JDS_DIR = profile_paths.jds_dir()
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
EXPIRED_DIR = os.path.join(JDS_DIR, "expired")
CHECKPOINTS_DIR = profile_paths.checkpoints_dir()
TRACKER_CSV = profile_paths.tracker_csv_path()
```
(Add `import sys` to the top-of-file import block if not already present — check first with `grep -n "^import sys" scripts/jd_manager.py`; it is not currently imported in this file.)

- [ ] **Step 4: Modify `scripts/jd_manager.py:245`**

Replace:
```python
APPLICATIONS_MD = os.path.join(PROJECT_ROOT, "data", "applications.md")
```
with:
```python
APPLICATIONS_MD = profile_paths.applications_md_path()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_jd_manager -v`
Expected: `OK`

- [ ] **Step 6: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK` for every test that doesn't depend on `resume-engine/knowledge_base` or `fixed_content` still being at their old paths (those still fail until Tasks 4-6; confirm remaining failures are exclusively about those two, not `jd_manager`-related).

- [ ] **Step 7: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "Route jd_manager.py's jds/output/tracker paths through profile_paths

JDS_DIR, COMPLETED_DIR, EXPIRED_DIR, CHECKPOINTS_DIR, TRACKER_CSV, and
APPLICATIONS_MD now resolve per-profile (jds/<profile>/,
output/<profile>/checkpoints, data/<profile>/applications.md) instead
of one shared top-level location -- closes the collision gap found
while tracing the design's data flow."
```

---

### Task 4: Wire the 9 KB-path scripts through `profile_paths`

**Files:**
- Modify: `scripts/audit_keepers.py:80-84`, `scripts/cluster_bullet_bank.py:65-67`, `scripts/detect_hidden_gems.py:31-33`, `scripts/embed_bullet_bank.py:47-61`, `scripts/rewrite_bullets.py:101-105`, `scripts/bootstrap_bullet_bank.py:31-33`, `scripts/bootstrap_profile.py:18-20`, `scripts/render_html.py:17-19`, `scripts/render_coverletter.py:19-21`
- Test: existing tests for these modules (run as regression, no new test file — these are the same one-line constant swap repeated 9 times, already covered by each module's existing test suite exercising its file I/O)

**Interfaces:**
- Consumes: `profile_paths.kb_dir()` (Task 1)
- Produces: each script's `KB_DIR` (or `TEMPLATE_PATH`, which stays engine-shared) constant now profile-scoped.

Each of these 9 files gets the identical two-line change: add `import profile_paths` (via the same `sys.path.insert` pattern already present in each file) and replace its hardcoded `KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")` with `KB_DIR = profile_paths.kb_dir()`. `render_html.py`/`render_coverletter.py`'s `TEMPLATE_PATH` is **not** changed — templates are shared engine assets, not profile data (per the Global Constraints).

- [ ] **Step 1: `scripts/audit_keepers.py`**

Replace lines 80-84:
```python
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
RULES_DIR    = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR  = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")
```
with:
```python
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR       = profile_paths.kb_dir()
RULES_DIR    = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR  = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")
```
(This file already does `if SCRIPT_DIR not in sys.path: sys.path.insert(0, SCRIPT_DIR)` later at line 86-87 for its `rewrite_bullets` import — move that check up here, or simply confirm `sys` is already imported and add the `profile_paths` import alongside the existing block at lines 86-90 rather than duplicating the `sys.path` check. Concretely: keep the existing lines 86-90 block as-is, and add `import profile_paths` as one more line in that same `from rewrite_bullets import (...)` import group, placed *before* it.)

- [ ] **Step 2: `scripts/cluster_bullet_bank.py`**

Replace line 67:
```python
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
```
with:
```python
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR       = profile_paths.kb_dir()
```
(Confirm `sys` is imported at the top of this file; add `import sys` alongside its existing `import os` if not already present.)

- [ ] **Step 3: `scripts/detect_hidden_gems.py`**

Replace line 33:
```python
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
```
with:
```python
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR       = profile_paths.kb_dir()
```
(Confirm `import sys` is present at the top of this file; add if missing.)

- [ ] **Step 4: `scripts/embed_bullet_bank.py`**

Replace line 61:
```python
KB_DIR           = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
```
with:
```python
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR           = profile_paths.kb_dir()
```
(Confirm `import sys` is present; add if missing.)

- [ ] **Step 5: `scripts/rewrite_bullets.py`**

Replace line 103:
```python
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
```
with:
```python
KB_DIR       = profile_paths.kb_dir()
```
(This file already imports `sys` and does its own `sys.path.insert(0, SCRIPT_DIR)` at lines 109-110 immediately below, right before its `from gemini_client import ...` line 112 — add `import profile_paths` to that same import block, right after line 112.)

- [ ] **Step 6: `scripts/bootstrap_bullet_bank.py`**

Replace line 33:
```python
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
```
with:
```python
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR = profile_paths.kb_dir()
```
Note this file already has an `if SCRIPT_DIR not in sys.path: sys.path.insert(0, SCRIPT_DIR)` block at lines 44-45, *after* the constants that need it — move that check up to before line 33, or (simpler) just add the two-line `import profile_paths` block directly above line 33 as shown, and leave the existing lines 44-45 block in place (redundant `if` checks are harmless, `sys.path.insert` is idempotent-safe given the `not in sys.path` guard).

- [ ] **Step 7: `scripts/bootstrap_profile.py`**

Replace line 20:
```python
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
```
with:
```python
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR = profile_paths.kb_dir()
```
(This file's existing `if SCRIPT_DIR not in sys.path` check is at lines 36-37, after the constants — same note as Step 6: add the import block above line 20 directly; the later duplicate check is harmless.)

- [ ] **Step 8: `scripts/render_html.py`**

No change needed — `render_html.py:19`'s `TEMPLATE_PATH` points at `resume-engine/templates/`, which is shared engine content per the Global Constraints, not profile data. Confirmed no `KB_DIR` or other profile-scoped constant exists in this file. Skip.

- [ ] **Step 9: `scripts/render_coverletter.py`**

No `KB_DIR` change needed here either (same reasoning as Step 8 — `TEMPLATE_PATH` at line 21 stays engine-shared). This file's `fixed_content` import is handled separately in Task 6, not here.

- [ ] **Step 10: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: every test exercising these 7 modified scripts (`audit_keepers`, `cluster_bullet_bank`, `detect_hidden_gems`, `embed_bullet_bank`, `rewrite_bullets`, `bootstrap_bullet_bank`, `bootstrap_profile`) now passes against `profiles/morgan/knowledge_base/`. Remaining failures should be exclusively in modules touched by Tasks 5-6 (`orchestrator`, `normalize_resume`) — confirm via the test output which module each remaining failure belongs to before proceeding.

- [ ] **Step 11: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/audit_keepers.py scripts/cluster_bullet_bank.py scripts/detect_hidden_gems.py scripts/embed_bullet_bank.py scripts/rewrite_bullets.py scripts/bootstrap_bullet_bank.py scripts/bootstrap_profile.py
git commit -m "Route the 7 bullet-bank pipeline scripts' KB_DIR through profile_paths

Mechanical, identical one-constant swap across audit_keepers.py,
cluster_bullet_bank.py, detect_hidden_gems.py, embed_bullet_bank.py,
rewrite_bullets.py, bootstrap_bullet_bank.py, bootstrap_profile.py.
render_html.py/render_coverletter.py need no change here -- their
TEMPLATE_PATH is shared engine content, not profile data."
```

---

### Task 5: Wire `orchestrator.py`'s `ResumeEngine` through `profile_paths`

**Files:**
- Modify: `scripts/orchestrator.py:980-989` (`ResumeEngine.__init__`)
- Test: `tests/test_orchestrator_main_batch.py` (existing suite exercises this indirectly; add one direct unit test)

**Interfaces:**
- Consumes: `profile_paths.kb_dir()`, `profile_paths.jds_dir()`, `profile_paths.output_dir()` (Task 1)
- Produces: `ResumeEngine.kb_dir`, `.jds_dir`, `.output_json_dir` now profile-scoped; `.engine_dir`/`.prompts_dir`/`.rules_dir`/`.scoring_dir`/`.templates_dir` unchanged (shared).

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_orchestrator_main_batch.py, new test class
class TestResumeEnginePathsAreProfileScoped(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = "morgan"

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_kb_dir_is_profile_scoped(self):
        engine = orchestrator.ResumeEngine()
        self.assertTrue(engine.kb_dir.endswith(os.path.join("profiles", "morgan", "knowledge_base")))

    def test_engine_dir_stays_shared(self):
        engine = orchestrator.ResumeEngine()
        self.assertTrue(engine.engine_dir.endswith("resume-engine"))
        self.assertNotIn("profiles", engine.engine_dir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_orchestrator_main_batch.TestResumeEnginePathsAreProfileScoped -v`
Expected: FAIL — `engine.kb_dir` still points at `resume-engine/knowledge_base`, no `profiles/morgan` segment.

- [ ] **Step 3: Modify `scripts/orchestrator.py:980-989`**

Replace:
```python
    def __init__(self):
        self.engine_dir      = os.path.join(PROJECT_ROOT, "resume-engine")
        self.prompts_dir     = os.path.join(self.engine_dir, "prompts")
        self.rules_dir       = os.path.join(self.engine_dir, "rules")
        self.scoring_dir     = os.path.join(self.engine_dir, "scoring")
        self.kb_dir          = os.path.join(self.engine_dir, "knowledge_base")
        self.templates_dir   = os.path.join(self.engine_dir, "templates")
        self.output_json_dir = os.path.join(PROJECT_ROOT, "output", "json")
        self.jds_dir         = os.path.join(PROJECT_ROOT, "jds")
        os.makedirs(self.output_json_dir, exist_ok=True)
        self._segment_cache: dict = {}
        self._gemma_segment_cache: dict = {}
```
with:
```python
    def __init__(self):
        self.engine_dir      = os.path.join(PROJECT_ROOT, "resume-engine")
        self.prompts_dir     = os.path.join(self.engine_dir, "prompts")
        self.rules_dir       = os.path.join(self.engine_dir, "rules")
        self.scoring_dir     = os.path.join(self.engine_dir, "scoring")
        self.kb_dir          = profile_paths.kb_dir()
        self.templates_dir   = os.path.join(self.engine_dir, "templates")
        self.output_json_dir = os.path.join(profile_paths.output_dir(), "json")
        self.jds_dir         = profile_paths.jds_dir()
        os.makedirs(self.output_json_dir, exist_ok=True)
        self._segment_cache: dict = {}
        self._gemma_segment_cache: dict = {}
```

- [ ] **Step 4: Add the `profile_paths` import to `orchestrator.py`'s top-of-file imports**

Check with `grep -n "^import jd_manager\|^import situational_roles" scripts/orchestrator.py` for the existing local-module import block (orchestrator.py already imports `jd_manager` and `situational_roles` the same way). Add `import profile_paths` immediately alongside those two lines.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_orchestrator_main_batch -v`
Expected: `OK`

- [ ] **Step 6: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK` for everything except `normalize_resume`/`fixed_content`-dependent tests (Task 6 fixes those).

- [ ] **Step 7: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/orchestrator.py tests/test_orchestrator_main_batch.py
git commit -m "Route ResumeEngine's kb_dir/jds_dir/output_json_dir through profile_paths

engine_dir/prompts_dir/rules_dir/scoring_dir/templates_dir stay
pointed at the shared resume-engine/ tree, unaffected by profile."
```

---

### Task 6: Wire `normalize_resume.py` + `render_coverletter.py`'s `fixed_content` through `profile_paths`

**Files:**
- Modify: `scripts/normalize_resume.py:11` (module-level import → function-level dynamic lookup)
- Modify: `scripts/render_coverletter.py:17`, `:44-45`
- Test: existing `tests/test_normalize_resume.py` / cover-letter render tests (regression), plus one new assertion

**Interfaces:**
- Consumes: `profile_paths.fixed_content_module()` (Task 1)
- Produces: `normalize_resume.normalize()` and `render_coverletter.render_coverletter()` now resolve `fixed_content` per active profile at call time instead of import time.

`fixed_content.py` is 100% profile data — a static `import fixed_content` at module load time locks in whichever profile was active when the *module* was first imported, which is wrong once two profiles can be active across different runs in the same process lifetime (e.g. a test suite). Both files switch to calling `profile_paths.fixed_content_module()` inside their function bodies instead.

- [ ] **Step 1: Check for an existing normalize_resume test file**

Run: `ls /Users/morganescott/resume-builder/tests/ | grep normalize`

If `tests/test_normalize_resume.py` exists, add the case below to it. If not, create it with this full content:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import normalize_resume  # noqa: E402


class TestNormalizeUsesActiveProfilesFixedContent(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = "morgan"

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_normalize_applies_morgans_contact_info(self):
        result = normalize_resume.normalize({})
        self.assertEqual(result["NAME"], "Morgan Escott")
        self.assertEqual(result["EMAIL"], "escott.morgan@gmail.com")
```

- [ ] **Step 2: Run test to verify current behavior (should already pass, since `fixed_content` still resolves at import time to whatever's on `sys.path`) — confirm baseline before changing the import mechanism**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_normalize_resume -v`
Expected: `OK` (this confirms the *test* is correct against current behavior, before the refactor; it should still pass identically after Step 3-4's refactor — this is a regression guard, not a new-behavior test).

- [ ] **Step 3: Modify `scripts/normalize_resume.py`**

Replace line 11:
```python
import fixed_content
```
with:
```python
import profile_paths
```

Then replace every bare `fixed_content.` reference in the file (lines 42, 46-50, 58, 65, 69, 73, 78, 80) with a `fixed_content` local variable resolved once at the top of `normalize()`. Replace:
```python
def normalize(resume_data: dict, include_optional_clients: bool = True) -> dict:
    """Returns a new dict; never mutates the input.

    `include_optional_clients=False` drops non-essential client rosters (see
    fixed_content.CLIENTS) -- used by orchestrator's trim loop as a free,
    non-LLM trim step before the more expensive LLM-driven ones.
    """
    result = dict(resume_data)

    result.update(fixed_content.CONTACT_INFO)
```
with:
```python
def normalize(resume_data: dict, include_optional_clients: bool = True) -> dict:
    """Returns a new dict; never mutates the input.

    `include_optional_clients=False` drops non-essential client rosters (see
    fixed_content.CLIENTS) -- used by orchestrator's trim loop as a free,
    non-LLM trim step before the more expensive LLM-driven ones.
    """
    fixed_content = profile_paths.fixed_content_module()
    result = dict(resume_data)

    result.update(fixed_content.CONTACT_INFO)
```
(Every other `fixed_content.X` reference later in the same function body — `CERTIFICATIONS`, `build_education`, `COMPANY_META`, `COMPANY_RENAME_NOTE`, `COMPANY_FIXED_TITLE`, `COMPANY_TITLE_DESCRIPTOR`, `CAREER_NOTE`, `CLIENTS` — needs no further edit, since `fixed_content` is now a local variable in scope for the rest of the function, shadowing the module-level import that no longer exists.)

- [ ] **Step 4: Modify `scripts/render_coverletter.py`**

Replace line 17:
```python
import fixed_content
```
with:
```python
import profile_paths
```

Replace lines 43-45:
```python
    company_name = cover_letter_data.get("company_name", "")
    contact = fixed_content.CONTACT_INFO
    title = f"{company_name} Cover Letter - Morgan Escott" if company_name else "Cover Letter - Morgan Escott"
```
with:
```python
    company_name = cover_letter_data.get("company_name", "")
    contact = profile_paths.fixed_content_module().CONTACT_INFO
    title = f"{company_name} Cover Letter - {contact['NAME']}" if company_name else f"Cover Letter - {contact['NAME']}"
```

- [ ] **Step 5: Run tests to verify they still pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_normalize_resume -v`
Expected: `OK`

- [ ] **Step 6: Run the full suite — this should be the first fully-green run since Task 2**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK` (615+ tests). If anything still fails, it means a stray reference to the old `resume-engine/knowledge_base` or `scripts/fixed_content.py` path was missed — grep the whole repo (`grep -rn "resume-engine/knowledge_base\|scripts/fixed_content\|scripts\.fixed_content" --include="*.py" .`) before proceeding, per the design spec's "migration completeness" error-handling note.

- [ ] **Step 7: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/normalize_resume.py scripts/render_coverletter.py tests/test_normalize_resume.py
git commit -m "Resolve fixed_content dynamically per active profile

normalize_resume.py and render_coverletter.py now call
profile_paths.fixed_content_module() instead of a static module-level
import, so the correct profile's data is used even if RESUME_PROFILE
changes within one process. Full test suite green -- Part A
(structural isolation) is now complete."
```

---

### Task 7: Add `roles`/`protected_bullets`/`fixed_credentials`/`voice_calibration_example` to Morgan's `profile.yml`

**Files:**
- Modify: `profiles/morgan/knowledge_base/profile.yml` (append new top-level sections, real current values)
- Test: `tests/test_profile_yml_schema.py` (new — validates the new sections parse with expected shape)

**Interfaces:**
- Consumes: nothing new
- Produces: `profile.yml`'s `roles:`, `protected_bullets:`, `fixed_credentials:`, `voice_calibration_example:` keys — consumed by Task 8's `build_role_rules_block()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_yml_schema.py
import os
import sys
import unittest

import yaml

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import profile_paths  # noqa: E402


class TestMorganProfileYmlNewSchema(unittest.TestCase):

    def setUp(self):
        path = os.path.join(profile_paths.kb_dir("morgan"), "profile.yml")
        with open(path, "r") as f:
            self.data = yaml.safe_load(f)

    def test_roles_section_has_all_six_companies_with_required_fields(self):
        roles = {r["name"]: r for r in self.data["roles"]}
        expected_companies = {
            "Mercor", "Treering Yearbooks", "Inside Sales Team",
            "Element 8 / Strategy LLC", "VML", "Callahan Creek",
        }
        self.assertEqual(set(roles.keys()), expected_companies)
        for role in roles.values():
            for field in ("min_bullets", "target_bullets", "page", "flex_priority"):
                self.assertIn(field, role)

    def test_mercor_floor_is_2(self):
        roles = {r["name"]: r for r in self.data["roles"]}
        self.assertEqual(roles["Mercor"]["min_bullets"], 2)

    def test_inside_sales_team_must_fit_page_1(self):
        roles = {r["name"]: r for r in self.data["roles"]}
        self.assertTrue(roles["Inside Sales Team"]["must_fit_page_1"])

    def test_protected_bullets_has_four_entries(self):
        self.assertEqual(len(self.data["protected_bullets"]), 4)
        self.assertTrue(any("Outreach.io" in b for b in self.data["protected_bullets"]))

    def test_fixed_credentials_has_certifications_and_education(self):
        creds = self.data["fixed_credentials"]
        self.assertEqual(len(creds["certifications"]), 3)
        self.assertEqual(len(creds["education"]), 3)
        jccc = [e for e in creds["education"] if e["institution"] == "Johnson County Community College"][0]
        self.assertEqual(jccc["bullet_count"], 1)

    def test_voice_calibration_example_present(self):
        self.assertIn("alignment", self.data["voice_calibration_example"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_profile_yml_schema -v`
Expected: FAIL — `KeyError: 'roles'`

- [ ] **Step 3: Append the new sections to `profiles/morgan/knowledge_base/profile.yml`**

Add at the end of the file (after the existing `cv:` section, which currently ends the file at line 312 `page_size: "letter"`):

```yaml

roles:
  - name: "Mercor"
    min_bullets: 2
    target_bullets: 3
    page: 1
    flex_priority: 2
  - name: "Treering Yearbooks"
    min_bullets: 6
    target_bullets: 7
    page: 1
    flex_priority: 1
  - name: "Inside Sales Team"
    min_bullets: 4
    target_bullets: 5
    page: 1
    flex_priority: 1
    must_fit_page_1: true
  - name: "Element 8 / Strategy LLC"
    min_bullets: 3
    target_bullets: 4
    page: 2
    flex_priority: 2
  - name: "VML"
    min_bullets: 3
    target_bullets: 4
    page: 2
    flex_priority: 2
  - name: "Callahan Creek"
    min_bullets: 3
    target_bullets: 4
    page: 2
    flex_priority: 2

protected_bullets:
  - "Outreach.io full platform ownership (vendor eval, Salesforce integration, migration, adoption training, ongoing stewardship)"
  - "CRM scrub: scale (thousands of accounts), systematic audit, verified $3M pipeline recovery"
  - "Content Committee: founded and chaired, 100+ assets, 129 sequences, QA process, voice/tone guidelines"
  - "SDR Process Map: 8-step website used as official onboarding asset years after creation"

fixed_credentials:
  certifications:
    - name: "Email Marketing Software Certification"
      issuer: "HubSpot"
      year: 2026
    - name: "Video for Sales Certification"
      issuer: "Vidyard"
      year: 2021
    - name: "Camp Portfolio"
      issuer: "Bernstein Rein, Kansas City"
      year: 2008
  education:
    - institution: "University of Kansas"
      credential: "BS, Journalism + Strategic Communication"
      bullet_count: 2
    - institution: "Kansas City Kansas Community College"
      credential: "AA, Journalism"
      bullet_count: 2
    - institution: "Johnson County Community College"
      credential: "Coursework, Graphic Design"
      bullet_count: 1

voice_calibration_example: "It felt like more than an opportunity -- it felt like alignment."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_profile_yml_schema -v`
Expected: `OK`

- [ ] **Step 5: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK` (adding new keys to `profile.yml` doesn't affect `AUDIT_PROFILE_KEEP`/`AUDIT_PROFILE_STOP`-based trimming since those two constants are an *allowlist*/*stoplist* of section names, and `roles`/`protected_bullets`/`fixed_credentials`/`voice_calibration_example` aren't in either list yet — verify this explicitly: `grep -n "AUDIT_PROFILE_KEEP\|AUDIT_PROFILE_STOP" -A 6 scripts/orchestrator.py` and confirm the new keys are absent from both, meaning they're silently excluded from the *audit*-stage's trimmed profile prefix today. This is fine — Task 8's `build_role_rules_block()` reads the full `profile.yml` independently via its own `load_yaml()` call, not through the audit-stage's trimmed prefix.)

- [ ] **Step 6: Commit**

```bash
cd /Users/morganescott/resume-builder
git add profiles/morgan/knowledge_base/profile.yml tests/test_profile_yml_schema.py
git commit -m "Add roles/protected_bullets/fixed_credentials/voice_calibration_example to profile.yml

Real current values matching tailor_resume.md's existing hardcoded
bullet-count floors, protected-bullet list, and fixed credential
order -- zero behavior change yet, this just makes the data available
for Task 8's dynamic ROLE RULES block."
```

---

### Task 8: `build_role_rules_block()` + wire into `build_tailored_resume()`

**Files:**
- Modify: `scripts/orchestrator.py` (new method on `ResumeEngine`, plus one call site in `build_tailored_resume()`)
- Test: `tests/test_orchestrator_role_rules.py` (new)

**Interfaces:**
- Consumes: `profile.yml`'s new schema (Task 7)
- Produces: `ResumeEngine.build_role_rules_block(profile_data: dict) -> str` — consumed by Task 10's rewritten `tailor_resume.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_role_rules.py
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestBuildRoleRulesBlock(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    def test_empty_roles_returns_empty_string(self):
        self.assertEqual(self.engine.build_role_rules_block({}), "")
        self.assertEqual(self.engine.build_role_rules_block({"roles": []}), "")

    def test_includes_role_rules_header(self):
        profile_data = {
            "roles": [
                {"name": "Acme Corp", "min_bullets": 2, "target_bullets": 3, "page": 1, "flex_priority": 1},
            ],
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("=== ROLE RULES ===", block)
        self.assertIn("Acme Corp", block)
        self.assertIn("| 2 | 3 | 1 |", block)

    def test_must_fit_page_1_role_is_called_out(self):
        profile_data = {
            "roles": [
                {"name": "Acme Corp", "min_bullets": 2, "target_bullets": 3, "page": 1,
                 "flex_priority": 1, "must_fit_page_1": True},
            ],
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("must fit entirely on page 1: Acme Corp", block)

    def test_protected_bullets_included(self):
        profile_data = {"roles": [], "protected_bullets": ["Owned the whole thing end to end"]}
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("Protected Bullets", block)
        self.assertIn("Owned the whole thing end to end", block)

    def test_fixed_credentials_included(self):
        profile_data = {
            "roles": [],
            "fixed_credentials": {
                "certifications": [{"name": "Widget Cert", "issuer": "Widget Co", "year": 2020}],
                "education": [{"institution": "State U", "credential": "BA", "bullet_count": 2}],
            },
        }
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("Widget Cert | Widget Co | 2020", block)
        self.assertIn("State U -- BA: exactly 2 bullet(s)", block)

    def test_voice_calibration_example_included(self):
        profile_data = {"roles": [], "voice_calibration_example": "A test quote."}
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("A test quote.", block)

    def test_real_morgan_profile_produces_nonempty_block(self):
        profile_data = self.engine.load_yaml(self.engine.kb_dir, "profile.yml")
        block = self.engine.build_role_rules_block(profile_data)
        self.assertIn("Mercor", block)
        self.assertIn("Treering Yearbooks", block)
        self.assertIn("Outreach.io", block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_orchestrator_role_rules -v`
Expected: FAIL — `AttributeError: 'ResumeEngine' object has no attribute 'build_role_rules_block'`

- [ ] **Step 3: Add `build_role_rules_block()` to `ResumeEngine`**

Add this method to `scripts/orchestrator.py`'s `ResumeEngine` class, immediately after `load_knowledge_base()` (which ends around line 1022 per the existing `load_prompt`/`load_knowledge_base` block read earlier):

```python
    def build_role_rules_block(self, profile_data: dict) -> str:
        """Formats profile.yml's roles/protected_bullets/fixed_credentials/
        voice_calibration_example into the '=== ROLE RULES ===' context
        block tailor_resume.md references generically. Returns "" if the
        profile has no roles: defined yet (e.g. a freshly-bootstrapped
        profile) -- tailor_resume.md falls back to general judgment in
        that case."""
        roles = profile_data.get("roles") or []
        if not roles:
            return ""

        lines = [
            "\n\n=== ROLE RULES ===",
            "Per-Role Bullet Count Targets:",
            "| Company | Min | Target | Page |",
            "| --- | --- | --- | --- |",
        ]
        for role in roles:
            lines.append(f"| {role['name']} | {role['min_bullets']} | {role['target_bullets']} | {role['page']} |")

        must_fit_page_1 = [r["name"] for r in roles if r.get("must_fit_page_1")]
        if must_fit_page_1:
            lines.append(f"\nThe following roles must fit entirely on page 1: {', '.join(must_fit_page_1)}.")

        flex_order = sorted(roles, key=lambda r: r.get("flex_priority", 999))
        lines.append(
            "\nTrim priority (lowest-priority roles trimmed toward their Min first, before any "
            f"higher-priority role loses a bullet): {', '.join(r['name'] for r in flex_order)}."
        )

        protected = profile_data.get("protected_bullets") or []
        if protected:
            lines.append("\nProtected Bullets -- Do Not Aggressively Shorten:")
            for bullet in protected:
                lines.append(f"- {bullet}")

        credentials = profile_data.get("fixed_credentials") or {}
        certs = credentials.get("certifications") or []
        if certs:
            lines.append("\nTraining & Certifications -- Fixed Order:")
            for i, cert in enumerate(certs, 1):
                lines.append(f"{i}. {cert['name']} | {cert['issuer']} | {cert['year']}")

        education = credentials.get("education") or []
        if education:
            lines.append("\nEducation -- Fixed Order and Bullet Counts:")
            for i, ed in enumerate(education, 1):
                lines.append(f"{i}. {ed['institution']} -- {ed['credential']}: exactly {ed['bullet_count']} bullet(s)")

        page_1_roles = [r["name"] for r in roles if r.get("page") == 1]
        page_2_roles = [r["name"] for r in roles if r.get("page") == 2]
        if page_1_roles or page_2_roles:
            lines.append(
                f"\nSection Order (Page 1 -> Page 2): Page 1 Work Experience: {', '.join(page_1_roles)}. "
                f"Page 2 Work Experience: {', '.join(page_2_roles)}."
            )

        voice_example = profile_data.get("voice_calibration_example")
        if voice_example:
            lines.append(f"\nVoice Calibration Example (this candidate's authentic voice): \"{voice_example}\"")

        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_orchestrator_role_rules -v`
Expected: `OK`

- [ ] **Step 5: Wire the block into `build_tailored_resume()`**

In `scripts/orchestrator.py`, find the situational-block construction (around line 2200-2211, right before the `builder_system = f"..."` line at 2226). Replace:
```python
            situational_block = ""
            if situational_candidates:
                situational_block = (
                    "\n\n=== SITUATIONAL ROLE CANDIDATES ===\n"
                    f"The JD's language matched a deterministic keyword gate for: "
                    f"{', '.join(situational_candidates)}. These are NOT automatically "
                    "included -- use your own judgment on whether including ONE of them "
                    "(as a small, 2-bullet supporting entry) would genuinely help this "
                    "specific JD, per the Situational/Optional Work History Entries rules. "
                    "If none would genuinely help, don't include any of them -- this "
                    "should be rare by construction, not a default."
                )
```
with:
```python
            situational_block = ""
            if situational_candidates:
                situational_block = (
                    "\n\n=== SITUATIONAL ROLE CANDIDATES ===\n"
                    f"The JD's language matched a deterministic keyword gate for: "
                    f"{', '.join(situational_candidates)}. These are NOT automatically "
                    "included -- use your own judgment on whether including ONE of them "
                    "(as a small, 2-bullet supporting entry) would genuinely help this "
                    "specific JD, per the Situational/Optional Work History Entries rules. "
                    "If none would genuinely help, don't include any of them -- this "
                    "should be rare by construction, not a default."
                )

            role_rules_block = self.build_role_rules_block(self.load_yaml(self.kb_dir, "profile.yml"))
```

Then replace the `builder_system` line:
```python
            builder_system = f"{build_prompt}\n\n{kb_context}{research_block}{situational_block}"
```
with:
```python
            builder_system = f"{build_prompt}\n\n{kb_context}{research_block}{situational_block}{role_rules_block}"
```

- [ ] **Step 6: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK` — this changes `build_tailored_resume()`'s constructed prompt content but not its return contract, so no existing test should break (existing tests mock `GeminiClient.generate`/`build_tailored_resume` at a level above this string construction; confirm this assumption holds by checking the diff of the actual test run, not just assuming).

- [ ] **Step 7: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/orchestrator.py tests/test_orchestrator_role_rules.py
git commit -m "Add build_role_rules_block() and inject it into build_tailored_resume()

Mirrors the existing situational-candidates block-injection pattern.
tailor_resume.md is not yet updated to reference this block (Task 10)
-- this task only makes the block available in the prompt context."
```

---

### Task 9: Refactor `situational_roles.py` to read from per-profile YAML

**Files:**
- Modify: `scripts/situational_roles.py` (replace hardcoded `SITUATIONAL_ROLES`/`SITUATIONAL_MIN_BULLETS` with a loader)
- Modify: `scripts/orchestrator.py:2633-2635` (the one other reference to `situational_roles.SITUATIONAL_ROLES`)
- Test: `tests/test_situational_roles.py` (existing suite — must pass unchanged against the new loader, proving zero behavior regression)

**Interfaces:**
- Consumes: `profile_paths.situational_roles_path()` (Task 1), `profiles/morgan/situational_roles.yaml` (Task 2)
- Produces: `situational_roles.load_situational_roles(profile: str = None) -> dict`, `detect_situational_candidates(jd_text: str, roles_data: dict = None) -> list`, `bank_minimums_for(candidates: list, roles_data: dict = None) -> dict` — signatures extended with an optional parameter (default `None` triggers an internal load), so existing call sites in `orchestrator.py` (`situational_roles.detect_situational_candidates(jd_text)`, `situational_roles.bank_minimums_for(situational_candidates)`) need **no changes** at their call sites.

- [ ] **Step 1: Confirm the existing test suite passes against current (pre-refactor) behavior, as a baseline**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_situational_roles -v`
Expected: `OK` (this is the regression baseline the refactor must not break)

- [ ] **Step 2: Rewrite `scripts/situational_roles.py`**

Replace the entire file's constants section and functions (everything from `SITUATIONAL_MIN_BULLETS = 2` through `bank_minimums_for()`) with:

```python
"""
situational_roles.py — the deterministic half of the "hybrid gate" for
situational/optional work-history entries (IDEAS.md, resolved 2026-07-04).

A keyword pre-check per optional company against the JD text; only
companies clearing this gate are even presented to the builder as
candidates. The LLM (guided by tailor_resume.md's own section) makes the
actual go/no-go call among cleared candidates -- this module never decides
whether a situational role actually gets used, only whether it's even a
candidate worth mentioning.

Situational-role data lives per-profile at profiles/<name>/situational_roles.yaml
(not hardcoded here) -- see profile_paths.situational_roles_path(). bank_tag
values must match that profile's bullet-bank-keepers-audited.csv's "Role /
Company" column exactly.
"""

import os
import re

import yaml

import profile_paths


def load_situational_roles(profile: str = None) -> dict:
    """Reads profiles/<profile>/situational_roles.yaml. Returns
    {"situational_min_bullets": int, "roles": {display_name: config_dict}}
    -- an empty {"situational_min_bullets": 2, "roles": {}} if the file
    doesn't exist yet (e.g. a freshly-bootstrapped profile with no
    situational roles defined)."""
    path = profile_paths.situational_roles_path(profile)
    if not os.path.exists(path):
        return {"situational_min_bullets": 2, "roles": {}}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    roles = {entry["display_name"]: entry for entry in data.get("roles", [])}
    return {"situational_min_bullets": data.get("situational_min_bullets", 2), "roles": roles}


def _any_match(patterns: list, text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in patterns)


def detect_situational_candidates(jd_text: str, roles_data: dict = None) -> list:
    """Returns the list of situational-role display names whose keyword
    gate matched jd_text; [] if none did."""
    if roles_data is None:
        roles_data = load_situational_roles()
    roles = roles_data["roles"]
    text_lower = (jd_text or "").lower()
    candidates = []

    for display_name, config in roles.items():
        if "admin_keywords" in config and "design_keywords" in config:
            if _any_match(config["admin_keywords"], text_lower) and _any_match(config["design_keywords"], text_lower):
                candidates.append(display_name)
            continue
        if _any_match(config.get("trigger_keywords", []), text_lower):
            candidates.append(display_name)

    return candidates


def bank_minimums_for(candidates: list, roles_data: dict = None) -> dict:
    """Maps each candidate's bank_tag to the situational minimum, for
    mine_bullet_bank()'s extra_company_minimums parameter."""
    if roles_data is None:
        roles_data = load_situational_roles()
    roles = roles_data["roles"]
    min_bullets = roles_data["situational_min_bullets"]
    return {roles[name]["bank_tag"]: min_bullets for name in candidates}
```

Note the USitek special-case (originally hardcoded as `if display_name == "USitek":`) is now detected generically by checking for the presence of `admin_keywords`/`design_keywords` keys instead of a hardcoded name match — any profile's situational role using that two-keyword-list shape gets the same AND-matching behavior, not just USitek specifically.

- [ ] **Step 3: Update `scripts/orchestrator.py:2633-2635`**

Replace:
```python
        fired_situational_roles = final_companies & set(situational_roles.SITUATIONAL_ROLES.keys())
        if fired_situational_roles:
            print(f"  🎯 Situational role fired: {', '.join(sorted(fired_situational_roles))}")
```
with:
```python
        fired_situational_roles = final_companies & set(situational_roles.load_situational_roles()["roles"].keys())
        if fired_situational_roles:
            print(f"  🎯 Situational role fired: {', '.join(sorted(fired_situational_roles))}")
```

- [ ] **Step 4: Run the existing situational_roles test suite to confirm zero behavior regression**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_situational_roles -v`
Expected: `OK` — every existing test (including `test_matches_humane_society_on_animal_welfare_language` and the USitek AND-matching cases) passes identically, proving the YAML-ification changed nothing observable.

- [ ] **Step 5: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/situational_roles.py scripts/orchestrator.py
git commit -m "Move situational_roles.py's hardcoded dict to per-profile YAML

SITUATIONAL_ROLES/SITUATIONAL_MIN_BULLETS module constants replaced
with load_situational_roles(), reading profiles/<name>/situational_roles.yaml.
detect_situational_candidates()/bank_minimums_for() take the loaded
data as an optional parameter (defaulting to an internal load), so
existing call sites in orchestrator.py need no changes. USitek's
two-keyword-list AND-matching is now generic (detected by shape, not
by hardcoded name), not USitek-specific. Zero behavior regression,
confirmed by the full existing test_situational_roles.py suite
passing unchanged."
```

---

### Task 10: Rewrite `tailor_resume.md`'s load-bearing sections to reference the ROLE RULES block

**Files:**
- Modify: `resume-engine/prompts/tailor_resume.md`
- Test: `tests/test_tailor_resume_prompt_is_generic.py` (new — regression guard against recontamination)

**Interfaces:**
- Consumes: the `=== ROLE RULES ===` block (Task 8) at runtime; this task only changes the static prompt text.
- Produces: a generic `tailor_resume.md` with zero hardcoded company names, consumed unchanged by `orchestrator.py`'s existing `load_prompt("tailor_resume.md")` call.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tailor_resume_prompt_is_generic.py
import os
import unittest

PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine", "prompts", "tailor_resume.md",
)

BANNED_STRINGS = [
    "Mercor", "Treering Yearbooks", "Element 8", "Strategy LLC", "VML",
    "Callahan Creek", "Inside Sales Team", "Humane Society of Greater Kansas City",
    "Unisource Document Products", "Kansas Colloquies", "KU Payroll Office",
    "DeJoy, Knauff & Blood", "USitek", "University of Kansas",
    "Kansas City Kansas Community College", "Johnson County Community College",
    "HubSpot", "Vidyard", "Bernstein Rein", "Morgan",
]


class TestTailorResumePromptIsGeneric(unittest.TestCase):

    def setUp(self):
        with open(PROMPT_PATH, "r") as f:
            self.text = f.read()

    def test_contains_no_hardcoded_company_or_personal_names(self):
        found = [s for s in BANNED_STRINGS if s in self.text]
        self.assertEqual(found, [], f"tailor_resume.md still contains profile-specific strings: {found}")

    def test_still_references_role_rules_block(self):
        self.assertIn("ROLE RULES", self.text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_tailor_resume_prompt_is_generic -v`
Expected: FAIL — the file currently contains most of `BANNED_STRINGS`.

- [ ] **Step 3: Rewrite `resume-engine/prompts/tailor_resume.md`**

Replace line 5:
```
You are Morgan Escott's Strategic Resume Writer. You produce exactly-2-page, ATS-optimized resumes by tailoring her verified career history to a specific Job Description. Furthermore, you never invent experience, metrics, titles, or skills. Every claim must be traceable to the provided candidate data.
```
with:
```
You are the candidate's Strategic Resume Writer. You produce exactly-2-page, ATS-optimized resumes by tailoring their verified career history to a specific Job Description. Furthermore, you never invent experience, metrics, titles, or skills. Every claim must be traceable to the provided candidate data.
```

Replace line 13:
```
Before selecting any content, fill in: "Morgan is an [X] who helps organizations through [Y]." Every bullet, skill, and summary sentence you choose must support that identity for THIS specific role.
```
with:
```
Before selecting any content, fill in: "The candidate is an [X] who helps organizations through [Y]." Every bullet, skill, and summary sentence you choose must support that identity for THIS specific role.
```

Replace lines 24-32 (Archetype Detection):
```
# Archetype Detection

Detect the primary role archetype from the JD and foreground the corresponding evidence:

- **Email Lifecycle:** campaign metrics, segmentation logic, Outreach.io depth, testing mindset
- **Sales Enablement:** Content Committee, library scale (100+ assets, 129 sequences), training systems, governance
- **B2B Content / Copywriter:** agency training (VML, Callahan Creek), journalism foundation, brand voice, regulated industries (CACU financial copy)
- **Marketing Ops / CRM:** Salesforce hygiene, reporting, QA, territory analytics, pipeline cleanup ($3M recovery), process docs
- **Generalist:** cross-functional range, multi-hat IC capability, adaptability
```
with:
```
# Archetype Detection

Detect the primary role archetype from the JD and foreground the corresponding evidence. Each
archetype's `notes` field in the profile's `archetypes:` section (in your knowledge base context)
names the real employers/experience that evidence it for this candidate -- use those, not any
example below, which are illustrative only:

- **Email Lifecycle:** campaign metrics, segmentation logic, CRM/ESP platform depth, testing mindset
- **Sales Enablement:** cross-functional governance bodies, content/training library scale, training systems
- **B2B Content / Copywriter:** agency training, journalism foundation, brand voice, regulated-industry copy
- **Marketing Ops / CRM:** CRM hygiene, reporting, QA, territory analytics, pipeline cleanup, process docs
- **Generalist:** cross-functional range, multi-hat IC capability, adaptability
```

Replace line 67 ("Education Achievement Bullet Selection" intro):
```
The Education section's University of Kansas and Kansas City Kansas Community College entries
each feature one pre-approved achievement bullet, selected (not written) via a key -- pick the
option whose framing best matches the archetype you detected above.
```
with:
```
The Education section's entries (see the ROLE RULES block's Education -- Fixed Order and Bullet
Counts for this candidate's real schools) may each feature one pre-approved achievement bullet,
selected (not written) via a key -- pick the option whose framing best matches the archetype you
detected above, where such a key exists in this candidate's context.
```

Replace lines 124-134 (Job Title Reframing's first two paragraphs):
```
# Job Title Reframing

Honest, role-specific reframing of job titles is allowed to better match responsibilities and the
target archetype -- this is about emphasis, not fabrication. Company, dates, and seniority level may
never be altered. Do NOT append your own industry/role descriptor in parentheses -- a fixed one is
appended automatically per company after generation (e.g. Mercor always gets "(AI Training)"
appended); just produce the title itself.

Element 8 / Strategy LLC's title is fixed and force-overwritten after generation regardless of what
you output -- it always renders as `Design Assistant → Lead Designer` to show the real in-role
promotion. Output any reasonable title for that entry; it will be replaced.
```
with:
```
# Job Title Reframing

Honest, role-specific reframing of job titles is allowed to better match responsibilities and the
target archetype -- this is about emphasis, not fabrication. Company, dates, and seniority level may
never be altered. Do NOT append your own industry/role descriptor in parentheses -- some companies
have a fixed descriptor appended automatically after generation (per this candidate's fixed_content
data); just produce the title itself.

Some companies have their title fixed and force-overwritten after generation regardless of what you
output, to show a real in-role promotion (per this candidate's fixed_content data). Output any
reasonable title for those entries; they will be replaced.
```

Replace lines 138-143 (the Inside-Sales/Treering additive-title examples):
```
- **Additive** (`Title A + Title B`): used when a role genuinely covered two distinct functions and
  the JD calls for emphasizing both. Examples already used and approved:
  - Inside Sales Team: `ABM Specialist + Business Development Representative`
  - Treering Yearbooks: `Creative Strategy Lead + Senior Sales Development Lead` or
    `Creative Strategy Lead + Senior Sales Development Manager` (or other similarly reasonable
    `X + Senior Sales Development Lead/Manager` combinations, chosen per archetype)
```
with:
```
- **Additive** (`Title A + Title B`): used when a role genuinely covered two distinct functions and
  the JD calls for emphasizing both -- e.g. a role that blended account management and business
  development might become `Account Manager + Business Development Representative`. Choose a
  combination that's honestly traceable to that role's real responsibilities.
```

Replace line 148:
```
must remain traceable to real work Morgan did in that role -- reframe emphasis, don't invent scope.
```
with:
```
must remain traceable to real work the candidate did in that role -- reframe emphasis, don't invent scope.
```

Replace the "Career Note" section (lines 150-154):
```
# Career Note (Treering Yearbooks)

A career note is auto-filled after generation, immediately after the Treering Yearbooks entry's
bullets (not optional, and not something you write) -- always output `""` for the `career_note`
field on every EXPERIENCE entry, including Treering Yearbooks.
```
with:
```
# Career Note

A career note may be auto-filled after generation for a specific role (per this candidate's
fixed_content data), immediately after that entry's bullets -- not optional, and not something you
write. Always output `""` for the `career_note` field on every EXPERIENCE entry.
```

Replace the "Protected Bullets" section (lines 156-161):
```
# Protected Bullets — Do Not Aggressively Shorten

- Outreach.io full platform ownership (vendor eval, Salesforce integration, migration, adoption training, ongoing stewardship)
- CRM scrub: scale (thousands of accounts), systematic audit, verified $3M pipeline recovery
- Content Committee: founded and chaired, 100+ assets, 129 sequences, QA process, voice/tone guidelines
- SDR Process Map: 8-step website used as official onboarding asset years after creation
```
with:
```
# Protected Bullets — Do Not Aggressively Shorten

See the ROLE RULES context block's "Protected Bullets" list, if present, for this candidate's
specific protected achievements. Bullets matching one of those (exact or near-match) must not be
aggressively shortened during trimming.
```

Replace the "Per-Role Bullet Count Targets" section (lines 163-176):
```
# Per-Role Bullet Count Targets

These are exact targets. Do not over-fill or under-fill any role. The total across all roles must fit the 2-page layout.

| Company | Bullets |
| --- | --- |
| Mercor | 2-3 |
| Treering Yearbooks | 6-7 |
| Inside Sales Team | 5 |
| Element 8 / Strategy LLC | 4 |
| VML | 4 |
| Callahan Creek | 4 |

**Allocation logic:** Treering and Inside Sales Team are the highest-signal roles for most archetypes — weight them first. If the resume doesn't fit 2 pages, reduce Treering to 6 or Inside Sales Team to 4 before trimming any other role. Never drop Mercor below 2. Never drop Element 8 / Strategy LLC, VML, or Callahan Creek below 3, even under trimming pressure.
```
with:
```
# Per-Role Bullet Count Targets

See the ROLE RULES context block's "Per-Role Bullet Count Targets" table for this candidate's exact
Min/Target/Page values per company. These are exact targets -- do not over-fill or under-fill any
role. The total across all roles must fit the 2-page layout.

**Allocation logic:** the ROLE RULES block's "Trim priority" line lists roles in the order they
should give up bullets under space pressure, lowest-priority first, each trimmed down toward its own
Min before the next-priority role loses anything. Never drop any role below its Min, even under
trimming pressure.
```

Replace the "Situational/Optional Work History Entries" section's guardrail bullets (lines 193-196 specifically, keeping the rest of that section's structure and the header/table which are already dynamically populated from the profile's own situational_roles.yaml — the table itself stays, since it's populated from the `=== SITUATIONAL ROLE CANDIDATES ===` block which already lists real per-profile candidate names, not this static file):
```
- **Shrink-not-replace, not a swap.** Nobody disappears from the resume. Include exactly ONE situational entry, exactly 2 bullets, using the exact company name from the table above.
- **Floor-of-2 exception, this scenario only.** Normally Element 8 / Strategy LLC, VML, and Callahan Creek never drop below 3 bullets (see the floor rule above). When a situational role is active, exactly ONE of those three may drop to a floor of 2 instead, to make room. Pick whichever of the three is least relevant to this specific JD.
- **Never shrink Mercor, Treering, or Inside Sales Team for this, full stop** -- they keep their normal targets/floors regardless of whether a situational role is active.
- If no `=== SITUATIONAL ROLE CANDIDATES ===` block is present, do not include any of these six companies at all.
```
with:
```
- **Shrink-not-replace, not a swap.** Nobody disappears from the resume. Include exactly ONE situational entry, exactly 2 bullets, using the exact company name given in the `=== SITUATIONAL ROLE CANDIDATES ===` block.
- **Floor-of-2 exception, this scenario only.** Normally page-2 roles (see ROLE RULES) never drop below their Min. When a situational role is active, exactly ONE page-2 role may drop one bullet below its normal Min instead, to make room. Pick whichever page-2 role is least relevant to this specific JD.
- **Page-1 roles (see ROLE RULES) never shrink for this, full stop** -- they keep their normal targets/floors regardless of whether a situational role is active.
- If no `=== SITUATIONAL ROLE CANDIDATES ===` block is present, do not include any situational entry at all.
```

Also replace the now-stale table above those bullets (lines 178-189):
```
# Situational/Optional Work History Entries (rare -- almost never applies)

If a `=== SITUATIONAL ROLE CANDIDATES ===` block is present in the context, one or more of these companies genuinely matched a deterministic keyword scan of the JD:

| Candidate company (use this exact name) | Title | Dates |
| --- | --- | --- |
| Humane Society of Greater Kansas City | Communications Intern | 05/2007 – 08/2007 |
| Unisource Document Products | Marketing & Design Intern | 05/2008 – 08/2008 |
| Kansas Colloquies | Editor-in-Chief / Reporter / Columnist | 02/2004 – 05/2006 |
| KU Payroll Office | Payroll Assistant | 11/2006 – 05/2008 |
| DeJoy, Knauff & Blood | Tax Administrative Assistant | 01/2012 – 04/2012 |
| USitek | Administrative Marketing Assistant | 06/2015 – 10/2015 |

**This block being present does not mean you should use one.** Only include a situational entry if it would genuinely, materially help this specific JD -- essentially never for most JDs, even when the block is present. If you do include one:
```
with:
```
# Situational/Optional Work History Entries (rare -- almost never applies)

If a `=== SITUATIONAL ROLE CANDIDATES ===` block is present in the context, one or more of this
candidate's optional past roles genuinely matched a deterministic keyword scan of the JD -- the
block itself names the exact company/candidates that cleared the gate.

**This block being present does not mean you should use one.** Only include a situational entry if it would genuinely, materially help this specific JD -- essentially never for most JDs, even when the block is present. If you do include one:
```

(Note: this task deliberately does not include an exact title/dates table for situational roles in the static prompt anymore, since that data is profile-specific. If a future task finds the LLM needs title/dates beyond just the company name to write a correct situational entry, that data should be added to `profiles/<name>/situational_roles.yaml` and threaded into the `=== SITUATIONAL ROLE CANDIDATES ===` block by `orchestrator.py` -- flagged here as a known follow-up, not silently assumed solved.)

Replace the "Section Order" section (lines 198-203):
```
# Section Order (Page 1 → Page 2)

Page 1: Header → Professional Summary → Skills → Work Experience (Mercor, Treering, Inside Sales Team)
Page 2: Work Experience continued (Element 8/Strategy LLC, VML, Callahan Creek) → Training & Certifications → Education → Why [Company]? (if present)

**Important:** The Inside Sales Team entry must fit fully on the first page without running into the second page. Likewise, the entire Inside Sales Team should never be pushed to the second page. If it does not fit, see "# Trimming Priority (when content exceeds 2 pages)" below.
```
with:
```
# Section Order (Page 1 → Page 2)

See the ROLE RULES context block's "Section Order" line for which of this candidate's companies
belong on page 1 vs. page 2. Page 1: Header → Professional Summary → Skills → Work Experience
(page-1 roles). Page 2: Work Experience continued (page-2 roles) → Training & Certifications →
Education → Why [Company]? (if present).

**Important:** any role the ROLE RULES block marks "must fit entirely on page 1" must not run into
the second page, and must never be pushed there entirely. If it does not fit, see "# Trimming
Priority (when content exceeds 2 pages)" below.
```

Replace "Training & Certifications — Fixed Order" (lines 205-210):
```
# Training & Certifications — Fixed Order

1. Email Marketing Software Certification | HubSpot | 2026
2. Video for Sales Certification | Vidyard | 2021
3. Camp Portfolio | Bernstein Rein, Kansas City | 2008
Only the certification name is bold; institution and year are regular weight.
```
with:
```
# Training & Certifications — Fixed Order

See the ROLE RULES context block's "Training & Certifications -- Fixed Order" list for this
candidate's exact certifications, in the exact order given there. Only the certification name is
bold; institution and year are regular weight.
```

Replace "Education — Fixed Order and Bullet Counts" (lines 212-216):
```
# Education — Fixed Order and Bullet Counts

1. University of Kansas — BS, Journalism + Strategic Communication: exactly 2 bullets (GPA + scholarship; one action-verb achievement)
2. Kansas City Kansas Community College — AA, Journalism: exactly 2 bullets (GPA + honors; one action-verb achievement)
3. Johnson County Community College — Coursework, Graphic Design: exactly 1 bullet (GPA + coursework summary)
```
with:
```
# Education — Fixed Order and Bullet Counts

See the ROLE RULES context block's "Education -- Fixed Order and Bullet Counts" list for this
candidate's exact schools, credentials, and bullet counts, in the exact order given there.
```

Replace line 225:
```
- Must reference specific company research details and connect each to verified facts from Morgan's history
```
with:
```
- Must reference specific company research details and connect each to verified facts from the candidate's history
```

Replace trimming-priority step 4 (line 243):
```
4. Remove least-relevant bullets starting with Treering (protect Outreach implementation and CRM hygiene bullets)
```
with:
```
4. Remove least-relevant bullets starting with the lowest flex-priority role (see ROLE RULES' Trim priority line), protecting anything on the Protected Bullets list first
```

Replace line 293 (the `career_note` schema-note sentence):
```
`achievements` is the array of bullet strings for that role. `career_note` is auto-filled after
generation for the Treering Yearbooks entry -- always output `""` for this field, on every entry.
```
with:
```
`achievements` is the array of bullet strings for that role. `career_note` may be auto-filled after
generation for a specific entry (per this candidate's fixed_content data) -- always output `""` for
this field, on every entry.
```

Replace the worked JSON example's illustrative comment (lines 337-338), which mentions "SDR Process Map at Treering" purely as flavor text inside an example value:
```
{
  "SECTION_WHY": "Why Abnormal Security?",
  "WHY_TEXT": "<p><em>Abnormal's behavioral-AI approach to email security is the kind of infrastructure-over-guesswork bet I look for in a company.</em> ...</p><p>...I built the SDR Process Map at Treering for exactly this reason — <em>durable systems outlast any single campaign.</em></p>"
}
```
with:
```
{
  "SECTION_WHY": "Why Abnormal Security?",
  "WHY_TEXT": "<p><em>Abnormal's behavioral-AI approach to email security is the kind of infrastructure-over-guesswork bet I look for in a company.</em> ...</p><p>...I built a similar system for exactly this reason — <em>durable systems outlast any single campaign.</em></p>"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_tailor_resume_prompt_is_generic -v`
Expected: `OK`

- [ ] **Step 5: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /Users/morganescott/resume-builder
git add resume-engine/prompts/tailor_resume.md tests/test_tailor_resume_prompt_is_generic.py
git commit -m "Genericize tailor_resume.md's load-bearing business rules

The ~9 sections that hardcoded Morgan's specific companies (bullet
floors, protected bullets, page assignment, fixed credentials,
archetype evidence, trim priority) now reference the '=== ROLE
RULES ===' context block (Task 8) generically instead. Allocation
logic/reasoning is unchanged -- only the profile-specific data moved
out. New regression test asserts the file contains zero hardcoded
company/personal names going forward."
```

---

### Task 11: Update `style_rules.yaml`'s contaminated lines

**Files:**
- Modify: `resume-engine/rules/style_rules.yaml` (lines 15, 285-286, 293)
- Test: extend `tests/test_tailor_resume_prompt_is_generic.py`'s pattern to this file, or add cases inline

**Interfaces:**
- Consumes: nothing new (this file is loaded as data via `self.load_yaml(self.rules_dir, "style_rules.yaml")`, already generic in that regard)
- Produces: a `style_rules.yaml` with zero hardcoded company names.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_tailor_resume_prompt_is_generic.py
import yaml

STYLE_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine", "rules", "style_rules.yaml",
)


class TestStyleRulesYamlIsGeneric(unittest.TestCase):

    def setUp(self):
        with open(STYLE_RULES_PATH, "r") as f:
            self.text = f.read()
            f.seek(0)
            self.data = yaml.safe_load(f)

    def test_contains_no_hardcoded_company_names(self):
        banned = ["Mercor", "Treering", "Element 8", "Strategy LLC", "VML", "Callahan Creek", "IST"]
        found = [s for s in banned if s in self.text]
        self.assertEqual(found, [])

    def test_page_assignment_is_still_valid_yaml(self):
        self.assertIn("page_1", self.data)
        self.assertIn("page_2", self.data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_tailor_resume_prompt_is_generic.TestStyleRulesYamlIsGeneric -v`
Expected: FAIL

- [ ] **Step 3: Modify `resume-engine/rules/style_rules.yaml`**

Replace line 15:
```
  - Repeat real differentiators deliberately; K-12 depth, Salesforce admin, Outreach implementation, lifecycle systems, CRM ops
```
with:
```
  - Repeat real differentiators deliberately; identify this candidate's 2-3 most distinctive real skills/experiences (from their verified profile data) and repeat them across sections rather than diluting focus with generic breadth
```

Replace lines 285-286:
```
  page_1: [Header, Professional Summary, Skills, Work Experience (Mercor if present, Treering, IST)]
  page_2: [Work Experience continued (Element 8/Strategy LLC VML Callahan Creek), Training & Certifications, Education, Why section if present]
```
with:
```
  page_1: [Header, Professional Summary, Skills, Work Experience (page-1 roles per this candidate's ROLE RULES)]
  page_2: [Work Experience continued (page-2 roles per this candidate's ROLE RULES), Training & Certifications, Education, Why section if present]
```

Replace line 293:
```
    4: Remove least-relevant bullets (protect Outreach implementation and CRM hygiene)
```
with:
```
    4: Remove least-relevant bullets from the lowest flex-priority role first (protect this candidate's Protected Bullets list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_tailor_resume_prompt_is_generic -v`
Expected: `OK`

- [ ] **Step 5: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /Users/morganescott/resume-builder
git add resume-engine/rules/style_rules.yaml tests/test_tailor_resume_prompt_is_generic.py
git commit -m "Genericize style_rules.yaml's 3 remaining contaminated lines

Page-assignment and trim-priority data now reference the ROLE RULES
block conceptually instead of naming Mercor/Treering/Element 8/VML/
Callahan Creek directly -- matches tailor_resume.md's Task 10 rewrite,
so the two files can no longer silently diverge."
```

---

### Task 12: Genericize the 5 smaller prompt files

**Files:**
- Modify: `resume-engine/prompts/evaluate_fit.md`, `critique_bullet.md`, `critique_resume.md`, `polish_resume.md`, `polish_coverletter.md`, `tailor_coverletter.md`
- Test: extend `tests/test_tailor_resume_prompt_is_generic.py`'s pattern to cover all 6 prompt files in a loop

**Interfaces:**
- Consumes: profile.yml's existing `target_roles`/`archetypes` (for `evaluate_fit.md`), Task 7's `protected_bullets` (for `critique_bullet.md`), a new `voice_calibration_example` field already added in Task 7 (for `critique_resume.md`)
- Produces: all 6 files free of hardcoded "Morgan"/company references.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_tailor_resume_prompt_is_generic.py
PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine", "prompts",
)
SMALLER_PROMPT_FILES = [
    "evaluate_fit.md", "critique_bullet.md", "critique_resume.md",
    "polish_resume.md", "polish_coverletter.md", "tailor_coverletter.md",
]


class TestSmallerPromptFilesAreGeneric(unittest.TestCase):

    def test_no_file_mentions_morgan_by_name(self):
        offenders = []
        for filename in SMALLER_PROMPT_FILES:
            with open(os.path.join(PROMPTS_DIR, filename), "r") as f:
                text = f.read()
            if "Morgan" in text:
                offenders.append(filename)
        self.assertEqual(offenders, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_tailor_resume_prompt_is_generic.TestSmallerPromptFilesAreGeneric -v`
Expected: FAIL — all 6 files currently mention "Morgan."

- [ ] **Step 3: `resume-engine/prompts/polish_resume.md`** (purely cosmetic, 2 occurrences)

Replace:
```
You are making a single, targeted edit to an already-finished resume for Morgan Escott, at her explicit request. This resume already satisfies every job-description-fit requirement -- you are not re-tailoring it, not re-optimizing it for keywords or ATS parsing, and not improving anything she didn't ask about.
```
with:
```
You are making a single, targeted edit to an already-finished resume for the candidate, at their explicit request. This resume already satisfies every job-description-fit requirement -- you are not re-tailoring it, not re-optimizing it for keywords or ATS parsing, and not improving anything they didn't ask about.
```
Replace:
```
You will receive the resume's current JSON and one plain-English instruction describing a change Morgan wants. Apply exactly that change and nothing else.
```
with:
```
You will receive the resume's current JSON and one plain-English instruction describing a change the candidate wants. Apply exactly that change and nothing else.
```

- [ ] **Step 4: `resume-engine/prompts/polish_coverletter.md`** (purely cosmetic, 3 occurrences)

Replace:
```
You are making a single, targeted edit to an already-finished cover letter for Morgan Escott, at her explicit request. This letter already satisfies every job-description-fit requirement -- you are not re-tailoring it, not re-grounding it in new facts, and not improving anything she didn't ask about.
```
with:
```
You are making a single, targeted edit to an already-finished cover letter for the candidate, at their explicit request. This letter already satisfies every job-description-fit requirement -- you are not re-tailoring it, not re-grounding it in new facts, and not improving anything they didn't ask about.
```
Replace:
```
You will receive the cover letter's current JSON and one plain-English instruction describing a change Morgan wants. Apply exactly that change and nothing else.
```
with:
```
You will receive the cover letter's current JSON and one plain-English instruction describing a change the candidate wants. Apply exactly that change and nothing else.
```
Replace:
```
- Never invent a new fact, metric, or claim about Morgan's background that wasn't already present in the letter.
```
with:
```
- Never invent a new fact, metric, or claim about the candidate's background that wasn't already present in the letter.
```

- [ ] **Step 5: `resume-engine/prompts/tailor_coverletter.md`** (mostly cosmetic, one numeric style constant)

Replace:
```
You are writing a first-person cover letter for Morgan Escott, tailored to a specific job description. This is NOT a resume -- no bullet points, no page-fit trimming, no third-person framing anywhere.
```
with:
```
You are writing a first-person cover letter for the candidate, tailored to a specific job description. This is NOT a resume -- no bullet points, no page-fit trimming, no third-person framing anywhere.
```
Replace:
```
2. **2-3 body paragraphs**, first-person throughout ("I..."), each tying a specific fact from the job description to a specific, real piece of Morgan's background from the context provided. Do not invent facts, metrics, or experience not present in the background context. Do not flatter the company with generic praise ("I've always admired your innovative culture") -- every sentence should be grounded in a real JD requirement or a real fact about Morgan.
```
with:
```
2. **2-3 body paragraphs**, first-person throughout ("I..."), each tying a specific fact from the job description to a specific, real piece of the candidate's background from the context provided. Do not invent facts, metrics, or experience not present in the background context. Do not flatter the company with generic praise ("I've always admired your innovative culture") -- every sentence should be grounded in a real JD requirement or a real fact about the candidate.
```
Replace:
```
- First person ("I") throughout every paragraph. Never refer to Morgan in the third person ("Morgan has...", "she brings...").
```
with:
```
- First person ("I") throughout every paragraph. Never refer to the candidate in the third person ("they have...", "she brings...").
```
Replace:
```
- If a `=== COMPANY RESEARCH ===` block is present in the context, use it for exactly two things: (1) the Company Connection -- tie **one** researched fact to a real piece of Morgan's background, avoiding generic flattery ("I've always admired your innovative culture") in favor of something specific and true; (2) tone-matching per this register: mission-driven org -> warmer, more resonant; playful startup -> sharper, slightly more personality; conventional B2B SaaS -> measured, crisp, lightly distinctive; advocacy/impact org -> purposeful, human, values-aware. Never copy the company's own phrases verbatim.
```
with:
```
- If a `=== COMPANY RESEARCH ===` block is present in the context, use it for exactly two things: (1) the Company Connection -- tie **one** researched fact to a real piece of the candidate's background, avoiding generic flattery ("I've always admired your innovative culture") in favor of something specific and true; (2) tone-matching per this register: mission-driven org -> warmer, more resonant; playful startup -> sharper, slightly more personality; conventional B2B SaaS -> measured, crisp, lightly distinctive; advocacy/impact org -> purposeful, human, values-aware. Never copy the company's own phrases verbatim.
```
Replace:
```
- Keep each paragraph to 4-6 lines, 400-450 words total across the whole
  letter -- warmly strategic, not an essay (per Morgan's own established
  platform-specific style rule).
```
with:
```
- Keep each paragraph to 4-6 lines, 400-450 words total across the whole
  letter -- warmly strategic, not an essay.
```

- [ ] **Step 6: `resume-engine/prompts/evaluate_fit.md`** (load-bearing North Star list)

Replace:
```
You are a candid, screen-risk-aware job-fit evaluator for Morgan Escott's search. Your only job is to score how worth pursuing a job posting is -- not to rewrite a resume or write a cover letter.
```
with:
```
You are a candid, screen-risk-aware job-fit evaluator for the candidate's search. Your only job is to score how worth pursuing a job posting is -- not to rewrite a resume or write a cover letter.
```
Replace:
```
- Morgan has done substantial marketing, lifecycle, enablement, operations, onboarding, support-adjacent, and content work even when her formal title didn't say so. Demonstrated function matters more than exact title lineage.
- Target role families ("North Star"): Lifecycle/CRM/Email Marketing, Sales Enablement/Revenue Enablement, Content Strategy/Copywriting/Brand Voice, Marketing Operations/Campaign Operations, Marketing Generalist/Coordinator/Cross-Functional Marketing.
```
with:
```
- This candidate has real demonstrated functional experience that may not always match their formal title lineage exactly (see their profile's target_roles/archetypes for what they've actually done) -- demonstrated function matters more than exact title lineage.
- Target role families ("North Star"): see the `target_roles` and `archetypes` sections in this candidate's profile.yml (in your knowledge base context) for their real primary/secondary target roles -- score alignment against those, not any example list.
```

- [ ] **Step 7: `resume-engine/prompts/critique_bullet.md`** (load-bearing protected-bullet bonus)

Replace:
```
You are a Skeptical Hiring Manager and Resume Editor. Your job is to evaluate a single resume bullet from Morgan Escott's bullet bank against strict quality standards.
```
with:
```
You are a Skeptical Hiring Manager and Resume Editor. Your job is to evaluate a single resume bullet from the candidate's bullet bank against strict quality standards.
```
Replace:
```
- +10 — Matches a protected bullet (exact or near-match to: $3M pipeline, Outreach.io ownership, 2900+ account CRM scrub, Content Committee, SDR Process Map)
```
with:
```
- +10 — Matches an entry on this candidate's Protected Bullets list (see the profile's protected_bullets, provided in your knowledge base context) -- exact or near-match
```

- [ ] **Step 8: `resume-engine/prompts/critique_resume.md`** (load-bearing voice-calibration quote)

Replace:
```
1. `profile.yml` — Morgan's canonical background, verified metrics, and constraints
```
with:
```
1. `profile.yml` — the candidate's canonical background, verified metrics, and constraints
```
Replace:
```
- When a recommendation in TOP 3 RECOMMENDATIONS is about voice,
  personality, or distinctiveness (not accuracy, JD-keyword alignment, or
  ATS formatting), phrase it as a reflective question aimed at Morgan
  rather than a directive -- e.g. "What made this project personally
  satisfying to you?" rather than "Add more personality here."
```
with:
```
- When a recommendation in TOP 3 RECOMMENDATIONS is about voice,
  personality, or distinctiveness (not accuracy, JD-keyword alignment, or
  ATS formatting), phrase it as a reflective question aimed at the
  candidate rather than a directive -- e.g. "What made this project
  personally satisfying to you?" rather than "Add more personality here."
```
Replace the entire "Voice Calibration Reference" block:
```
## Voice Calibration Reference

From Morgan's own established writing-style rubric -- use these as
calibration examples when judging whether a section reads as
distinctive/flat, and how much personality is appropriate per section:

**Contrast examples (same underlying idea, different execution):**
- Generic/Professional: "I'm writing to express my interest in the role."
  (too stiff, no personality)
- Try-Hard/Creative: "I'm a unicorn who eats KPIs for breakfast."
  (performative, lacks depth)
- Morgan's actual voice: "It felt like more than an opportunity -- it felt
  like alignment." (human, reflective, quietly compelling)
```
with:
```
## Voice Calibration Reference

Use this candidate's `voice_calibration_example` (in profile.yml, provided
in your knowledge base context) as the calibration anchor for judging
whether a section reads as distinctive/flat, and how much personality is
appropriate per section -- contrast it against these two illustrative
extremes to judge where a given section falls:

**Contrast examples (same underlying idea, different execution):**
- Generic/Professional: "I'm writing to express my interest in the role."
  (too stiff, no personality)
- Try-Hard/Creative: "I'm a unicorn who eats KPIs for breakfast."
  (performative, lacks depth)
- This candidate's actual voice: see their `voice_calibration_example`.
  (human, reflective, quietly compelling is the general target register --
  but defer to their own example over this description)
```
Replace:
```
- Do not suggest removing Morgan's canonical certifications
```
with:
```
- Do not suggest removing the candidate's canonical certifications
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_tailor_resume_prompt_is_generic -v`
Expected: `OK`

- [ ] **Step 10: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`

- [ ] **Step 11: Commit**

```bash
cd /Users/morganescott/resume-builder
git add resume-engine/prompts/evaluate_fit.md resume-engine/prompts/critique_bullet.md resume-engine/prompts/critique_resume.md resume-engine/prompts/polish_resume.md resume-engine/prompts/polish_coverletter.md resume-engine/prompts/tailor_coverletter.md tests/test_tailor_resume_prompt_is_generic.py
git commit -m "Genericize the 5 smaller contaminated prompt files

evaluate_fit.md's North Star list and critique_bullet.md's
protected-bullet bonus now reference profile.yml's target_roles/
archetypes/protected_bullets generically instead of hardcoding
Morgan's data. critique_resume.md's voice-calibration quote now
references voice_calibration_example. polish_resume.md/
polish_coverletter.md/tailor_coverletter.md's cosmetic 'Morgan'
mentions are genericized to 'the candidate.' Part B (generalizing
tailor_resume.md's business rules) is now complete."
```

---

### Task 13: Bootstrap "new profile" entry point

**Files:**
- Modify: `scripts/bootstrap_bullet_bank.py` (new function + `main()` wiring)
- Modify: `scripts/menu.py:62-89` (`_handle_bootstrap()`)
- Test: `tests/test_bootstrap_new_profile.py` (new)

**Interfaces:**
- Consumes: `profile_paths.PROFILES_DIR` (Task 1)
- Produces: `bootstrap_bullet_bank.create_new_profile(name: str) -> str` (returns the created profile root path) — called from `menu.py`'s bootstrap handler before the existing ingestion flow runs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap_new_profile.py
import os
import shutil
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import profile_paths  # noqa: E402


class TestCreateNewProfile(unittest.TestCase):

    def setUp(self):
        self.test_profile = "test_profile_xyz"
        self.profile_path = os.path.join(profile_paths.PROFILES_DIR, self.test_profile)

    def tearDown(self):
        if os.path.isdir(self.profile_path):
            shutil.rmtree(self.profile_path)

    def test_creates_profile_directory_structure(self):
        result = bootstrap_bullet_bank.create_new_profile(self.test_profile)
        self.assertEqual(result, self.profile_path)
        self.assertTrue(os.path.isdir(os.path.join(self.profile_path, "knowledge_base")))
        self.assertTrue(os.path.isdir(os.path.join(self.profile_path, "knowledge_base", "bootstrap", "source_documents")))

    def test_scaffolds_empty_fixed_content_py(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        fixed_content_path = os.path.join(self.profile_path, "fixed_content.py")
        self.assertTrue(os.path.exists(fixed_content_path))
        with open(fixed_content_path) as f:
            content = f.read()
        self.assertIn("CONTACT_INFO", content)

    def test_scaffolds_empty_situational_roles_yaml(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        path = os.path.join(self.profile_path, "situational_roles.yaml")
        self.assertTrue(os.path.exists(path))

    def test_raises_if_profile_already_exists(self):
        bootstrap_bullet_bank.create_new_profile(self.test_profile)
        with self.assertRaises(FileExistsError):
            bootstrap_bullet_bank.create_new_profile(self.test_profile)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_bootstrap_new_profile -v`
Expected: FAIL — `AttributeError: module 'bootstrap_bullet_bank' has no attribute 'create_new_profile'`

- [ ] **Step 3: Add `create_new_profile()` to `scripts/bootstrap_bullet_bank.py`**

Add this function near the top of the file, after the existing path constants (after line 42's `BULLET_BANK_CLEAN_PATH` definition):

```python
_FIXED_CONTENT_SCAFFOLD = '''"""fixed_content.py — this profile's contact info, company facts, and
fixed credentials. Fill in real values as they become known; every dict
here may start empty and grow over time."""

CONTACT_INFO = {
    "NAME": "",
    "PHONE": "",
    "EMAIL": "",
    "LINKEDIN_DISPLAY": "",
    "LOCATION": "",
}

COMPANY_META = {}
COMPANY_TITLE_DESCRIPTOR = {}
CLIENTS = {}
COMPANY_RENAME_NOTE = {}
COMPANY_FIXED_TITLE = {}
CAREER_NOTE = ""
CERTIFICATIONS = []
KU_ACHIEVEMENT_OPTIONS = {}
KCKCC_ACHIEVEMENT_OPTIONS = {}


def build_education(ku_achievement_key: str = "", kckcc_achievement_key: str = "") -> list:
    return []
'''

_SITUATIONAL_ROLES_SCAFFOLD = """situational_min_bullets: 2
roles: []
"""


def create_new_profile(name: str) -> str:
    """Scaffolds a fresh profiles/<name>/ directory: knowledge_base/ (plus
    its bootstrap/source_documents/ subfolder), a blank fixed_content.py,
    and an empty situational_roles.yaml. Raises FileExistsError if the
    profile already exists -- never silently overwrites one."""
    import profile_paths

    profile_root = os.path.join(profile_paths.PROFILES_DIR, name)
    if os.path.isdir(profile_root):
        raise FileExistsError(f"profiles/{name}/ already exists -- refusing to overwrite it.")

    os.makedirs(os.path.join(profile_root, "knowledge_base", "bootstrap", "source_documents"))

    with open(os.path.join(profile_root, "fixed_content.py"), "w") as f:
        f.write(_FIXED_CONTENT_SCAFFOLD)

    with open(os.path.join(profile_root, "situational_roles.yaml"), "w") as f:
        f.write(_SITUATIONAL_ROLES_SCAFFOLD)

    return profile_root
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_bootstrap_new_profile -v`
Expected: `OK`

- [ ] **Step 5: Wire it into `menu.py`'s bootstrap handler**

Read the current full `_handle_bootstrap()` function first: `sed -n '62,90p' scripts/menu.py`. Then replace its opening (before the existing `os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)` line) to prompt for a profile name when `RESUME_PROFILE` isn't already set to an existing profile, and print the export line the user needs to add to their shell profile:

```python
def _handle_bootstrap() -> bool:
    import profile_paths

    try:
        current = profile_paths.active_profile()
        is_existing = os.path.isdir(os.path.join(profile_paths.PROFILES_DIR, current)) and \
            os.path.isdir(os.path.join(profile_paths.kb_dir(current)))
    except ValueError:
        is_existing = False

    if not is_existing or profile_paths.active_profile() == "morgan" and not os.environ.get("RESUME_PROFILE"):
        # RESUME_PROFILE unset (default "morgan") or pointing at a profile
        # with no knowledge_base/ yet -- offer to create a new one rather
        # than silently reusing/overwriting Morgan's.
        name = questionary.text(
            "What's your name (used as your profile ID, e.g. 'dominick')?"
        ).ask()
        if not name:
            return False
        bootstrap_bullet_bank.create_new_profile(name)
        print(f"\nCreated profiles/{name}/. Add this to your shell profile, then restart your "
              f"shell (or run `export RESUME_PROFILE={name}` for this session only):\n")
        print(f"  export RESUME_PROFILE={name}\n")
        os.environ["RESUME_PROFILE"] = name

    os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)
```

(Keep the rest of the existing function body — the empty-folder-vs-N-files-found messaging and the subprocess launch — unchanged below this point.)

- [ ] **Step 6: Run the full suite**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`. If any existing `menu.py`/bootstrap test fails because it didn't expect the new profile-name prompt, check `tests/test_menu_bootstrap.py` for a mocked `questionary.confirm`/`questionary.text` call and add a corresponding mock for the new `questionary.text("What's your name...")` call, following that test file's existing mocking pattern.

- [ ] **Step 7: Commit**

```bash
cd /Users/morganescott/resume-builder
git add scripts/bootstrap_bullet_bank.py scripts/menu.py tests/test_bootstrap_new_profile.py
git commit -m "Add a 'new profile' entry point to the bootstrap flow

create_new_profile() scaffolds profiles/<name>/ (knowledge_base/,
blank fixed_content.py, empty situational_roles.yaml). menu.py's
'New User? Start Here!' now prompts for a profile name when
RESUME_PROFILE isn't already pointing at an existing, populated
profile, and prints the shell-profile export line to add going
forward -- this is the entry point Dom's onboarding will actually use."
```

---

### Task 14: Full regression pass + live-verify against real JDs (acceptance)

**Files:** none modified — this task is verification only.

**Interfaces:** none — this is the plan's final acceptance gate.

- [ ] **Step 1: Run the complete test suite one final time**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests -v 2>&1 | tail -20`
Expected: `OK`, with a total test count higher than the 615 baseline (this plan adds `test_profile_paths.py`, `test_profile_yml_schema.py`, `test_orchestrator_role_rules.py`, `test_tailor_resume_prompt_is_generic.py`, `test_bootstrap_new_profile.py`, plus cases added to `test_jd_manager.py`/`test_orchestrator_main_batch.py`/`test_normalize_resume.py`).

- [ ] **Step 2: Repo-wide grep for any missed stray reference to the old paths**

Run:
```bash
cd /Users/morganescott/resume-builder
grep -rn "resume-engine/knowledge_base\|scripts/fixed_content\|import fixed_content\b" --include="*.py" --include="*.md" --include="*.sh" . | grep -v "^./docs/superpowers/"
```
Expected: no output (the `docs/superpowers/` exclusion is because historical specs/plans legitimately reference the old paths as history, not live code — everything else should be clean). If anything else turns up, fix it before proceeding — this is the design spec's explicit "migration completeness" requirement.

- [ ] **Step 3: Live-verify against a real JD with `RESUME_PROFILE` unset (Morgan's default path)**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && unset RESUME_PROFILE && python scripts/orchestrator.py jds/dummy_jd.txt`

Confirm manually:
- The build completes without error.
- The output PDF's bullet counts per company match what they'd have been before this plan (Mercor 2-3, Treering 6-7, Inside Sales Team 5, Element 8/VML/Callahan Creek 4 each) — spot-check against a resume built before this plan if one is available, or against the Per-Role Bullet Count Targets this plan moved into `profiles/morgan/knowledge_base/profile.yml`.
- Page 1/Page 2 assignment matches the original (Mercor/Treering/IST on page 1; Element 8/VML/Callahan Creek on page 2).
- The four Protected Bullets (Outreach.io ownership, CRM scrub, Content Committee, SDR Process Map) survived if the JD triggered any trimming.
- Training & Certifications and Education sections show the same 3 fixed entries in the same order as before.

- [ ] **Step 4: Live-verify situational-role gating still fires correctly**

Run a JD containing animal-welfare language (matching the existing `test_situational_roles.py` fixture pattern) through the pipeline and confirm the Humane Society entry is correctly considered as a situational candidate (not necessarily included — per the existing "essentially never" guardrail — just correctly gated and available).

- [ ] **Step 5: Live-verify a second profile can bootstrap without touching Morgan's data**

Run:
```bash
cd /Users/morganescott/resume-builder && source .venv/bin/activate
export RESUME_PROFILE=test_second_profile
python -c "
import sys
sys.path.insert(0, 'scripts')
import bootstrap_bullet_bank
bootstrap_bullet_bank.create_new_profile('test_second_profile')
"
ls profiles/test_second_profile/
```
Expected: a fresh `knowledge_base/`, `fixed_content.py`, `situational_roles.yaml` — and confirm `profiles/morgan/` is completely untouched: `git status --short profiles/morgan/` should show no changes from this step.

Clean up afterward: `rm -rf /Users/morganescott/resume-builder/profiles/test_second_profile`

- [ ] **Step 6: Final commit (if any cleanup/fixes were needed in Steps 2-5)**

```bash
cd /Users/morganescott/resume-builder
git add -A
git status --short  # review before committing -- confirm nothing unintended is staged
git commit -m "Final regression fixes from engine/profile split acceptance pass" --allow-empty
```

(Use `--allow-empty` only if Steps 1-5 required zero fixes and this commit would otherwise have nothing to add — otherwise omit that flag once real changes are staged.)

---

## Self-Review

**Spec coverage:** every section of `docs/superpowers/specs/2026-07-16-engine-profile-split-design.md` maps to a task — Goals' `profile_paths.py`/migration (Tasks 1-2), path-redirect for all scripts (Tasks 3-6), `roles`/`protected_bullets`/`fixed_credentials`/`voice_calibration_example` schema (Task 7), `build_role_rules_block()` (Task 8), `situational_roles.py` YAML-ification (Task 9), `tailor_resume.md`/`style_rules.yaml`/5 smaller prompts genericized (Tasks 10-12), bootstrap new-profile entry point (Task 13), acceptance bar (Task 14). The one deliberately-deferred spec item — `TREERING_KEYWORDS`/`KB_ALLOWLIST` verification, flagged as "confirm during implementation" in the design spec — is addressed inline in Task 4's commentary (`KB_ALLOWLIST` confirmed filename-only, no change needed) and should be re-checked for `TREERING_KEYWORDS` specifically during Task 9 or Task 10 execution, since it's still used by `is_treering_bullet()` elsewhere in `orchestrator.py` outside this plan's direct scope — flagging this as a real follow-up rather than silently dropping it: **`TREERING_KEYWORDS` at `orchestrator.py:234` is NOT touched by this plan** and remains Morgan-specific; it's used by `is_treering_bullet()` for Tier-2 segment filtering logic unrelated to `tailor_resume.md`'s prompt content, and generalizing it is out of this plan's scope per the Global Constraints' focus on `profile_paths`/prompt genericization — track it as a known gap for a future pass, not resolved here.

**Placeholder scan:** no "TBD"/"TODO"/"implement later" found on re-read. One judgment call worth surfacing again here rather than leaving implicit: Task 13's Step 5 `_handle_bootstrap()` logic for detecting "does this profile need setup" is a reasonable heuristic (checks `RESUME_PROFILE` unset-or-morgan-without-override), not an exhaustive state machine — flagged inline in that task's step, not hidden.

**Type consistency:** `profile_paths.py`'s function names (`active_profile`, `profile_root`, `kb_dir`, `fixed_content_module`, `situational_roles_path`, `jds_dir`, `output_dir`, `checkpoints_dir`, `applications_md_path`, `tracker_csv_path`) are used identically across Tasks 3, 5, 6, 9, 13 — verified consistent on re-read. `build_role_rules_block(profile_data: dict) -> str` signature matches between its Task 8 definition and Task 8's own call site. `situational_roles.py`'s new `load_situational_roles()`/`detect_situational_candidates()`/`bank_minimums_for()` signatures match between Task 9's definition and its two call sites in `orchestrator.py` (both already-existing calls need no signature changes, confirmed).

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-16-engine-profile-split.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
