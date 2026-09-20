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

### Phase 1: Quick Wins (Automated)
- [ ] Run pydocstyle auto-fixes where safe
- [ ] Add `# nosec` to intentional try-except-pass patterns
- [ ] Suppress bandit false positives

**Estimated effort:** 2-3 hours  
**Expected reduction:** ~9,000+ issues (pydocstyle)

### Phase 2: Type Safety (High Impact)
- [ ] Fix implicit Optional parameters (most common mypy error)
- [ ] Add None checks to union-attr violations
- [ ] Use `cast()` for Any-return mismatches

**Estimated effort:** 8-10 hours  
**Expected reduction:** ~400+ mypy errors

### Phase 3: Complexity Reduction (Ongoing)
- [ ] Refactor liveness._verify_candidates (F rating)
- [ ] Break down db.upsert_job and picker functions
- [ ] Document "why this is complex" in comments

**Estimated effort:** 4-6 hours per function  
**Expected reduction:** 5-10 Radon ratings per function

---

## Not Starting

- ❌ Full mypy compliance (too much scope)
- ❌ Complete docstring rewrite (low ROI)
- ❌ Refactor all complex functions at once (too risky)

---

## Next Steps

1. **TODAY:** Run pydocstyle auto-fix, suppress bandit
2. **THIS WEEK:** Fix implicit Optional parameters
3. **ONGOING:** Address complexity as files are touched
