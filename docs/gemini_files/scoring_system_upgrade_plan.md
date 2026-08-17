# Implementation Plan: Upgrading Fit & Interview Odds Scoring (Ultra-Premium Edition)

This document outlines the final, ultra-premium technical design and implementation plan to upgrade the Fit and Interview/Hiring Odds scoring engines in the `resume-builder` repository. It integrates advanced mathematical, statistical, and conceptual mechanisms extracted from state-of-the-art talent research.

---

## 🎯 Upgrade Goals & Specifications

1.  **Eliminate Score Compression (The Split-Agent Architecture)**: Split the monolithic 18-variable evaluation into two dedicated, isolated LLM calls (`evaluate_capability.md` and `evaluate_recruiter.md`) to reduce cognitive load and prevent regression-to-the-mean.
2.  **Generic, Profile-Driven Hard-Stops & Skip Overrides**: Implement a dynamic Python-level post-processor that reads `deal_breakers` and `location.remote_required` from the user's `profile.yml`. If any deal-breaker is triggered or if a remote-only requirement is violated (i.e. `remote_quality < 5`), force the `composite_score` to `0.00` and the recommendation to `"Skip"`.
3.  **Bayesian Interview Probability Converter (The *HiringOdds* Standard)**: Automatically convert the qualitative 1-5 `interview_odds_score` into a mathematically rigorous **Absolute Interview Probability Percentage** using baseline odds and Odds Ratio ($OR$) multipliers:
    $$\text{Odds}_{\text{baseline}} = \frac{p}{1-p} \quad (\text{where } p = 0.02 \text{ baseline response rate})$$
    $$\text{Odds}_{\text{new}} = OR \times \text{Odds}_{\text{baseline}}$$
    $$P_{\text{interview}} = \frac{\text{Odds}_{\text{new}}}{1 + \text{Odds}_{\text{new}}}$$
4.  **CoBlack-Style Capability Gaps Mapping**: Require the capability agent to output an explicit, structured list of conceptual capability mismatches or narrative omissions (`capability_gaps`), giving the candidate an actionable "edit list" for their resume before applying.
5.  **Prestige-Tier Funnel Friction Calibration**: Calibrate the subjective `funnel_friction` score by instructing the LLM to classify the company into a prestige/volume tier (Tier-1: High-Volume cap, Tier-2: Mid-Market, Tier-3: Niche/Boutique) and applying mathematical caps in Python.
6.  **Heuristic Ghost Job Risk Classifier**: Deterministically compute a `ghost_job_probability` percentage in Python by evaluating a list of explicit red flags returned by the LLM (boilerplate language, posting age, evergreen wording, etc.).
7.  **Career Gap-Period Sensitivity**: Instruct the recruiter evaluation agent to adjust `recruiter_legibility` and `narrative_burden` according to the organizational profile, penalizing traditional rigid corporate structures while rewarding modern, mission-driven, or empathetic cultures.
8.  **Complete Backward Compatibility**: Recombine the outputs of the split calls into the identical dictionary format expected by all existing downstream CLI and dashboard components.

---

## 🙋 User Review Required

> [!IMPORTANT]
> **No Downstream Code Breaks**: 
> All new metrics (`estimated_interview_probability`, `capability_gaps`, `ghost_job_probability`, `prestige_tier`) will be injected as optional metadata fields into the returned evaluation dictionary. This ensures that the Terminal UI, batch evaluators, and Go-based dashboards continue to work seamlessly.

> [!WARNING]
> **Rigid Override Failure Case**: 
> If the Python override triggers a "Skip" (score `0.00`) due to a remote deal-breaker or profile hard-stop, the `estimated_interview_probability` will be forced to `0.0%` because the candidate has zero intent to apply.

---

## ⚙️ Proposed Changes

We will group our modifications logically, starting with the prompt templates, followed by the orchestrator script, and ending with test coverage.

### 1. Prompt Templates (`resume-engine/prompts/`)
We will split the existing prompt `evaluate_fit.md` into two highly focused templates.

#### [NEW] `evaluate_capability.md`
Dedicated entirely to the candidate's actual capability fit: functional alignment, role family alignment, level plausibility, and tools overlap.

