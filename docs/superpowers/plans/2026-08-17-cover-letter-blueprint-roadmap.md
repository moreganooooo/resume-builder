# Cover Letter Blueprint Roadmap

> **Source**: `docs/cover_letter_research_master_blueprint.md` (Gemini-authored, 23-feature roadmap)
> **Status as of 2026-08-17**: Groups A-E complete. All 5 roadmap groups fully implemented and verified.
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

### Group C — DOCX exporter ✅ COMPLETE
Feature #3. Added automatic, ATS-optimized `.docx` export for both resumes and cover letters, built directly with `python-docx` and wired into `orchestrator.py` to generate alongside existing JSON/HTML/PDF artifacts on every build.

- **`render_coverletter_docx.py`**: Added renderer producing ATS-optimized single-column `.docx` cover letters with recipient block, dynamic tagline, and contact info. Tests in `tests/test_render_coverletter_docx.py`.
- **`render_resume_docx.py`**: Added renderer producing ATS-optimized single-column `.docx` resumes with Word standard styles (`Title`, `Heading 1`, `Normal`, `List Bullet`). Tests in `tests/test_render_resume_docx.py`.
- **`orchestrator.py` integration**: Added `self.output_docx_dir`, wired cover letter DOCX generation right after PDF creation in `build_tailored_coverletter()`, and wired resume DOCX generation right after PDF text check in `build_tailored_resume()`. Tests in `tests/test_orchestrator_docx_export.py`.

Full suite: 1634 tests passing after Group C (was 1608 after Group B).

### Group D — Voice anchor matcher ✅ COMPLETE
Feature #9. Statistical stylometry and voice anchor analyzer:
- **Design Spec**: [`docs/superpowers/specs/2026-08-17-voice-anchor-matcher-design.md`](file:///Users/morganescott/resume-builder/docs/superpowers/specs/2026-08-17-voice-anchor-matcher-design.md)
- **Implementation Plan**: [`docs/superpowers/plans/2026-08-17-voice-anchor-matcher-implementation.md`](file:///Users/morganescott/resume-builder/docs/superpowers/plans/2026-08-17-voice-anchor-matcher-implementation.md)
- **`voice_rules.yaml`**: Declarative voice thresholds ($\sigma \ge 4.5$, span $\ge 12$, max length 55, min length 3, TTR $\ge 0.46$, max consecutive opener 2) in `resume-engine/scoring/voice_rules.yaml`.
- **`voice_metrics.py`**: Pure-function stylometry module with abbreviation/decimal-safe sentence tokenizer, statistical variance/burstiness math, lexical diversity (TTR), and opener repetition detector. Unit tests in `tests/test_voice_metrics.py`.
- **Prompt rules**: Added explicit instructions on sentence length variance (mixing 4-8 word punchy statements with 22-35 word compound sentences) and varied openers in `resume-engine/prompts/tailor_coverletter.md`.
- **`validate_coverletter.py`**: Integrated `_check_voice_metrics()` and updated `validate(voice_rules=...)`. Tests in `tests/test_validate_coverletter_voice.py`.
- **`orchestrator.py`**: Loaded `self.voice_rules` in `ResumeEngine.__init__()` and passed `voice_rules=self.voice_rules` to `validate_coverletter.validate()` in `build_tailored_coverletter()` with single-retry fix loop. Integration tests in `tests/test_orchestrator_coverletter_voice.py`.
- **Failure Mode**: Catches *statistical* AI tells (monotonous sentence length variance $\sigma < 4.5$, low burstiness/span $< 12$, low TTR $< 0.46$, repetitive consecutive openers) vs. Morgan's authentic writing specimens.

Full suite: 1648 tests passing after Group D (was 1634 after Group C).

### Group E — One-command pipeline ✅ COMPLETE
Feature #19. Unified application package generation pipeline that orchestrates liveness verification, candidate-role fit evaluation, tailored resume generation, tailored cover letter generation (with ATS classification and keyword front-loading), and status/DB updates:
- **Design Spec**: [`docs/superpowers/specs/2026-08-17-one-command-pipeline-design.md`](file:///Users/morganescott/resume-builder/docs/superpowers/specs/2026-08-17-one-command-pipeline-design.md)
- **Implementation Plan**: [`docs/superpowers/plans/2026-08-17-one-command-pipeline-implementation.md`](file:///Users/morganescott/resume-builder/docs/superpowers/plans/2026-08-17-one-command-pipeline-implementation.md)
- **`orchestrator.py`**: Implemented `ResumeEngine.build_application_package()` and module-level `run_application_package()` supporting fail-fast liveness and fit gating, producing all 4 artifacts (Resume PDF/DOCX + Cover Letter PDF/DOCX), logging to SQLite and tracker, and moving JD to `jds/completed/`. Tests in `tests/test_application_package.py`.
- **`cli_art.py`**: Added `render_application_package_hud()` for beautiful Rich terminal output with company, role, ATS classification tier, and direct artifact file links. Tests in `tests/test_cli_art_package_hud.py`.
- **`cli.py`**: Added `resume package` and `resume build` commands supporting `--master`, `--output`, `--referral`, `--force`, `--skip-liveness`, `--skip-fit`, `--pick`, and `--yes`. Tests in `tests/test_cli_package.py`.
- **`menu.py`**: Added "Build Full Application Package" to interactive menu submenu under Build Documents with next-step chaining. Tests in `tests/test_menu_package.py`.

Full suite: 1663 tests passing after Group E (was 1648 after Group D).

## Resuming this work

1. All 5 roadmap groups (A, B, C, D, E) are fully implemented, integrated, and verified (1,663 total tests passing).
2. The other 15 features from the original 23-feature blueprint were deliberately excluded from this roadmap (already shipped, misdescribed, or lower value/effort ratio than the 8 selected) — see Verification findings above before reviving any of them.
