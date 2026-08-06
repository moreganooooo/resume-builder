# Phase 10 — Scoring rubrics & rule files

Run 2026-08-05, Opus 5. Owns all of `resume-engine/rules/` (6 files) and all of
`resume-engine/scoring/` (16 YAML + `README.md`).

**Ownership correction:** `PLAN.md` says "18 YAML files plus its `README.md`" in
`scoring/`. There are **16**. `competencies_score.yaml` and
`education_score.yaml` were retired (`scoring/README.md:28-31`); the count in
`PLAN.md` predates that. No file went unowned — the number is just wrong.

**No files claimed from other phases.** One deliberate read outside the
ownership boundary: `critique_resume.md` and `evaluate_fit.md` were read to
answer the reachability question ("what loads this rubric, into which prompt"),
which cannot be answered from inside `scoring/`. No findings are filed against
prompt *content* — that is Phase 3's.

---

## Answer to the phase question

> Are these rubrics sound, current, and actually enforced — or are they a
> well-formed vocabulary nothing reads?

**Split verdict, cleanly along the two directories.**

`rules/` — **all 6 files are live and correctly wired.** `hard_failures.yaml`,
`truthfulness_rules.yaml`, `style_rules.yaml`, `language_quality.yaml`,
`verb_taxonomy.yaml` and `verb_intent_mapping.yaml` are each loaded by
`orchestrator.py` (bullet-critique system at `:1383-1390`, rewrite loop at
`:1678-1683`) *and* independently by `rewrite_bullets.py:269-274`, with
`polish.py:150` and `audit_bullet_bank.py:29` pulling `style_rules.yaml` on
their own paths. Content reaches the model, not just filenames. No finding.

`scoring/` — **12 of 16 files are read by no code in this repo.** They are
named in `critique_resume.md`'s "Load and Apply" list and nowhere else. Only
`manager_test.yaml` and `believability.yaml` (bullet loop, `:1383-1384`) and
`summary_score.yaml` and `top_third_score.yaml` (holistic critique,
`:2696-2697`) ever have their contents put in front of a model. The other
twelve are a well-formed vocabulary nothing reads.

This is **partly known**: `scoring/README.md:33-42` documents it accurately and
calls wiring the rest "future work". What the README does not say is that the
prompt's own safety rule makes the gap unsafe rather than merely incomplete
(Finding 2), that the receiving schema could not hold the results even if they
were wired (Finding 4), and that no threshold in any rubric is implemented
anywhere (Finding 5).

---

## Reachability map (evidence for everything below)

| File | Loaded by Python? | Where |
|---|---|---|
| `rules/hard_failures.yaml` | **yes** | `orchestrator.py:1389,1681`; `rewrite_bullets.py:272` |
| `rules/truthfulness_rules.yaml` | **yes** | `orchestrator.py:1390,1682`; `rewrite_bullets.py:273` |
| `rules/style_rules.yaml` | **yes** | `orchestrator.py:1385,1683,2335,2527`; `polish.py:150`; `audit_bullet_bank.py:29` |
| `rules/language_quality.yaml` | **yes** | `orchestrator.py:1386,1680`; `rewrite_bullets.py:269` |
| `rules/verb_taxonomy.yaml` | **yes** | `orchestrator.py:1387,1679`; `rewrite_bullets.py:270` |
| `rules/verb_intent_mapping.yaml` | **yes** | `orchestrator.py:1388,1678`; `rewrite_bullets.py:271` |
| `scoring/manager_test.yaml` | **yes** | `orchestrator.py:1383`; `rewrite_bullets.py:282`; `audit_bullet_bank.py:22` |
| `scoring/believability.yaml` | **yes** | `orchestrator.py:1384`; `rewrite_bullets.py:283`; `score_keeper_gems.py:91` |
| `scoring/summary_score.yaml` | **yes** | `orchestrator.py:2696` |
| `scoring/top_third_score.yaml` | **yes** | `orchestrator.py:2697` |
| `scoring/ai_risk.yaml` | **no** | prompt name only |
| `scoring/ats_match.yaml` | **no** | prompt name only |
| `scoring/certifications_score.yaml` | **no** | prompt name only |
| `scoring/evidence_alignment.yaml` | **no** | prompt name only |
| `scoring/experience_structure_score.yaml` | **no** | prompt name only |
| `scoring/professional_identity_score.yaml` | **no** | prompt name only |
| `scoring/recruiter_score.yaml` | **no** | prompt name only |
| `scoring/resume_cohesion_score.yaml` | **no** | prompt name only |
| `scoring/role_dna.yaml` | **no** | prompt name only |
| `scoring/skills_scoring.yaml` | **no** | prompt name only |
| `scoring/specificity.yaml` | **no** | prompt name only |
| `scoring/summary_patterns.yaml` | **no** | prompt name only |