```markdown
# Evaluate Job Fit: Capability & Function

## Role
You are an objective, hard-nosed technical assessor. Your only job is to evaluate if the candidate has the functional experience and skills to perform the work in the job description.

## Candidate Fact Context
- Everything you know about the candidate comes only from the `=== CANDIDATE PROFILE ===` and `=== ROLE ARCHETYPE LIBRARY ===` blocks below.
- Focus heavily on demonstrated functional experience rather than formal title alignment (that will be analyzed separately).
- Rate alignment of level (slightly overqualified is fine; major underqualification is a severe screening risk).

## Task
Read the job description and candidate profile and evaluate the following 5 Fit subscores (each 1-5):
1. **functional_alignment**: (1-5) Direct, convincing match to core demonstrated work.
2. **north_star_alignment**: (1-5) Clearly one of the target role families.
3. **level_plausibility**: (1-5) Level alignment; screens out major underqualification.
4. **work_style_sustainability**: (1-5) Day-to-day rhythm suitability.
5. **tools_process_overlap**: (1-5) Specific tools/systems named in JD (e.g., Salesforce, Outreach.io) match candidate's real experience.

Identify the single best-matching role family archetype from the `=== ROLE ARCHETYPE LIBRARY ===` keys.

Also identify any **capability_gaps** -- explicit conceptual or functional mismatches where the candidate's narrative or historical experience falls short of the JD's core operational needs. Return this as a list of strings, empty if none.
```

#### [NEW] `evaluate_recruiter.md`
Dedicated entirely to recruiter perception, corporate rigidity, and company-specific filters. It handles the Career Gap-Period screening risk evaluation and assesses practical constraints like remote viability, legitimacy, and hard blockers.

```markdown
# Evaluate Job Fit: Recruiter Perception & Practical Constraints

## Role
You are a candid, risk-aware recruiter scanner. Your job is to predict the psychological friction a standard corporate recruiter or automated filter will experience when reviewing this candidate's application.

## ⚠️ Special Assessment: Career Gap-Period Screening Risk
The candidate has a visible gap-period on their resume (2024-25) representing intentional time taken to support a loved one's health and invest in professional growth.
You must adjust `recruiter_legibility` and `narrative_burden` according to the organizational profile of the company:
- **Traditional / Rigid Corporates** (e.g., large legacy enterprises, rigid finance/defense, traditional agency settings): Treat this gap as a high screening risk. Recruiter legibility and narrative burden should be scored lower (e.g. 2 or 3) because traditional recruiters require a linear, gapless path.
- **Modern / Mission-Driven / Empathy-First** (e.g., EdTech, non-profits, mission-driven B2B SaaS, mental health/wellness): Treat this gap with empathy and standard explanation. Recruiter legibility and narrative burden should be scored higher (e.g. 4 or 5) because these cultures value diverse, non-linear life journeys.

## Company Prestige & Volume Classification
Classify the hiring company into one of the following `prestige_tier` values:
- **"Tier-1"**: High-volume/Prestige (famous tech giants, top-tier unicorns, highly visible brands). High risk of severe competition and automated auto-rejection.
- **"Tier-2"**: Mid-Market (established B2B SaaS, national agencies, mid-size EdTech). Average volume.
- **"Tier-3"**: Niche/Boutique (local nonprofits, early-stage startups, specialized boutiques). High recruiter visibility and lower competition.

## Task
Read the job description and evaluate:
1. **title_continuity**: (1-5) Does recent title lineage map cleanly onto this title?
2. **evidence_match**: (1-5) Can resume bullets prove core asks with metrics/specifics?
3. **domain_credibility**: (1-5) Does candidate's industry background feel instantly credible?
4. **recruiter_legibility**: (1-5) Can a recruiter understand the match in 6 seconds?
5. **narrative_burden**: (1-5) How little explanation is required before the match makes sense (take gap-period into account)?
6. **funnel_friction**: (1-5) Funnel risk vs. applicant volume.

Also evaluate practical constraints:
- **remote_quality**: (1-5) 5 = fully remote, 3 = hybrid, 1 = onsite-required.
- **posting_legitimacy_score**: (1-5) Is the posting active or a ghost job?
- **hard_blockers**: Extract explicit disqualifiers (e.g., "onsite required, no remote", "citizenship required", "must have Salesforce certification").

Identify any **ghost_job_red_flags** -- explicit markers of inactive, generic, or fake postings (e.g. "always looking for great talent", "establishing a talent pipeline", extremely generic description with no specific team details, generic template reposted repeatedly). Return this as a list of strings, empty if none.

Compare the JD constraints against the candidate's explicit `deal_breakers` list. If any deal-breaker is triggered, report it in `hard_blockers` using its literal text.
```

---

### 2. Core Orchestrator (`scripts/orchestrator.py`)

#### [NEW] Custom Pydantic schemas inside `scripts/orchestrator.py`
We will define isolated Pydantic schemas for the Stage 1 and Stage 2 LLM calls:

