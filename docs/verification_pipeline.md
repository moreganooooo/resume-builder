# Resume Tailoring: Verification, Corrections & Recruiter Feedback Pipeline

## Overview
The latter portion of resume tailoring (Steps 4-7) includes:
1. **Step 4** - Build resume from refined bullets
2. **Step 4 Validation Loop** - Deterministic checks + LLM-driven fix attempts
3. **Step 5** - Holistic critique with recommendations
4. **Step 5.5** - Apply actionable recommendations one by one
5. **Step 6** - Save output JSON
6. **Step 7** - Render HTML & generate PDF
7. **Step 8** - Recruiter feedback queuing (via bullet_feedback.py)

---

## STEP 4: BUILDER + INITIAL VALIDATION

### File: `orchestrator.py:4887-5357`

**Entry Point:** `ResumeEngine.build_tailored_resume()` → Step 4

**Prompts/Files Involved:**
- `prompts/tailor_resume.md` - Main builder prompt, attached to builder_system
- `rules/style_rules.yaml` - Banned phrases and bullet structure rules (attached to builder)
- `scoring/ai_risk.yaml` - AI-risk scoring rubric (attached to builder)
- `profile.yml` - Role roster, bullet minimums/maximums, candidate identity

**Key Data Structures:**
- Input: `jd_keywords` (Step 1), `refined_bullets` (Step 3), `master_resume`
- Output: `resume_data` (JSON dict matching `TemplateSchema`)

### 4a. Initial Build
**Lines:** `orchestrator.py:5027-5057`

```
GeminiClient.generate(
    model=BUILDER_MODEL (gemini-3.1-flash-lite),
    system_instruction=builder_system (includes KB, style rules, AI risk rubric),
    contents=combined_contents (JD keywords + JD text + master resume + refined bullets),
    response_schema=TemplateSchema,
    temperature=0.0
)
```

**Normalization:** `normalize_resume.normalize(resume_data)` - Cleans/standardizes fields

---

### 4b. Deterministic Validation
**Lines:** `orchestrator.py:5060-5079`

**Function:** `validate_resume.validate(resume_data, style_rules, role_roster, role_bullet_minimums, role_bullet_maximums)`

**Returns:** List of violation strings

**Validation Checks:** (from `validate_resume.py`)

| Check | Function | What It Validates |
|-------|----------|-------------------|
| Forbidden phrases | `_check_forbidden_phrases()` | Word-boundary match against style_rules banned list |
| Forbidden openers | `_check_forbidden_openers()` | Bullet/achievement opening words against banned list |
| Unique opening verbs | `_check_unique_opening_verbs()` | No duplicate opening verbs across full CV |
| Tagline length | `_check_tagline_length()` | TITLE/SUBTITLE/TAGLINE length bounds |
| Bullet lengths | `_check_bullet_lengths()` | Individual bullet character count |
| Bullet widows | `_check_bullet_widows()` | Bullets wrapping to 2nd line with <5 words (configurable) |
| Skills line lengths | `_check_skills_line_lengths()` | Individual SKILLS line character/word count |
| Skills title case | `_check_skills_title_case()` | Proper case enforcement on skill categories |
| Pronouns outside WHY | `_check_pronouns_outside_why()` | Flags I/me/we/our in bullets/summary (should only be in WHY_TEXT) |
| Metric uniqueness | `_check_metric_uniqueness()` | No duplicate metrics (numbers + adjacent context word) |
| Experience completeness | `_check_experience_completeness()` | All roles in roster have entries |
| Experience order | `_check_experience_order()` | Chronological descending order |
| Education completeness | `_check_education_completeness()` | All education in profile has entries |
| Achievements per role | `_check_achievements_per_role()` | Meet min/max bullet count per role |
| Skills categories | `_check_skills_categories()` | Match declared categories in profile |
| Summary specificity | `check_summary_specificity()` | After years-of-experience figure, at least one metric/named tool/scope |
| Hallucinated tools | `_check_hallucinated_tools()` | All skills/tools in SKILLS and bullets come from verified_tools.json |
| ATS keywords | `check_keyword_coverage()` | JD keywords appear in resume text (warnings only, not fatal) |

### 4c. Surgical Micro-Repairs
**Lines:** `orchestrator.py:5071-5079`

