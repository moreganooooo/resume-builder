# Cover Letter Blueprint Roadmap

> **Source**: `docs/cover_letter_research_master_blueprint.md` (Gemini-authored, 23-feature roadmap)
> **Status as of 2026-08-17**: Groups A-B complete. Groups C-E not started.
> **Purpose**: Tracks the decomposed, verified subset of the blueprint actually worth building, so this work can resume in a fresh session without re-deriving context.

## Why this doc exists

The blueprint proposes 23 features across 7 pillars. It was verified against the actual codebase (not trusted at face value — see Verification Findings below) before any work started. Several of its claims turned out to be wrong: some "missing" features already exist, and some existing files it references do something different from what it describes. Only the genuinely-missing, highest-value items were selected for implementation, then decomposed into 5 build-order groups (A-E) per the brainstorming skill's "too large for one spec, decompose into sub-projects" guidance.

## Verification findings (already fully done — do not re-verify)

**Already fully shipped** (blueprint over-claims these as missing/new): #10 KB metric traceability (`_check_kb_traceability`, B14), #15 single-column safeguard (`style_rules.yaml`'s `ats_rules`), #16 PDF ligature verification (wired into `orchestrator.py` build pipeline), #20 Syncthing mobile sync (CLAUDE.md documents it fully), #21 liveness re-sweeper/archiver (`liveness.py` + `stale_sweep.py`), #23 `resume doctor` (already 17 checks deep), #11 JD keyword extraction (exists in `orchestrator.py`'s `JDKeywordSchema`, not `jd_manager.py` as the blueprint claims).

**Misdescribed, not missing:**
- **#1 ATS URL classification** — `scan_ats.py` is a job-board *fetcher* (finds postings across ~400 companies via 7 ATS providers), not a per-JD classifier. Its `_ATS_HOST_PATTERNS` dict is a reusable primitive for the real feature, which doesn't exist yet.
- **#9 Voice anchor matcher** — `build_voice_anchors.py` only compiles quote artifacts into a KB file; there's no sentence-variance/vocabulary-distribution analysis.

**Doc self-contradiction worth knowing:** the blueprint's own Feature #8 lists "Spearheaded" as an AI-cliché to ban, but `style_rules.yaml` has it in the *recommended verbs* list. Deliberately NOT added to the forbidden list (see Group A below) — it's a real, specific verb in this codebase's style guide, not filler.

**Partial (real work, smaller than the doc implies):** #6 career-break framing (exists resume-side in `normalize_resume.py`/`validate_resume.py`, not cover-letter-side), #14 matched design system (both renderers already share `theme.py`/`profile_paths` contact data), #22 follow-up generator (`followup.py` has cadence/urgency date-math already; only the LLM drafting call is net-new), #19 one-command pipeline (every sub-step already exists individually, just no chaining command).

## Build-order groups

Selected 8 features (of the 23), grouped by dependency and bounded/architectural scope, in build order:

### Group A — Cover-letter quality quick wins ✅ COMPLETE
Features #4, #5, #8. Bounded scope (additive changes to existing validators/config, no new subsystems).

- **#4 word count validator**: `resume-engine/prompts/tailor_coverletter.md` prompt target changed from 400-450 → **300-450 words** (user's explicit "split the difference" call between the prompt's original tuning and the blueprint's 250-350 research benchmark). `scripts/validate_coverletter.py` got `_check_word_count()`, wired into `validate()`. Tests extended in `tests/test_validate_coverletter.py`.
- **#5 referral hook injector**: New `jd_manager.save_referral()`/`read_referral()` pair, following the existing `_evaluation`/`_liveness`/`_application` underscore-metadata convention (per-JD, not profile-wide — user's call). `--referral` CLI flag on the `coverletter` command (rejected when combined with `--pick` — one referral can't apply to multiple JDs). Interactive menu prompts once per JD (skipped if already saved) via a new `_prompt_for_referral_if_unset()` in `menu.py`. `orchestrator.py`'s `build_tailored_coverletter()` reads it and folds a `=== REFERRAL ===` block into `system_instruction`; `tailor_coverletter.md` instructs the model to name the referral in the opening 1-2 sentences when the block is present. Tests added to `tests/test_jd_manager.py`, `tests/test_orchestrator_coverletter_enrichment.py`, `tests/test_cli_coverletter_pick.py`, `tests/test_menu.py`.
- **#8 cliché phrase extension**: 9 phrases appended to `style_rules.yaml`'s `forbidden_phrases` (furthermore, testament to, delve, delve into, in conclusion, seamlessly, seamless integration, it is important to note, plays a pivotal role). Single-file change — `forbidden_phrases` is the canonical master list; other files' subsets are tested by `test_banned_phrase_consistency.py` and only fail if something is banned elsewhere but missing from the master.

**Gotcha hit during implementation**: a shared test fixture in `tests/test_orchestrator_coverletter_injection.py` (`_clean_letter_json()`, ~53 words) started failing the new word-count check even though it wasn't part of Group A's scope — had to expand it in place. If future groups touch cover-letter fixtures, check word count first.

Full suite: 1585 tests passing after Group A.

### Group B — ATS-aware keyword strategy ✅ COMPLETE
Features #1 (ATS classification) + #12 (first-100-words keyword front-loading), paired deliberately: **classification alone has no value** — it's just metadata unless something downstream consumes it (established via explicit discussion with the user before scoping). #12 gives it a consumer.

