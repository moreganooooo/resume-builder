# Resume Pipeline Phase 3: Deterministic Validation Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop trusting a single LLM call to follow `ResumeDesignSystem.md`'s formatting rules correctly. Move every rule that has zero legitimate per-JD variation into Python (never asked of the LLM at all, or forced as post-processing regardless of what it returns), and add a real deterministic validator that gates the rules which do require generated text (banned words, verb uniqueness, length limits) with a targeted-retry loop — instead of the current setup, where `ResumeDesignSystem.md` compliance rests entirely on prose instructions an LLM may or may not follow, with only an advisory critique afterward that doesn't block anything.

**Architecture:** Three layers, built bottom-up across 8 tasks:
1. **Rules consolidation** (Tasks 1-2, 8): one canonical machine-readable rules source (`style_rules.yaml`), with the stale/contradictory duplicates retired or reconciled. Task 8 folds in a gap discovered after Phase 2 shipped: banned-phrase lists (not just verbs) also differ across `style_rules.yaml`, `summary_score.yaml`, and `language_quality.yaml`.
2. **Fixed-content ownership** (Tasks 3-4): content with zero legitimate variation (Certifications, most of Education, section header labels, tagline casing, date formatting, ampersand substitution) becomes Python constants and unconditional post-processing, never left to the LLM to get right.
3. **Deterministic validation + retry** (Tasks 5-6): a pure-function validator checks the LLM-generated content (Summary, Skills, Bullets, Why) against `style_rules.yaml`; violations trigger a small targeted fix call (not a full regenerate), capped at 3 attempts, then a loud failure — never a silently-shipped bad PDF.

**Tech Stack:** Python 3.10+, stdlib `unittest`, Pydantic, PyYAML.

## Global Constraints

