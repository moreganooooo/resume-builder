# Sparkle Critique Signals — Design

## Problem

An external brainstorm (`SparkleConcept.docx`) proposed a whole new "Sparkle"
subsystem for scoring resumes on warmth/memorability/distinctiveness,
separate from ATS/keyword fit. Investigation found this project already does
much of the underlying work piecemeal (`forbidden_phrases` in
`style_rules.yaml`, `hidden_gem_score`/`hidden_gem_flag` in the bullet-bank
curation scripts, mandatory first-person warmth in `WHY_TEXT`) — what's
missing is surfacing "where does this read generic, and what's already
distinctive that shouldn't be flattened" as part of the per-resume critique
that already runs on every build, and making the existing automated
recommendation-apply step protect the good parts instead of risking them.

## Goals

1. `ResumeCritiqueSchema` gains two new fields: `distinctive_moments`
   (2-3 verbatim quotes already in the resume that read as memorable) and
   `flat_sections` (section names that read generic/interchangeable).
2. `critique_resume.md` is updated to populate both, and to phrase
   voice/personality recommendations (not accuracy/keyword/ATS ones) as
   reflective questions rather than directives.
3. Step 5's console output prints both new fields alongside the existing
   scores/flags/recommendations (console only — no new log file).
4. Step 5.5's recommendation-apply loop protects `distinctive_moments`
   (instructs each per-recommendation call to preserve them verbatim unless
   that specific recommendation targets them).
5. A reflective-question recommendation is only auto-applied if the answer
   is already grounded in the provided background context (`profile.yml`,
   verified facts, bullet bank) — never fabricated. Otherwise it lands in a
   new third tracking bucket, `needs_personal_input`, and the final summary
   calls these out as good candidates for a `resume polish` session.
6. Zero new Gemini API calls — everything rides on the existing Step 5
   critique call and Step 5.5 per-recommendation calls.

## Non-Goals

- No new pipeline stage (`SparkleAnalyzer`/`SparkleEnhancer`/etc.) — this
  extends the existing critique/recommendation-apply loop only.
- No weighted composite "Sparkle score" — no `sparkleScore: 71`-style single
  number. Coarse signals (quotes + section names) only, consistent with how
  `flags`/`recommendations` already work.
- No CSV/log file aggregating this across runs (per explicit decision —
  console only, plus whatever lands in each run's saved JSON via
  `resume_data["_critique"]`, same as today).
- No protection of `distinctive_moments` in the page-fit trim loop (Step 7)
  — scoped to the recommendation-apply loop (Step 5.5) only for this first
  experiment.
- No parallel multi-prompt "optimize for curiosity/warmth/craft" + judge-model
  scheme — out of scope, real added cost for unproven benefit.
- No new UI/visualization ("Sparkle Heatmap") — this project has no web UI
  layer; console output only.

## Architecture

### 1. Schema changes (`scripts/orchestrator.py`)

```python
class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int       = Field(description="0-100: does the Summary match the JD role and tone?")
    skills_relevance_score:  int       = Field(description="0-100: are Skills JD-relevant?")
    overall_fit_score:       int       = Field(description="0-100: holistic resume-to-JD fit")
    top_third_score:         int       = Field(description="0-100: does the top third of page one alone communicate fit within a 15-30 second first read (first-impression / above-the-fold test)?")
    flags:                   List[str] = Field(description="Specific issues found")
    recommendations:         List[str] = Field(description="Actionable fixes, one per flag")
    distinctive_moments:     List[str] = Field(description=(
        "2-3 EXACT sentences or achievement bullets already present in the "
        "resume, quoted verbatim, that read as memorable and "
        "personality-forward rather than generic. Protected from later "
        "automated recommendation edits."
    ))
    flat_sections:           List[str] = Field(description=(
        "Section names (e.g. 'Professional Summary', 'VML experience') "
        "that read as competent but generic -- interchangeable with other "
        "candidates' resumes."
    ))
```

`RecommendationApplySchema` (already `TemplateSchema` + two tracking lists)
gains a third:

