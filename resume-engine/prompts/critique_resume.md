# critique_resume.md

## Purpose

Run a full, structured critique of a resume against a target job description.
Evaluate every major dimension — identity, structure, skills, evidence,
cohesion, ATS fit, and recruiter/manager readiness — and return a scored,
actionable report.

---

## Load and Apply

Load and apply all of the following scoring files before evaluating:

1. `profile.yml` — Morgan's canonical background, verified metrics, and constraints
2. `style_rules.yaml` — Formatting, length, section order, and archetype-specific rules
3. `professional_identity_score.yaml` — Detect primary identity; set archetype for all downstream scoring
4. `resume_cohesion_score.yaml` — Cross-section narrative alignment and identity consistency
5. `believability.yaml` — Metric verification and claim credibility
6. `experience_structure_score.yaml` — Bullet structure, depth, and role-level formatting
7. `manager_test.yaml` — Hiring manager decision-readiness evaluation
8. `skills_scoring.yaml` — Skills grouping relevance, evidence support, and archetype alignment
9. `role_dna.yaml` — Role archetype fit and keyword alignment
10. `ats_match.yaml` — ATS keyword coverage against JD
11. `ai_risk.yaml` — AI-pattern detection and human authenticity signals
12. `evidence_alignment.yaml` — Achievement-to-claim support
13. `summary_patterns.yaml` — Summary quality, specificity, and positioning strength
14. `certifications_score.yaml` — Certification relevance and canonical credential anchoring
15. `recruiter_score.yaml` — Recruiter first-pass readability and signal clarity
16. `specificity.yaml` — Education section specificity (bullet- and
    summary-level specificity are already covered by believability.yaml and
    summary_patterns.yaml respectively)

> Rule: If a file is listed here but not attached, flag it as missing rather than
> proceeding without it. Do not substitute guesses for missing scoring criteria.

---

## Evaluation Sequence

Evaluate in this order. Each step informs the next.

### Step 1 — Detect Identity

Using `professional_identity_score.yaml`:
- Identify `primary_identity`, `secondary_identity`, and any `tertiary_identity`
- Note the `style_rules_archetype` for the primary identity — this governs
  section ordering and skills category priority for all downstream steps
- Flag any `competing_narratives` or `unsupported_positioning`

### Step 2 — Evaluate Cohesion

Using `resume_cohesion_score.yaml`:
- Run all 7 `alignment_checks` with their `pass_threshold` values
- Score each check and note any failures
- Produce `primary_identity`, `recruiter_takeaway`, `strongest_alignment`,
  `weakest_alignment`

### Step 3 — Evaluate Structure

Using `experience_structure_score.yaml` and `style_rules.yaml`:
- Check bullet format, depth, and action verb strength per role
- Verify section order matches the `style_rules_archetype` from Step 1
- Flag any formatting violations

### Step 4 — Evaluate Claims and Evidence

Using `believability.yaml`, `evidence_alignment.yaml`, and `profile.yml`:
- Verify all metrics against `profile.yml` verified metrics
- Flag any unverified, inflated, or inconsistent claims
- Assess whether accomplishments support stated skills and identity

### Step 5 — Evaluate Skills

Using `skills_scoring.yaml`:
- Score grouping logic, relevance to primary identity, and evidence support
- Flag `ungrouped_skills`, `unsupported_skills`, or `archetype_mismatch`

### Step 6 — Evaluate Role Fit

Using `role_dna.yaml`, `ats_match.yaml`, and `manager_test.yaml`:
- Score keyword coverage against JD
- Run manager-readiness checks
- Flag gaps between resume positioning and JD requirements

### Step 7 — Evaluate Supporting Sections

Using `summary_patterns.yaml`, `certifications_score.yaml`, `specificity.yaml`:
- Score summary quality and positioning clarity
- Confirm canonical certifications are present and correctly positioned
- Score Education section specificity

### Step 8 — Risk and Readability Checks

Using `ai_risk.yaml` and `recruiter_score.yaml`:
- Flag any AI-pattern risk signals
- Score recruiter first-pass readability

---

## Output Format

Return a structured report with the following sections:

```
IDENTITY DETECTED
  Primary: [name] ([style_rules_archetype]) — Confidence: [score]%
  Secondary: [name] — Confidence: [score]%
  Conflicts: [none | list]

COHESION SCORE: [x/100]
  Strongest alignment: [check name]
  Weakest alignment: [check name]
  Recruiter takeaway: [one sentence]

SECTION SCORES
  Professional Identity:    [x/100]
  Resume Cohesion:          [x/100]
  Experience Structure:     [x/100]
  Skills:                   [x/100]
  Believability:            [x/100]
  ATS Match:                [x/100]
  Manager Test:             [x/100]
  Summary:                  [x/100]
  Certifications:           [x/100]
  AI Risk:                  [x/100] (lower = better)
  Recruiter Readability:    [x/100]

OVERALL SCORE: [x/100]

FLAGS
  [List all active flags from all scoring files]

TOP 3 RECOMMENDATIONS
  1. [Most impactful fix]
  2. [Second most impactful fix]
  3. [Third most impactful fix]
```

---

## Constraints

- Do not invent metrics or accomplishments not present in the resume or `profile.yml`
- Do not suggest removing Morgan's canonical certifications
- Do not reorder skills categories away from the `style_rules_archetype` ordering
  unless flagging it as a structural issue
- Flag but do not auto-correct AI-risk patterns — surface them for review