Method: `grep` for each filename across `scripts/`, `resume-engine/`, `tests/`
excluding `scripts/archive/`. "Prompt name only" means the sole live reference
is the literal string in `critique_resume.md` — the model is told a file exists
and never given it.

---

## Findings

### F1 — 14 of the 18 rubrics `critique_resume.md` requires are never attached. BLOCKER · goals 1, 2

`resume-engine/prompts/critique_resume.md:14-37` lists 18 files to "load and
apply". `orchestrator.py:2698-2702` builds the critique system instruction from
the prompt plus exactly two of them:

```python
critique_system = (
    f"{critique_prompt}"
    f"\n\nSUMMARY SCORING RUBRIC:\n{summary_score_rules}"
    f"\n\nTOP-THIRD-OF-PAGE-ONE SCORING RUBRIC:\n{top_third_score_rules}"
)
```

Not attached: `profile.yml`, `style_rules.yaml`, `professional_identity_score`,
`resume_cohesion_score`, `believability`, `experience_structure_score`,
`manager_test`, `skills_scoring`, `role_dna`, `ats_match`, `ai_risk`,
`evidence_alignment`, `summary_patterns`, `certifications_score`,
`recruiter_score`, `specificity`.

The prompt's 9-step evaluation sequence then instructs the model to run steps
that are impossible: Step 1 "Using `professional_identity_score.yaml`", Step 2
"Run all 7 `alignment_checks` with their `pass_threshold` values", Step 6 "If
`ats_match.yaml`'s `archetype_overrides` has an entry matching…, use those
weights". None of those artifacts exist in the model's context. What the model
returns for steps 1–6 is invention conditioned on a filename.

Not a style nit: every `_critique` score that has ever driven a
recommendation-rewrite pass (`orchestrator.py:2763`) was produced this way.

### F2 — the prompt's own guard against exactly this cannot fire. BLOCKER · goals 1, 2

`critique_resume.md:39-40`:

> Rule: If a file is listed here but not attached, flag it as missing rather
> than proceeding without it. Do not substitute guesses for missing scoring
> criteria.

This is the correct instinct and it is inert twice over. First, `flags` in
`ResumeCritiqueSchema` (`orchestrator.py:906`) is described as "Specific issues
found" — a resume-issue channel, not a plumbing-error channel, so a compliant
model reporting 16 missing rubrics contaminates the same list the
recommendation loop consumes. Second, nothing on the Python side inspects
`flags` for a missing-file signal; `:2722-2727` prints them and moves on.

The result is worse than having no guard: the file reads as if the failure mode
is handled. F1 has been shipping for the life of this prompt and the guard that
was written to catch it never produced a single observable signal.

### F3 — five rubrics have a malformed `flags:` block that parses as one string. MAJOR · goal 2

`flags:` is written as a bare indented block with no `- ` item markers, so
`yaml.safe_load` returns a single space-joined scalar instead of a list:

