# Onboarding & Remediation Guide

Companion to `master_audit_document.md`. Each task below corresponds 1:1 to a finding ID (F1–F15). Ordered by phase: **Critical** fixes first (data integrity / silently-broken-forever bugs), then **Major**, then **Minor**. Do not check a task off without running its verification command and seeing the stated result — this mirrors the audit's own rule: no issue is "resolved" without empirical test execution and inspection of raw output.

---

## Addendum status (empirical verification pass)

- **Task 0.1 baseline: DONE.** `python -m unittest discover -s tests -v` → 1520 tests, 75.5s, `OK`. No pre-existing failures to worry about.
- **Task 1.1 (F11) repro: EMPIRICALLY CONFIRMED**, safely, via throwaway copies of the real bullet bank (never touched `profiles/morgan/`, `embed_bullet_bank.main` mocked so no real API calls were made). See `master_audit_document.md`'s addendum for the exact output. The fix in Task 1.1 below is unchanged — this just confirms it's fixing a real, reproduced bug, not a theoretical one.
- **Task 2.1 (F9) repro: EMPIRICALLY CONFIRMED.** A bullet with a strong verb, strong outcome language, and zero numbers scores exactly 60/100 — always short of the 70 threshold. Confirmed by direct execution, not just code reading.
- **Cross-reference finding:** most of this repo's `M`/`??` git status at session start was commit `a0eabe8e` ("35-point audit" remediation) sitting uncommitted — it landed mid-audit, along with `69f017da` and `9d32f6f3` (which added `tests/test_remediation_protections.py`). **Task 1.3a/b/d below need re-scoping** — `db.py` and `vector_store.py` are no longer *zero*-coverage, see the revised note under Task 1.3.
- **New tasks added below:** 1.4 (F16 — finish the Bayesian docstring cleanup), 1.5 (F18 — close both test blind spots), 3.8 (F17 — add `skills_menu.py` tests).

---

## Phase 0 — Before touching anything

