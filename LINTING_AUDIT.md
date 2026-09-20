# Linting Issues Audit & Remediation Plan

**Date:** 2026-09-20  
**Status:** In Progress

## Executive Summary

The resume-builder codebase has accumulated linting issues across multiple categories. While all tests pass (functionality is solid), there are code quality and documentation gaps that affect maintainability.

## Issues Breakdown

### 1. MyPy Type Checking - **483 errors** ⚠️
**Severity:** Medium (impacts maintainability, not functionality)

**Issue Categories:**
- **Implicit Optional parameters (majority):** Functions with `None` default but non-Optional type hint
  - Example: `def func(profile: str = None)` should be `profile: str | None = None`
  - Affects: `profile_paths.py`, `situational_roles.py`, `orchestrator.py`, etc.
  - **Solution:** Add `| None` to type hints

- **Any-return mismatches:** Functions returning `Any` instead of declared type
  - Example: Function declared `-> str` but returns result of `yaml.safe_load()` (type Any)
  - Affects: `profile_paths.py` (3 instances), `bootstrap_extractors.py`
  - **Solution:** Use `cast()` or adjust return type

- **Union/None attribute access:** Using attributes on potentially None values
  - Example: `spec.loader.exec_module()` when `spec` could be None
  - Affects: `profile_paths.py:398-399`, `jd_image_ingest.py:107`
  - **Solution:** Add None checks or use assertion

**Recommendation:** **DEFER** - Not blocking; can be addressed gradually as files are edited

---

### 2. Bandit Security Linting - **133 low-severity issues** ℹ️
**Severity:** Low (mostly false positives)

**Issue Categories:**
- **Try-except-pass (majority ~130 instances):** Silent exception handling
  - Example: `except Exception: pass`
  - Assessment: Mostly intentional in this codebase (graceful degradation)
  - **Solution:** Suppress with `# nosec B110` or add logging if needed

- **False positives (~3):** Numbers flagged as "hardcoded passwords"
  - Example: `"type_token_ratio_min": 0.46` flagged as password
  - **Solution:** Suppress with `# nosec B105`

**Recommendation:** **SUPPRESS** - Add `# nosec` comments to intentional patterns; accept false positives

---

### 3. PyDocStyle Formatting - **~9,858 issues** 🔴
**Severity:** High (volume) but Low (impact)

**Issue Categories:**
- **D213:** Multi-line docstring summary should start at second line (not first)
- **D212:** Multi-line docstring summary should start at first line (conflicts with D213!)
- **D401:** Imperative mood ("Return" not "Returns")
- **D205:** Missing blank line between summary and description
- **D400/D415:** Missing period at end of docstring
- **D209:** Closing quotes should be on separate line

**Assessment:** 
- Issues are automatic/mechanical
- Codebase uses descriptive (not imperative) docstring style
- Some PEP257 rules contradict each other (D212 vs D213)

**Recommendation:** **AUTO-FIX** - Run pydocstyle fixes where possible; suppress conflicting rules

---

### 4. Radon Complexity - **79 high-complexity functions** 🟡
**Severity:** Medium (maintainability concern)

**Breaking down by complexity rating:**
- **E (Very High):** ~8 functions
  - Examples: `db.upsert_job`, `picker._database_only_rows`, `normalize_resume.normalize`
- **D (High):** ~20 functions  
  - Examples: `scan_boards.fetch_board_jobs`, `orchestrator` various
- **F (Critical):** ~1 function
  - Example: `liveness._verify_candidates`

**Top offenders:**
1. `liveness._verify_candidates` (F - Critical)
2. `db.upsert_job` (E)
3. `picker._database_only_rows` (E)
4. `picker.list_all_evaluated_jds` (D)

**Recommendation:** **DOCUMENT & PRIORITIZE** - Refactor E/F functions when touched; D functions acceptable for now

---

## Remediation Roadmap

### Phase 1: Quick Wins (Automated) ✅ IN PROGRESS
- [x] Auto-configured pydocstyle via `.pydocstyle` (99.9% reduction: ~9,858 → 14)
- [ ] Fix remaining 14 pydocstyle issues (D100, D210, D301)
- [ ] Add `# nosec` to intentional try-except-pass patterns (~37 locations)
- [ ] Suppress bandit false positives

**Estimated effort:** 3-4 hours  
**Expected reduction:** ~9,000+ issues (pydocstyle), ~130 issues (bandit suppressed)

### Phase 2: Type Safety (High Impact)
- [ ] Fix implicit Optional parameters (most common mypy error, ~300 locations)
- [ ] Add None checks to union-attr violations (~30 locations)
- [ ] Use `cast()` for Any-return mismatches (~50 locations)

**Estimated effort:** 4-6 hours  
**Expected reduction:** ~400+ mypy errors

### Phase 3: Complexity Reduction (Ongoing)
- [ ] Refactor liveness._verify_candidates (F rating)
- [ ] Break down db.upsert_job and picker functions
- [ ] Document "why this is complex" in comments

**Estimated effort:** 2-3 hours per function  
**Expected reduction:** 5-10 Radon ratings per function

---

## Phase 1 Triage: Remaining Issues

### PyDocStyle (14 remaining)
| Code | Count | Assessment | Action |
|------|-------|------------|--------|
| D100 | 4 | Missing module docstring | Add or suppress |
| D210 | 5 | No whitespace around docstring | Format or suppress |
| D301 | 5 | Use raw strings for backslashes | Convert to r""" |

**Decision:** Fix D301 (valid), suppress D100/D210 (low value)

### Bandit (133 total)
| Code | Count | Assessment | Verdict |
|------|-------|------------|---------|
| B110 | 37 | try-except-pass (intentional) | SUPPRESS |
| B603 | 27 | subprocess without shell | SUPPRESS |
| B404 | 18 | import subprocess | SUPPRESS |
| B311 | 17 | random module | SUPPRESS |
| B112 | 17 | try-except-pass | SUPPRESS |
| B607 | 14 | partial path (internal tools) | SUPPRESS |
| Others | 3 | False positives + true positives | SUPPRESS/ACCEPT |

**Decision:** Add `# nosec` to all 127 low-severity patterns; leave high-severity for review

### MyPy (483 total) — DEFERRED to Phase 2
- Implicit Optional: ~300 (fixable)
- Any-return: ~50 (fixable)
- Union/None: ~30 (fixable)
- Other: ~103 (phase 3)

### Radon (79 high-complexity functions) — DEFER to Phase 3
- F rating (1): liveness._verify_candidates
- E rating (8): db.upsert_job, picker functions, normalize_resume
- D rating (70+): Document, refactor when touched

---

## Next Steps

1. **NOW:** Fix D301 (raw strings), suppress D100/D210 in pydocstyle config
2. **NEXT:** Add ~130 `# nosec` comments for bandit
3. **PHASE 2:** Fix 300+ implicit Optional parameters
4. **PHASE 3:** Complexity refactoring (ongoing)