- **#1 ATS classification**: `scan_ats.py`'s `_ATS_HOST_PATTERNS` extended with `taleo.net` and `ats.rippling.com` (was 7 providers, now 9). New `_ATS_WEIGHT_TIERS` dict + `classify_ats(source_url)` function map provider → `enterprise_high` (Workday/Taleo), `ai_prescreened` (Rippling), `startup_zero` (Greenhouse/Lever), `evidence_based` (Ashby), or `unknown` (Recruitee/SmartRecruiters/Workable, or an unrecognized host). New `jd_manager.save_ats_classification()`/`read_ats_classification()` pair, following the exact `_referral` convention (per-JD `_ats_classification` key: provider_id, weight_tier, classified_at) — computed once, cached, read back on rebuilds rather than reclassified every time.
- **#12 keyword front-loading**: new `orchestrator._build_keyword_block()` flattens `JDKeywordSchema`'s `tools`/`hard_skills`/`core_functions` (capped at 8, in that field order), formatted into a new `=== KEYWORDS ===` context block with front-loading instruction wording that scales by `weight_tier` — "critical" for enterprise/AI-prescreened tiers, "light touch" for human-read tiers, "helpful context" for unknown/unclassified. `tailor_coverletter.md` got one new rule explaining the block. Wired into `build_tailored_coverletter()` right after the existing referral block.
- **Standalone-run gap closed**: `build_tailored_coverletter()` previously read `jd_keywords` from the checkpoint but never used it — and a cover-letter-only run (no prior resume build) has no checkpoint at all. Now, if no checkpoint keywords exist, it makes one extra `GeminiClient.generate()` call to `extract_keywords.md` on demand, in-memory only (deliberately not written to a checkpoint, preserving the "cover letter has no checkpoint" invariant from the function's own docstring).

**Gotcha hit during implementation**: the new on-demand keyword-extraction call means `build_tailored_coverletter()` can now call `GeminiClient.generate()` twice (keywords, then the letter) instead of always once — any test asserting on `mock_generate.call_args_list[0]` to inspect the letter-generation call broke, because index 0 became the keyword-extraction call whenever the test JD had no seeded checkpoint. Fixed by switching those assertions to `call_args_list[-1]` (`tests/test_orchestrator_coverletter_enrichment.py`'s `TestReferralInjection` class). A second, subtler gotcha: `jd_manager.compute_job_key()` hashes a JD file's raw bytes when it has no `source_job_id`, so any metadata-persisting call that rewrites the file (`save_ats_classification()`, `save_referral()`, etc.) changes the job_key — a test seeding a checkpoint must do so *after* any such rewrite, keyed off a freshly recomputed job_key, not one cached from before the rewrite.

Full suite: 1608 tests passing after Group B (was 1585 after Group A).

### Group C — DOCX exporter (not started, architectural — needs its own spec)
Feature #3. Genuinely net-new subsystem — no DOCX *output* infra exists anywhere in the repo today (`python-docx` is currently only used to *read* uploaded resumes, in `bootstrap_extractors.py`). Needs design decisions before implementation:
- Library choice (`python-docx` is already a dependency for reading, likely reusable for writing)
- Template fidelity vs. the Typst-rendered PDF as the source of truth — how much visual parity is expected
- Where it hooks into `orchestrator.py`'s render pipeline (parallel to `render_coverletter()`'s PDF path, or a separate on-demand command)
- Whether this is cover-letter-only or eventually resume-only too (blueprint's Feature #3 concept covers both, citing Taleo/Workday's 97% DOCX parse rate)

### Group D — Voice anchor matcher (not started, architectural — needs its own spec)
Feature #9. Needs design decisions:
- What baseline corpus represents "Morgan's authentic voice" (existing `build_voice_anchors.py` output is quote artifacts, not a statistical baseline — may need new corpus-building work)
- What metrics to compute (sentence-length variance, vocabulary diversity/burstiness are the blueprint's suggestions)
- Where it plugs into the validation retry loop in `build_tailored_coverletter()`, and what threshold triggers a violation
- This is a different failure mode than #8's cliché blocklist — catches *statistical* AI-tells, not specific banned words (established via explicit discussion with the user)

### Group E — One-command pipeline (not started, bounded — glue only)
Feature #19. Every sub-step it would chain (liveness check, dual-metric scoring, resume build, cover letter build, company research, DB logging) already works individually — this is pure orchestration, no new logic. Deliberately sequenced last because it benefits from Group B (ATS-aware format/strategy selection) and Group C (DOCX vs. PDF choice) already existing, so the one-command version can be "smart" from day one rather than needing a later retrofit. Could still be built earlier as a dumb chain-only version if that's ever wanted out of order.

## Resuming this work

1. Re-read this doc for status and the group boundaries/dependencies.
2. For Groups C and D: these need the full architectural brainstorming path (multiple design decisions, new subsystems) — expect clarifying questions, 2-3 proposed approaches, a written design doc under `docs/superpowers/specs/`, then `superpowers:writing-plans` before implementation.
3. For Group E: bounded, can move straight to a short in-chat design once B and C exist (both now true for B) (or sooner, as a dumb version, if explicitly requested out of order).
4. The other 15 features from the original 23-feature blueprint were deliberately excluded from this roadmap (already shipped, misdescribed, or lower value/effort ratio than the 8 selected) — see Verification findings above before reviving any of them.