```python
class RecommendationApplySchema(TemplateSchema):
    applied_recommendations:  List[str] = Field(...)   # unchanged
    skipped_recommendations:  List[str] = Field(...)   # unchanged
    needs_personal_input:     List[str] = Field(description=(
        "Recommendations that ARE actionable edits to this resume's own "
        "content, phrased as a reflective question about personal "
        "motivation/meaning, but for which the provided background context "
        "does not already contain a grounded, verified answer. Left "
        "unapplied rather than inventing an answer -- exact original text "
        "here so Morgan can address it herself (e.g. via `resume polish`)."
    ))
```

### 2. Prompt changes (`resume-engine/prompts/critique_resume.md`)

New evaluation step (after Step 9, before "Output Format"):

```
### Step 9.5 — Identify Distinctive Moments and Flat Sections

- Scan the resume for 2-3 EXACT sentences or bullets (quoted verbatim) that
  already read as memorable, personality-forward, or distinctive rather
  than generic/interchangeable with other candidates' resumes. List these
  as `distinctive_moments`.
- Identify which sections (by name) read as competent but generic -- the
  kind of writing that could describe thousands of other candidates just
  as easily. List these as `flat_sections`.
- When a recommendation in TOP 3 RECOMMENDATIONS is about voice,
  personality, or distinctiveness (not accuracy, JD-keyword alignment, or
  ATS formatting), phrase it as a reflective question aimed at Morgan
  rather than a directive -- e.g. "What made this project personally
  satisfying to you?" rather than "Add more personality here."
  Recommendations about factual accuracy, keyword coverage, or formatting
  stay as direct instructions.
```

"Output Format" block gains two new sections mirroring `FLAGS`:

```
DISTINCTIVE MOMENTS (protect these)
  [List of exact quoted sentences]

FLAT SECTIONS
  [List of section names reading generic]
```

### 3. Step 5 console output (`build_tailored_resume`, around
`orchestrator.py:1943-1957`)

After the existing `flags`/`recommendations` printing, add:

```python
moments = critique_data.get("distinctive_moments", [])
if moments:
    print("  Distinctive moments (protected):")
    for m in moments:
        print(f"    - {m}")
flat = critique_data.get("flat_sections", [])
if flat:
    print("  Flat sections:")
    for f in flat:
        print(f"    - {f}")
```

### 4. Step 5.5 recommendation-apply loop (`orchestrator.py:1975-2052`)

Capture `distinctive_moments` once, alongside `recs`, before the loop starts
(same lifetime/lookup pattern `recs` already uses — `resume_data["_critique"]`
is only intact at this point, before any recommendation replaces
`resume_data`):

```python
recs = (resume_data.get("_critique") or {}).get("recommendations", [])
distinctive_moments = (resume_data.get("_critique") or {}).get("distinctive_moments", [])
```

Build a protected-moments block once, reused in every iteration's
`rec_contents`:

```python
protected_block = (
    "=== PROTECTED DISTINCTIVE MOMENTS (preserve verbatim unless THIS "
    "recommendation specifically targets them) ===\n"
    + "\n".join(f"- {m}" for m in distinctive_moments) + "\n\n"
) if distinctive_moments else ""
```

`rec_contents` becomes:

```python
rec_contents = (
    f"=== CURRENT RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
    f"{protected_block}"
    f"=== RECOMMENDATION TO CONSIDER ===\n{rec}\n\n"
    f"=== INSTRUCTIONS ===\n"
    f"Decide whether the recommendation above is a concrete, actionable edit to "
    f"THIS resume's own content (e.g. naming a specific tool, rewording a title/"
    f"summary/skills phrase to mirror the JD). If so, apply ONLY this one "
    f"recommendation and put its exact original text in applied_recommendations. "
    f"If it describes something outside the document itself -- networking, "
    f"referrals, applying elsewhere, or any action a person would take rather than "
    f"an edit to this resume's text -- change nothing and put its exact original "
    f"text in skipped_recommendations instead. If the recommendation asks you to "
    f"reveal something personal (e.g. why a project mattered, what felt "
    f"satisfying) and the provided background context does NOT already contain a "
    f"grounded, verified answer, do not invent one -- change nothing and put its "
    f"exact original text in needs_personal_input instead. Return the complete "
    f"resume JSON with every field -- change only what this one recommendation "
    f"asked for, if anything; leave everything else untouched."
)
```

Tracking through the loop (mirrors the existing `applied`/`skipped` pattern
exactly, one line added at each of the same spots):

