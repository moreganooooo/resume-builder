# resume-engine/scoring/

This folder holds YAML scoring rubrics used by `orchestrator.py`'s per-bullet
audit loop and the document-level critique driven by
`resume-engine/prompts/critique_resume.md`, plus `score_keeper_gems.py`.

## Files that belong here

| File | Used by | Purpose |
|---|---|---|
| `manager_test.yaml` | `orchestrator.py`, `critique_resume.md` | Pass/fail rules the Skeptical Editor uses to judge bullets |
| `believability.yaml` | `orchestrator.py`, `score_keeper_gems.py`, `critique_resume.md` | Rubric for bullet-level believability scoring (0-100) |
| `ai_risk.yaml` | `critique_resume.md` only | Definitions of high-risk AI-sounding language patterns. Deliberately *not* loaded by `orchestrator.py` -- `CritiqueSchema` has no `ai_risk` field, so there is nowhere for a result to land (see `orchestrator.py`'s comment at the rubric-attach site). |
| `professional_identity_score.yaml` | `critique_resume.md` | Identity/archetype detection driving all downstream document-level scoring |
| `resume_cohesion_score.yaml` | `critique_resume.md` | Cross-section narrative alignment and identity consistency |
| `experience_structure_score.yaml` | `critique_resume.md` | Bullet structure, depth, and role-level formatting |
| `skills_scoring.yaml` | `critique_resume.md` | Skills grouping relevance, evidence support, archetype alignment; also the canonical skills-vocabulary bank |
| `role_dna.yaml` | `orchestrator.py` (`evaluate_fit`), `critique_resume.md` | Archetype library (evidence signals + summary framing). Referenced by `critique_resume.md`, and attached to the fit-evaluation call so the returned `archetype` comes from a controlled vocabulary. It is *not* referenced by `tailor_resume.md`, despite an earlier version of this row. |
| `ats_match.yaml` | `critique_resume.md` | ATS keyword-match weighting against the JD |
| `evidence_alignment.yaml` | `critique_resume.md` | Achievement-to-claim support -- traces every metric/tool/claim back to verified evidence |
| `summary_patterns.yaml` | `critique_resume.md` | Summary-level pattern scoring (opener style, specificity, length) |
| `summary_score.yaml` | `critique_resume.md`, actually attached to the Step 5 critique API call | Summary quality scoring by JD-relevance/specificity/alignment/credibility/readability (readability is line-count based, matching the spec's 5-line limit) |
| `certifications_score.yaml` | `critique_resume.md` | Certification relevance and canonical credential anchoring |
| `recruiter_score.yaml` | `critique_resume.md` | Recruiter first-pass scannability (distinct from `top_third_score.yaml`'s narrative-comprehension check) |
| `top_third_score.yaml` | `critique_resume.md`, actually attached to the Step 5 critique API call | Whether the top third of page one alone communicates fit within a 15-30 second first read |
| `specificity.yaml` | `critique_resume.md` | Education section specificity only (Projects criteria removed -- that section no longer exists; bullet- and summary-level specificity are covered separately by `believability.yaml` and `summary_patterns.yaml`) |

`competencies_score.yaml` and `education_score.yaml` have been retired:
Competencies no longer exists as a resume section, and Education's rules are
fully fixed content (see `docs/superpowers/specs/2026-07-01-resume-spec-enforcement-design.md`'s
Phase 3 design), leaving nothing for an LLM rubric to judge.

## Status

`critique_resume.md`'s "Load and Apply" list is the source of truth for
which files drive the document-level critique. As of this rewrite,
`summary_score.yaml` and `top_third_score.yaml` are both listed there AND
have their real YAML content attached to the Step 5 critique API call in
`orchestrator.py` (not just referenced by name) -- the remaining 14 files in
the Load and Apply list are still prose-only references the critique model
must infer compliance with; wiring their actual content into the call the
same way is future work, not required by this rewrite.

## Format reference

See any file in this folder for the convention: `version`, `max_score`,
`reject_if.score_below`, a `criteria` block with per-item `weight` +
`description` + `good`/`bad` examples, then `penalties` and `bonuses` blocks.
`resume-engine/rules/` uses a similar but not identical convention for
bullet-rewrite rules (as opposed to scoring rubrics).