| File | `type(flags)` after parse |
|---|---|
| `scoring/summary_score.yaml:98-105` | `str` — `'generic_summary buzzword_heavy unsupported_claim role_mismatch too_long low_specificity'` |
| `scoring/top_third_score.yaml` | `str` — `'unclear_identity buried_accomplishments weak_top_section slow_recruiter_comprehension generic_positioning'` |
| `scoring/experience_structure_score.yaml` | `str` |
| `scoring/professional_identity_score.yaml` | `str` |
| `scoring/skills_scoring.yaml` | `str` |

Reproduce:

```
python3 -c "import yaml; d=yaml.safe_load(open('resume-engine/scoring/summary_score.yaml')); print(type(d['flags']), repr(d['flags']))"
```

`summary_score.yaml` and `top_third_score.yaml` are **the only two scoring
files actually attached to a live API call** — so this is the one rubric defect
in this phase that is provably reaching the model today. `json.dumps()` at
`:2696-2697` serialises the mangled scalar verbatim, and the model is shown a
run-on token string where a controlled flag vocabulary was intended. The other
three are latent, and will land the moment F1 is fixed.

*Fix:* add `- ` to each item in all five files. Two lines of intent, ~27 lines
touched, no code change.

### F4 — `ResumeCritiqueSchema` cannot hold what the prompt computes. MAJOR · goal 2

`ResumeCritiqueSchema` (`orchestrator.py:901-918`) has 4 integers and 4 string
lists. The prompt's evaluation sequence names these outputs with no field to
return them in: `primary_identity`, `secondary_identity`, `tertiary_identity`,
`competing_narratives`, `unsupported_positioning` (Step 1);
`recruiter_takeaway`, `strongest_alignment`, `weakest_alignment` (Step 2);
`ungrouped_skills`, `unsupported_skills`, `archetype_mismatch` (Step 5).

Because it is a structured-output call, the surplus is not truncated with a
warning — it is never generated. Fixing F1 without fixing this buys nothing:
the rubrics would be attached, evaluated, and then discarded at the schema
boundary. **F4 must ship with F1 or F1 is wasted.**

### F5 — no threshold in any rubric is implemented. MAJOR · goals 1, 2

`reject_if.score_below` appears in 5 `scoring/` files. `pass_threshold` appears
in `resume_cohesion_score.yaml` and `professional_identity_score.yaml`.
`ats_match.yaml:15-18` defines `excellent_match: 85 / good_match: 70 /
weak_match: 50`. `summary_score.yaml:15-21` defines 5 `hard_failures`.

`grep -rn "reject_if\|score_below" scripts/` returns **nothing** outside
`scripts/archive/`. No Python code reads a threshold from any rubric, and
`ResumeCritiqueSchema` has no boolean/hard-failure field for a model to report
one through. The critique's four scores are printed (`:2716-2720`) and stored;
only `recommendations` and `distinctive_moments` re-enter the pipeline
(`:2763-2764`). A resume can score 10/100 on every dimension and ship.

The rubrics express a rejection contract the pipeline has no mechanism to
honour. Either wire a gate or delete the `reject_if` blocks — leaving them is
how a future reader concludes the scores mean something.

### F6 — B18 answered: `ats_match.yaml` **is** the intended JD-keyword check, and it is wired to nothing. MAJOR · goals 1, 2