- [ ] Task 0.1: Run the full suite once to establish a clean baseline.
  ```bash
  source .venv/bin/activate
  python -m unittest discover -s tests -v 2>&1 | tail -30
  ```
  Expected: all tests pass (or note any pre-existing failures here so later phases don't get blamed for them).
- [ ] Task 0.2: Reconcile against existing tracked work before starting — some of F1–F15 may already be known.
  ```bash
  grep -rli "orchestrator\|vector_store\|data.db\|star.quality\|xyz" docs/review/*.md | grep -v master_audit_document
  ```
  Read any hits before starting Phase 1, to avoid duplicating in-flight work.

---

## Phase 1 — Critical (data integrity, silently-and-permanently-broken behavior)

### Task 1.1 (F11): Fix vector-search cache invalidation so it fires on add/remove, not just same-count edits

**Root cause:** the row-count mismatch branch returns early, before the hash-based re-embed logic ever runs.

**Before** (`scripts/vector_store.py:45–56`):
```python
    if not os.path.exists(csv_path) or not os.path.exists(npy_path):
        return []

    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        embs = np.load(npy_path)
    except Exception:
        return []

    if "Bullet Point" not in df.columns or len(df) != len(embs):
        return []
```

**After:**
```python
    if not os.path.exists(csv_path) or not os.path.exists(npy_path):
        return []

    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        embs = np.load(npy_path)
    except Exception:
        return []

    if "Bullet Point" not in df.columns:
        return []

    if len(df) != len(embs):
        # Row count changed (bullet added/removed) -- re-embed instead of
        # bailing out silently, same recovery path as a content-hash
        # mismatch below (F11, docs/review/master_audit_document.md).
        try:
            import embed_bullet_bank
            embed_bullet_bank.main()
            embs = np.load(npy_path)
            if len(df) != len(embs):
                return []
        except Exception as e:
            print(f"Warning: vector auto-reembedding failed ({e}); falling back to keyword search.")
            return []
```
Then let the existing hash-based branch (lines 58–72) run as-is underneath — it still covers same-count content edits.

**Verification:**
```bash
# Manual repro: append a throwaway row to a profile's keeper CSV, confirm
# search_bullet_bank() re-embeds instead of returning [].
python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import pandas as pd, os
import profile_paths
kb = profile_paths.kb_dir()
csv_path = os.path.join(kb, "bullet-bank-keepers-audited.csv")
df = pd.read_csv(csv_path)
before = len(df)
df2 = pd.concat([df, df.iloc[[0]]], ignore_index=True)  # duplicate one row
df2.to_csv(csv_path, index=False)
import vector_store
results = vector_store.search_bullet_bank("test JD text about marketing", top_k=3)
print("results:", len(results), "expected non-empty after auto-reembed")
df.to_csv(csv_path, index=False)  # restore original row count
EOF
```
Expected: `results` is non-empty (not silently `[]`), confirming the row-count-change path now triggers re-embedding.

**Regression test requirement:** add `tests/test_vector_store.py` covering: (a) matching row count + matching hash → no re-embed call; (b) matching row count + mismatched hash → re-embed called; (c) **mismatched row count → re-embed called** (this is the case that was broken). Mock `embed_bullet_bank.main` to assert call count rather than hitting the real embedding API.

---

### Task 1.2 (F4): Sync `data.db` status on `move_jd_to()`, not just on the next unrelated save

**Before** (`scripts/jd_manager.py`, around `move_jd_to` — confirm exact line before editing, file has shifted since audit):
```python
def move_jd_to(jd_path: str, dest_dir: str) -> str:
    ...
    # (no _sync_jd_to_db call)
```

**After:**
```python
def move_jd_to(jd_path: str, dest_dir: str) -> str:
    ...
    new_path = <existing return value computation>
    try:
        with open(new_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _sync_jd_to_db(new_path, data)
    except Exception:
        pass  # best-effort, same posture as _sync_jd_to_db's own callers
    return new_path
```
Read the actual current function body first — `move_jd_to` may return before or after the physical `os.rename`/`shutil.move`; the sync call must happen with the **new** path (post-move) so `_sync_jd_to_db`'s `"completed" in jd_path` / `"expired" in jd_path` status inference sees the right directory.

**Verification:**
```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import jd_manager, db, json, os
# Use a real pending JD fixture path from your active profile, or fixtures/sample_jd.txt-style JSON.
# After calling move_jd_to(), assert the DB row's status matches the new location.
EOF
```
Expected: `db.get_jobs_by_status("completed")` (or `"expired"`) includes the moved JD's `id` immediately after the move, with no intervening `save_*` call.

**Regression test requirement:** extend `tests/test_jd_manager.py` (or add a case to whichever existing test exercises `move_jd_to`) asserting `data.db`'s status column matches the JD's new directory immediately after a move.

---

### Task 1.3 (F13): Add test coverage for the four untested modules

This is a coverage gap, not a single code fix — treat each sub-item as its own small task:

- [ ] Task 1.3a: `tests/test_db.py` — `get_db`/`init_db` create the expected schema on a throwaway path; `upsert_job` round-trips a record; `update_job_status` updates only the targeted row; WAL/busy_timeout pragmas are actually set (query `PRAGMA journal_mode` back).
- [ ] Task 1.3b: `tests/test_vector_store.py` — see Task 1.1's regression requirement; also cover the `len(df) != len(embs)` empty/short-circuit paths and the "no csv/npy yet" early return.
- [ ] Task 1.3c: `tests/test_render_typst.py` — `_escape_typst` round-trips all six special characters (`# $ @ _ [ ]`) plus the markdown-bold conversion; `generate_typst_markup` produces valid Typst for a minimal fixture resume (assert no raw unescaped special chars leak through for a bullet containing all of them).
- [ ] Task 1.3d: `tests/test_migrate_filesystem_to_db.py` — run the migration against a small fixture directory tree, assert every JD's JSON state lands correctly in `data.db`, and assert the migration is idempotent (running it twice doesn't duplicate/corrupt rows).