```python
class CapabilityEvaluationSchema(BaseModel):
    archetype:                  str                       = Field(description="Best-matching role archetype, or closest hybrid of two")
    fit_subscores:              FitSubscores
    capability_gaps:            List[str]                 = Field(description="Conceptual capability gaps or narrative omissions; empty if none")

class RecruiterEvaluationSchema(BaseModel):
    hard_blockers:              List[str]                 = Field(description="Explicit disqualifying constraints found; empty list if none")
    interview_odds_subscores:   InterviewOddsSubscores
    practical_pursue_subscores: PracticalPursueSubscores
    prestige_tier:              Literal["Tier-1", "Tier-2", "Tier-3"] = Field(description="Classification of the company size and volume risk")
    recommendation:             Literal["Strong pursue", "Selective pursue", "Low-priority pursue", "Skip"]
    why:                        str                       = Field(description="2-4 plain-language sentences justifying the recommendation")
    recruiter_read:             str                       = Field(description="1-2 sentences on how a recruiter is likely to read this candidate for this role at first glance")
    posting_legitimacy:         Literal["High Confidence", "Proceed with Caution", "Suspicious"] = Field(description="Does this posting look real, active, and worth pursuing?")
    posting_legitimacy_notes:   str                       = Field(description="1-2 sentences on the signals behind the posting_legitimacy assessment")
    ghost_job_red_flags:        List[str]                 = Field(description="Explicit indicators of fake, stale, or evergreen listings; empty if none")
```

#### [MODIFY] `scripts/orchestrator.py`
We will rewrite `evaluate_fit(self, jd_path: str)` to execute both calls, run the advanced mathematical converters, and apply dynamic overrides.

```python
    def evaluate_fit(self, jd_path: str) -> dict:
        """
        Ultra-Premium grounded two-stage fit evaluation check for a JD.
        Loads profile.yml dynamically to apply custom deal-breaker skips and 
        advanced Bayesian calculations in Python.
        """
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(f"  {theme.colorize_icon('error')} JD file not found: {jd_path}", soft_wrap=True)
            return {}

        # Load candidate profile configuration
        profile = self.load_yaml(self.kb_dir, "profile.yml")
        remote_required = profile.get("location", {}).get("remote_required", False)

        # 1. Prepare evaluation context
        fit_context = self.build_fit_evaluation_context(jd_text)

        # 2. Stage 1 LLM Call: Capability Fit
        capability_prompt = self.load_prompt("evaluate_capability.md")
        cap_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=capability_prompt,
            contents=fit_context,
            response_schema=CapabilityEvaluationSchema,
            temperature=0.0,
        )
        capability_data = GeminiClient.parse_json(cap_text or "") or {}

        # 3. Stage 2 LLM Call: Recruiter & Legitimacy Fit
        recruiter_prompt = self.load_prompt("evaluate_recruiter.md")
        rec_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=recruiter_prompt,
            contents=fit_context,
            response_schema=RecruiterEvaluationSchema,
            temperature=0.0,
        )
        recruiter_data = GeminiClient.parse_json(rec_text or "") or {}

        # 4. Synthesize Split Results into the unified FitEvaluationSchema format
        evaluation = {
            "archetype": capability_data.get("archetype", "Unknown"),
            "hard_blockers": recruiter_data.get("hard_blockers", []),
            "fit_subscores": capability_data.get("fit_subscores", {}),
            "interview_odds_subscores": recruiter_data.get("interview_odds_subscores", {}),
            "practical_pursue_subscores": recruiter_data.get("practical_pursue_subscores", {}),
            "recommendation": recruiter_data.get("recommendation", "Selective pursue"),
            "why": recruiter_data.get("why", ""),
            "recruiter_read": recruiter_data.get("recruiter_read", ""),
            "posting_legitimacy": recruiter_data.get("posting_legitimacy", "Proceed with Caution"),
            "posting_legitimacy_notes": recruiter_data.get("posting_legitimacy_notes", ""),
            # Advanced Metadata injection
            "capability_gaps": capability_data.get("capability_gaps", []),
            "ghost_job_red_flags": recruiter_data.get("ghost_job_red_flags", []),
            "prestige_tier": recruiter_data.get("prestige_tier", "Tier-2"),
        }

        # 5. Prestige-Tier Funnel Friction Calibration
        # Apply strict caps to funnel friction score in Python based on prestige tier
        prestige_tier = evaluation["prestige_tier"]
        funnel_friction_score = evaluation["interview_odds_subscores"].get("funnel_friction", 3)
        if prestige_tier == "Tier-1":
            # Tier 1 has extreme competition, capping friction score at 2 out of 5
            evaluation["interview_odds_subscores"]["funnel_friction"] = min(funnel_friction_score, 2)
        elif prestige_tier == "Tier-3":
            # Tier 3 has low competition, boosting friction score by +1 (capped at 5)
            evaluation["interview_odds_subscores"]["funnel_friction"] = min(funnel_friction_score + 1, 5)

        # 6. Compute base weighted subscores
        fit_score = compute_fit_score(evaluation["fit_subscores"])
        interview_odds_score = compute_interview_odds_score(evaluation["interview_odds_subscores"])
        practical_pursue_score = compute_practical_pursue_score(evaluation["practical_pursue_subscores"])
        posting_age_days = jd_manager.compute_posting_age_days(jd_path)

        # 7. Apply Generic, Profile-Driven Hard-Stops & Skip Overrides in Python
        triggered_by_profile_filters = False
        blockers_triggered = list(evaluation["hard_blockers"])

        # A. Remote required verification
        remote_val = evaluation["practical_pursue_subscores"].get("remote_quality", 5)
        if remote_required and remote_val < 5:
            triggered_by_profile_filters = True
            msg = f"Onsite/hybrid signal detected (Remote Quality scored {remote_val}/5)"
            if msg not in blockers_triggered:
                blockers_triggered.append(msg)

        # B. Profile-level deal-breaker validation (checking hard_blockers strings)
        if blockers_triggered:
            triggered_by_profile_filters = True
            evaluation["hard_blockers"] = blockers_triggered

        # C. Apply Overrides
        if triggered_by_profile_filters:
            evaluation["recommendation"] = "Skip"
            evaluation["why"] = f"Application skipped due to triggered deal-breakers: {', '.join(blockers_triggered)}"
            composite = 0.00
            estimated_prob = 0.0
        else:
            composite = fit_composite_score(
                fit_score, interview_odds_score, practical_pursue_score, posting_age_days,
            )
            # D. Advanced Bayesian Probability Converter
            # We map 1-5 interview_odds_score to Odds Ratio (OR) multipliers
            # x is on a 1-5 scale
            x = interview_odds_score
            if x >= 4.5:
                or_multiplier = 20.0  # Elite match (20x improvement)
            elif x >= 4.0:
                or_multiplier = 8.0   # Strong match (8x improvement)
            elif x >= 3.0:
                or_multiplier = 2.5   # Average match (2.5x improvement)
            elif x >= 2.0:
                or_multiplier = 1.0   # Baseline match (1x)
            else:
                or_multiplier = 0.1   # Extreme screen-out risk (10x worse)

            p_baseline = 0.02  # 2% baseline response rate
            odds_baseline = p_baseline / (1.0 - p_baseline)
            odds_new = or_multiplier * odds_baseline
            estimated_prob = round((odds_new / (1.0 + odds_new)) * 100.0, 1)

        # E. Heuristic Ghost Job Probability Calculator
        # Compute ghost job probability based on red flags and posting age
        red_flags_count = len(evaluation["ghost_job_red_flags"])
        ghost_score = 0.0
        if posting_age_days is not None:
            if posting_age_days > 30:
                ghost_score += 0.40
            elif posting_age_days > 14:
                ghost_score += 0.20
        ghost_score += min(red_flags_count * 0.20, 0.50)
        evaluation["ghost_job_probability"] = round(min(ghost_score * 100.0, 95.0), 1)

        evaluation["posting_age_days"] = posting_age_days
        evaluation["fit_score"] = fit_score
        evaluation["interview_odds_score"] = interview_odds_score
        evaluation["practical_pursue_score"] = practical_pursue_score
        evaluation["composite_score"] = composite
        evaluation["estimated_interview_probability"] = estimated_prob

        return evaluation
```