Backlog **B18** asks whether `ats_match.yaml` is supposed to be the missing
verification of JD-keyword coverage. It is — `critique_resume.md:25` ("ATS
keyword coverage against JD") and `:86-91` ("Score keyword coverage against
JD") place it in exactly that role. It is loaded by no code.

Even if attached, it is only half a check: the file is pure weighting
(`exact_match: 1.0 / semantic_match: 0.7 / partial_match: 0.4`, section
multipliers, a `-25` hard-requirement penalty) with no keyword-extraction step
and nothing to extract from. `extract_keywords.md` exists as a prompt and its
output is not routed here.

The calibration question the plan asked, answered from the file's own comment
(`ats_match.yaml:23-27`):

> Not derived from data -- a first-pass guess at which match type should carry
> more weight for each archetype's kind of work. Tune these based on what
> critique_resume.md actually flags over time.

Honest, and describes a feedback loop that cannot close: `critique_resume.md`
never receives this file, so it can never flag anything attributable to these
weights, so the tuning signal does not exist. The weights are arbitrary and
structurally unable to stop being arbitrary. Same shape holds for `ai_risk`,
`believability`, `specificity`, `role_dna`, `recruiter_score` — except
`believability`, which is genuinely calibrated in the sense that it is attached
to a live per-bullet call and its output field exists in `CritiqueSchema`.

### F7 — B3 answered: the rubrics assume a knowledge-base context `evaluate_fit()` never sends. BLOCKER · goals 1, 2

Backlog **B3** established that `evaluate_fit()` sends no candidate context.
The rubric-side answer to "do these rubrics assume a context that was never
supplied": **yes, explicitly, in writing.**

`resume-engine/prompts/evaluate_fit.md:10`:

> Target role families ("North Star"): see the `target_roles` and `archetypes`
> sections in this candidate's profile.yml (**in your knowledge base context**)
> for their real primary/secondary target roles — score alignment against
> those, not any example list.

`orchestrator.py:2143-2150` sends `system_instruction=eval_prompt` and
`contents=f"=== JOB DESCRIPTION ===\n{jd_text}"`. There is no knowledge-base
context. The prompt does not merely omit the profile — it directs the model to
a context block that the call site has never constructed, and then forbids the
fallback ("not any example list") that would at least be predictable.

Compounding it: **no `scoring/` rubric is attached to `evaluate_fit` either**,
and `role_dna.yaml` — the archetype library, the one file that could supply
"archetypes" independently of `profile.yml` — is loaded by nothing (F1). Every
`archetype` value ever written into a JD's `_evaluation` block was picked by a
model that had seen neither the candidate's archetype list nor the archetype
library.

*Fix note for B3:* attaching `profile.yml`'s `target_roles`/`archetypes` is the
minimum. Attaching `role_dna.yaml` alongside it is what makes the returned
`archetype` string belong to a controlled vocabulary instead of being freeform.

### F8 — four incompatible archetype vocabularies, one of them pointing at a key that does not exist. MAJOR · goal 2

| Source | Vocabulary |
|---|---|
| `profiles/morgan/knowledge_base/profile.yml` `archetypes[].name` | `Customer Marketing Manager`, `Lifecycle Marketing Specialist`, `Sales Enablement Specialist`, … |
| `scoring/ats_match.yaml:28-56` `archetype_overrides` | `Lifecycle Marketing Specialist`, `Customer Onboarding & Implementation Specialist`, `Sales Enablement Specialist`, `B2B Content Strategist`, `Customer Marketing Manager` |
| `scoring/role_dna.yaml` `archetypes` | `email_lifecycle`, `sales_enablement`, `b2b_content_copywriter`, `marketing_ops_crm`, `generalist_coordinator` |
| `scoring/professional_identity_score.yaml` `style_rules_archetype` | `marketing_ops`, `enablement`, `lifecycle`, `copywriter` |

Four naming schemes for one concept, and no mapping table between any pair.
`ats_match.yaml`'s own comment claims its keys are "keyed to the archetype
names in profile.yml's archetypes list" — true for 4 of 5; `Customer Onboarding
& Implementation Specialist` is not a `profile.yml` archetype name, so that
override can never match.

Worse, the chain terminates in a dangling reference.
`professional_identity_score.yaml:386`:

```
style_rules_archetype: string   # maps to style_rules.yaml archetype_ordering key
```

`style_rules.yaml` has no `archetype_ordering` key. Its top-level keys are
`version, philosophy, writing_style, bullet_structure, verb_rules, vague_verbs,
verb_upgrades, forbidden_openers, forbidden_phrases, punctuation_rules,
metrics_rules, pronoun_rules, tool_mention_rules, redundancy_rules, tagline,
skills_section, ats_rules, layout_rules, typography` — none archetype-keyed.

So `critique_resume.md:52-53` ("Note the `style_rules_archetype` for the primary
identity — this governs section ordering and skills category priority for all
downstream steps") instructs the model to resolve a value through a lookup table
that was never written. Step 1 is the step every later step is declared to
depend on.

### F9 — hand-trace: `summary_score.yaml` would have caught the generic Summary. It is attached. Nothing acts on the result. MAJOR · goal 2

Backlog **B29** asks whether `summary_score.yaml` / `summary_patterns.yaml`
already encode the rule that would have caught the generic Summary. Traced by
hand against the shipped artifact
(`output/morgan/json/MorganEscott_ContentStrategist_AbnormalAI_Resume.json`,
`SUMMARY_TEXT`) — a Content Strategist JD:

> **Campaign & CRM Strategist with 10+ years of experience transforming complex
> technical inputs into high-performing campaign assets and activation-ready
> narratives.** Specializes in using AI-assisted workflows to accelerate content
> transformation, repurposing, and distribution across B2B SaaS and cybersecurity
> environments. Leverages a revenue-first perspective … Maintains brand alignment
> at scale while driving engagement through data-informed storytelling. Translates
> research, threat reports, and customer stories into cohesive, multi-channel
> content …

| Criterion (weight) | Rubric signal | Score |
|---|---|---|
| `relevance_to_jd` (30) | `excellent` requires `target_role_explicitly_identified`. Opener names "Campaign & CRM Strategist" against a Content Strategist JD → `no_target_role_signal`. | ~15 |
| `specificity_and_evidence` (25) | `excellent` requires `named_platforms`, `measurable_scope`, `unique_differentiators`. **Zero platforms named** — no Outreach.io, no HubSpot, despite both being verified profile tools. Only scope figure is "10+ years". | ~8 |
| `role_alignment` (20) | `summary_matches_target_role` fails on the same title mismatch. | ~10 |
| `credibility` (15) | Believable, no inflated seniority, no consultant-speak. | ~13 |
| `readability` (10) | Within the 5-line limit; sentences 3–4 are dense and adjective-led. | ~7 |
| **Total** | | **≈53/100** |

`hard_failures` check: `first_person_pronouns` clean, `buzzword_opener` clean,
`generic_professional_summary` **arguably tripped** by "Leverages a revenue-first
perspective" and "driving engagement through data-informed storytelling".

So the rubric is sound — it independently reproduces Phase 3's finding, and it
is one of only two rubrics actually in the model's context. The failure is
downstream: `summary_score.yaml` declares 5 `hard_failures` and
`ResumeCritiqueSchema` exposes `summary_alignment_score: int` and nothing else,
so a hard failure and a 53/100 and an 85/100 are the same object to the
pipeline (F5). The rubric answered correctly and the plumbing threw the answer
away.

Secondary defect surfaced by the trace: the banned-opener lists diverge.
`tailor_resume.md:70` bans `passionate, driven, results-oriented, dynamic,
synergy, best-in-class, seeking opportunities, visionary`.
`summary_score.yaml:23-33` bans `results-driven, dynamic professional,
accomplished professional, highly motivated, dedicated professional, seasoned
professional, proven track record, strategic thinker, visionary leader`. The
builder is permitted to write five phrases the scorer treats as a hard failure
(`proven track record`, `strategic thinker`, `seasoned professional`,
`accomplished professional`, `highly motivated`), and the scorer permits three
the builder bans (`passionate`, `synergy`, `best-in-class`). Neither list is a
superset. This one is live today.

### F10 — `scoring/README.md` has two false "Used by" rows. MINOR · goal 5

`README.md:13` claims `ai_risk.yaml` is used by `orchestrator.py`. It appears in
no Python file in the repo. `README.md:18` claims `role_dna.yaml` is used by
`tailor_resume.md`; `grep role_dna resume-engine/prompts/` returns only
`critique_resume.md:24,86`.

Every other row is accurate, and `README.md:33-42` is a genuinely honest status
section — which is what makes the two wrong rows worth fixing rather than
ignoring. A reader auditing reachability from this table would clear both files
and miss F1 for two of the twelve.

---

## Staleness check

Asked by the plan: is any rubric stale relative to what the pipeline now
produces? Three checks, all **clean** — recording them so they are not re-run:

- **`recruiter_score.yaml`'s date format.** The Phase-3 validation-layer plan
  flagged `recruiter_score.yaml:24` citing "MMM YYYY per formatting_rules.yaml"
  after `formatting_rules.yaml` was deleted. Already fixed — `:23,27` now say
  `MM/YYYY with en-dash`, matching `style_rules.yaml`. No live reference to
  `formatting_rules.yaml` or `ats_rules.yaml` remains in either directory.
- **`specificity.yaml` v3.0.** Correctly narrowed to Education-only after the
  Projects section was removed, with the reasoning recorded in-file. Sound.
- **Retired files.** `competencies_score.yaml` and `education_score.yaml` are
  gone from disk and from `critique_resume.md`'s list. Clean retirement.

**The one real staleness gap: the cover-letter path has no rubric at all.**
`scoring/` predates it and nothing was added. `tailor_coverletter.md` and
`polish_coverletter.md` run with `style_rules.yaml` only — no believability, no
AI-risk, no specificity check on a document that is *more* prone to generic
AI-voice than the resume is. Filed as **B52**.

---

## What is working — do not "fix" these

- **All 6 `rules/` files.** Live, double-wired, and reaching the model with real
  content. `hard_failures.yaml`'s 7 conditions and `truthfulness_rules.yaml`'s
  4 tests are terse and well-formed; terseness is correct for something
  concatenated into every per-bullet call.
- **`orchestrator.py:1686-1720`'s curated injection.** `verb_taxonomy` is
  trimmed to `priority_tiers` + `avoid` before injection rather than dumped
  whole, with the reasoning (Gemma's 16k TPM cap) recorded in-comment. This is
  the right pattern and F1's eventual fix should follow it — attaching all 14
  files raw would add roughly 80KB to every critique call.
- **`believability.yaml` + `manager_test.yaml`.** The only two `scoring/` files
  with a complete loop: attached to a live call, and with matching output
  fields on `CritiqueSchema`. They are the template for what F1+F4 should make
  the other twelve look like.
- **`scoring/README.md:33-42`.** Do not delete the status section when fixing
  F10 — it is the only place the wiring gap was written down.

---

## Handoffs

None. Phases 11 and 12 are the only phases that have not run, and nothing found
here falls in their traces.

---

## Backlog items added

**B47–B54** appended to `phase-9-backlog.md`, sorted into the existing tiers:

| B | Tier | Finding |
|---|---|---|
| B47 | 0 | Malformed `flags:` in 5 rubrics; 2 are live (F3) |
| B48 | 0 | Two false "Used by" rows in `scoring/README.md` (F10) |
| B49 | 1 | 14 of 18 rubrics never attached; the guard can't fire (F1, F2) |
| B50 | 1 | `ResumeCritiqueSchema` can't hold the prompt's outputs (F4) |
| B51 | 1 | No rubric threshold is implemented anywhere (F5) |
| B52 | 2 | Four archetype vocabularies; `archetype_ordering` doesn't exist (F8) |
| B53 | 2 | Builder and scorer ban different words (F9) |
| B54 | 2 | No rubric covers the cover-letter path (staleness check) |

**B49 → B50 → B51 is one ordered chain** — B49 without B50 attaches rubrics
whose results the schema discards; B50 without B51 returns scores nothing acts
on. B47 should land before B49 so the three latent malformed files are fixed
before the rewiring makes them live.

**B3, B18 and B29** were annotated in place with this phase's answers rather
than duplicated — B18 and B29 stay open as written; B3's fix scope widened to
include `role_dna.yaml`.