> **Revised scope note:** `tests/test_remediation_protections.py` (added in commit `9d32f6f3`) already covers a slice of 1.3a (`db.get_db`/`upsert_job` connection lifecycle, including an `"interview"`-status row proving the CHECK constraint fix) and a slice of 1.3b (`vector_store`'s same-row-count hash-mismatch path). 1.3a/1.3b above are **not** starting from zero anymore — narrow their scope to what's still actually uncovered: `update_job_status` isolation, WAL/busy_timeout pragma assertions, and (critically) the exact F11 row-count-mismatch case, which `test_remediation_protections.py` does not exercise — see Task 1.5 below, which supersedes the row-count-mismatch portion of 1.3b. 1.3c (`render_typst`) and 1.3d (`migrate_filesystem_to_db`) are unaffected — still fully uncovered beyond the one escaping unit test `test_remediation_protections.py::test_typst_special_character_escaping` already added.

**Verification (for all of 1.3):**
```bash
python -m unittest discover -s tests -v 2>&1 | grep -E "test_db|test_vector_store|test_render_typst|test_migrate_filesystem_to_db|test_remediation_protections"
```
Expected: all new test files present and passing.

---

### Task 1.4 (F16): Finish the Bayesian-terminology cleanup — fix the docstring, not just the comment

**Before** (`scripts/orchestrator.py:2621–2625`):
```python
    def evaluate_fit(self, jd_path: str) -> dict:
        """
        Ultra-Premium grounded two-stage fit evaluation check for a JD.
        Loads profile.yml dynamically to apply custom deal-breaker skips and
        advanced Bayesian calculations in Python.
        """
```

**After** (match the wording already used in the fixed inline comment nearby, for consistency):
```python
    def evaluate_fit(self, jd_path: str) -> dict:
        """
        Ultra-Premium grounded two-stage fit evaluation check for a JD.
        Loads profile.yml dynamically to apply custom deal-breaker skips and
        empirical score calibration (piecewise linear interpolation) in Python.
        """
```

**Verification:**
```bash
grep -n -i "bayesian" scripts/orchestrator.py   # expect: no matches
python -m unittest tests.test_deal_breaker_overrides -v   # expect: 4/4 still pass, unaffected (docstring-only change)
```

**Regression test requirement:** none needed beyond the existing `test_deal_breaker_overrides.py` (already correctly named/documented as piecewise linear) continuing to pass — this is a doc-string wording fix with no behavior change.

---

### Task 1.5 (F18): Close both "tests the happy path, misses the actual bug" blind spots

**1.5a — `tests/test_star_quality_grader.py`:** add a case for the exact boundary F9 identifies.
```python
    def test_qualitative_bullet_with_strong_verb_and_outcome_still_fails_without_a_metric(self):
        """Pins F9: verb+outcome alone caps at 60/100, always below the 70 threshold,
        so this is the case that proves a purely qualitative bullet can never pass —
        not just an unlikely one. See docs/review/master_audit_document.md F9."""
        resume = {"EXPERIENCE": [{"company": "Acme", "achievements": [
            "Spearheaded a cross-functional trust rebuild with a disengaged VP stakeholder, "
            "resulting in the team selecting me to lead go-to-market strategy for the region"
        ]}]}
        violations = validate_resume._check_bullet_star_quality(resume)
        self.assertEqual(len(violations), 1)
        self.assertIn("Score 60/100", violations[0])
```
Once Task 2.1's fix (qualitative-evidence fallback) lands, flip this test's assertion to expect a pass (or a smaller penalty) — until then, it documents the bug precisely, the same way a failing test pinned to a bug report should.

**1.5b — `tests/test_remediation_protections.py::test_vector_store_stale_hash_trigger`:** add a sibling case for the row-count-mismatch path.
```python
    def test_vector_store_row_count_mismatch_triggers_reembed(self):
        """Pins F11: adding/removing a bullet (row count changes) must also
        trigger re-embedding, not just same-count content edits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.meta")
            csv_path = os.path.join(tmpdir, "bullet-bank-keepers-audited.csv")
            npy_path = os.path.join(tmpdir, "bullet_vectors_ge2_d768.npy")

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"bullets_sha": "irrelevant-matches-nothing"}, f)
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Bullet Point\nBullet One\nBullet Two\n")  # 2 rows

            import numpy as np
            np.save(npy_path, np.zeros((1, 768)))  # only 1 embedding row -- mismatch

            with patch("embed_bullet_bank.main") as mock_reembed, \
                 patch("scripts.vector_store.profile_paths.kb_dir", return_value=tmpdir):
                vector_store.search_bullet_bank("dummy_query", top_k=5)
                self.assertTrue(mock_reembed.called)  # currently FAILS -- this is F11
```
This test should currently **fail** against unfixed `vector_store.py` (proving F11), and pass once Task 1.1's fix lands.

**Verification:**
```bash
python -m unittest tests.test_star_quality_grader tests.test_remediation_protections -v
```
Expected today (before Phase 1/2 fixes land): 1.5a passes (it's asserting the *current buggy* score), 1.5b fails (asserting the *fixed* behavior that doesn't exist yet) — that failure is the point, it's a red test pinned to F11 until Task 1.1 ships. After Task 1.1 + Task 2.1 land, update 1.5a's assertion and re-run both — expect all green.

---

## Phase 2 — Major (real bugs, no data loss, but wrong behavior)

### Task 2.1 (F9): Let qualitative bullets pass the STAR/XYZ grader

**Before** (`scripts/validate_resume.py:940–944`):
```python
            # 2. Metric check
            metrics = _extract_metric_signatures(bullet)
            if not metrics:
                score -= 40
                reasons.append("no quantified metric or numeric evidence found")
```

**After** — add a qualitative-evidence fallback so a strong causal/outcome claim can partially substitute for a missing number, rather than making the check binary-and-mandatory:
```python
            # 2. Metric or qualitative-evidence check. A number is the
            # strongest form of "as measured by," but Google's own XYZ
            # framing doesn't require one -- a scope change, a promotion,
            # or a named stakeholder outcome are legitimate Y's too. Only
            # the full 40-point penalty (no metric AND no qualitative
            # evidence) should be enough to fail a bullet on this axis
            # alone; a strong qualitative claim should cost less.
            metrics = _extract_metric_signatures(bullet)
            has_qualitative_evidence = any(
                phrase in bullet.lower() for phrase in QUALITATIVE_EVIDENCE_PHRASES
            )
            if not metrics and not has_qualitative_evidence:
                score -= 40
                reasons.append("no quantified metric or qualitative evidence of impact found")
            elif not metrics:
                score -= 15
                reasons.append("no quantified metric (qualitative evidence present)")
```
Define `QUALITATIVE_EVIDENCE_PHRASES` near `result_indicators` (line ~916) — e.g. phrases like "promoted to", "recognized by", "selected to", "trusted with", "became the go-to", "praised by", "adopted company-wide", etc. This is a judgment call on wording — needs a human pass, not just an LLM-generated list, since false-positive qualitative matches would undermine the whole check.

**Verification:**
```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import validate_resume as v
resume = {"EXPERIENCE": [{"company": "Acme", "achievements": [
    "Rebuilt trust with a disengaged VP stakeholder, becoming their go-to advisor on go-to-market strategy",
]}]}
violations = v._check_bullet_star_quality(resume)
print("violations:", violations)
EOF
```
Expected: with the fix, this specific well-written-but-numberless bullet either passes (no violation) or fails with a smaller, more honest penalty — not an automatic, unwinnable −40.

**Regression test requirement:** add cases to `tests/test_star_quality_grader.py` (already exists) for: a purely qualitative bullet with strong evidence phrasing (should score ≥70 after the fix), and confirm a genuinely weak bullet (no verb, no metric, no outcome language) still fails.

---

### Task 2.2 (F10): Strip nav/header/footer/cookie-banner boilerplate before company text reaches the LLM

**Before** (`scripts/company_research.py:58–63`):
```python
def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()
```

**After:**
```python
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
```

**Verification:**
```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
from company_research import _extract_visible_text
html = """
<html><body>
<nav>Home About Careers Contact</nav>
<div id="cookie-banner">We use cookies. Accept All</div>
<main><p>Acme Corp builds widgets for the enterprise.</p></main>
<footer>Privacy Policy | Terms</footer>
</body></html>
"""
text = _extract_visible_text(html)
print(text)
assert "widgets for the enterprise" in text
assert "Accept All" not in text
assert "Home About Careers" not in text
print("OK")
EOF
```
Expected: prints `OK`; the assertions confirm boilerplate is gone and real content survives.

**Regression test requirement:** add `tests/test_company_research.py` case (file may already exist — check first) feeding a fixture HTML string with nav/footer/cookie-banner markup and asserting they're absent from the extracted text while body content survives.

---

### Task 2.3 (F3): Fail loudly instead of falling back to a hardcoded profile in the hallucination guard

**Before** (`scripts/validate_resume.py:714–721`):
```python
    try:
        import profile_paths
        kb_dir = profile_paths.get_kb_dir()
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        kb_dir = os.path.join(project_root, "profiles", "morgan", "knowledge_base")
```

**After:**
```python
    import profile_paths
    kb_dir = profile_paths.get_kb_dir()  # let failures propagate -- validating
    # against the wrong profile's knowledge base is worse than a loud crash.
```
If `get_kb_dir()` genuinely needs a fallback for some legitimate caller (e.g. a standalone script context where no profile is set), that fallback belongs inside `profile_paths.get_kb_dir()` itself — using `active_profile()`'s already-documented `morgan` default (consistent with the rest of the app) — not re-implemented ad hoc in `validate_resume.py`.

**Verification:**
```bash
RESUME_PROFILE=some_other_profile python -m unittest tests.test_validate_resume -v
```
Expected: no test relies on the old silent fallback; if one does, it needs updating to expect the loud failure (or to mock `get_kb_dir()` properly).

**Regression test requirement:** add a case asserting `_check_hallucinated_tools` (or its caller) does **not** read from `profiles/morgan/` when `RESUME_PROFILE` is set to a different profile and that profile's `get_kb_dir()` is mocked to raise.

---

### Task 2.4 (F5): Promote silent DB-sync failures from `debug` to `warning`, and surface in `resume doctor`

**Before** (`scripts/jd_manager.py:123–124`):
```python
    except Exception as e:
        logging.debug(f"SQLite db sync skipped/failed for {jd_path}: {e}")
```

**After:**
```python
    except Exception as e:
        logging.warning(f"SQLite db sync skipped/failed for {jd_path}: {e}")
```
Additionally, add a `data.db` connectivity/integrity check to `scripts/doctor.py` (it already does the equivalent for Node/Playwright/Go — follow that pattern): attempt `db.get_db()` + a trivial `SELECT 1`, report pass/fail with the same actionable-fix-instruction format the other checks use.

**Verification:**
```bash
# Force a failure (e.g. point RESUME_PROFILE at a read-only location) and confirm it's visible:
chmod 444 profiles/<test-profile>/  # or simulate via a mocked db.upsert_job raising
python -c "import sys; sys.path.insert(0,'scripts'); import jd_manager; jd_manager.save_evaluation('some/jd.json', {})" 2>&1 | grep -i warning
chmod 755 profiles/<test-profile>/
```
Expected: a `WARNING` line appears (not silence).

**Regression test requirement:** extend `tests/test_doctor.py` with a case for the new `data.db` health check (both healthy and simulated-broken paths).

---

## Phase 3 — Minor (hygiene, DX, low-probability edge cases)

### Task 3.1 (F2): Delete the dead `API_KEY` constant in `orchestrator.py`

**Before** (`scripts/orchestrator.py:52`):
```python
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
```

**After:**
```python
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
```
(Confirm `BASE_URL` is actually used before keeping it; if it's also dead, remove it too. `API_KEY` is confirmed dead via `grep -n "API_KEY" scripts/orchestrator.py` showing only the definition and the unrelated comment block above it.)

**Verification:**
```bash
grep -n "API_KEY" scripts/orchestrator.py   # expect: no matches after removal
python -m unittest discover -s tests -v 2>&1 | tail -5
```
Expected: no matches; full suite still passes (proves nothing depended on the constant).

**Regression test requirement:** none needed — this is dead-code removal with no behavior change.

---

### Task 3.2 (F6): Add an explicit WAL checkpoint at natural sync boundaries

**Where:** anywhere the app knows a Syncthing-relevant boundary is happening — e.g. at the end of `orchestrator.run_pipeline()`, or as a step in `resume doctor` / a new `resume sync-checkpoint` maintenance action.

**After (new helper in `scripts/db.py`):**
```python
def checkpoint(profile: Optional[str] = None) -> None:
    """Forces a WAL checkpoint so all committed writes land in data.db
    itself, not just the (Syncthing-excluded) -wal file. Call this at
    the end of any flow after which a sync is likely to happen soon."""
    conn = get_db(profile)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()
```
Call `db.checkpoint()` at the end of `orchestrator.run_pipeline()` and at the end of a batch `resume run`.

**Verification:**
```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import db
conn = db.get_db("some-test-profile")
conn.execute("INSERT OR REPLACE INTO jobs (id, title, company, raw_text, status) VALUES ('t1','T','C','x','pending')")
conn.commit()
db.checkpoint("some-test-profile")
import os
wal_path = db.get_db_path("some-test-profile") + "-wal"
print("wal size after checkpoint:", os.path.getsize(wal_path) if os.path.exists(wal_path) else 0)
EOF
```
Expected: WAL file size is 0 (or near-0) immediately after `checkpoint()`, confirming writes landed in the main `data.db` file that Syncthing actually syncs.

**Regression test requirement:** add to `tests/test_db.py` (from Task 1.3a) — write a row, call `checkpoint()`, assert the `-wal` file is empty/absent.

---

### Task 3.3 (F1): Split `orchestrator.py` — schemas first, as the lowest-risk slice

Full `ResumeEngine` decomposition is a larger refactor outside this guide's scope (it's a design decision, not a fix — flag for a separate planning pass). The lowest-risk, highest-value first slice:

- [ ] Task 3.3a: Move all 22 Pydantic schema classes (`BulletAuditSchema` through `RecommendationApplySchema`) into a new `scripts/schemas.py`, with `orchestrator.py` importing from it.
  ```bash
  grep -n "^class.*BaseModel" scripts/orchestrator.py
  ```
  Use that list to confirm every schema is moved and nothing is missed.

**Verification:**
```bash
python -m unittest discover -s tests -v 2>&1 | tail -10
python -c "import sys; sys.path.insert(0,'scripts'); import schemas; print(schemas.ResumeSchema)"
```
Expected: full suite still passes; the new module imports cleanly and exposes the schema types.

**Regression test requirement:** none beyond the existing suite passing unchanged — this is a pure move, not a behavior change. If any test imports a schema class directly from `orchestrator`, update its import to `schemas` (grep `tests/` for `from orchestrator import` first).

---

### Task 3.4 (F14): Add a `resume quickstart` command

**After (new subcommand in `scripts/cli.py`):**
```python
@cli.command()
def quickstart():
    """One-shot setup: venv, deps, Playwright, .env prompt, doctor check."""
    # Sequence the existing pieces that already work individually:
    # 1. Check/create .venv (or instruct if not run via `resume` wrapper)
    # 2. pip install -r requirements.txt
    # 3. npm install && npx playwright install chromium
    # 4. Prompt for GEMINI_API_KEY if profile .env is missing (reuse
    #    the existing menu.py flow that already does this interactively)
    # 5. Run doctor.py's checks and print the summary
```
This wraps existing, already-tested pieces (`doctor.py`'s checks, `menu.py`'s API-key prompt flow) rather than reimplementing them — keep it a thin sequencer.

**Verification:**
```bash
resume quickstart   # on a machine/profile that's only partially set up
```
Expected: completes (or clearly reports the one remaining manual step, e.g. "install Go for the dashboard") without the user needing to know the individual commands from CLAUDE.md's Setup section.

**Regression test requirement:** `tests/test_cli_quickstart.py` — mock the sub-steps (venv/pip/npm/playwright checks) and assert they're called in sequence; assert a partial-failure in one step doesn't silently swallow the rest (should report which step failed).

---

### Task 3.5 (F15): Add `--version` and `--verbose` to `cli.py`

**After:**
```python
@click.group(invoke_without_command=True)
@click.version_option(package_name="resume-builder")  # or a hardcoded string if not packaged
@click.option("--verbose", is_flag=True, default=False, help="Print detailed step-by-step output.")
@click.option("--profile", default=None, help="Override RESUME_PROFILE for this invocation only.")
def cli(verbose, profile, ...):
    ...
```
`--dry-run` is more invasive (needs threading through the pipeline to skip actual LLM calls/writes) — scope as a separate follow-up task rather than bundling here.

**Verification:**
```bash
python scripts/cli.py --version
python scripts/cli.py --help | grep -E "verbose|version"
```
Expected: version string prints; `--help` lists both new flags.

**Regression test requirement:** extend `tests/test_cli_help.py` to assert `--version` and `--verbose` appear in `--help` output.

---

### Task 3.6 (F7): Document the Windows `fcntl` locking gap

No code change needed — this is a documentation task. Add a one-line note to CLAUDE.md's cross-platform section (near the existing Windows/Termux mentions) stating that CSV-append locking (`jd_manager.py`'s `_append_row`/`append_application_row`) is best-effort on native Windows (silently unlocked; fine under WSL2). No verification command — check the doc renders and is accurate.

