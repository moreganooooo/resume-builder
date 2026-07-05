# Situational Role-Swap Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the builder rarely, deliberately swap in one of Morgan's other real roles (Humane Society of Greater Kansas City, Unisource Document Products, Kansas Colloquies, KU Payroll Office, DeJoy Knauff & Blood, USitek) as a small 2-bullet supporting entry when a JD's language specifically matches, instead of always using the same fixed six roles.

**Architecture:** A deterministic keyword gate (`situational_roles.py`) flags candidate companies from the JD text; `mine_bullet_bank()` guarantees 2 real bullets per flagged candidate (already-audited content confirmed present in `bullet-bank-keepers-audited.csv`); `build_tailored_resume()` folds the candidate list into the builder's context; `tailor_resume.md` gets a new section spelling out the LLM's own judgment call, the shrink-not-replace mechanic, and the inverted floor-of-2 exception. An audit log line fires whenever a situational role actually survives into the final resume.

**Tech Stack:** Python 3.10+, existing Gemini/orchestrator pipeline, no new dependencies.

## Global Constraints

- This is per this plan's own design basis (IDEAS.md, resolved 2026-07-04) — the design itself is not re-litigated here, only implemented. Confirmed with Morgan 2026-07-05: use the existing 6 companies only (a 7th real candidate, Lied Center of Kansas Performing Arts, was found during research but deliberately excluded from this pass).
- **Hybrid gate**: a deterministic keyword pre-check per company against the JD text; only companies clearing this gate are even presented to the builder. The LLM makes the actual go/no-go call among cleared candidates.
- **Shrink-not-replace, not a swap**: nobody disappears from the resume. A situational entry is a small, 2-bullet addition, not a replacement for one of the six fixed roles.
- **Floor-of-2 exception, this scenario only**: Element 8/Strategy LLC, VML, and Callahan Creek normally have a floor of 3 bullets (per `tailor_resume.md`'s existing trim-order line) — when a situational role is active, exactly one of those three may drop to a floor of 2 to make room. Mercor, Treering, and Inside Sales Team must **never** shrink for this, full stop.
- **Auditability, not a numeric rarity threshold**: no extra score gate beyond the double-gate (keyword + LLM judgment) — but a log line must print whenever a situational role actually survives into the final resume, so "rare" stays a checkable fact.
- Company display names used in `fixed_content.py`/the resume output differ from the informal tags already present in `bullet-bank-keepers-audited.csv`'s `Role / Company` column (confirmed 2026-07-05) — `KU Payroll Office` is tagged `Payroll` in the bank; `DeJoy, Knauff & Blood` is tagged `DeJoy`. The other four match their display names exactly (`Humane Society of Greater Kansas City`, `Unisource Document Products`, `Kansas Colloquies`, `USitek`).
- Spec: IDEAS.md's "Situational/optional work history entries" section (`## Hard`, resolved 2026-07-04) — used as-is per Morgan's explicit confirmation 2026-07-05, no separate spec doc written for this pass.

---

### Task 1: `fixed_content.py` entries for the 6 situational companies

**Files:**
- Modify: `scripts/fixed_content.py:34-55` (add entries to the existing `COMPANY_META` and `COMPANY_TITLE_DESCRIPTOR` dicts)

**Interfaces:**
- Consumes: nothing from other tasks (pure data, mirrors the existing 6-company pattern already in these dicts).
- Produces: `fixed_content.COMPANY_META` and `fixed_content.COMPANY_TITLE_DESCRIPTOR` gain 6 new keys, matching the exact display names Task 3's `tailor_resume.md` instructions will tell the builder to output verbatim: `"Humane Society of Greater Kansas City"`, `"Unisource Document Products"`, `"Kansas Colloquies"`, `"KU Payroll Office"`, `"DeJoy, Knauff & Blood"`, `"USitek"`. `normalize_resume.py` already does `fixed_content.COMPANY_META.get(company)`/`fixed_content.COMPANY_TITLE_DESCRIPTOR.get(company)` generically for whatever company name the builder outputs — no changes needed there.

- [ ] **Step 1: Add the entries**

In `scripts/fixed_content.py`, find:

```python
COMPANY_META = {
    "Mercor": {"size_revenue": "~800 employees; $75M+ revenue", "location": "Short-Term Contract | Remote"},
    "Treering Yearbooks": {"size_revenue": "~120 employees; $17M+ revenue", "location": "Remote"},
    "Inside Sales Team": {"size_revenue": "~150 employees; ~$21M revenue", "location": "Buffalo, NY"},
    "Element 8 / Strategy LLC": {"size_revenue": "~10–15 employees; ~$1M+ revenue", "location": "Lenexa, KS"},
    "VML": {"size_revenue": "~600+ employees; ~$75M+ revenue", "location": "Kansas City, MO"},
    "Callahan Creek": {"size_revenue": "~30 employees; ~$5M revenue", "location": "Lawrence, KS"},
}
```

Change to:

```python
COMPANY_META = {
    "Mercor": {"size_revenue": "~800 employees; $75M+ revenue", "location": "Short-Term Contract | Remote"},
    "Treering Yearbooks": {"size_revenue": "~120 employees; $17M+ revenue", "location": "Remote"},
    "Inside Sales Team": {"size_revenue": "~150 employees; ~$21M revenue", "location": "Buffalo, NY"},
    "Element 8 / Strategy LLC": {"size_revenue": "~10–15 employees; ~$1M+ revenue", "location": "Lenexa, KS"},
    "VML": {"size_revenue": "~600+ employees; ~$75M+ revenue", "location": "Kansas City, MO"},
    "Callahan Creek": {"size_revenue": "~30 employees; ~$5M revenue", "location": "Lawrence, KS"},
    # Situational/optional entries -- rare, deliberate use only (see
    # tailor_resume.md's "Situational/Optional Work History Entries"
    # section). No size_revenue: cv.md doesn't record it for these roles
    # either, so omitting rather than guessing.
    "Humane Society of Greater Kansas City": {"location": "Kansas City, MO"},
    "Unisource Document Products": {},
    "Kansas Colloquies": {"location": "Bonner Springs, KS"},
    "KU Payroll Office": {"location": "Lawrence, KS"},
    "DeJoy, Knauff & Blood": {"location": "Rochester, NY"},
    "USitek": {},
}
```

Find:

```python
COMPANY_TITLE_DESCRIPTOR = {
    "Mercor": "AI Training",
    "Treering Yearbooks": "SaaS/EdTech",
    "Inside Sales Team": "Outbound/Agency",
    "Element 8 / Strategy LLC": "Design/Agency/Startup",
    "VML": "Agency/Digital/Brand",
    "Callahan Creek": "Agency/Creative/Brand",
}
```

Change to:

```python
COMPANY_TITLE_DESCRIPTOR = {
    "Mercor": "AI Training",
    "Treering Yearbooks": "SaaS/EdTech",
    "Inside Sales Team": "Outbound/Agency",
    "Element 8 / Strategy LLC": "Design/Agency/Startup",
    "VML": "Agency/Digital/Brand",
    "Callahan Creek": "Agency/Creative/Brand",
    "Humane Society of Greater Kansas City": "Nonprofit/Animal Welfare",
    "Unisource Document Products": "Print/Document Solutions",
    "Kansas Colloquies": "Student Journalism",
    "KU Payroll Office": "Higher Ed/Payroll",
    "DeJoy, Knauff & Blood": "Tax/Accounting",
    "USitek": "Clerical/Graphic Design",
}
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as before (190) -- pure data addition, no behavior change for existing companies.

- [ ] **Step 3: Commit**

```bash
git add scripts/fixed_content.py
git commit -m "$(cat <<'EOF'
Add fixed_content.py entries for 6 situational/optional companies

Mechanical -- mirrors the existing 6-role pattern exactly. Part of
situational role-swap logic (design resolved 2026-07-04 in IDEAS.md,
confirmed 2026-07-05 to use as-is).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Keyword gate (`situational_roles.py`)

**Files:**
- Create: `scripts/situational_roles.py`
- Test: `tests/test_situational_roles.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure regex matching against a plain JD-text string).
- Produces: `situational_roles.SITUATIONAL_ROLES` dict (keys are the 6 display names from Task 1, each value a dict with `bank_tag` and `trigger_keywords`), `situational_roles.detect_situational_candidates(jd_text: str) -> list[str]` (returns display names whose keyword gate matched, `[]` if none), `situational_roles.bank_minimums_for(candidates: list[str]) -> dict` (maps each candidate's `bank_tag` to a guaranteed minimum of 2, for `mine_bullet_bank()`). Task 3 calls both functions with these exact signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_situational_roles.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import situational_roles  # noqa: E402


class TestDetectSituationalCandidates(unittest.TestCase):

    def test_no_match_on_ordinary_marketing_jd(self):
        jd_text = "We're hiring a Lifecycle Marketing Manager to own our email campaigns and CRM strategy."
        self.assertEqual(situational_roles.detect_situational_candidates(jd_text), [])

    def test_matches_humane_society_on_animal_welfare_language(self):
        jd_text = "Join our animal welfare team supporting shelter operations and adoption events."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Humane Society of Greater Kansas City", candidates)

    def test_matches_unisource_on_print_production_language(self):
        jd_text = "Seeking a coordinator experienced in print production and document management workflows."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Unisource Document Products", candidates)

    def test_matches_kansas_colloquies_on_journalism_language(self):
        jd_text = "We need a reporter for our newspaper's editorial team covering local news."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Kansas Colloquies", candidates)

    def test_matches_ku_payroll_office_on_payroll_language(self):
        jd_text = "This role handles payroll processing and payroll administration for a mid-size firm."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("KU Payroll Office", candidates)

    def test_matches_dejoy_on_tax_accounting_language(self):
        jd_text = "Looking for a bookkeeping specialist to support tax preparation and audit readiness."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("DeJoy, Knauff & Blood", candidates)

    def test_matches_usitek_only_on_combined_clerical_and_design_language(self):
        jd_text = "This role blends administrative support with hands-on graphic design work for local retail clients."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("USitek", candidates)

    def test_does_not_match_usitek_on_design_language_alone(self):
        jd_text = "We're looking for a talented graphic designer to build our brand identity system."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertNotIn("USitek", candidates)

    def test_does_not_match_usitek_on_clerical_language_alone(self):
        jd_text = "This administrative support role handles scheduling, filing, and clerical correspondence."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertNotIn("USitek", candidates)

    def test_can_return_multiple_candidates(self):
        jd_text = "Reporter role covering local newspaper journalism, plus occasional payroll processing support."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Kansas Colloquies", candidates)
        self.assertIn("KU Payroll Office", candidates)


class TestBankMinimumsFor(unittest.TestCase):

    def test_maps_display_names_to_bank_tags_with_minimum_of_2(self):
        minimums = situational_roles.bank_minimums_for(["KU Payroll Office", "DeJoy, Knauff & Blood"])
        self.assertEqual(minimums, {"Payroll": 2, "DeJoy": 2})

    def test_empty_candidates_returns_empty_dict(self):
        self.assertEqual(situational_roles.bank_minimums_for([]), {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_situational_roles -v`
Expected: `ModuleNotFoundError: No module named 'situational_roles'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `scripts/situational_roles.py`:

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

bank_tag values must match bullet-bank-keepers-audited.csv's "Role /
Company" column exactly -- confirmed 2026-07-05 that KU Payroll Office and
DeJoy, Knauff & Blood are tagged more tersely there ("Payroll", "DeJoy")
than their proper display names used on the actual resume.
"""

import re

SITUATIONAL_MIN_BULLETS = 2

SITUATIONAL_ROLES = {
    "Humane Society of Greater Kansas City": {
        "bank_tag": "Humane Society of Greater Kansas City",
        "trigger_keywords": [r"animal welfare", r"animal shelter", r"animal rescue", r"humane society", r"veterinary"],
    },
    "Unisource Document Products": {
        "bank_tag": "Unisource Document Products",
        "trigger_keywords": [r"print production", r"document management", r"print services", r"document solutions"],
    },
    "Kansas Colloquies": {
        "bank_tag": "Kansas Colloquies",
        "trigger_keywords": [r"journalism", r"newspaper", r"editorial", r"\breporter\b", r"news writing"],
    },
    "KU Payroll Office": {
        "bank_tag": "Payroll",
        "trigger_keywords": [r"payroll processing", r"payroll administration", r"\bpayroll\b"],
    },
    "DeJoy, Knauff & Blood": {
        "bank_tag": "DeJoy",
        "trigger_keywords": [r"tax preparation", r"tax compliance", r"bookkeeping", r"\baudit\b", r"accounting clerk"],
    },
    # USitek is a deliberate blend (clerical + graphic design) -- neither
    # signal alone is specific enough (generic admin roles and generic
    # design roles are both common and unrelated to this niche combo), so
    # detection requires both an admin-ish AND a design-ish term present.
    "USitek": {
        "bank_tag": "USitek",
        "admin_keywords": [r"clerical", r"administrative support", r"administrative assistant"],
        "design_keywords": [r"graphic design"],
    },
}


def _any_match(patterns: list, text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in patterns)


def detect_situational_candidates(jd_text: str) -> list:
    """Returns the list of situational-role display names whose keyword
    gate matched jd_text; [] if none did."""
    text_lower = (jd_text or "").lower()
    candidates = []

    for display_name, config in SITUATIONAL_ROLES.items():
        if display_name == "USitek":
            if _any_match(config["admin_keywords"], text_lower) and _any_match(config["design_keywords"], text_lower):
                candidates.append(display_name)
            continue
        if _any_match(config["trigger_keywords"], text_lower):
            candidates.append(display_name)

    return candidates


def bank_minimums_for(candidates: list) -> dict:
    """Maps each candidate's bank_tag to SITUATIONAL_MIN_BULLETS, for
    mine_bullet_bank()'s extra_company_minimums parameter."""
    return {SITUATIONAL_ROLES[name]["bank_tag"]: SITUATIONAL_MIN_BULLETS for name in candidates}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_situational_roles -v`
Expected: all 12 tests pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 12 from the prior total (190 → 202).

- [ ] **Step 6: Commit**

```bash
git add scripts/situational_roles.py tests/test_situational_roles.py
git commit -m "$(cat <<'EOF'
Add deterministic keyword gate for situational role candidates

Part of situational role-swap logic (design resolved 2026-07-04 in
IDEAS.md). This is the deterministic half of the hybrid gate -- the LLM
still makes the actual go/no-go call among cleared candidates.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire into `build_tailored_resume` + `mine_bullet_bank` + `tailor_resume.md`

**Files:**
- Modify: `scripts/orchestrator.py:7` (add `import situational_roles`)
- Modify: `scripts/orchestrator.py:1338` (extend `mine_bullet_bank`'s signature with `extra_company_minimums`)
- Modify: `scripts/orchestrator.py:1566` (compute `situational_candidates` once, near the top of `build_tailored_resume`)
- Modify: `scripts/orchestrator.py:1684` (pass `extra_company_minimums` into the `mine_bullet_bank` call)
- Modify: `scripts/orchestrator.py:1745-1762` (fold a `SITUATIONAL ROLE CANDIDATES` block into `builder_system` when candidates exist)
- Modify: `scripts/orchestrator.py:2129` (audit log line when a situational role survives into the final resume)
- Modify: `resume-engine/prompts/tailor_resume.md` (new "Situational/Optional Work History Entries" section + floor-of-2 exception)

**Interfaces:**
- Consumes: `situational_roles.detect_situational_candidates(jd_text) -> list[str]`, `situational_roles.bank_minimums_for(candidates) -> dict`, `situational_roles.SITUATIONAL_ROLES` (Task 2); `fixed_content.COMPANY_META`/`COMPANY_TITLE_DESCRIPTOR` (Task 1, consumed transparently via `normalize_resume.py`, no direct call here).
- Produces: no new public interface — `build_tailored_resume`'s existing signature/return shape is unchanged, just its behavior when a situational role gets used.

No automated tests for this task (same reasoning as the company-research plan's resume-wiring task: this hinges on real LLM judgment, not deterministic logic — verified live instead). This is the highest-stakes task in this plan, touching the same complex, already-proven pipeline as company research did.

- [ ] **Step 1: Add the import**

In `scripts/orchestrator.py`, find line 7:

```python
import company_research
```

Change to:

```python
import company_research
import situational_roles
```

- [ ] **Step 2: Extend `mine_bullet_bank`'s signature**

In `scripts/orchestrator.py`, find:

```python
    def mine_bullet_bank(
        self,
        jd_text: str,
        master_resume: dict,
    ) -> List[Tuple[str, str, str]]:
```

Change to:

```python
    def mine_bullet_bank(
        self,
        jd_text: str,
        master_resume: dict,
        extra_company_minimums: dict = None,
    ) -> List[Tuple[str, str, str]]:
```

Then find:

```python
        if "Role / Company" in df.columns:
            company_values = df["Role / Company"].values
            for company, min_count in COMPANY_MIN_BULLETS.items():
```

Change to:

```python
        if "Role / Company" in df.columns:
            company_values = df["Role / Company"].values
            combined_minimums = {**COMPANY_MIN_BULLETS, **(extra_company_minimums or {})}
            for company, min_count in combined_minimums.items():
```

- [ ] **Step 3: Compute candidates once, near the top of `build_tailored_resume`**

In `scripts/orchestrator.py`, find (near the start of `build_tailored_resume`, right after the JD file is read):

```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        if job_key is None:
```

Change to:

```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        situational_candidates = situational_roles.detect_situational_candidates(jd_text)
        if situational_candidates:
            print(f"  Situational role candidate(s) cleared the keyword gate: {', '.join(situational_candidates)}")

        if job_key is None:
```

- [ ] **Step 4: Pass the minimums into the `mine_bullet_bank` call**

In `scripts/orchestrator.py`, find:

```python
            bullet_tuples = self.mine_bullet_bank(jd_text, master_resume)
```

Change to:

```python
            bullet_tuples = self.mine_bullet_bank(
                jd_text, master_resume,
                extra_company_minimums=situational_roles.bank_minimums_for(situational_candidates),
            )
```

- [ ] **Step 5: Fold the candidates into the builder's context**

In `scripts/orchestrator.py`, find this exact block (the `jd_data`/`research`/`research_block` snippet appears twice in the file -- this specific match is unique because it's the one immediately preceded by `kb_context = self.load_knowledge_base()`, which only happens inside `build_tailored_resume`, not `build_tailored_coverletter`):

```python
            kb_context = self.load_knowledge_base()

            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data)
            research_block = format_company_research_block(research) if research else ""
