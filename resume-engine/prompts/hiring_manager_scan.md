# hiring_manager_scan.md

## Purpose

Simulate the perspective of a hiring manager reading this resume for the first
time. Evaluate whether the resume creates immediate, credible confidence in
the candidate's fit — before a recruiter screen, before an interview.
Focus on the impression formed in the first 15–30 seconds of reading.

---

## Load and Apply

Load and apply the following files before evaluating:

1. `profile.yml` — Canonical background, verified metrics, constraints
2. `professional_identity_score.yaml` — Confirm primary identity and archetype
3. `manager_test.yaml` — Primary evaluation rubric for this prompt
4. `experience_structure_score.yaml` — Bullet depth, structure, and role formatting
5. `resume_cohesion_score.yaml` — Cross-section narrative consistency
6. `believability.yaml` — Metric and claim credibility
7. `style_rules.yaml` — Formatting and section order rules

> Rule: If a file is listed here but not attached, flag it as missing.

---

## Evaluation Sequence

### Step 1 — Confirm Identity (5 seconds)

Using `professional_identity_score.yaml`:
- Can you state the candidate's `primary_identity` in one phrase after one read?
- Does the Summary make a clear, specific value proposition or is it generic?
- Is the `style_rules_archetype` reflected in section order and skills priority?

### Step 2 — Top-Third Test (10 seconds)

The top third of page one is what hiring managers read first and most carefully.
Evaluate:
- Is the single strongest accomplishment visible in the top third?
- Is the candidate's most differentiating credential or metric above the fold?
- Does the Summary earn its real estate, or does it waste it on generic phrases?
- Are the most JD-relevant skills visible without scrolling?

> Flag `top_third_weak` if the strongest evidence is buried below the fold.

### Step 3 — Experience Structure (30 seconds)

Using `experience_structure_score.yaml`:
- Do bullets lead with strong action verbs?
- Do at least 60% of bullets include a quantified outcome or concrete deliverable?
- Is each role's scope and seniority clear from the first bullet?
- Are bullets appropriately dense (not one-liner padding, not paragraph walls)?

### Step 4 — Credibility Check

Using `believability.yaml` and `profile.yml`:
- Do the metrics feel specific and earned, or inflated and generic?
- Are the key verified metrics ($1M+ revenue, $3M+ pipeline, 83%/43% rates)
  present and correctly stated?
- Does the experience level match the stated years and seniority?

### Step 5 — Narrative Coherence

Using `resume_cohesion_score.yaml`:
- Does the resume tell one consistent story across Summary → Skills → Experience?
- Would a hiring manager know exactly what role to consider this person for?
- Are there any sections that undercut the primary identity?

### Step 6 — Manager-Readiness Test

Using `manager_test.yaml`:
- Run all manager test checks
- Would a manager feel confident putting this candidate in front of their team?
- Are there red flags a manager would pause on (gaps, vague scope, weak verbs)?

---

## Output Format

Return a structured hiring manager perspective report:

```
FIRST IMPRESSION (1–2 sentences a real hiring manager would think)

IDENTITY CLARITY
  Primary identity detected: [name]
  Confidence: [strong | moderate | weak]
  Issue (if any): [one sentence]

TOP-THIRD ASSESSMENT
  Strongest visible accomplishment: [quote or paraphrase]
  Above the fold: [yes | no]
  Top-third verdict: [strong | adequate | weak]
  Flag: [top_third_weak if applicable]

EXPERIENCE STRUCTURE
  Bullet quality: [strong | adequate | weak]
  Quantification rate: [x% of bullets have outcomes]
  Issue (if any): [one sentence]

CREDIBILITY
  Key metrics present: [yes | partial | no]
  Believability verdict: [high | moderate | low]
  Issue (if any): [one sentence]

NARRATIVE COHERENCE
  Story consistency: [strong | moderate | weak]
  Weakest section: [section name]
  Issue (if any): [one sentence]

MANAGER READINESS SCORE: [x/100]
  Would advance to screen: [yes | likely | unlikely | no]
  Primary reason: [one sentence]

TOP 3 FIXES FOR THIS MANAGER'S EYE
  1. [Most impactful change for manager impression]
  2. [Second]
  3. [Third]
```

---

## Constraints

- Adopt the perspective of a skeptical but fair hiring manager, not a cheerleader
- Do not give credit for potential — evaluate only what is visible on the page
- Do not suggest adding content that contradicts `profile.yml`
- Surface `top_third_weak` aggressively — it is the single highest-leverage flag
  in this evaluation