### Task 3.8 (F17): Add `tests/test_skills_menu.py`

**Why this one specifically:** direct reading confirmed `_add_skill()`'s Ctrl+C/Esc handling is already correct (every `questionary...ask()` call is followed by an `is None`/falsy check that cleanly returns) — this task is about pinning that correct behavior down, not fixing a bug.

```python
# tests/test_skills_menu.py
from unittest.mock import patch
import skills_menu

def test_add_skill_returns_early_on_ctrl_c_at_name_prompt():
    with patch("questionary.text") as mock_text:
        mock_text.return_value.ask.return_value = None  # simulates Ctrl+C/Esc
        data = {"tools": []}
        skills_menu._add_skill(data)
        assert data["tools"] == []  # nothing partially written
```
Add sibling cases for cancellation at each subsequent prompt (`category`, `confidence`, `evidence_count_str`, `use_notes`, `tr_references_str`) to pin down that a cancel at *any* step aborts cleanly rather than only the first.

**Verification:**
```bash
python -m unittest tests.test_skills_menu -v
```
Expected: all cancellation-point cases pass against the current (already-correct) implementation.

**Regression test requirement:** this task *is* the regression test — no further requirement.

---

### Task 3.7 (F8): Document the plaintext-secrets tradeoff explicitly

No code change needed (this is a deliberate, already-good design per CLAUDE.md's Syncthing section) — add a one-line cross-reference in CLAUDE.md's "Multi-computer sync" section noting that `keyring`/OS-vault integration was considered and explicitly not used, for the benefit of anyone auditing this again later.

---

## Phase 4 — From the second cross-reference pass (`docs/gemini_files/`, all 24 files)

### Task 4.1 (F19): Correct `refactoring_plan.md`'s two false "[COMPLETED]" claims — no code fix, a documentation-trust fix

No code change needed for the claims themselves (nothing regressed — they were never true). Action: add a short correction note at the top of `docs/gemini_files/refactoring_plan.md` (or a sibling `docs/gemini_files/CORRECTIONS.md`) flagging dimensions #1 (icon default), #10/#13 (pandas/numpy removal), and #17 (Mobile Compatibility, see Task 4.3) as **not actually completed**, so a future read of that file doesn't get treated as ground truth. This is about not letting a stale planning doc mislead a future session (including a future me).

**Verification:** none applicable — this is a documentation-hygiene task, not a code change.

---

### Task 4.2 (F20): Either fix `orchestrator.py`'s pandas/numpy dependency for real, or correct the mobile plan's claim — don't leave both standing

This is a **decision task**, not a prescribed fix — two legitimate paths:

- **Path A (small):** Edit `mobile_and_install_setup_plan.md` to remove the "excludes Pandas, NumPy... 250MB down to 15MB" claim, or caveat it as aspirational/future work, so it can't be followed literally today.
- **Path B (larger, real fix):** Actually make `pandas`/`numpy` lazy in `orchestrator.py` — most usages there are narrow (bullet DataFrame filtering, cosine similarity) and could plausibly move behind a `try/except ImportError` with a stdlib fallback, mirroring what `cluster_bullet_bank.py` would also need. This is a real scope-of-work item, not a quick fix — don't start it without deciding mobile support is an active near-term goal.

**Verification (whichever path):**
```bash
# If Path B: confirm orchestrator still imports and runs without pandas/numpy installed
python3 -c "
import sys
sys.modules['pandas'] = None
sys.modules['numpy'] = None
sys.path.insert(0, 'scripts')
import orchestrator
"
```
Expected (Path B only): no `ImportError` at import time for code paths that don't actually need array/DataFrame operations.

**Regression test requirement:** if Path B is taken, add a `tests/test_orchestrator_no_heavy_deps.py` asserting core JD-parsing/schema code paths work with `pandas`/`numpy` mocked absent. If Path A, no test needed — it's a doc edit.

---

### Task 4.3 (F21): Resolve the Mobile Compatibility contradiction with a real Termux smoke test, not a checkbox

Two prior planning docs disagree on whether this works at all. Settle it empirically rather than trusting either document:
```bash
# On an actual Termux/Android ARM environment (or an ARM Linux container as a proxy):
pkg install python nodejs git -y
git clone <repo> && cd resume-builder
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
npx playwright install chromium   # <- this is the step expected to fail on ARM/Termux
```
**Verification:** record whether `playwright install chromium` succeeds or fails on real Termux. If it fails (expected, per Playwright's own platform support matrix), that settles F21 in `audit_report.md`'s favor, and `refactoring_plan.md`'s "#17 COMPLETED" checkbox should be corrected per Task 4.1's approach. If a workaround exists (e.g. `render_typst.py`'s Typst engine, which doesn't need Chromium, could become the mobile-side renderer instead of Playwright), that's the real fix — not a documentation edit.

**Regression test requirement:** none until a real fix path is chosen — this task is about establishing ground truth, not shipping code.

---

### Task 4.4 (F22, optional, pairs with Task 2.1): Consider restoring the STAR grader's 4th factor instead of (or alongside) Task 2.1's qualitative-evidence fallback

`resume_writing_audit_report.md`'s original design used 4 independent factors (verb, tool/methodology, metric, outcome) rather than the shipped 3 (verb, metric, outcome). Restoring a tool/methodology check — reusing the same `verified_tools.json` cross-reference `_check_hallucinated_tools()` already does — would naturally reduce the metric check's relative weight from 40 points to closer to 25, independent of adding a qualitative-evidence carve-out. Worth evaluating alongside Task 2.1's fix rather than in isolation, since both address the same root score-distribution problem from different angles.

**Verification:** re-run the Task 1.5a pinned test after whichever combination of Task 2.1 / Task 4.4 is chosen; confirm the qualitative bullet now scores ≥70 for a defensible reason (either path), not by coincidence.

**Regression test requirement:** covered by Task 1.5a's existing pinned test, updated to assert the new passing behavior once a fix lands.

---

## Final sign-off checklist — ALL COMPLETE (2026-08-17)

- [x] All Phase 1 (Critical) tasks verified with commands (F11, F4, F13, F16, F18 — F4's fix also caught and fixed a second, near-identical gap in `archive_jd()` not originally named, plus a live race-condition crash in `get_pending_jds()` discovered and fixed mid-session).
- [x] All Phase 2 (Major) tasks verified (F9, F10, F3 — F3 turned out more severe than scoped: `profile_paths.get_kb_dir()` never existed, so the hardcoded-morgan fallback fired on *every* call, not just failures; F5, which also uncovered and fixed a real production throughput bug — `batch_evaluate.py`'s pacing constant was stale against the 2-call split-agent redesign, causing constant HTTP 429s on the real 522-JD refresh run).
- [x] Phase 3 (Minor) tasks completed: F2, F6, F1 (orchestrator.py 4207→~3915 lines; new `scripts/schemas.py`), F14 (`resume quickstart`), F15 (`--version`/`--verbose`), F7+F8 (CLAUDE.md notes), F17 (also caught and fixed a real crash-on-cancel bug: `cli_art.display_warning()` never existed, called from 3 sites each in `skills_menu.py` and `menu.py` — cancelling those prompts would have thrown `AttributeError` in real use).
- [x] Phase 4 doc corrections done: F19/F20 via `docs/gemini_files/CORRECTIONS.md`, F21 documented as an open item (needs a real Termux device — Dom's Pixel 10 is a plausible tester), F22 resolved as part of the Task 2.1 implementation (qualitative-phrase fallback chosen over a 4th grader factor).
- [x] Full suite green: **1571 tests, `OK`** (up from the 1520-test baseline; +51 new/extended tests across this remediation pass).
- [x] Go test suite green: `go test ./...` — all packages `ok`.
- [x] `resume doctor` run clean at the end: **16/16 checks pass**, including the new SQLite `data.db` check added in this pass.
- [x] Coverage Limitations section of `master_audit_document.md` re-reviewed — nothing in this remediation pass touched those blind spots (board-scanners providers, CI workflows, `resume-engine/templates/*.html`, remaining scoring YAMLs); still open for a future pass if warranted.

### Bugs found and fixed during remediation that weren't in the original F1–F22 list
Empirical testing (writing and running real tests, not just reading code) surfaced these — each is a genuine "would have crashed or misbehaved in real use" bug, not a style nit:
1. **`archive_jd()`** had the identical F4 dual-source-of-truth gap as `move_jd_to()` — same fix applied, same regression test pattern.
2. **`get_pending_jds()`** crashed with `FileNotFoundError` on a real, observed race: a concurrent `resume evaluate --refresh` run archived a JD between this function's directory listing and file-open. Now skips vanished files instead of crashing — caught live because the background refresh job was actually running during this session.
3. **`batch_evaluate.py`'s `SECONDS_BETWEEN_CALLS = 4.5`** was calibrated for the pre-split-agent single-call design; `evaluate_fit()`'s upgrade to two back-to-back calls per JD doubled the effective request rate to ~26.7 RPM against a 15 RPM cap, causing the real 522-JD refresh to nearly stall on constant 429 retries. Bumped to 9.0s with the math documented inline.
4. **`profile_paths.get_kb_dir()` never existed** — `validate_resume.py`'s hallucination guard called a function that doesn't exist (real one is `kb_dir()`), so its `except` branch's hardcoded `profiles/morgan/` fallback fired on literally every call, for every profile, not just on rare failures as originally scoped.
5. **`cli_art.display_warning()` never existed** — 6 call sites across `skills_menu.py` (3) and `menu.py` (3) would have thrown `AttributeError` the moment a user cancelled certain prompts or hit certain empty-list states in real interactive use. Fixed to use the existing `cli_art.WARNING` + `console.print` pattern already used everywhere else in the codebase.
6. **`migrate_bullet_bank()`** opened a SQLite connection and never closed it (caught via `ResourceWarning` while testing idempotency) — added the missing `conn.close()`.
7. **`run_pipeline()`** had a duplicated, unreachable `return 0, 0` — dead-code cleanup while adding the WAL checkpoint call in the same function.