---

### 3. Tests (`tests/`)

#### [NEW] `tests/test_deal_breaker_overrides.py`
We will write a comprehensive unit test suite to verify that:
*   Remote requirements dynamically trigger a `0.00` score and `"Skip"` recommendation if `remote_quality < 5`.
*   Triggered hard blockers force a composite score of `0.00` and `"Skip"` recommendation.
*   The Bayesian probability calculations execute correctly and match expected thresholds.
*   The scoring engine remains backward compatible and returns all the expected keys of `FitEvaluationSchema`.

---

## 🧪 Verification Plan

### Automated Tests
We will execute our new and existing unit tests to verify mathematical correctness and logic flow:

```bash
# Run existing orchestrator tests
python -m unittest tests/test_orchestrator_fit_composite_score.py

# Run our newly created deal-breaker override tests
python -m unittest tests/test_deal_breaker_overrides.py
```

### Manual Verification
1.  **Test Remote Skip**: Run `scripts/cli.py evaluate` (or use the interactive TUI menu) on an on-site or hybrid job description file.
    *   *Verify*: The terminal output shows a final composite score of `0.00` and recommendation `Skip`.
2.  **Test Clean Fully Remote Fit**: Run the evaluation on a high-confidence, fully remote JD.
    *   *Verify*: The system calculates normal scores (e.g. `4.25`), provides a clean absolute percentage like `14.0%` or `29.0%` for interview probability, and outputs a non-empty list of capability gaps (if any).