**Function:** `repair_violations_surgically(resume_data, violations, style_rules, role_roster, role_bullet_minimums, bullet_tuples, role_bullet_maximums)`

Zero-token deterministic fixes for specific violation types:
- Empty experience entries (fill from bullet_tuples)
- Missing required fields
- Overflowing metrics (trim to limits)
- Duplicate opening verbs (swap similar one)

**If violations remain after surgical repair → Enter fix loop**

---

### 4d. Fix Loop (Hill-Climb Retry)
**Lines:** `orchestrator.py:5081-5327`

**Algorithm:**
- Up to 4 attempts
- Hill-climb: each attempt starts from `best_resume_data` (lowest violation count seen so far)
- Temperature escalation on stalls:
  - Attempt 1: temperature=0.0
  - Stalled (no improvement): escalate to 0.4, 0.6, 0.8, 0.9
- Exact repeat detection: if same violations as last attempt, explicitly tell model "your output was unchanged"

**Per-Attempt Flow:**

1. **Build fix_contents** with:
   - Current resume JSON
   - Refined bullets (for reference)
   - Context-specific hints (e.g., "All opening verbs in use", "Character counts for widow bullets")
   - Exact violations to fix
   - "YOUR LAST ATTEMPT DID NOT CHANGE THIS TEXT" if stalled

2. **Call GeminiClient.generate()** with:
   - model=BUILDER_MODEL
   - system_instruction=build_prompt (bare, no KB for cost savings)
   - contents=fix_contents
   - response_schema=TemplateSchema
   - temperature=(0.0 or escalated)

3. **Parse & validate** returned JSON:
   - Normalize with `normalize_resume.normalize()`
   - Re-validate with `validate_resume.validate()`
   - Apply surgical repairs if violations remain
   - Compare violation count against `best_violations`
   - Update `best_resume_data` if improved

4. **Track progress:**
   - `best_resume_data`, `best_violations` (persisted to checkpoint)
   - `stall_streak` counter (0 on improvement, increments on stall)

**Exit Conditions:**
- Violations empty → Success, move to Step 5
- Reached 4 attempts:
  - Separate fatal vs. soft warnings
  - Fatal violations → Return empty dict (fail this JD)
  - Soft warnings only → Continue with warnings, proceed to Step 5

---

## STEP 5: HOLISTIC CRITIQUE & RECOMMENDATIONS

### Files: `orchestrator.py:5359-5758`

**Entry Point:** Step 5 rule at line 5360

**Prompts/Files Involved:**
- `prompts/critique_resume.md` - Main critique prompt
- `scoring/` directory (15 YAML rubrics):
  - `style_rules.yaml`
  - `professional_identity_score.yaml`
  - `resume_cohesion_score.yaml`
  - `believability.yaml`
  - `experience_structure_score.yaml`
  - `manager_test.yaml`
  - `skills_scoring.yaml`
  - `role_dna.yaml`
  - `ats_match.yaml`
  - `ai_risk.yaml`
  - `evidence_alignment.yaml`
  - `summary_patterns.yaml`
  - `certifications_score.yaml`
  - `recruiter_score.yaml`
  - `specificity.yaml`
  - `summary_score.yaml`
  - `top_third_score.yaml`
- `voice-anchors.md` (via `static_prefix`)

### 5a. Critique Generation
**Lines:** `orchestrator.py:5449-5541`

**Function Call:**
```
GeminiClient.generate(
    model=CRITIQUE_MODEL (gemini-3.1-flash-lite),
    system_instruction=critique_system (critique_resume.md + static_prefix + 15 rubrics),
    contents=critique_contents (JD text + resume JSON),
    response_schema=ResumeCritiqueSchema,
    temperature=0.0
)
```

**ResumeCritiqueSchema fields:**
- `summary_alignment_score` (1-5)
- `skills_relevance_score` (1-5)
- `top_third_score` (1-5)
- `overall_fit_score` (1-5)
- `primary_identity`, `secondary_identity`
- `weakest_ats_platform`
- `hard_failures_triggered` (list) - rubric thresholds tripped
- `recommendations` (list of strings) - actionable edits
- `distinctive_moments` (list) - phrases to protect in edits
- `flags` (list) - non-actionable observations
- `flat_sections` (list) - areas lacking specificity
- `platform_parsing_risks` (list) - ATS fragility warnings