```

Change to:

```python
            kb_context = self.load_knowledge_base()

            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data)
            research_block = format_company_research_block(research) if research else ""

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

Then find:

```python
            builder_system = f"{build_prompt}\n\n{kb_context}{research_block}"
```

Change to:

```python
            builder_system = f"{build_prompt}\n\n{kb_context}{research_block}{situational_block}"
```

- [ ] **Step 6: Add the audit log line**

In `scripts/orchestrator.py`, find:

```python
        if page_count is not None and page_count > 2:
            print(f"  ERROR: PDF still {page_count} pages after {max_trim_attempts} trim attempts.")
            return {}

        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
```

Change to:

```python
        if page_count is not None and page_count > 2:
            print(f"  ERROR: PDF still {page_count} pages after {max_trim_attempts} trim attempts.")
            return {}

        final_companies = {job.get("company") for job in resume_data.get("EXPERIENCE", [])}
        fired_situational_roles = final_companies & set(situational_roles.SITUATIONAL_ROLES.keys())
        if fired_situational_roles:
            print(f"  🎯 Situational role fired: {', '.join(sorted(fired_situational_roles))}")

        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
```

- [ ] **Step 7: Add the `tailor_resume.md` section**

In `resume-engine/prompts/tailor_resume.md`, find:

```
**Allocation logic:** Treering and Inside Sales Team are the highest-signal roles for most archetypes — weight them first. If the resume doesn't fit 2 pages, reduce Treering to 6 or Inside Sales Team to 4 before trimming any other role. Never drop Mercor below 2. Never drop Element 8 / Strategy LLC, VML, or Callahan Creek below 3, even under trimming pressure.
```