- Run all Python tests via `/usr/local/bin/python3.13 -m unittest tests.<module> -v` (stdlib unittest, not pytest).
- Never touch `resume-engine/knowledge_base/` source-of-truth files — read from them (e.g. `bullet-bank.md`'s Education section), never modify them.
- Every task ends with a passing test run and its own commit.
- What stays advisory, not hard-gated, per the design doc: tone-mirroring quality, archetype-detection correctness, the "who cares" test, believability/credibility judgment, and the top-third/first-impression score — these remain in `critique_resume.md` as scored, logged feedback. Do not add auto-retry logic keyed on any `ResumeCritiqueSchema` score in this plan.
- On validator-retry exhaustion, `build_tailored_resume` returns `{}` (falsy) — the existing pattern already used for the PDF-generation-failure path. Do not add a new tracker/mark_failed call site; `scripts/orchestrator.py`'s `main()` batch loop already calls `tracker.mark_failed(...)` generically whenever `build_tailored_resume` returns falsy (confirmed at `scripts/orchestrator.py:1500-1506`).
- Exact numbers used throughout this plan, copied verbatim from `ResumeDesignSystem.md` / `style_rules.yaml`: bullets 110-120 chars (one-liner) / up to 220 chars (two-liner), max 2 printed lines; Skills lines max 110 chars; Summary max 5 lines; Why section max 8 lines; tagline max 80 chars; per-role bullet counts (Mercor 2-3, Treering 6-8, Inside Sales Team 4-5, Element 8/Strategy LLC 3-4, VML 3-4, Callahan Creek 3-4); dates `MM/YYYY` with en-dash, never named months.

## Execution Strategy (token-budget optimization)

Dispatch as 4 batches, not 8 individual task dispatches, to cut subagent overhead:

- **Batch A — Tasks 1-3 and 8:** one Haiku implementer dispatch (all four are rules-file/YAML cleanup, fully specified with literal before/after content; Task 8 was folded in after Phase 2 surfaced the same class of gap for banned phrases that Task 2 fixes for verbs). One Haiku reviewer dispatch on the combined diff.
- **Batch B — Tasks 4-5:** one Haiku implementer dispatch (Task 5 depends on Task 4's `fixed_content.py`, so run in that order within the batch — they're already designed as a tightly-coupled pair). One Sonnet reviewer dispatch — this batch changes `TemplateSchema`'s LLM-facing contract, worth more scrutiny than pure content edits.
- **Task 6 alone:** one Haiku implementer dispatch (the validator module is fully specified, but it's real logic with the largest test surface in this phase — genuinely the highest-value review target). One Sonnet reviewer dispatch.
- **Task 7 alone:** one Haiku implementer dispatch (code is fully specified, so still cheapest-tier per the "transcription plus testing" rule; escalate to Sonnet only if the implementer reports BLOCKED). One Sonnet reviewer dispatch — this is the highest-risk task in the phase (two retry loops modifying the core `build_tailored_resume` control flow), worth the extra reviewer scrutiny even though the implementer stays on the cheap tier.
- **Final whole-branch review:** one Sonnet dispatch (not Opus) covering the full phase diff.

Keep per-task TDD discipline intact within each batch (failing test before implementation, full suite before the batch's commit(s)) — the savings come from fewer dispatches and cheaper models, not from skipping verification.

---

### Task 1: Retire formatting_rules.yaml and ats_rules.yaml

**Files:**
- Delete: `resume-engine/rules/formatting_rules.yaml`
- Delete: `resume-engine/rules/ats_rules.yaml`
- Modify: `scripts/orchestrator.py` (`audit_and_refine_bullets` — remove the live `ats_rules.yaml` load and its prompt block)
- Modify: `scripts/rewrite_bullets.py` (`RulesBundle.__init__` — remove the two dead loads)
- Modify: `resume-engine/scoring/recruiter_score.yaml` (fix stale date-format reference)
- Test: Create `tests/test_rules_consolidation.py`

**Interfaces:**
- Consumes: none.
- Produces: `resume-engine/rules/` contains only `verb_taxonomy.yaml`, `truthfulness_rules.yaml`, `language_quality.yaml`, `formatting_rules.yaml`(deleted), `hard_failures.yaml`, `ats_rules.yaml`(deleted), `style_rules.yaml`, `verb_intent_mapping.yaml` minus the two deleted files. `audit_and_refine_bullets`'s `critique_system` string no longer contains an `ATS RULES:` block (its content is already present via the `style_rules` block, which includes an `ats_rules:` key).

**Context:** `formatting_rules.yaml` requires `MMM YYYY` dates, directly contradicting the spec's numeric `MM/YYYY` en-dash format and `style_rules.yaml` itself — and it's loaded in exactly one place (`rewrite_bullets.py:356`), where the result is discarded without ever being assigned to a variable, i.e. it's already dead code. `ats_rules.yaml`'s `section_headers.preferred` list is stale/incomplete compared to `style_rules.yaml`'s `ats_rules:` section, and while `rewrite_bullets.py:355` also loads it into an unused variable (dead there too), `scripts/orchestrator.py:914` **does** load it live and inject it into the per-bullet critique prompt as an `ATS RULES:` block — that block is redundant with the `style_rules` block already in the same prompt (`style_rules.yaml` has had a correct, complete `ats_rules:` section since v2.1). `resume-engine/scoring/recruiter_score.yaml:24` cites "MMM YYYY per formatting_rules.yaml" for its `years_of_experience_clarity` criterion — needs to point at the correct format and source once `formatting_rules.yaml` is gone.

- [ ] **Step 1: Write the failing test**

Create `tests/test_rules_consolidation.py`:

```python
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestRetiredRuleFiles(unittest.TestCase):

    def test_formatting_rules_yaml_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(RULES_DIR, "formatting_rules.yaml")))

    def test_ats_rules_yaml_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(RULES_DIR, "ats_rules.yaml")))

    def test_bullet_audit_static_prefix_has_no_dedicated_ats_rules_block(self):
        engine = orchestrator.ResumeEngine()
        prefix = engine.build_audit_static_prefix()
        self.assertNotIn("ATS RULES:", prefix)
        self.assertIn("STYLE RULES", prefix.upper())  # style_rules.yaml's ats_rules: section still covers this


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_rules_consolidation -v`
Expected: FAIL — both files still exist; `build_audit_static_prefix()` (check the method name against `scripts/orchestrator.py` before running — it is the method that builds the string assigned to `critique_system` inside `audit_and_refine_bullets`; if the static-prefix construction is not factored into its own method, adapt this test to call `audit_and_refine_bullets`'s prefix-building logic however it is actually exposed) still contains an `ATS RULES:` block.

- [ ] **Step 3: Delete both files**

```bash
git rm resume-engine/rules/formatting_rules.yaml resume-engine/rules/ats_rules.yaml
```

- [ ] **Step 4: Remove the live ats_rules.yaml usage in orchestrator.py**

In `scripts/orchestrator.py`, remove this line:

```python
        ats_rules           = json.dumps(self.load_yaml(self.rules_dir,   "ats_rules.yaml"))
        print("   ✅ Rules loaded: ats_rules")
```

Then, in the `critique_system` assignment immediately below, remove the `ATS RULES` block — replace:

```python
        critique_system = (
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nATS RULES:\n{ats_rules}"
            f"\n\n{self.recruiter_context_block()}"
        )
```

with:

```python
        critique_system = (
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nSTYLE RULES (includes ATS rules):\n{style_rules}"
            f"\n\n{self.recruiter_context_block()}"
        )
```

(`style_rules` is already loaded a few lines above this block via `style_rules = json.dumps(self.load_yaml(self.rules_dir, "style_rules.yaml"))` — confirm this variable name before editing; it must already exist since `style_rules.yaml` is loaded for other reasons in this same function.)

- [ ] **Step 5: Remove the two dead loads in rewrite_bullets.py**

In `scripts/rewrite_bullets.py`, remove these two lines from `RulesBundle.__init__`:

```python
        ats = _load_yaml_safe(os.path.join(rules_dir, "ats_rules.yaml"),             "ats_rules")
        _load_yaml_safe(os.path.join(rules_dir, "formatting_rules.yaml"),            "formatting_rules")
```

(Confirm `ats` has no other use anywhere else in `RulesBundle.__init__` before deleting the line — the audit found it unused, but re-check the current file since this task runs after Phase 1/2 may have touched neighboring code.)

- [ ] **Step 6: Fix recruiter_score.yaml's stale date-format reference**

In `resume-engine/scoring/recruiter_score.yaml`, replace:

```yaml
  years_of_experience_clarity:
    weight: 25
    description: >
      Can a recruiter determine total years of relevant experience within a
      6-second scan, without doing date math themselves? Driven by whether
      role periods are consistently formatted (MMM YYYY per formatting_rules.yaml)
      and whether the tagline/summary states seniority level explicitly.
    examples:
      good: "Consistent MMM YYYY dates across every role; tagline states seniority"
      bad: "Mixed date formats; no explicit seniority signal anywhere in top third"
```

with:

```yaml
  years_of_experience_clarity:
    weight: 25
    description: >
      Can a recruiter determine total years of relevant experience within a
      6-second scan, without doing date math themselves? Driven by whether
      role periods are consistently formatted (MM/YYYY with en-dash, per
      style_rules.yaml) and whether the tagline/summary states seniority
      level explicitly.
    examples:
      good: "Consistent MM/YYYY dates across every role; tagline states seniority"
      bad: "Mixed date formats; no explicit seniority signal anywhere in top third"
```

- [ ] **Step 7: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_rules_consolidation -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation -v
```
Expected: all PASS. (This includes Phase 2's test files — Phase 3 assumes Phase 1 is merged; Phase 2 does not need to be merged first, since these two phases touch disjoint files, but if Phase 2 has also landed by the time this runs, its tests must still pass too.)

- [ ] **Step 9: Commit**

```bash
git add scripts/orchestrator.py scripts/rewrite_bullets.py resume-engine/scoring/recruiter_score.yaml tests/test_rules_consolidation.py
git commit -m "$(cat <<'EOF'
Retire formatting_rules.yaml and ats_rules.yaml

formatting_rules.yaml required MMM YYYY dates, contradicting the spec's
MM/YYYY en-dash format and style_rules.yaml itself, and was already dead
code everywhere it was loaded. ats_rules.yaml's section-header list was
stale, and its one live use (orchestrator.py's per-bullet critique prompt)
was redundant with style_rules.yaml's own ats_rules section already in the
same prompt.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Reconcile contradictory verb-rule files

**Files:**
- Modify: `resume-engine/rules/style_rules.yaml`
- Modify: `resume-engine/rules/language_quality.yaml`
- Modify: `resume-engine/rules/verb_taxonomy.yaml`
- Modify: `resume-engine/rules/verb_intent_mapping.yaml`
- Test: Create `tests/test_verb_rule_consistency.py`

**Interfaces:**
- Consumes: none.
- Produces: a reusable regression test that mechanically verifies no verb in `style_rules.yaml`'s `vague_verbs` list is recommended as an upgrade, an elite verb, or a preferred verb anywhere in the other three files — this guards against the exact class of bug this task fixes ever recurring.

**Context:** `scripts/orchestrator.py`'s `audit_and_refine_bullets` concatenates `style_rules.yaml`, `language_quality.yaml`, `verb_taxonomy.yaml`, and `verb_intent_mapping.yaml` into the same bullet-rewrite prompt. Seven verbs are recommended as strong/elite/upgrade choices in one or more of the three supporting files while being explicitly listed as vague and banned in `style_rules.yaml`'s own `vague_verbs` list: `developed`, `created`, `facilitated`, `oversaw`, `supported`, `utilized`, `leveraged`. `style_rules.yaml` also self-contradicts: its own `verb_rules` → "Recommended verbs" inline list includes `Developed`, despite `developed` being in that same file's `vague_verbs` list five lines below the `verb_upgrades` table that explains exactly how to replace it. Resolution rule for this task: `style_rules.yaml`'s `vague_verbs` list is authoritative (it is the most detailed, most actively maintained source, with a matching `verb_upgrades` table of concrete per-domain replacements) — no verb in that list may appear as a positive-tier recommendation anywhere, including in `style_rules.yaml` itself.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verb_rule_consistency.py`:

```python
import os
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "rules")


def _load(filename):
    with open(os.path.join(RULES_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestVerbRuleConsistency(unittest.TestCase):

    def setUp(self):
        self.style_rules = _load("style_rules.yaml")
        self.language_quality = _load("language_quality.yaml")
        self.verb_taxonomy = _load("verb_taxonomy.yaml")
        self.verb_intent_mapping = _load("verb_intent_mapping.yaml")
        self.vague_verbs = set(self.style_rules["vague_verbs"])

    def test_no_vague_verb_recommended_as_an_upgrade_in_language_quality(self):
        for weak_verb, entry in self.language_quality["weak_verbs"].items():
            for suggestion in entry.get("preferred", []):
                self.assertNotIn(
                    suggestion, self.vague_verbs,
                    f"language_quality.yaml recommends vague verb '{suggestion}' as an upgrade for '{weak_verb}'"
                )

    def test_no_vague_verb_in_language_quality_elite_verbs(self):
        for v in self.language_quality["elite_verbs"]:
            self.assertNotIn(v, self.vague_verbs)

    def test_leverage_and_utilized_are_high_risk_not_medium_in_language_quality(self):
        buzzwords = self.language_quality["buzzwords"]
        self.assertNotIn("leverage", buzzwords.get("medium_risk", []))
        self.assertNotIn("utilized", buzzwords.get("medium_risk", []))
        self.assertIn("leverage", buzzwords.get("high_risk", []))
        self.assertIn("utilized", buzzwords.get("high_risk", []))

    def test_no_vague_verb_in_verb_taxonomy_positive_tiers(self):
        positive_tiers = (
            self.verb_taxonomy["universal"]
            + self.verb_taxonomy["priority_tiers"]["elite"]
            + self.verb_taxonomy["priority_tiers"]["strong"]
            + self.verb_taxonomy["priority_tiers"]["acceptable"]
        )
        for v in positive_tiers:
            self.assertNotIn(v, self.vague_verbs)

    def test_no_vague_verb_in_verb_intent_mapping_preferred_verbs(self):
        for intent, config in self.verb_intent_mapping["intent_categories"].items():
            preferred = config.get("preferred_verbs", {})
            for tier_name, verbs in preferred.items():
                for v in verbs:
                    self.assertNotIn(
                        v, self.vague_verbs,
                        f"verb_intent_mapping.yaml's '{intent}.{tier_name}' recommends vague verb '{v}'"
                    )

    def test_style_rules_recommended_verbs_list_has_no_self_contradiction(self):
        recommended_line = next(
            r for r in self.style_rules["verb_rules"] if r.startswith("Recommended verbs:")
        )
        recommended = {v.strip() for v in recommended_line.split(":", 1)[1].split(",")}
        overlap = {v for v in recommended if v.lower() in self.vague_verbs}
        self.assertEqual(overlap, set(), f"style_rules.yaml's own Recommended verbs list contains vague verbs: {overlap}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_verb_rule_consistency -v`
Expected: FAIL on at least 5 of the 6 tests (the `leverage`/`utilized` risk-tier test, the `language_quality` upgrade/elite tests, the `verb_taxonomy` positive-tiers test, the `verb_intent_mapping` preferred-verbs test, and the `style_rules` self-contradiction test).

- [ ] **Step 3: Fix style_rules.yaml's self-contradiction**

In `resume-engine/rules/style_rules.yaml`, replace:

```yaml
  - Recommended verbs: Architected, Authored, Launched, Recovered, Systematized, Audited, Spearheaded,
      Negotiated, Synthesized, Produced, Streamlined, Championed, Deployed, Developed, Expanded,
      Coordinated, Mentored, Built, Implemented, Founded, Delivered, Drove, Engineered, Established,
      Executed, Generated, Identified, Led, Managed, Orchestrated, Overhauled, Piloted, Redesigned,
      Reduced, Secured, Trained, Unified
```

with:

```yaml
  - Recommended verbs: Architected, Authored, Launched, Recovered, Systematized, Audited, Spearheaded,
      Negotiated, Synthesized, Produced, Streamlined, Championed, Deployed, Expanded,
      Coordinated, Mentored, Built, Implemented, Founded, Delivered, Drove, Engineered, Established,
      Executed, Generated, Identified, Led, Managed, Orchestrated, Overhauled, Piloted, Redesigned,
      Reduced, Secured, Trained, Unified
```

- [ ] **Step 4: Fix language_quality.yaml's six contradictions**

In `resume-engine/rules/language_quality.yaml`, replace:

```yaml
  helped:
    severity: medium

    preferred:

      - supported
      - facilitated
      - coordinated
      - executed
      - enabled
      - improved
      - implemented
      - streamlined
      - optimized
```

with:

```yaml
  helped:
    severity: medium

    preferred:

      - coordinated
      - executed
      - enabled
      - improved
      - implemented
      - streamlined
      - optimized
```

Replace:

```yaml
  worked_on:
    severity: medium

    preferred:

      - developed
      - created
      - designed
      - built
      - launched
      - executed
      - implemented
```

with:

```yaml
  worked_on:
    severity: medium

    preferred:

      - designed
      - built
      - launched
      - executed
      - implemented
```

Replace:

```yaml
  responsible_for:
    severity: high

    preferred:

      - managed
      - administered
      - directed
      - coordinated
      - owned
      - oversaw
```

with:

```yaml
  responsible_for:
    severity: high

    preferred:

      - managed
      - administered
      - directed
      - coordinated
      - owned
```

Replace:

```yaml
  assisted:
    severity: medium

    preferred:

      - supported
      - facilitated
      - contributed_to
      - coordinated
```

with:

```yaml
  assisted:
    severity: medium

    preferred:

      - contributed_to
      - coordinated
      - executed
```

Replace:

```yaml
  participated_in:
    severity: medium

    preferred:

      - contributed_to
      - collaborated_on
      - executed
      - supported
```

with:

```yaml
  participated_in:
    severity: medium

    preferred:

      - contributed_to
      - collaborated_on
      - executed
```

Replace:

```yaml
  made:
    severity: low

    preferred:

      - created
      - developed
      - generated
      - produced
      - designed
```

with:

```yaml
  made:
    severity: low

    preferred:

      - generated
      - produced
      - designed
```

Replace:

```yaml
elite_verbs:

  - built
  - created
  - developed
  - designed
  - launched
  - implemented
  - executed
  - optimized
  - improved
  - streamlined
  - automated
  - configured
  - administered
  - integrated
  - analyzed
  - audited
  - identified
  - generated
  - increased
  - reduced
  - accelerated
  - led
  - coordinated
  - enabled
  - delivered
```

with:

```yaml
elite_verbs:

  - built
  - designed
  - launched
  - implemented
  - executed
  - optimized
  - improved
  - streamlined
  - automated
  - configured
  - administered
  - integrated
  - analyzed
  - audited
  - identified
  - generated
  - increased
  - reduced
  - accelerated
  - led
  - coordinated
  - enabled
  - delivered
```

- [ ] **Step 5: Escalate leverage/utilized to high_risk/severe in language_quality.yaml**

Replace:

```yaml
  medium_risk:

    - leverage
    - utilized
    - various
    - several
    - multiple
    - numerous
    - stakeholders
    - cross-functional
    - end-to-end ownership
```

with:

```yaml
  medium_risk:

    - various
    - several
    - multiple
    - numerous
    - stakeholders
    - cross-functional
    - end-to-end ownership
```

(Add `leverage` and `utilized` to the file's `high_risk` list — read the current `high_risk` list first, since the plan's own audit of this file only read the `medium_risk`/`low` sections directly; append both terms to whatever `high_risk` currently contains, don't overwrite it.)

Replace:

```yaml
  low:

    - utilized
    - various
    - multiple
    - several
```

with:

```yaml
  low:

    - various
    - multiple
    - several
```

(Add `utilized` and `leverage technology` to this file's `ai_language_patterns.severe` list, matching the pattern already used for `leverage technology` at the `moderate` tier — read the current `severe` list first and append, don't overwrite.)

- [ ] **Step 6: Fix verb_taxonomy.yaml's four contradictions**

In `resume-engine/rules/verb_taxonomy.yaml`, replace:

```yaml
universal:

  - built
  - created
  - developed
  - designed
  - launched
  - implemented
  - executed
  - delivered
  - improved
  - optimized
  - streamlined
  - transformed
  - enhanced
  - generated
  - increased
  - reduced
  - accelerated
  - expanded
  - achieved
  - produced
```

with:

```yaml
universal:

  - built
  - designed
  - launched
  - implemented
  - executed
  - delivered
  - improved
  - optimized
  - streamlined
  - transformed
  - enhanced
  - generated
  - increased
  - reduced
  - accelerated
  - expanded
  - achieved
  - produced
```

Replace:

```yaml
priority_tiers:

  elite:

    - built
    - launched
    - implemented
    - optimized
    - automated
    - integrated
    - generated
    - increased
    - reduced
    - accelerated
    - identified
    - created
    - developed
    - led
    - delivered

  strong:

    - managed
    - coordinated
    - executed
    - facilitated
    - improved
    - analyzed
    - configured
    - administered
    - standardized

  acceptable:

    - supported
    - collaborated
    - assisted
    - maintained

# --------------------------------------------------
# VERBS TO AVOID
# --------------------------------------------------

avoid:

  - helped
  - worked_on
  - responsible_for
  - participated_in
  - did
```

with:

```yaml
priority_tiers:

  elite:

    - built
    - launched
    - implemented
    - optimized
    - automated
    - integrated
    - generated
    - increased
    - reduced
    - accelerated
    - identified
    - led
    - delivered

  strong:

    - managed
    - coordinated
    - executed
    - improved
    - analyzed
    - configured
    - administered
    - standardized

  acceptable:

    - collaborated
    - maintained

# --------------------------------------------------
# VERBS TO AVOID
# --------------------------------------------------

avoid:

  - helped
  - worked_on
  - responsible_for
  - participated_in
  - did
  - created
  - developed
  - facilitated
  - supported
  - assisted
```

- [ ] **Step 7: Fix verb_intent_mapping.yaml's four contradictions**

In `resume-engine/rules/verb_intent_mapping.yaml`, replace:

```yaml
    preferred_verbs:

      elite:

        - built
        - developed
        - created
        - launched

      strong:

        - designed
        - produced
        - generated
```

with:

```yaml
    preferred_verbs:

      elite:

        - built
        - launched
        - designed

      strong:

        - produced
        - generated
```

Replace:

```yaml
    preferred_verbs:

      elite:

        - onboarded
        - retained
        - enabled

      strong:

        - supported
        - guided
        - facilitated
```

with:

```yaml
    preferred_verbs:

      elite:

        - onboarded
        - retained
        - enabled

      strong:

        - guided
```

Replace:

```yaml
    preferred_verbs:

      elite:

        - trained
        - coached
        - mentored

      strong:

        - guided
        - educated
        - facilitated
```

with:

```yaml
    preferred_verbs:

      elite:

        - trained
        - coached
        - mentored

      strong:

        - guided
        - educated
```

Replace:

```yaml
    preferred_verbs:

      elite:

        - built
        - developed
        - automated

      strong:

        - maintained
        - generated
        - monitored
```

with:

```yaml
    preferred_verbs:

      elite:

        - built
        - automated

      strong:

        - maintained
        - generated
        - monitored
```

Replace:

```yaml
    preferred_verbs:

      elite:

        - created
        - developed
        - authored

      strong:

        - wrote
        - edited
        - refined
```

with:

```yaml
    preferred_verbs:

      elite:

        - authored

      strong:

        - wrote
        - edited
        - refined
```

- [ ] **Step 8: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_verb_rule_consistency -v`
Expected: PASS (6 tests)

- [ ] **Step 9: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation tests.test_verb_rule_consistency -v
```
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add resume-engine/rules/style_rules.yaml resume-engine/rules/language_quality.yaml resume-engine/rules/verb_taxonomy.yaml resume-engine/rules/verb_intent_mapping.yaml tests/test_verb_rule_consistency.py
git commit -m "$(cat <<'EOF'
Reconcile 7 verb contradictions across the four verb-rule files

style_rules.yaml, language_quality.yaml, verb_taxonomy.yaml, and
verb_intent_mapping.yaml get concatenated into the same bullet-rewrite
prompt and directly contradicted each other on facilitated, oversaw,
developed, created, supported, utilized, and leveraged -- each banned in
style_rules.yaml's vague_verbs list while recommended as a strong/elite
upgrade elsewhere (style_rules.yaml even contradicted itself). Resolution
rule: style_rules.yaml's vague_verbs list is authoritative; added a
regression test that mechanically verifies no vague verb appears in any
positive tier across all four files.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Fix load_yaml's silent fallback

**Files:**
- Modify: `scripts/orchestrator.py` (`ResumeEngine.load_yaml`)
- Test: extend `tests/test_orchestrator_load_prompt.py`

**Interfaces:**
- Consumes: `orchestrator.ResumeEngine()`.
- Produces: `ResumeEngine.load_yaml(dir_path, filename) -> dict` now raises `FileNotFoundError` instead of silently returning `{}` on a missing file. Every current call site (`manager_test.yaml`, `believability.yaml`, `style_rules.yaml`, `language_quality.yaml`, `verb_taxonomy.yaml`, `verb_intent_mapping.yaml`, `hard_failures.yaml`, `truthfulness_rules.yaml`) points at a file that still exists after Tasks 1-2, so removing the fallback is safe.

**Context:** `load_yaml` has the exact same silent-fallback bug `load_prompt` had before Phase 1 Task 1 fixed it — swallowing `FileNotFoundError` and returning an empty dict instead of raising. This matters now specifically because Task 1 just deleted two files that used to be loaded via this method (`ats_rules.yaml` was removed from its one live call site, but if any other code still calls `load_yaml(self.rules_dir, "ats_rules.yaml")` or `"formatting_rules.yaml"` and this method silently returns `{}`, that mistake would be invisible instead of raising loudly like it should.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_orchestrator_load_prompt.py` (reuses the existing `TestLoadPromptFailsLoudly` class and its `self.engine`):

```python
    def test_load_yaml_raises_instead_of_silent_empty_dict(self):
        with self.assertRaises(FileNotFoundError):
            self.engine.load_yaml(self.engine.rules_dir, "this_file_does_not_exist.yaml")

    def test_load_yaml_still_loads_a_real_file(self):
        data = self.engine.load_yaml(self.engine.rules_dir, "style_rules.yaml")
        self.assertIsInstance(data, dict)
        self.assertIn("vague_verbs", data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_load_prompt -v`
Expected: FAIL — `load_yaml` currently returns `{}` for a missing file instead of raising.

- [ ] **Step 3: Remove the silent fallback**

In `scripts/orchestrator.py`, replace:

```python
    def load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}
```

with:

```python
    def load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        with open(path, "r") as f:
            return yaml.safe_load(f)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_load_prompt -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation tests.test_verb_rule_consistency -v
```
Expected: all PASS. (This is the critical check for this task — if any call site still references a deleted file, this run surfaces it immediately instead of silently degrading.)

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_load_prompt.py
git commit -m "$(cat <<'EOF'
Fix load_yaml's silent fallback on missing files

Same bug class as load_prompt (fixed in Phase 1): swallowed
FileNotFoundError and returned {} instead of raising. Matters now
specifically because Task 1 just deleted two files this method used to
load -- any missed call site would previously have failed silently with an
empty rules dict instead of a clear error.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Make Certifications and Education fixed-content, remove them from the LLM's output schema

**Files:**
- Create: `scripts/fixed_content.py`
- Test: Create `tests/test_fixed_content.py`
- Modify: `scripts/orchestrator.py` (`TemplateSchema` — remove `CERTIFICATIONS`/`SECTION_CERTIFICATIONS`/`EDUCATION` free-form fields, add two achievement-key fields)

**Interfaces:**
- Consumes: none.
- Produces: `fixed_content.CERTIFICATIONS: list[dict]`, `fixed_content.build_education(ku_key: str, kckcc_key: str) -> list[dict]` — both return data shaped exactly as `render_html.py`'s `build_certifications_html`/`build_education_html` already expect (`title`/`org`/`year` dicts; `degree`/`institution`/`year`/`description` dicts). Task 5 consumes both of these to inject fixed content into `resume_data` after the builder call.

**Context:** `ResumeDesignSystem.md` fixes Certifications completely (3 entries, fixed order, fixed title/org/year, never varies) and fixes almost all of Education (3 schools, fixed order, fixed institution/degree/GPA-line) — the sole per-resume variable is which one of several pre-approved achievement bullets to feature per school (per this project's design decision: "Fixed structure, LLM picks the achievement bullet"). `resume-engine/knowledge_base/bullet-bank.md:237-264` already contains the exact pre-approved options for KU (3 options) and KCKCC (3 options) — JCCC has no achievement bullet at all, just one fixed GPA+coursework line (`ResumeDesignSystem.md`: "JCCC: exactly 1 bullet (GPA + coursework summary line)").

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixed_content.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import fixed_content  # noqa: E402
import orchestrator  # noqa: E402


class TestFixedContent(unittest.TestCase):

    def test_certifications_are_exactly_three_in_fixed_order(self):
        certs = fixed_content.CERTIFICATIONS
        self.assertEqual(len(certs), 3)
        self.assertEqual(certs[0], {"title": "Email Marketing Software Certification", "org": "HubSpot", "year": "2026"})
        self.assertEqual(certs[1], {"title": "Video for Sales Certification", "org": "Vidyard", "year": "2021"})
        self.assertEqual(certs[2], {"title": "Camp Portfolio", "org": "Bernstein Rein, Kansas City", "year": "2008"})

    def test_build_education_returns_three_items_in_fixed_order(self):
        edu = fixed_content.build_education("content_generalist", "writing_content")
        self.assertEqual(len(edu), 3)
        self.assertEqual(edu[0]["institution"], "University of Kansas")
        self.assertEqual(edu[1]["institution"], "Kansas City Kansas Community College")
        self.assertEqual(edu[2]["institution"], "Johnson County Community College")

    def test_build_education_selects_the_requested_ku_achievement(self):
        edu = fixed_content.build_education("email_ops", "generalist")
        self.assertIn("800%", edu[0]["description"])
        self.assertIn("managed promotional campaigns", edu[0]["description"])

    def test_build_education_falls_back_to_first_option_on_unknown_key(self):
        edu = fixed_content.build_education("not_a_real_key", "not_a_real_key_either")
        self.assertIn(edu[0]["description"], fixed_content.KU_ACHIEVEMENT_OPTIONS.values())
        self.assertIn(edu[1]["description"], fixed_content.KCKCC_ACHIEVEMENT_OPTIONS.values())

    def test_template_schema_has_no_free_form_certifications_or_education_fields(self):
        fields = orchestrator.TemplateSchema.model_fields
        self.assertNotIn("CERTIFICATIONS", fields)
        self.assertNotIn("SECTION_CERTIFICATIONS", fields)
        self.assertNotIn("EDUCATION", fields)
        self.assertIn("KU_ACHIEVEMENT_KEY", fields)
        self.assertIn("KCKCC_ACHIEVEMENT_KEY", fields)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_fixed_content -v`
Expected: FAIL — `scripts/fixed_content.py` doesn't exist yet; `TemplateSchema` still has the old fields.

- [ ] **Step 3: Create scripts/fixed_content.py**

```python
"""
fixed_content.py — Canonical, unchanging resume content per ResumeDesignSystem.md.

Certifications and most of Education have zero legitimate per-JD variation,
so they live here as Python constants instead of LLM-generated fields: the
builder is never asked to produce this content and can't introduce drift.
The one genuine per-resume variable -- which pre-approved achievement bullet
to feature for KU and KCKCC -- is a selection from a fixed menu, not free
text; JCCC has no achievement bullet at all (spec: exactly 1 fixed bullet).

Source: resume-engine/knowledge_base/bullet-bank.md's EDUCATION section.
"""

CERTIFICATIONS = [
    {"title": "Email Marketing Software Certification", "org": "HubSpot", "year": "2026"},
    {"title": "Video for Sales Certification", "org": "Vidyard", "year": "2021"},
    {"title": "Camp Portfolio", "org": "Bernstein Rein, Kansas City", "year": "2008"},
]

KU_ACHIEVEMENT_OPTIONS = {
    "content_generalist": "Marketing Intern, Lied Center of Performing Arts, drove 800% social media follower growth through organic content strategy and audience engagement",
    "email_ops":          "Marketing Intern, Lied Center of Performing Arts, managed promotional campaigns and digital channels, growing social media following by 800%",
    "content":            "Marketing Intern, Lied Center of Performing Arts, produced editorial and promotional content across channels, built early instinct for audience-specific messaging",
}

KCKCC_ACHIEVEMENT_OPTIONS = {
    "writing_content": "Editor-in-Chief, student newspaper for 1.5 years, assigned coverage, led editorial team, and managed weekly publication from story conception through print",
    "enablement_mgmt": "Editor-in-Chief, student newspaper, led a team of reporters and columnists, managed editorial calendar, and upheld writing and voice standards across all content",
    "generalist":       "Editor-in-Chief, Kansas Colloquies student newspaper, managed publication end-to-end for 1.5 years while maintaining a full academic scholarship",
}


def build_education(ku_achievement_key: str, kckcc_achievement_key: str) -> list[dict]:
    """
    Assembles the fixed 3-item Education list. `ku_achievement_key` and
    `kckcc_achievement_key` select which pre-approved achievement bullet to
    feature per school; an unrecognized key falls back to that school's
    first option rather than raising, since every option is genuine,
    verified content -- an archetype-suboptimal pick is a quality issue,
    not a truthfulness issue.
    """
    ku_bullet = KU_ACHIEVEMENT_OPTIONS.get(
        ku_achievement_key, next(iter(KU_ACHIEVEMENT_OPTIONS.values()))
    )
    kckcc_bullet = KCKCC_ACHIEVEMENT_OPTIONS.get(
        kckcc_achievement_key, next(iter(KCKCC_ACHIEVEMENT_OPTIONS.values()))
    )
    return [
        {
            "degree": "BS, Journalism + Strategic Communication",
            "institution": "University of Kansas",
            "year": "2006–2008",
            "description": f"3.56 GPA, Phi Theta Kappa Scholarship recipient; {ku_bullet}",
        },
        {
            "degree": "AA, Journalism",
            "institution": "Kansas City Kansas Community College",
            "year": "2004–2006",
            "description": f"3.75 GPA, Full academic scholarship, Graduated with honors; {kckcc_bullet}",
        },
        {
            "degree": "Relevant Coursework, Graphic Design",
            "institution": "Johnson County Community College",
            "year": "2010–2011",
            "description": "3.86 GPA, studied color theory, typography, illustration, 3D concepts, desktop publishing, and film photography",
        },
    ]
```

- [ ] **Step 4: Narrow TemplateSchema**

In `scripts/orchestrator.py`, remove:

```python
    SECTION_EDUCATION:      str       = Field(default="Education")
    EDUCATION:              List[dict] = Field(
        description=(
            "KU, KCKCC, and JCCC items. Each dict must contain: "
            "degree (str), institution (str), year (str), description (str). "
            "KU: exactly 2 bullets. KCKCC: exactly 2 bullets. JCCC: exactly 1 bullet."
        )
    )
    SECTION_CERTIFICATIONS: str       = Field(default="Training & Certifications")
    CERTIFICATIONS:         List[dict] = Field(
        min_length=3, max_length=3,
        description=(
            "Exactly 3 certifications in fixed order. Each dict: title, org, year. "
            "Order: 1) Email Marketing Software Certification | HubSpot | 2026, "
            "2) Video for Sales Certification | Vidyard | 2021, "
            "3) Camp Portfolio | Bernstein Rein, Kansas City | 2008."
        )
    )
```

and replace with:

```python
    KU_ACHIEVEMENT_KEY:     str       = Field(description=(
        "Which pre-approved KU achievement bullet best fits this JD's archetype. "
        "Must be exactly one of: content_generalist, email_ops, content."
    ))
    KCKCC_ACHIEVEMENT_KEY:  str       = Field(description=(
        "Which pre-approved KCKCC achievement bullet best fits this JD's archetype. "
        "Must be exactly one of: writing_content, enablement_mgmt, generalist."
    ))
```

(Leave `SECTION_EDUCATION` and `SECTION_CERTIFICATIONS` removed entirely — Task 5 forces both section header labels unconditionally in Python, so the LLM is never asked for them either.)

- [ ] **Step 5: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_fixed_content -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation tests.test_verb_rule_consistency tests.test_fixed_content -v
```

**Note:** removing `CERTIFICATIONS`/`EDUCATION` from `TemplateSchema` will very likely break the mocked `TemplateSchema` JSON in `tests/test_orchestrator_build_checkpoint.py`'s existing tests if those tests validate against the real schema anywhere (check whether `GeminiClient.parse_json`'s mocked return value is validated against `TemplateSchema` before this task, or just passed through as a raw dict) — if any existing test fails here as a direct result of this schema change, that is expected and must be fixed as part of this task (update the mocked JSON fixtures, do not weaken the assertions), not deferred.

Expected after any necessary fixture updates: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/fixed_content.py scripts/orchestrator.py tests/test_fixed_content.py
git commit -m "$(cat <<'EOF'
Make Certifications and Education fixed content, not LLM-generated

Neither section has legitimate per-JD variation beyond which pre-approved
achievement bullet to feature per school (already curated in
bullet-bank.md). Certifications is now a pure Python constant; Education's
institution/degree/GPA/order are constants, and the builder only selects
(never writes) one achievement-bullet key per KU and KCKCC from a fixed
menu.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Force fixed content and formatting as unconditional post-processing

**Files:**
- Create: `scripts/normalize_resume.py`
- Test: Create `tests/test_normalize_resume.py`
- Modify: `scripts/orchestrator.py` (`build_tailored_resume` — call the new normalizer right after the builder call, before Step 5's critique)

**Interfaces:**
- Consumes: `fixed_content.CERTIFICATIONS`, `fixed_content.build_education(ku_key, kckcc_key)` (from Task 4).
- Produces: `normalize_resume.normalize(resume_data: dict) -> dict` — a pure function, returns a new dict with `CERTIFICATIONS`/`EDUCATION` injected, `SECTION_*` labels forced to their canonical strings, `TAGLINE` forced uppercase, and `&`/`and` substitution applied to `TAGLINE` and `SECTION_*` values. Task 6's validator and Task 7's retry loop both operate on `normalize()`'s output, not the builder's raw output.

**Context:** Several rules have zero legitimate per-JD variation but were previously left to the LLM to get right on every call: section header labels (`"Skills"`, `"Professional Summary"`, etc. — spelled out verbatim in the spec), the tagline's hard-coded-uppercase requirement (`ResumeDesignSystem.md`: "hard‑coded uppercase in HTML, not via CSS text‑transform" — meaning the *data string* itself must already be uppercase), and "&" vs "and" usage in headings/labels. None of these require generation — they're either always the same string or a mechanical transform of a string the LLM already produced. Doing them in Python removes an entire category of "did the LLM remember the formatting rule" risk.

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalize_resume.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import normalize_resume  # noqa: E402
import fixed_content  # noqa: E402


class TestNormalizeResume(unittest.TestCase):

    def setUp(self):
        self.raw = {
            "NAME": "Morgan Escott",
            "TAGLINE": "lifecycle marketing manager and crm strategist",
            "KU_ACHIEVEMENT_KEY": "content_generalist",
            "KCKCC_ACHIEVEMENT_KEY": "writing_content",
        }

    def test_injects_fixed_certifications(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["CERTIFICATIONS"], fixed_content.CERTIFICATIONS)

    def test_injects_fixed_education_using_the_selected_achievement_keys(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(len(result["EDUCATION"]), 3)
        self.assertIn("800% social media follower growth", result["EDUCATION"][0]["description"])

    def test_forces_section_header_labels(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["SECTION_SUMMARY"], "Professional Summary")
        self.assertEqual(result["SECTION_SKILLS"], "Skills")
        self.assertEqual(result["SECTION_EXPERIENCE"], "Work Experience")
        self.assertEqual(result["SECTION_CERTIFICATIONS"], "Training & Certifications")
        self.assertEqual(result["SECTION_EDUCATION"], "Education")

    def test_forces_tagline_uppercase_and_ampersand(self):
        result = normalize_resume.normalize(self.raw)
        self.assertEqual(result["TAGLINE"], "LIFECYCLE MARKETING MANAGER & CRM STRATEGIST")

    def test_does_not_mutate_the_input_dict(self):
        original = dict(self.raw)
        normalize_resume.normalize(self.raw)
        self.assertEqual(self.raw, original)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_normalize_resume -v`
Expected: FAIL — `scripts/normalize_resume.py` doesn't exist yet.

- [ ] **Step 3: Create scripts/normalize_resume.py**

```python
"""
normalize_resume.py — Unconditional post-processing for content that has
zero legitimate per-JD variation. Runs on the builder's raw output before
critique and before the validator (validate_resume.py) sees it, so those
downstream steps only ever deal with already-correct fixed content and
formatting, never the builder's attempt at it.
"""

import re

import fixed_content

_SECTION_DEFAULTS = {
    "SECTION_SUMMARY": "Professional Summary",
    "SECTION_SKILLS": "Skills",
    "SECTION_EXPERIENCE": "Work Experience",
    "SECTION_CERTIFICATIONS": "Training & Certifications",
    "SECTION_EDUCATION": "Education",
}


def _and_to_ampersand(text: str) -> str:
    return re.sub(r"\band\b", "&", text)


def normalize(resume_data: dict) -> dict:
    """Returns a new dict; never mutates the input."""
    result = dict(resume_data)

    result["CERTIFICATIONS"] = fixed_content.CERTIFICATIONS
    result["EDUCATION"] = fixed_content.build_education(
        result.get("KU_ACHIEVEMENT_KEY", ""),
        result.get("KCKCC_ACHIEVEMENT_KEY", ""),
    )

    for key, value in _SECTION_DEFAULTS.items():
        result[key] = value

    if result.get("TAGLINE"):
        result["TAGLINE"] = _and_to_ampersand(result["TAGLINE"]).upper()

    return result
```

- [ ] **Step 4: Wire normalize() into build_tailored_resume**

In `scripts/orchestrator.py`'s `build_tailored_resume`, after the builder call's `resume_data = GeminiClient.parse_json(resume_text)` block (Step 4) and before the `checkpoint["resume_data"] = resume_data` line, add the normalization call. Replace:

```python
            resume_data = GeminiClient.parse_json(resume_text)
            if not resume_data:
                print("  ERROR: Could not parse builder JSON.")
                print(f"  Raw response (first 500 chars):\n{resume_text[:500]}")
                return {}

            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)
```

with:

```python
            resume_data = GeminiClient.parse_json(resume_text)
            if not resume_data:
                print("  ERROR: Could not parse builder JSON.")
                print(f"  Raw response (first 500 chars):\n{resume_text[:500]}")
                return {}

            resume_data = normalize_resume.normalize(resume_data)

            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)
```

Add the import near the top of `scripts/orchestrator.py`, alongside the existing `from render_html import render_html` line:

```python
import normalize_resume
```

**Note:** the checkpoint-resume path (`resume_data = checkpoint.get("resume_data")`, a few lines above this block, used when resuming an interrupted run) already contains a previously-normalized dict from a prior run, since it's saved *after* normalization now — no separate handling needed for that branch.

- [ ] **Step 5: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_normalize_resume -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation tests.test_verb_rule_consistency tests.test_fixed_content tests.test_normalize_resume -v
```

**Note:** `tests/test_orchestrator_build_checkpoint.py`'s existing mocked `TemplateSchema` JSON fixtures (e.g. `{"SUMMARY": "Test summary."}`) will now pass through `normalize()`, which calls `fixed_content.build_education("", "")` — this must not raise (Task 4's fallback-to-first-option behavior handles empty-string keys gracefully) but confirm this explicitly by running the suite; if any test's mocked data trips on a missing key `normalize()` assumes is present, fix the fixture, not `normalize()`'s contract.

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/normalize_resume.py scripts/orchestrator.py tests/test_normalize_resume.py
git commit -m "$(cat <<'EOF'
Force fixed content and formatting as unconditional post-processing

Section header labels, tagline uppercase-and-ampersand formatting, and
Certifications/Education content have zero legitimate per-JD variation.
normalize_resume.normalize() runs right after the builder call and forces
all of it in Python, so critique and the validator only ever see
already-correct content -- removing an entire category of "did the LLM
remember the formatting rule" risk.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Build the deterministic validator module

**Files:**
- Create: `scripts/validate_resume.py`
- Test: Create `tests/test_validate_resume.py`

**Interfaces:**
- Consumes: a normalized `resume_data` dict (Task 5's `normalize()` output shape) and `style_rules.yaml` (loaded via the existing `ResumeEngine.load_yaml` pattern, but this module takes the already-loaded rules dict as a parameter rather than loading it itself, so it stays a pure, independently-testable function with no filesystem dependency).
- Produces: `validate_resume.validate(resume_data: dict, style_rules: dict) -> list[str]` — a list of human-readable violation strings, empty if compliant. Task 7 consumes this list to decide whether to retry.

**Context:** Nothing in the current pipeline checks any of `ResumeDesignSystem.md`'s hard rules before a PDF is generated. This task builds the checks that are genuinely mechanical — no LLM judgment needed to determine whether they pass or fail.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_resume.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_resume  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
    "forbidden_openers": ["responsible for", "helped with", "worked on", "assisted with", "participated in"],
    "bullet_structure": {"one_liner_max_chars": 120, "two_liner_max_chars": 220, "max_printed_lines": 2},
    "skills_section": {"line_max_chars": 110},
}


def _valid_resume():
    return {
        "SUMMARY_TEXT": "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Returning to full-time work after a caregiving pause.",
        "SKILLS": ["**Lifecycle & Retention Marketing:** Email Automation, Segmentation, Drip Campaigns"],
        "EXPERIENCE": [
            {"company": "Treering", "achievements": [
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
                "Architected the SDR onboarding program used company-wide for three years",
            ]},
        ],
        "WHY_TEXT": "",
    }


class TestValidateResume(unittest.TestCase):

    def test_valid_resume_has_no_violations(self):
        violations = validate_resume.validate(_valid_resume(), STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_forbidden_phrase_in_summary(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>A results-driven lifecycle marketer.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

    def test_flags_forbidden_opener_in_bullet(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append("Responsible for CRM data hygiene")
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("forbidden opener" in v.lower() for v in violations))

    def test_flags_duplicate_opening_verb_across_bullets(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Architected the SDR onboarding program used company-wide for three years",
            "Architected the CRM data model powering territory reporting",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("architected" in v.lower() and "unique" in v.lower() for v in violations))

    def test_flags_bullet_exceeding_two_liner_max_chars(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append("X" * 221)
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("exceeds" in v.lower() and "220" in v for v in violations))

    def test_flags_skills_line_exceeding_max_chars(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**Category:** " + ", ".join(["Item"] * 40)]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("110" in v for v in violations))

    def test_flags_pronoun_outside_why_section(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>I am a lifecycle marketer.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_allows_pronoun_inside_why_section(self):
        resume = _valid_resume()
        resume["WHY_TEXT"] = "<p><em>I built the SDR Process Map at Treering for exactly this reason.</em></p>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_duplicate_metric_across_summary_and_bullets(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>Recovered 3M in dormant pipeline as a lifecycle marketer.</strong>"
        # _valid_resume() already has "Recovered 3M" in a bullet -- now it's in both places.
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("3m" in v.lower() and ("once" in v.lower() or "duplicate" in v.lower()) for v in violations))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_validate_resume -v`
Expected: FAIL — `scripts/validate_resume.py` doesn't exist yet.

- [ ] **Step 3: Create scripts/validate_resume.py**

```python
"""
validate_resume.py — Deterministic checks for the parts of ResumeDesignSystem.md
that require generated text (Summary, Skills, Bullets, Why) rather than fixed
content. Pure function: takes a normalized resume_data dict and an already-
loaded style_rules dict, returns a list of violation strings. No filesystem
access, no LLM calls -- everything here is mechanically checkable.
"""

import re

_METRIC_PATTERN = re.compile(r"\$?\d[\d,.]*[%MK]?\b", re.IGNORECASE)
_PRONOUN_PATTERN = re.compile(r"\b(i|me|my|we|our)\b", re.IGNORECASE)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _all_bullets(resume_data: dict) -> list[str]:
    bullets = []
    for job in resume_data.get("EXPERIENCE", []):
        bullets.extend(job.get("achievements", []))
    return bullets


def _check_forbidden_phrases(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    phrases = [p.lower() for p in style_rules.get("forbidden_phrases", [])]
    haystacks = [_strip_html(resume_data.get("SUMMARY_TEXT", ""))] + _all_bullets(resume_data)
    for text in haystacks:
        lowered = text.lower()
        for phrase in phrases:
            if phrase in lowered:
                violations.append(f"Forbidden phrase '{phrase}' found in: {text!r}")
    return violations


def _check_forbidden_openers(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    openers = [o.lower() for o in style_rules.get("forbidden_openers", [])]
    for bullet in _all_bullets(resume_data):
        lowered = bullet.lower()
        for opener in openers:
            if lowered.startswith(opener):
                violations.append(f"Bullet uses forbidden opener '{opener}': {bullet!r}")
    return violations


def _check_unique_opening_verbs(resume_data: dict) -> list[str]:
    violations = []
    seen = {}
    for bullet in _all_bullets(resume_data):
        first_word = bullet.split(" ", 1)[0].lower().rstrip(",;:")
        if first_word in seen:
            violations.append(
                f"Opening verb '{first_word}' is not unique across the CV "
                f"(used in both {seen[first_word]!r} and {bullet!r})"
            )
        else:
            seen[first_word] = bullet
    return violations


def _check_bullet_lengths(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    limits = style_rules.get("bullet_structure", {})
    two_liner_max = limits.get("two_liner_max_chars", 220)
    for bullet in _all_bullets(resume_data):
        if len(bullet) > two_liner_max:
            violations.append(f"Bullet exceeds {two_liner_max}-char two-liner max ({len(bullet)} chars): {bullet!r}")
    return violations


def _check_skills_line_lengths(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    max_chars = style_rules.get("skills_section", {}).get("line_max_chars", 110)
    for line in resume_data.get("SKILLS", []):
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        if len(plain) > max_chars:
            violations.append(f"Skills line exceeds {max_chars}-char max ({len(plain)} chars): {line!r}")
    return violations


def _check_pronouns_outside_why(resume_data: dict) -> list[str]:
    violations = []
    checked_fields = {
        "SUMMARY_TEXT": _strip_html(resume_data.get("SUMMARY_TEXT", "")),
    }
    checked_fields.update({f"SKILLS[{i}]": s for i, s in enumerate(resume_data.get("SKILLS", []))})
    checked_fields.update({f"BULLET[{i}]": b for i, b in enumerate(_all_bullets(resume_data))})
    for field_name, text in checked_fields.items():
        if _PRONOUN_PATTERN.search(text):
            violations.append(f"Pronoun found outside the Why section, in {field_name}: {text!r}")
    return violations


def _check_metric_uniqueness(resume_data: dict) -> list[str]:
    violations = []
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    bullets = _all_bullets(resume_data)
    summary_metrics = set(m.lower() for m in _METRIC_PATTERN.findall(summary))
    seen_in_bullets: dict = {}
    for bullet in bullets:
        for metric in _METRIC_PATTERN.findall(bullet):
            key = metric.lower()
            if key in summary_metrics:
                violations.append(f"Metric '{metric}' appears in both the Summary and a bullet: {bullet!r}")
            elif key in seen_in_bullets:
                violations.append(
                    f"Metric '{metric}' appears more than once, in both "
                    f"{seen_in_bullets[key]!r} and {bullet!r}"
                )
            else:
                seen_in_bullets[key] = bullet
    return violations


def validate(resume_data: dict, style_rules: dict) -> list[str]:
    violations: list[str] = []
    violations.extend(_check_forbidden_phrases(resume_data, style_rules))
    violations.extend(_check_forbidden_openers(resume_data, style_rules))
    violations.extend(_check_unique_opening_verbs(resume_data))
    violations.extend(_check_bullet_lengths(resume_data, style_rules))
    violations.extend(_check_skills_line_lengths(resume_data, style_rules))
    violations.extend(_check_pronouns_outside_why(resume_data))
    violations.extend(_check_metric_uniqueness(resume_data))
    return violations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_validate_resume -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_resume.py tests/test_validate_resume.py
git commit -m "$(cat <<'EOF'
Build the deterministic resume validator

Checks the parts of ResumeDesignSystem.md that require generated text
(banned phrases, forbidden openers, unique opening verbs, bullet/skills
length limits, pronoun placement, metric uniqueness) with real Python
logic instead of trusting LLM prompt-following. Pure function, no
filesystem or API access -- Task 7 wires this into the build pipeline
with a retry loop.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Wire the validator into the pipeline with targeted retry, page-count trim loop, and deterministic bullet ordering

**Files:**
- Modify: `scripts/orchestrator.py` (`build_tailored_resume` — add the validation/retry loop after Step 4's normalization, and the page-count trim loop after Step 7's PDF generation; `audit_and_refine_bullets` — sort refined bullets deterministically before they're handed to the builder)
- Test: extend `tests/test_orchestrator_build_checkpoint.py`

**Interfaces:**
- Consumes: `validate_resume.validate(resume_data, style_rules) -> list[str]` (Task 6), `resume_data["_page_count"]` (Phase 1 Task 5).
- Produces: `build_tailored_resume` now returns `{}` (not a partially-invalid resume) when the validator's targeted-retry loop is exhausted (3 attempts) or the page-count trim loop is exhausted (4 attempts, one per the spec's trim-priority step) — matching the existing PDF-failure return convention exactly, so `main()`'s generic `tracker.mark_failed(...)` on falsy return needs no changes.

**Context:** This is the integration point that makes Tasks 5-6 actually enforce anything. Two loops:
1. **Content violations** (Task 6's `validate()`): on failure, send only the flagged bullets/fields and their violation reasons back to Gemini in a small follow-up call ("fix only these issues, change nothing else"), re-validate, cap at 3 attempts.
2. **Page count**: `generate-pdf.mjs` already computes this (Phase 1); if `_page_count > 2`, apply the spec's exact trim-priority order (trim Summary/Why to their line limits → tighten bullets → remove least-relevant bullets starting with Treering → drop Why entirely) as successive small follow-up calls, re-rendering and re-checking after each, capped at 4 attempts (one per trim step).

Also folds in `rank_bullets.md`'s insight (retired as a prompt in Phase 2 Task 1): bullet ordering by manager-test pass/fail then believability is a deterministic sort over data `audit_and_refine_bullets` already computes via `CritiqueSchema` (`manager_test`, `believability_score`) — no LLM call needed. (`CritiqueSchema` currently has no `ai_risk` field, so this sort uses only `manager_test` and `believability_score`; adding an `ai_risk` field to the per-bullet audit is out of scope for this task.)

- [ ] **Step 1: Write the failing test for the retry loop**

Add to `tests/test_orchestrator_build_checkpoint.py`'s `TestBuildCheckpointResume` class:

```python
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_validator_retry_fixes_a_violation_then_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        builder_call_count = {"n": 0}

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                builder_call_count["n"] += 1
                if builder_call_count["n"] == 1:
                    return (json.dumps({
                        "SUMMARY_TEXT": "<strong>A results-driven marketer.</strong>",
                        "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
                        "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
                    }), {})
                return (json.dumps({
                    "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
                    "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
                    "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
                }), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "top_third_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        self.assertNotIn("results-driven", result["SUMMARY_TEXT"])
        self.assertEqual(builder_call_count["n"], 2)  # 1 initial + 1 targeted fix

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_validator_retry_exhaustion_returns_falsy(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        always_bad = {
            "SUMMARY_TEXT": "<strong>A results-driven marketer.</strong>",
            "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
            "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(always_bad), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result, {})
        mock_subprocess_run.assert_not_called()  # never reached PDF generation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: FAIL — no retry loop exists yet, so the builder is only ever called once and the "always bad" case does not return `{}` before reaching PDF generation.

- [ ] **Step 3: Add the targeted-retry validation loop**

In `scripts/orchestrator.py`, add the import near the top (alongside `import normalize_resume`):

```python
import validate_resume
```

Replace the builder-call block (Step 4, after Task 5's `normalize_resume.normalize(resume_data)` call and before `checkpoint["resume_data"] = resume_data`):

```python
            resume_data = normalize_resume.normalize(resume_data)

            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)
```

with:

```python
            resume_data = normalize_resume.normalize(resume_data)

            style_rules_for_validation = self.load_yaml(self.rules_dir, "style_rules.yaml")
            violations = validate_resume.validate(resume_data, style_rules_for_validation)
            max_fix_attempts = 3
            fix_attempt = 0
            while violations and fix_attempt < max_fix_attempts:
                fix_attempt += 1
                print(f"  Validator found {len(violations)} issue(s), attempt {fix_attempt}/{max_fix_attempts}:")
                for v in violations:
                    print(f"    - {v}")
                fix_contents = (
                    f"=== ORIGINAL RESUME JSON ===\n{json.dumps(resume_data, indent=2)}\n\n"
                    f"=== ISSUES TO FIX (change nothing else) ===\n" + "\n".join(f"- {v}" for v in violations)
                )
                fix_text, _ = GeminiClient.generate(
                    model=BUILDER_MODEL,
                    system_instruction=build_prompt,
                    contents=fix_contents,
                    response_schema=TemplateSchema,
                    temperature=0.0,
                )
                fixed = GeminiClient.parse_json(fix_text or "")
                if not fixed:
                    print("  WARNING: Fix attempt returned unparseable JSON; keeping prior resume_data.")
                    break
                resume_data = normalize_resume.normalize(fixed)
                violations = validate_resume.validate(resume_data, style_rules_for_validation)

            if violations:
                print(f"  ERROR: Validator still found {len(violations)} issue(s) after {max_fix_attempts} attempts:")
                for v in violations:
                    print(f"    - {v}")
                return {}

            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)
```

- [ ] **Step 4: Run the two new tests to verify they pass**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: PASS (both new tests).

- [ ] **Step 5: Write the failing test for the page-count trim loop**

Add to the same test class:

```python
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_page_count_trim_loop_retries_then_succeeds(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        good_resume = {
            "SUMMARY_TEXT": "<strong>A lifecycle marketer with 8 years in CRM.</strong>",
            "SKILLS": [], "EXPERIENCE": [], "WHY_TEXT": "",
            "KU_ACHIEVEMENT_KEY": "content_generalist", "KCKCC_ACHIEVEMENT_KEY": "writing_content",
        }

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps(good_resume), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "top_third_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        pdf_call_count = {"n": 0}

        def subprocess_side_effect(*args, **kwargs):
            pdf_call_count["n"] += 1
            pages = 3 if pdf_call_count["n"] == 1 else 2
            return MagicMock(returncode=0, stdout=f"📊 Pages: {pages}\n", stderr="")

        mock_subprocess_run.side_effect = subprocess_side_effect

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        self.assertEqual(result["_page_count"], 2)
        self.assertEqual(pdf_call_count["n"], 2)  # 1 over-length render + 1 trimmed re-render
```

- [ ] **Step 6: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: FAIL — no trim loop exists yet, so the function returns after a single PDF render regardless of page count.

- [ ] **Step 7: Add the page-count trim loop**

In `scripts/orchestrator.py`'s Step 7, replace:

```python
        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode != 0:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
            return {}

        print(pdf_result.stdout)

        page_count_match = re.search(r"Pages:\s*(\d+)", pdf_result.stdout)
        page_count = int(page_count_match.group(1)) if page_count_match else None
        if page_count is not None and page_count > 2:
            print(f"  ⚠️  WARNING: PDF is {page_count} pages — spec requires exactly 2. "
                  f"(Automatic trim-and-retry is not implemented yet; see Phase 3.)")

        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {"json": output_path, "html": html_out, "pdf": pdf_out}
        resume_data["_page_count"] = page_count

        return resume_data
```

with:

```python
        trim_instructions = [
            "Trim the Summary to its 5-line limit and the Why section to its 8-line limit.",
            "Tighten bullets: trim adjectives, front-load keywords, collapse redundant clauses.",
            "Remove the least-relevant bullets, starting with Treering, while protecting the "
            "Outreach.io implementation and CRM-hygiene bullets.",
            "Remove the Why section entirely (set SECTION_WHY and WHY_TEXT to empty strings).",
        ]
        max_trim_attempts = len(trim_instructions)
        trim_attempt = 0
        page_count = None

        while True:
            pdf_result = subprocess.run(
                ["node", pdf_script, html_out, pdf_out, "--format=letter"],
                capture_output=True, text=True
            )
            if pdf_result.returncode != 0:
                print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
                return {}

            print(pdf_result.stdout)
            page_count_match = re.search(r"Pages:\s*(\d+)", pdf_result.stdout)
            page_count = int(page_count_match.group(1)) if page_count_match else None

            if page_count is None or page_count <= 2 or trim_attempt >= max_trim_attempts:
                break

            print(f"  PDF is {page_count} pages, applying trim step {trim_attempt + 1}/{max_trim_attempts}...")
            trim_contents = (
                f"=== ORIGINAL RESUME JSON ===\n{json.dumps(resume_data, indent=2)}\n\n"
                f"=== TRIM INSTRUCTION (apply only this step) ===\n{trim_instructions[trim_attempt]}"
            )
            trim_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=build_prompt,
                contents=trim_contents,
                response_schema=TemplateSchema,
                temperature=0.0,
            )
            trimmed = GeminiClient.parse_json(trim_text or "")
            if not trimmed:
                print("  WARNING: Trim attempt returned unparseable JSON; stopping trim loop.")
                break
            resume_data = normalize_resume.normalize(trimmed)
            render_html(resume_data, html_out)
            trim_attempt += 1

        if page_count is not None and page_count > 2:
            print(f"  ERROR: PDF still {page_count} pages after {max_trim_attempts} trim attempts.")
            return {}

        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {"json": output_path, "html": html_out, "pdf": pdf_out}
        resume_data["_page_count"] = page_count

        return resume_data
```

- [ ] **Step 8: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: PASS (all tests in this file).

- [ ] **Step 9: Add deterministic bullet ordering to audit_and_refine_bullets**

`audit_and_refine_bullets` already produces per-bullet `CritiqueSchema` results (`manager_test`, `believability_score`) during its audit loop. Locate where it assembles the final `refined_bullets`/`refined_tuples` list it returns, and sort that list before returning: bullets with `manager_test == "PASS"` first, then descending by `believability_score`. Since this task's exact insertion point depends on the loop's current variable names (which may have shifted since this plan was written), read the function's current tail (from where it builds its return value backward to where each bullet's `CritiqueSchema` result is available) before writing the sort, and add:

```python
def _bullet_sort_key(bullet_result: dict) -> tuple:
    """PASS before FAIL, then descending believability_score. Ported from the
    retired rank_bullets.md prompt -- this is a deterministic sort over data
    the audit loop already computes, not a judgment call, so it needs no LLM
    call. (ai_risk is not included: CritiqueSchema has no ai_risk field.)"""
    manager_test_rank = 0 if bullet_result.get("manager_test") == "PASS" else 1
    return (manager_test_rank, -bullet_result.get("believability_score", 0))
```

and call `sorted(..., key=_bullet_sort_key)` on the per-bullet critique results immediately before the function extracts the final list of bullet strings to return. Add a focused unit test for `_bullet_sort_key` directly (no mocking needed — it's a pure function):

```python
    def test_bullet_sort_key_ranks_pass_before_fail(self):
        pass_result = {"manager_test": "PASS", "believability_score": 50}
        fail_result = {"manager_test": "FAIL", "believability_score": 99}
        self.assertLess(
            orchestrator._bullet_sort_key(pass_result),
            orchestrator._bullet_sort_key(fail_result),
        )

    def test_bullet_sort_key_ranks_higher_believability_first_within_same_pass_status(self):
        higher = {"manager_test": "PASS", "believability_score": 90}
        lower = {"manager_test": "PASS", "believability_score": 40}
        self.assertLess(
            orchestrator._bullet_sort_key(higher),
            orchestrator._bullet_sort_key(lower),
        )
```

(Add these two to `tests/test_orchestrator_audit_resume.py`, whose existing class already imports `orchestrator` — match its existing class name rather than creating a new one.)

- [ ] **Step 10: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_audit_resume -v`
Expected: PASS (including the two new tests).

- [ ] **Step 11: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation tests.test_verb_rule_consistency tests.test_fixed_content tests.test_normalize_resume tests.test_validate_resume -v
```
Expected: all PASS.

- [ ] **Step 12: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_build_checkpoint.py tests/test_orchestrator_audit_resume.py
git commit -m "$(cat <<'EOF'
Wire the validator into the pipeline: targeted retry, page-count trim loop, deterministic bullet ordering

Content violations trigger a small targeted fix call (not a full
regenerate), capped at 3 attempts, then a loud failure (return {}) instead
of a silently-shipped bad PDF -- reusing the existing falsy-return
convention main()'s tracker.mark_failed() already handles. Page-count
overflow applies the spec's exact trim-priority order as successive
targeted calls, capped at 4 attempts. Also ports the retired rank_bullets.md
prompt's sort logic (manager_test pass/fail, then believability) into a
plain Python sort -- it was always a deterministic operation over data the
audit loop already computes, never a judgment call.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Unify banned-phrase lists across rule files

**Files:**
- Modify: `resume-engine/rules/style_rules.yaml` (expand `forbidden_phrases` to the complete union)
- Modify: `resume-engine/scoring/summary_score.yaml` (no content change needed if already a subset — verify only)
- Modify: `resume-engine/rules/language_quality.yaml` (no content change needed if already a subset after Task 2's edits — verify only)
- Test: Create `tests/test_banned_phrase_consistency.py`

**Interfaces:**
- Consumes: none.
- Produces: a regression test mechanically verifying every phrase in `summary_score.yaml`'s `buzzword_openers`, `language_quality.yaml`'s `buzzwords.high_risk`, and `language_quality.yaml`'s `ai_language_patterns.severe` also appears in `style_rules.yaml`'s `forbidden_phrases` — the same "one canonical source, others are subsets" pattern Task 2 already established for verbs.

**Context:** Discovered after Phase 2 shipped (tracker item #9, originally scoped separately but folded in here since it's the same class of fix as Task 2, just for multi-word phrases instead of single verbs). Three files independently list banned buzzwords/clichés with only partial overlap: `style_rules.yaml`'s `forbidden_phrases` (16 phrases), `summary_score.yaml`'s `buzzword_openers` (9 phrases, only 3 shared with `style_rules.yaml`), and `language_quality.yaml`'s `buzzwords.high_risk` (23 phrases as of Task 2's edits, which added `leverage`/`utilized`) plus `ai_language_patterns.severe` (7 phrases as of Task 2's edits). None of these differences are contradictions (unlike Task 2's verb case) — they're gaps: each file bans some genuine buzzwords the others miss. Resolution: `style_rules.yaml` becomes the complete union of all phrases from all three files (deduplicated), and the other two files' lists — already narrower, purpose-specific subsets — must each be verified as fully contained within it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_banned_phrase_consistency.py`:

```python
import os
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")


def _load(dir_path, filename):
    with open(os.path.join(dir_path, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestBannedPhraseConsistency(unittest.TestCase):

    def setUp(self):
        self.style_rules = _load(RULES_DIR, "style_rules.yaml")
        self.language_quality = _load(RULES_DIR, "language_quality.yaml")
        self.summary_score = _load(SCORING_DIR, "summary_score.yaml")
        self.master_list = set(self.style_rules["forbidden_phrases"])

    def test_summary_score_buzzword_openers_are_a_subset_of_style_rules(self):
        missing = set(self.summary_score["buzzword_openers"]) - self.master_list
        self.assertEqual(missing, set(), f"summary_score.yaml bans phrases not in style_rules.yaml: {missing}")

    def test_language_quality_high_risk_buzzwords_are_a_subset_of_style_rules(self):
        missing = set(self.language_quality["buzzwords"]["high_risk"]) - self.master_list
        self.assertEqual(missing, set(), f"language_quality.yaml's high_risk bans phrases not in style_rules.yaml: {missing}")

    def test_language_quality_severe_ai_patterns_are_a_subset_of_style_rules(self):
        missing = set(self.language_quality["ai_language_patterns"]["severe"]) - self.master_list
        self.assertEqual(missing, set(), f"language_quality.yaml's severe ai_language_patterns ban phrases not in style_rules.yaml: {missing}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_banned_phrase_consistency -v`
Expected: FAIL — `style_rules.yaml`'s current 16-phrase list is missing many phrases the other two files ban (e.g. `accomplished professional`, `highly motivated`, `hard worker`, `world-class`, `cutting-edge`, and more).

- [ ] **Step 3: Expand style_rules.yaml's forbidden_phrases to the complete union**

In `resume-engine/rules/style_rules.yaml`, replace:

```yaml
forbidden_phrases:
  - results-driven
  - results-oriented
  - dynamic professional
  - self-starter
  - go-getter
  - thought leader
  - visionary
  - synergized
  - synergy
  - best-in-class
  - passionate
  - driven professional
  - seeking opportunities
  - proven track record
  - detail-oriented
  - team player
```

with:

```yaml
forbidden_phrases:
  - results-driven
  - results-driven professional
  - results-oriented
  - dynamic professional
  - self-starter
  - go-getter
  - thought leader
  - visionary
  - visionary leader
  - synergized
  - synergy
  - synergies
  - best-in-class
  - passionate
  - passionate professional
  - driven professional
  - seeking opportunities
  - proven track record
  - detail-oriented
  - detail-oriented professional
  - team player
  - accomplished professional
  - highly motivated
  - highly motivated professional
  - dedicated professional
  - seasoned professional
  - strategic thinker
  - innovative thinker
  - hard worker
  - fast learner
  - excellent communication skills
  - demonstrated success
  - thrives in fast-paced environments
  - world-class
  - cutting-edge
```

(This is the deduplicated union of `style_rules.yaml`'s original 16 phrases, `summary_score.yaml`'s `buzzword_openers`, and `language_quality.yaml`'s `buzzwords.high_risk` + `ai_language_patterns.severe`, computed while writing this plan — the implementer does not need to recompute it, only verify the test passes once this replacement is applied. If Task 2's edits to `language_quality.yaml` changed since this plan was written such that a phrase here is stale or a new one is missing, trust the test failure output over this literal list and add whatever it reports missing.)

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_banned_phrase_consistency -v`
Expected: PASS (3 tests). No changes to `summary_score.yaml` or `language_quality.yaml` should be needed — they were already the narrower, purpose-specific lists; only `style_rules.yaml` needed to grow to cover them.

- [ ] **Step 5: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml tests.test_rules_consolidation tests.test_verb_rule_consistency tests.test_banned_phrase_consistency -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add resume-engine/rules/style_rules.yaml tests/test_banned_phrase_consistency.py
git commit -m "$(cat <<'EOF'
Unify banned-phrase lists: style_rules.yaml becomes the complete union

style_rules.yaml, summary_score.yaml, and language_quality.yaml each
independently listed banned buzzwords/clichés with only partial overlap --
not contradictions like Task 2's verb case, but gaps: each file caught some
genuine buzzwords the others missed. style_rules.yaml is now the complete
union; a regression test verifies the other two files' narrower lists stay
subsets of it going forward.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** Every element of the design doc's Phase 3 section is covered: rules consolidation (Tasks 1-2), fixed-content ownership for Education/Certifications/section-headers/tagline-casing/date-formatting/ampersands (Tasks 4-5), the deterministic validator (Task 6), targeted-retry + page-count trim loop + hard-fail-via-existing-falsy-return (Task 7), and the deterministic bullet-ordering sort folded in as part of Task 7 (its natural home, since `rank_bullets.md`'s retirement in Phase 2 explicitly deferred the actual sort implementation here). Task 8 (banned-phrase unification) was added after Phase 2 shipped to close tracker item #9, which fell through the gap between the original Phase 2 and Phase 3 scopes — it's independent of Tasks 1-7 and batches naturally with Task 1's rules-file cleanup.
- **Placeholder scan:** no TBD/TODO. Two steps (Task 1 Step 4's `style_rules` variable-name confirmation, Task 7 Step 9's "read the function's current tail" instruction) ask the implementer to confirm an exact variable name or insertion point against the live file rather than presuming byte-for-byte text this plan can't fully re-derive without re-reading the entire 1500+ line file at plan-writing time — both come with the complete transformation to apply once located, not a vague "do the right thing."
- **Type consistency:** `fixed_content.build_education(ku_key: str, kckcc_key: str) -> list[dict]` (Task 4) is called identically in `normalize_resume.normalize()` (Task 5) and in `tests/test_fixed_content.py`. `validate_resume.validate(resume_data: dict, style_rules: dict) -> list[str]` (Task 6) is called identically in Task 7's retry loop. `normalize_resume.normalize(resume_data: dict) -> dict` (Task 5) is called in Task 7's fix/trim loops with the same signature it's defined with.
- **Scope check:** This plan assumes Phase 1 is merged (it depends on `_page_count` from Phase 1 Task 5, and `load_prompt`'s raise-loudly behavior from Phase 1 Task 1). It does **not** require Phase 2 to be merged first — Phase 2 touches `critique_resume.md`, `ResumeCritiqueSchema`'s advisory fields, and scoring YAML retirement; this plan touches `TemplateSchema`'s generated fields, `style_rules.yaml`-family files, and the builder/render pipeline. The only shared file is `scripts/orchestrator.py`, and the two phases' edits land in different functions (`build_tailored_resume`'s Step 4/7 here vs. Step 5 in Phase 2) — if both phases are in flight on separate branches, merge whichever lands first, then rebase the other; do not attempt to write both simultaneously in the same working tree without merging one first.