### 5b. Hard Failures → Recommendations
**Lines:** `orchestrator.py:5467-5471`

If `hard_failures_triggered` is non-empty:
```python
critique_data["recommendations"] += [
    f"Fix rubric hard failure -- {hf}" for hf in hard_failures
]
```

Pulls rubric violations into the recommendation loop for correction.

### 5c. Output to User
**Lines:** `orchestrator.py:5473-5534`

Prints scores, flags, recommendations, distinctive moments, flat sections, platform risks.

**Saved to checkpoint:** `critique_data`
**Attached to resume_data:** `_critique` field

---

## STEP 5.5: APPLY ACTIONABLE RECOMMENDATIONS

### Files: `orchestrator.py:5543-5758`

**Entry Point:** Step 5.5 rule at line 5610

**Filtering Rules:**
- Filter out questions (end with `?`) → Route to `needs_polish` list
- Remaining recommendations are edits

**Interactive Mode:**
If `interactive=True` (single-file mode only):
- Prompt user for each recommendation: y/n approve?
- Approved recommendations → added to work list
- Rejected → removed

### 5.5 Loop: Apply Each Recommendation
**Lines:** `orchestrator.py:5619-5728`

**Per-Recommendation Flow:**

1. **Build rec_contents** with:
   - Current resume JSON
   - Protected distinctive moments (don't edit these)
   - The recommendation to apply
   - Detailed instructions (edit vs. skip vs. needs_input classification)

2. **Call GeminiClient.generate()** with:
   - model=BUILDER_MODEL
   - system_instruction=build_prompt + static_prefix (needs voice grounding)
   - contents=rec_contents
   - response_schema=RecommendationApplySchema
   - temperature=0.0

3. **RecommendationApplySchema fields:**
   - `applied_recommendations` (list) - recommendations actually applied
   - `skipped_recommendations` (list) - outside-resume edits or actions
   - `needs_personal_input` (list) - needs user context to fulfill

4. **Validate the result:**
   - Normalize: `normalize_resume.normalize()`
   - Validate: `validate_resume.validate()`
   - If violations introduced: **discard this recommendation only**, track in `skipped`
   - Otherwise: accept and update `resume_data`

5. **Track & Checkpoint:**
   - `applied`, `skipped`, `needs_polish` lists
   - Save checkpoint after each recommendation (resumable)

**Exit:** All recommendations processed or skipped

### 5.5 Results
**Lines:** `orchestrator.py:5744-5757`

Prints summary of:
- Applied recommendations
- Skipped recommendations
- Needs your input (candidates for `resume polish`)

**Attached to resume_data:** `_recommendation_actions` dict

---

## VOCABULARY SUBSTITUTIONS
**Lines:** `orchestrator.py:5759-5767`

**Function:** `company_research.apply_vocabulary_substitutions_to_resume()`

After recommendations applied, deterministically swaps company vocabulary:
- Example: "customers" → "guests" (if company prefers that term)
- Per-JD company research (Step 2b)
- Regex-based, doesn't touch metrics/verbs/claims
- Last step before output (so no later step can undo it)

---

## STEP 6: SAVE OUTPUT

### Files: `orchestrator.py:5769-5782`

**Output JSON saved to:** `output/<profile>/pdf/{stem}_Resume.json`

Contains:
- Full resume_data dict
- `_critique` field (ResumeCritiqueSchema)
- `_recommendation_actions` field
- All normalized content ready for render

---

## STEP 7: RENDER HTML & GENERATE PDF

### Files: `orchestrator.py:5783-5850+`

**Prompts/Files Involved:**
- `scripts/render_html.py` - Template rendering
- `scripts/render_resume_docx.py` - DOCX generation
- `scripts/generate-pdf.mjs` (Node.js) - PDF via Playwright
- `templates/resume_template.html` - Main template
- `templates/` - CSS, fonts, images

**Process:**
1. Render HTML from resume JSON
2. Write temp HTML to disk
3. Launch Chromium with Playwright
4. Navigate to temp HTML (file:// URL)
5. PDF screenshot → output PDF

**PDF Outputs:**
- PDF: `output/<profile>/pdf/{stem}_Resume.pdf`
- HTML: `output/<profile>/html/{stem}_Resume.html`
- DOCX: `output/<profile>/docx/{stem}_Resume.docx` (if enabled)

---

## STEP 8: BULLET FEEDBACK QUEUING

### Files: `scripts/bullet_feedback.py` + `scripts/orchestrator.py:3626-3640`

**When it fires:** During Step 3 (Audit & Refine Bullets), in `audit_and_refine_bullets()`

**Entry Point:** `orchestrator.py:3626-3640`

```python
if bullet_feedback.queue_accepted_rewrite(
    original_bullet,
    rewritten_bullet,
    company,
    tags,
    critique_to_record,  # ResumeCritiqueSchema for the rewritten bullet
):
    print("Queued for bank review (needs-review.csv)")
```

### 8a. Acceptance Criteria
**Lines:** `bullet_feedback.py:116-176`

**Function:** `queue_accepted_rewrite(original_bullet, rewritten_bullet, company, tags, critique)`

Only queues if ALL of:
1. **Passes keeper bar:** `decide_action(critique) == "KEEP"` (reuses `rewrite_bullets.py` logic)
2. **Manager test passes:** `critique.get("manager_test") == "PASS"`
3. **Text not already known:** Text not in `KEEPERS`, `KEEPERS_AUDITED`, or previous rows in `NEEDS_REVIEW`

### 8b. What Gets Written
**Lines:** `bullet_feedback.py:149-176`

**File:** `profiles/<profile>/kb/needs-review.csv`

**Columns:**
- Original: `Bullet Point`, `Role / Company`, `Tags`
- Critique scores: `accuracy_score`, `believability_score`, `clarity_score`, `ats_value`, `manager_test`, `weaknesses`
- Hidden gem fields: `hidden_gem_score`, `hidden_gem_flag`, `hidden_gem_reason`
- Rewrite: `final_bullet`, `rewrite_status` (blank), `rewrite_attempts`, `rewrite_date`

**Return:** True if queued, False if rejected or already known

### 8c. Post-Processing
After a run, recruiter/KB owner runs:

**Script:** `scripts/triage_needs_review.py`

**What it does:**
1. Read `needs-review.csv` (including newly queued rows from `queue_accepted_rewrite()`)
2. For each row:
   - Classify action (KEEP, EDIT, DISCARD based on rewrite_status)
   - Copy passing rows to `bullet-bank-keepers.csv`
3. These get picked up in the next run's `mine_bullet_bank()`

---

## SUMMARY: DATA FLOW

```
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Build Resume (orchestrator.py:4887-5357)            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. GeminiClient.generate() → builder (tailor_resume.md)   │
│  2. normalize_resume.normalize()                            │
│  3. validate_resume.validate() → violations list            │
│  4. repair_violations_surgically() → zero-token fixes       │
│  5. IF violations remain:                                   │
│     - Fix loop (4 attempts, hill-climb)                    │
│     - Each attempt: generate() → validate() → compare      │
│  6. Fatal violations? → FAIL & return                      │
│     Soft warnings only? → Continue with warnings           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Holistic Critique (orchestrator.py:5359-5541)      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Load 17 rubric YAML files                              │
│  2. GeminiClient.generate() → critique_resume.md           │
│     Returns: scores, recommendations, hard_failures        │
│  3. Add hard_failures to recommendations                    │
│  4. Print scores, flags, recommendations                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5.5: Apply Recommendations (orchestrator.py:5543-5758)│
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Filter questions → needs_polish list                   │
│  2. Interactive mode? → Prompt user for approval           │
│  3. For each recommendation:                               │
│     - Build contents (current resume + recommendation)     │
│     - GeminiClient.generate() → RecommendationApplySchema  │
│     - validate_resume.validate() the result                │
│     - If valid: accept, else: discard just this one        │
│  4. Update resume_data, checkpoint after each              │
│  5. Apply vocabulary substitutions (deterministic)         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 6: Save JSON (orchestrator.py:5769-5782)              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Save resume_data to output/<profile>/pdf/{stem}_Resume.json
│  (includes _critique and _recommendation_actions fields)    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 7: Render & PDF (orchestrator.py:5783-5850+)          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. render_html.py → HTML from resume_data                 │
│  2. generate-pdf.mjs (Node) → Playwright Chromium → PDF     │
│  3. Outputs: .html, .pdf, .docx                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 8: Recruiter Feedback (orchestrator.py:3626 + Step 3) │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  During audit_and_refine_bullets() (Step 3):              │
│  - When a bullet rewrite is ACCEPTED (scored better)      │
│  - bullet_feedback.queue_accepted_rewrite()               │
│    → Write to needs-review.csv if passes keeper bar       │
│                                                              │
│  Post-run:                                                  │
│  - triage_needs_review.py routes approved rows             │
│    → bullet-bank-keepers.csv                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## KEY FILES REFERENCE

| Component | File Path | Purpose |
|-----------|-----------|---------|
| Main pipeline | `scripts/orchestrator.py` | Orchestrates all 8 steps, calls validation/fix loops |
| Resume validation | `scripts/validate_resume.py` | ~10 deterministic checks, pure function |
| Cover letter validation | `scripts/validate_coverletter.py` | Similar checks for cover letter |
| PDF text validation | `scripts/validate_pdf_text.py` | Post-render PDF OCR checks |
| Surgical repairs | `scripts/orchestrator.py` (function) | Zero-token fixes for specific violations |
| Recruiter feedback | `scripts/bullet_feedback.py` | Queues accepted rewrites to needs-review.csv |
| Triage processing | `scripts/triage_needs_review.py` | Post-run: routes approved bullets to keepers |
| Builder prompt | `prompts/tailor_resume.md` | Main builder instructions & constraints |
| Critique prompt | `prompts/critique_resume.md` | Holistic critique instructions |
| Style rules | `rules/style_rules.yaml` | Forbidden phrases, bullet structure limits |
| AI risk rubric | `scoring/ai_risk.yaml` | AI-risk scoring rubric |
| Other rubrics | `scoring/*.yaml` | 15 additional scoring rubrics |
| HTML render | `scripts/render_html.py` | Template rendering from resume JSON |
| PDF generation | `scripts/generate-pdf.mjs` | Playwright/Chromium PDF render |

---

## RECRUITER FEEDBACK: THE FULL STORY

### Entry Point: Step 3 (Audit & Refine Bullets)
When a bullet is rewritten and the rewrite scores BETTER than the original:
- Accept the rewrite
- Call `bullet_feedback.queue_accepted_rewrite()`

### What Happens to Queued Bullets
1. **Queued row structure:**
   - Original bullet text (as written by generator)
   - Company & tags (source context)
   - Critique scores from the rewrite (manager_test, accuracy, believability, clarity, etc.)
   - `final_bullet` field = the rewritten text
   - `rewrite_status` = blank (needs human review)

2. **Post-Run Triage** (manual step, not automatic):
   - Run `scripts/triage_needs_review.py`
   - Reads `needs-review.csv` (includes new rows from `queue_accepted_rewrite()`)
   - User/recruiter reviews each queued rewrite
   - Sets `rewrite_status` (KEEP, EDIT, DISCARD)
   - Script copies KEEP rows to `bullet-bank-keepers.csv`

3. **Next Run:**
   - `mine_bullet_bank()` in Step 2 reads from `bullet-bank-keepers-audited.csv`
   - Approved rewrites are now available for selection on future JDs

### Key Constraint: Keeper Bar
Only rewrites that pass BOTH criteria get queued:
- `decide_action(critique) == "KEEP"` (from rewrite_bullets.py's logic)
- `critique.get("manager_test") == "PASS"`

This ensures only genuinely strong rewrites enter the review queue—not just "better than the original bad bullet."

### Is It Addressed?
**YES, in the post-run step**, but **NOT automatically**:
- Approved bullets DO feed back into the bank
- They DO get selected on future JDs
- But the triage step (routing to keepers.csv) requires manual intervention
- It's not part of the automated pipeline—it's a separate recurring task

---

## CHECKPOINTING & RESUMABILITY

All 8 steps save to `data/<profile>/checkpoints/{job_key}.json`:

- `jd_keywords` (Step 1)
- `bullet_tuples` (Step 2)
- `refined_bullets` (Step 3)
- `vocabulary_substitutions` (Step 2b, re-saved Step 4)
- `resume_data` (Step 4)
- `critique_data` (Step 5)
- `recommendation_actions` (Step 5.5)

If a run is interrupted:
- Rerun the same JD
- System resumes from the last checkpoint
- No wasted API calls on completed steps

If a run fails:
- Checkpoint stays on disk
- Rerun resumes; can fix the issue and continue