Insert immediately after it:

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

- **Shrink-not-replace, not a swap.** Nobody disappears from the resume. Include exactly ONE situational entry, exactly 2 bullets, using the exact company name from the table above.
- **Floor-of-2 exception, this scenario only.** Normally Element 8 / Strategy LLC, VML, and Callahan Creek never drop below 3 bullets (see the floor rule above). When a situational role is active, exactly ONE of those three may drop to a floor of 2 instead, to make room. Pick whichever of the three is least relevant to this specific JD.
- **Never shrink Mercor, Treering, or Inside Sales Team for this, full stop** -- they keep their normal targets/floors regardless of whether a situational role is active.
- If no `=== SITUATIONAL ROLE CANDIDATES ===` block is present, do not include any of these six companies at all.
```

- [ ] **Step 8: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 2 (202) -- this task adds no new automated tests, per the note above.

- [ ] **Step 9: Live verification -- a JD that should trigger a situational role**

```bash
cat > jds/smoketest_situational.json << 'EOF'
{
  "job_title": "Animal Welfare Communications Coordinator",
  "company_name": "Test Animal Rescue Org",
  "source_url": null,
  "company_website": null,
  "description": "We are hiring an Animal Welfare Communications Coordinator to support our shelter's adoption campaigns and donor communications. This role partners with our marketing team on email campaigns, CRM management, and lifecycle marketing to drive engagement across our supporter base. Experience with animal welfare, animal shelter operations, or humane society work is a strong plus. You'll also own segmentation, automation workflows, and reporting for our donor CRM."
}
EOF
source .venv/bin/activate
python scripts/cli.py tailor jds/smoketest_situational.json
```

Expected: console output shows `Situational role candidate(s) cleared the keyword gate: Humane Society of Greater Kansas City` early on, and -- if the LLM judges it genuinely helpful for this deliberately animal-welfare-flavored JD -- `🎯 Situational role fired: Humane Society of Greater Kansas City` near the end. Check the output JSON for whether it appears:

```bash
cat output/json/smoketest_situational_resume.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for job in d.get('EXPERIENCE', []):
    if job.get('company') == 'Humane Society of Greater Kansas City':
        print('Situational entry found:', job)