- Initial state dict (`orchestrator.py:1977-1979`): add `"needs_polish": []`.
- Unpacking state (`orchestrator.py:1987`): add `needs_polish = state["needs_polish"]`.
- Per-iteration pop (`orchestrator.py:2021-2022`): add
  `this_needs_input = rec_result.pop("needs_personal_input", [])`, and when
  `this_needs_input` is non-empty, treat it like a skip (resume_data
  unchanged) but append to `needs_polish` instead of `skipped`.
- Checkpoint save (`orchestrator.py:2039-2041`): add `"needs_polish": needs_polish`.
- Final tracking dict (`orchestrator.py:2044`):
  `resume_data["_recommendation_actions"] = {"applied": applied, "skipped": skipped, "needs_polish": needs_polish}`.
- Final console summary: after the existing `if skipped:` block, add:
  ```python
  if needs_polish:
      print("\n  Needs your input -- good candidates for `resume polish`:")
      for n in needs_polish:
          print(f"    - {n}")
  ```

## Data Flow

```
Step 5 (critique call, response_schema=ResumeCritiqueSchema)
  -> critique_data now includes distinctive_moments, flat_sections
  -> printed to console
  -> resume_data["_critique"] = critique_data   (unchanged mechanism)

Step 5.5 (recommendation-apply loop)
  -> recs, distinctive_moments captured once from resume_data["_critique"]
  -> for each rec:
       rec_contents includes protected_block (built from distinctive_moments)
       call Gemini (response_schema=RecommendationApplySchema)
       pop applied_recommendations / skipped_recommendations / needs_personal_input
       this_applied     -> validate -> apply or discard-on-violation (unchanged)
       this_skipped     -> skipped bucket (unchanged)
       this_needs_input -> needs_polish bucket (NEW, resume_data unchanged)
  -> resume_data["_recommendation_actions"] = {applied, skipped, needs_polish}
  -> console summary mentions `resume polish` for anything in needs_polish
```

## Error Handling

- Gemini omits `distinctive_moments`/`flat_sections` from a response (should
  not happen — they're required schema fields, same as `flags`) —
  `critique_data.get(..., [])` defaults to an empty list, same defensive
  pattern already used for `flags`/`recommendations`.
- `distinctive_moments` is empty (nothing rose to that bar) —
  `protected_block` is an empty string, `rec_contents` is unchanged from
  today's behavior, no special-casing needed.
- A recommendation lands in more than one of the three buckets in a single
  response (model error) — not specially guarded against, matches today's
  existing behavior for `applied_recommendations`/`skipped_recommendations`
  (no cross-bucket validation exists there either); out of scope to add now.
- `needs_personal_input` populated but the resume is otherwise fully valid —
  no validator involvement needed (resume_data is simply left unchanged for
  that recommendation, same code path as a skip).

## Testing

Extends `tests/test_orchestrator_build_checkpoint.py`'s existing
schema-dispatched `GeminiClient.generate` mock pattern (see
`test_recommendation_pass_applies_actionable_and_skips_the_rest`):

- New test: a `RecommendationApplySchema` response with a populated
  `needs_personal_input` list results in `result["_recommendation_actions"]["needs_polish"]`
  containing that exact text, `resume_data` unchanged from before that
  recommendation, and the recommendation absent from both `applied` and
  `skipped`.
- New test: when `ResumeCritiqueSchema`'s response includes
  `distinctive_moments`, the `contents` argument passed to the
  `RecommendationApplySchema`-schema `GeminiClient.generate` call (inspected
  via the mock's `call_args`) contains the exact protected-moments text.
- New test: when `distinctive_moments` is empty, the protected-moments block
  is absent from `contents` entirely (not an empty/awkward header with no
  quotes under it).
- Existing tests
  (`test_recommendation_pass_applies_actionable_and_skips_the_rest`,
  `test_recommendation_pass_discards_result_that_introduces_a_violation`)
  continue to pass unchanged — confirms the new field is additive, not a
  breaking change to the existing applied/skipped behavior.
- Live verification: run a real `resume tailor <file>` (or `resume run`)
  against an actual pending JD, and eyeball whether `distinctive_moments`/
  `flat_sections` look like genuine signal or noise, and whether any
  `needs_polish` callouts feel like real candidates for a follow-up
  `resume polish` session.