"
```

Note: the LLM might reasonably decide NOT to include it even here (the guardrail says "essentially never," and this is a deliberately soft/marginal trigger, not a slam-dunk case) -- either outcome (fired or not) is a valid result of this test; the goal is confirming the mechanism runs end-to-end without crashing, not forcing a specific LLM decision.

- [ ] **Step 10: Live verification -- confirm zero regression on an ordinary JD**

Run the same real Userpilot JD used in the company-research plan's verification (no situational language at all):

```bash
python scripts/cli.py tailor jds/completed/2026-07-04_Userpilot_ContentEditor.json 2>&1 | grep -i "situational"
```

Expected: no output at all (grep finds nothing) -- confirms `detect_situational_candidates` correctly returns `[]` for an ordinary JD and the pipeline behaves exactly as it did before this feature existed.

- [ ] **Step 11: Clean up test artifacts**

```bash
rm -f jds/smoketest_situational.json jds/completed/smoketest_situational.json \
  output/json/smoketest_situational_resume.json output/html/smoketest_situational_resume.html output/pdf/smoketest_situational_resume.pdf
```

(The Userpilot re-run in Step 10 will re-append a tracker/`applications.md` row for a JD already completed once before -- that's expected and fine to leave, same as any other real completed build.)

- [ ] **Step 12: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/tailor_resume.md
git commit -m "$(cat <<'EOF'
Wire situational role candidates into build_tailored_resume()

mine_bullet_bank() now guarantees 2 bullets per cleared candidate;
builder_system gains a SITUATIONAL ROLE CANDIDATES block when any exist;
tailor_resume.md's new section spells out the shrink-not-replace
mechanic and the floor-of-2 exception (Element 8/VML/Callahan Creek
only -- Mercor/Treering/Inside Sales Team never shrink for this). An
audit log line fires whenever a situational role survives into the
final resume. Live-verified: a deliberately animal-welfare-flavored JD
correctly clears the keyword gate; an ordinary JD (Userpilot) shows zero
situational-role activity, confirming no regression.

Completes situational role-swap logic (design resolved 2026-07-04 in
IDEAS.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
