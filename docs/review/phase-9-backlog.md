# Phase 9 — Synthesis, contradiction resolution & fix backlog

Run 2026-08-05, Opus 5. **Reads no source code**, per the plan. Inputs: the
nine `docs/review/phase-*.md` docs plus `PLAN.md` and `plan-gaps.md`. The only
non-doc commands run were `git ls-files` enumerations for the mechanical
ownership check, which the plan requires.

**This file supersedes the nine phase docs as the working document.** They stay
as evidence; cited as `P<n>F<m>` (e.g. `P4F2` = Phase 4, Finding 2).

**Totals.** 9 docs, ~100 distinct findings, merged to **41 backlog items** —
6 blockers, 22 majors, 13 minors/roll-ups. Ranked by (goal × severity ÷ effort),
not by phase order.

---

## 1. Contradictions — resolved, with the loser recorded

Seven live disagreements across the docs. Each is settled here so the fix pass
does not relitigate them.

### C1. Ligature fix layer — **CSS wins. The normalizer loses.**
`P2F1` said fix it in the templates' CSS. `PLAN.md:211-216` told Phase 4 to
"pick a side" at the `normalizeTextForATS()` layer. `P4F7(b)` picked, with
proof: the ligature is created by the font shaper *inside Chromium at render
time*, after `generate-pdf.mjs` has finished transforming the source and handed
the file off. The HTML the normalizer inspects contains the plain string
`workflows`; the PDF contains `workﬂows`. **There is no character in the
normalizer's input to match** — adding `ﬁ`/`ﬂ` to `sanitizeText()` would be dead
code. **Decision: two CSS lines in both templates. Nothing is added to
`generate-pdf.mjs`.** Closed; do not reopen.

### C2. The Playwright doctor warning — **not a false positive.**
`P0 §1` recorded it as a false positive because PDFs rendered anyway. `P1
Corrections` and `P4F1` independently root-caused it: `node_modules/` does not
exist in this repo at all, and `require.resolve('playwright')` resolves to
`/Users/morganescott/node_modules/playwright` — a stray install two levels up.
Doctor was right and, if anything, understates it. **`phase-0-smoke.md:26-33`
is wrong and should be annotated in place.**

### C3. `_resume_ensure_profile: command not found` — **not a product defect.**
`P0 §1` reported it on 100% of invocations. `P1 Corrections` proved it is a
Claude Code shell-snapshot artifact: the snapshot captures `resume ()` but
filters out underscore-prefixed functions, so the review harness had the caller
without the callee. A real terminal sourcing `~/.zshrc` has both.
**`P4`'s Handoff re-flagging it as "the first thing any user sees on every run"
was written without `P1`'s correction in view and is superseded.** The only
residue is `P1F11`'s one-line guard (B36), which is genuinely minor.

### C4. Browse & Manage column truncation — **both causes are real; one is primary.**
`P0 §3` flagged it and could not tell whether it was a no-TTY capture artifact.
`P1F7` proposed wide/ambiguous-width fallback icons as the cause. `P2F4`
measured it at controlled widths and proved it real at 80 and 100 columns with
the *default* icon set — nine columns, no `no_wrap`, no width ratios.
**Primary cause is `P2F4`.** `P1F7` is a real, additive, independent defect (4
double-width + 5 ambiguous glyphs in the Unicode fallback set) that would make
it worse on the stranger's path — but it was never actually tested under
`RESUME_BUILDER_ICONS=unicode` (see H5). Both stay on the backlog; neither is a
duplicate of the other.

### C5. The launch banner — **a bug, not a design decision.**
`P0 §3` flagged 20–25s and asked for "a design judgment call." `P2F3` measured
`_stats_line_text()` at 0.88s × 31 frames = ~27.2s of recomputing a string that
cannot change during a 1.6-second animation. **No judgment call needed.**

### C6. `liveness.py:211`'s raw `❌` — **already fixed.**
`PLAN.md:266-270` and `P4F13` both record it as present. `P7F16` verified
commit `348fe628` replaced it and `liveness.py` now routes through
`theme.colorize_icon_ansi()` throughout. `PLAN.md` is stale here.
Separately, `PLAN.md:242-245`'s claim that `generate-pdf.mjs:211` was "the last
un-swept instance in the repo" is wrong three times over — `P1F15`
(`bootstrap_bullet_bank.py:352`), `P6 #11` (`ingest.py:82,93`), and `P7F16`
(`check-liveness.mjs:41,74`) each found another. Full residue list in B38.

### C7. Does `P6F1` invalidate `P3F9` ("no fabrication found")? — **No. Narrow caveat only.**
`PLAN.md:544-547` requires Phase 9 to treat any Phase 6 finding that invalidates
a Phase 3 input as grounds for re-testing that *specific* Phase 3 finding.
`P6F1` corrupts columns 10–16 of `bullet-bank-keepers.csv`, destroying the
`source` provenance field. `P3F9` traced every quantitative claim in the shipped
documents to a KB file by *content match* — the bullet-text columns are upstream
of the shift and unaffected. **`P3F9`'s core claim ("nothing was invented")
stands and needs no re-test.** What `P6F1` does invalidate is the narrower
claim that a given bullet can be *shown* to have come from a real resume: for
any row written through `triage_needs_review.py`, `source` now holds an integer
and the true value is unrecoverable (`:180` deletes the input in the same run).
That is a provenance-auditability defect, tracked as B8, not a fabrication one.
`P6`'s own Handoff to Phase 3 — that `voice-anchors.md` derives only from
`application-answers-index.csv` and has no connection to the bullet bank —
matches what `P3F8b` already said. No conflict.

---

## 2. Handoff ledger — every "Handoffs" line across nine docs

**Structural finding first.** The suggested order (`0 → 3 → 2 → 1 → 4 → 6 → 7 →
7b → 8 → 5 → 9`) meant handoffs travelling *backwards* — Phase 8 → Phase 3,
Phase 7b → Phase 7, Phase 6 → Phase 1, Phase 4 → Phase 1/2 — landed on phases
that had already ended. **11 of 31 handoffs fell through, and 10 of those 11 are
backward-pointing.** This is a property of the plan's ordering, not of any
phase's diligence. Every one is carried onto the backlog below rather than
re-dispatched, since there are no phases left to receive them.

| # | From → To | Item | Status |
|---|---|---|---|
| H1 | 0 → 1 | Brand-new profile first-run experience | ✅ `P1` created a real `phase1probe` profile |
| H2 | 0 → 2 | Verify column truncation at real terminal width | ✅ `P2F4` |
| H3 | 0 → 2/3 | Banner cost: intentional or not | ✅ `P2F3` |
| H4 | 0 → 3 | PDF text-layer check shipping anyway (§2d) | ✅ `P3` MAJOR 2 |
| H5 | 1 → 2 | Re-check truncation **under `RESUME_BUILDER_ICONS=unicode`** | ⚠️ **partial** — `P2` tested widths, never the fallback icon set → B22 |
| H6 | 1 → 4 | Test residue `{jds,output,data}/test_guest_trigger_profile_xyz/`; top-level `output/{checkpoints,html,json,pdf}` coexisting with profile-scoped paths | ✅ **picked up by `P11` trace 3** → B62 |
| H7 | 1 → 5 | Packaging collapses setup steps 1–7 + 11 | ✅ `P5 #6` |
| H8 | 1 → 4 | `menu.py:186-215` onboarding-logic coverage gap | ✅ assigned in `PLAN.md`, `P4F3` |
| H9 | 2 → 3/4 | **3 employers on the design system's page 2 are absent from the rendered resume**, with 7.33in of free space | ✅ **root-caused by `P11` trace 1** → B60 |
| H10 | 2 → 4 | `get_completed_jds()` returns 0; banner advertises "0 Resumes Customized All-Time" | ✅ **root-caused by `P11` trace 2** → B61 |
| H11 | 2 → 4 | `_stats_line_text()`/`get_pending_jds()` walks 1,144 files per call | ⚠️ partial — `P2F3` removes 30 of 31 calls; the ~1s residue untouched → B24 |
| H12 | 2 → 5 | `theme.py` has no light variant; Go side does | ✅ `P5 #5` |
| H13 | 3 → 2 | Ligature CSS fix (blocking) | ✅ `P2F1` |
| H14 | 3 → 4 | `validate_pdf_text.py` needs an owner | ✅ `P4` claimed + verified the patch |
| H15 | 3 → 4 | Validator log can't distinguish "0 issues" from "budget exhausted" | ❌ **fell through** → B33 |
| H16 | 3 → 4 | **Nothing verifies JD-keyword coverage of the finished resume** | ❌ **fell through — architecture gap** → B18 |
| H17 | 3 → 1 | `build_voice_anchors.py` weakness inherited by every new profile | ⚠️ partial — `P6` verified reproducibility, not the onboarding angle → B21 |
| H18 | 3 (patch) → 4 | **Cover-letter PDF is never text-layer checked at all** | ❌ **fell through** → B9 |
| H19 | 4 → 1 | `resume-cli.sh` shell-function bug | ✅ pre-empted by `P1F10`/`F11` (see C3) |
| H20 | 4 → 1 | doctor should check `npm` | ✅ pre-empted by `P1F8` |
| H21 | 4 → 1 | Empty-string `KU`/`KCKCC` achievement key from bootstrap-written `profile.yml` | ❌ **fell through** (also orphaned from `P0 §2b`) → B31 |
| H22 | 4 → 2 | `liveness.py` orphan (reassigned) | ✅ → Phase 7, `P7F4` |
| H23 | 4 → 2 | `generate-pdf.mjs` missed by the emoji sweep | ❌ fell through (cosmetic) → B38 |
| H24 | 4 → 2 | Ligature CSS (confirming `P2F1`) | ✅ |
| H25 | 6 → 2 | `bullet_bank_menu.py:225-228` mtime status logic breaks if F2's atomic write lands | ❌ fell through → noted inside B7 |
| H26 | 6 → 4 | `.npy` staleness guard must be enforced at `mine_bullet_bank()`'s read | ❌ **fell through** → B20 |
| H27 | 6 → 8 | Four non-atomic KB writes | ✅ `P8F8` (expanded to 17 sites) |
| H28 | 6 → 1 | Real stranger's-resume ingestion is `bootstrap_extractors.py` | ⚠️ partial — `P1F1/F2` cover ingestion *failure*, not output quality → B21 |
| H29 | 7 → 2 | `render_scan_report` has nowhere to display *why* a source returned zero | ❌ fell through → folded into B12 |
| H30 | 7 → 4 | `jd_manager.job_key_known()`'s four-directory walk | ❌ fell through → B19 |
| H31 | 7 → 8 | Confirm `JOBRIGHT_COOKIE_STRING` / `li_at` can't reach a log or the tracker | ✅ `P8F7` — verified clean, 0 hits |
| H32 | 7b → 7 | `NODE_TIMEOUT_SECONDS = 30`; ~400 sequential spawns; JSON error-envelope consumer | ❌ fell through → folded into B6 and B12 |
| H33 | 7b → 8 | `adzuna.mjs` puts `app_key` in the query string | ⚠️ partial — `P8F7` verified *Gemini* key hygiene, not this → B39 |
| H34 | 8 → 3 | **`evaluate_fit()` sends no KB context** despite the prompt promising it | ❌ **fell through** → B3 |
| H35 | 8 → 3 | `validate_coverletter.py` has no factual-grounding check | ✅ carried inside `P8F1` → B1 |
| H36 | 8 → 7 | `git_update` will nudge a new user to commit their own untracked PII | ❌ fell through → folded into B11 |
| H37 | 8 → 7b | 24 provider subprocesses inherit `GEMINI_API_KEY` + JobRight cookie | ❌ fell through → B32 |
| H38 | 5 → — | Fold packaging/caching/batch into `IDEAS.md` | ❌ not done → B41 |
| H39 | 6/7 → 9 | `PLAN.md` corrections (ingest/normalize pairing; stale emoji note; `board-scanners/` residue wording) | ✅ this doc, §4 |

---

## 3. The ranked backlog

> ### ⛳ FIX-PASS STATUS — start here next session (updated 2026-08-06)
>
> **Tier 0 is COMPLETE, plus B15.** 18 items across five commits
> (`37e70126`, `323e92c9`, `3839f980`, `b8542292`, `139786af`). Test suite
> 1098 → 1135, all passing.
>
> **Done:** B1 · B2 · B3 · B4 · B5 · B6 · B7 · B8 · B9 · B10 · B11 · B12 ·
> B13 · B14 · B15 · B16 · B17 · B18 · B19 · B20 · B24 · B26 · B27 · B28 ·
> B29 · B30 · B36 ·
> B37 · B38 · B39 · B43 ·
> B44 (partial — see below) · B45 · B47 · B48 · B49 · B50 · B51 · B53 · B54 ·
> B55 · B56 · B57 · B58 · B59 · B60 · B61 · B62
>
> **B52 — checked, not fixed: already resolved.** Verified live against the
> actual files, not the doc's snapshot — see the 2026-08-06 entry below.
>
> **2026-08-06 — Tier 3, first 11 of 15 items, commit `67aa78b2`.** Worked the
> hygiene/modernization tier in easiest-to-hardest order (deletions and config
> first, then well-specified single-file edits, then multi-file sweeps).
> Deliberately stopped before B40/B41/B42/B46 — B40 needs a root-cause dig
> (where `profile.yml` gets a blank achievement key at bootstrap time is still
> unknown), B41 touches the credential/env-allowlist surface across 24
> provider subprocesses, and B46 bundles a real architecture decision (the
> Batch Mode call-site split) in with its trivial pieces — none of those fit
> the "trivial effort" framing the rest of the tier had. B44 shipped partial:
> #8 (wrong `.env` path), #11 (dead `ingest.py`, deleted), #12 (exception text
> in the `weaknesses` column), #13 (unhelpful `ValueError`), and #14 (stale
> docstring) are done; #9 (unreachable-script inventory, feeds B30) and #10
> (duplicate `hidden-gems.csv` schemas, already inert per the doc's own note)
> were left as-is — informational, not actionable within this item. Also left
> `generate-pdf.mjs`/`check-liveness.mjs`'s raw emoji alone (B45's residue
> list) — no JS-side theming infrastructure exists to route through, and
> building one is a new-feature-sized piece of work, not hygiene.
>
> **B38 changed a public function's contract** (`_parse_pdf_result` gained a
> `pdf_path` parameter and now reads pypdf instead of regexing stdout), which
> broke 8 tests that depended on the old "unverifiable page count treated as
> fine" behavior. Fixed by updating the tests (a class-level patch restoring
> the old regex behavior for the 15 tests that fake the PDF subprocess without
> writing a real file, plus rewriting the 3 tests that exercise
> `_parse_pdf_result` directly) rather than reverting the fix. Full suite:
> 1136 passed, 0 failed.
>
> **Verified against real artifacts, not just tests:**
> - **B1** — ligature corruption **7 corrupted tokens → 0** on a freshly
>   rendered PDF, with `workflows` (the JD phrase the renderer used to break)
>   extracting intact. Baseline captured pre-fix from the shipped PDFs:
>   resume 7, cover letter 7.
> - **B9** — cover-letter text-layer check ran clean across 3 paragraphs.
> - **B60** — detection confirmed live: caught all three missing employers
>   and correctly refused to ship the incomplete resume.
> - **B15** — see the correction below; rendering works again.
>
> **⚠️ B15 was not what this document assumed.** `npm install` alone does not
> close it. This machine is macOS 12.7.6 and **Playwright ≥1.62 dropped macOS
> 12 support** — `npx playwright install chromium` refuses outright, so no
> browser lands and every render dies at `chromium.launch()`. Now pinned to
> **exact `1.61.1`** (no caret) in `package.json`; that is the last release
> supporting macOS 12, and it pins Chromium 1228. The trap: `npm install`
> *succeeds*, only the browser step fails, and it fails after printing
> "Removing unused browser…" lines that read like normal cleanup. Recorded in
> CLAUDE.md's Setup section — **do not loosen the pin.**
>
> **🔄 B60 — root-caused, needs one confirming run.** Three consecutive
> sample runs reported `Element 8 / Strategy LLC` missing while every other
> violation got fixed (8 → 3 → 1 across attempts) and the 4-attempt loop
> exhausted on it every time. **The defect was in the check, not the model.**
> This project's own sources disagree on the name: `profile.yml` says
> `Element 8 / Strategy LLC`, `cv.md` says `Element 8 + Strategy, LLC`. The
> builder writes the work history from the KB, so it emits the KB's spelling
> — and the roster check, comparing punctuation, called a company missing
> that was already in the document, then spent every fix attempt asking for
> an entry that existed. The tell: VML and Callahan Creek are spelled
> identically in both sources, which is why they were the only two that ever
> appeared to get "fixed". Names are now normalized to lowercase
> alphanumerics before matching (`1db98f5d`).
>
> **Next session: run `resume sample` once to confirm six employers and a
> completed resume PDF.** Do not reach for `max_fix_attempts` or a
> deterministic seed from `fixed_content.py` — an earlier version of this
> note proposed both on the strength of the bad diagnosis, and neither is
> warranted. Mining was never the problem either (the checkpoint carries 3
> refined bullets for Element 8, matching Phase 11).
>
> **Worth fixing separately, low priority:** the underlying name drift
> between `cv.md` and `profile.yml` is still there. The check now tolerates
> it, but any future code that joins on company name will hit the same wall.
>
> **Two Tier-0 items came out bigger than filed:** B47 named five rubrics
> with broken `flags:` blocks — it is **seven** (all fixed, with a test that
> checks every rubric so a new file can't reintroduce the shape). And B60's
> roster check needed a follow-up: exact-match name comparison produced a
> false positive on `Inside Sales Team` vs. `Inside Sales Team (Now
> Alleyoop)`, which mattered because each false positive consumes one of the
> validator's 4 fix attempts that a genuinely absent employer needs. Matching
> is now containment in either direction.
>
> **2026-08-06 — B13 (KB durability).** `grep -rn
> "open(.*[\"']w[\"']" scripts/*.py` found **56** candidate sites, not the
> doc's "17+" — the finding's own count (`P8F8`, phase-8) undercounted
> because its methodology was `open()`-only; `df.to_csv()` writes (e.g.
> `cluster_bullet_bank.py`'s `CLUSTER_MAP_CSV`) share the same truncate-at-
> open risk but a different call shape, and were left alone as a separate,
> unfiled finding rather than folded into this fix silently. Of the 56,
> **42 converted** to the new `atomic_write()` helper (`scripts/
> atomic_write.py` — write to a sibling temp file, `os.replace()` on clean
> exit, remove the temp file and leave the original untouched on any
> exception) — every KB writer named in `P8F8` plus its full 18-site
> `bootstrap_profile.py` range, `bootstrap_bullet_bank.py`'s six KB/
> checkpoint writes (not individually named in the doc but the same
> character: the actual `bullet-bank-clean.csv`, ingestion's own
> checkpoint), `jd_manager.py`'s five (`save_checkpoint` — named explicitly
> — plus `save_evaluation`/`save_liveness`/`save_application_status`/
> `split_batch_jds`, all truncating a JD's own already-live JSON file, not
> just metadata), and `scan.py`'s new-JD write. **14 deliberately excluded**
> as out of B13's "knowledge base" scope, not oversights: per-JD output
> artifacts (`orchestrator.py` ×2, `polish.py`, `render_html.py`,
> `render_coverletter.py`, `detect_blank_scores.py` — the last is B62's
> wrong-path finding, not this one) and writes already guarded by a
> not-exists check or flagged as scratch by another backlog item
> (`profile_paths.py`'s `.stignore`, `liveness.py`'s temp input file per
> B62, `jd_manager.py`'s `append_application_row` header,
> `bootstrap_bullet_bank.py`'s five-site `create_new_profile()` scaffold —
> a fresh profile's boilerplate, not live data). (b) `load_checkpoint` now
> logs which file and what exception before falling back to `{}`, at the
> same call site as (a)'s `save_checkpoint` fix. (c) `scripts/
> kb_snapshot.py` adds a 5-rotation pre-run snapshot (top-level KB files
> only, not `archive/`/`bootstrap/`) into `profile_paths.kb_snapshot_dir()`
> — a new path function, `data/<profile>/kb_snapshots/`, following the
> existing `data_dir()`/sync-root convention rather than a new one — called
> once from `orchestrator.run_pipeline()` before any JD is processed. (d)
> `doctor.check_kb_allowlist()` now also flags zero-byte or future-mtime
> KB_ALLOWLIST files and sweeps the KB directory for `.sync-conflict-*`
> files, folded into the same check rather than a new one. Full suite: 1155
> passed (was 1136 after B60's fix), 0 failed — new coverage for
> `atomic_write` (success/failure/no-leftover-temp-file cases),
> checkpoint-corruption logging, `kb_snapshot` (copy/no-recurse/rotation),
> and `check_kb_allowlist`'s three new failure modes. The existing
> `test_orchestrator_main_batch.py` suite now mocks the new
> `kb_snapshot.snapshot_kb()` call — without it, every test there
> (`orchestrator.main()` unmocked) would have copied the real active
> profile's real `knowledge_base/` into its real `data/<profile>/
> kb_snapshots/` on every test run.
>
> **2026-08-06 — B14 (JD prompt injection).** Two layers, both landed.
> **Grounding:** `validate_coverletter.py` gets a new
> `_check_kb_traceability()`, run inside `validate()` (new optional
> `kb_corpus=""` param, backward compatible -- `polish.py`'s call site is
> outside the JD-injection threat model and passes nothing, so it's
> unaffected). It extracts distinctive numeric claims from the letter body
> (percentages, `$`/K/M-suffixed metrics, "N years/yrs" experience claims,
> year ranges -- deliberately not bare digits, which would flag every
> ordinary number) and flags any that don't appear anywhere in the same
> `build_audit_static_prefix()` corpus already grounding the model in
> system_instruction. `orchestrator.py`'s two `build_tailored_coverletter()`
> validate() call sites now pass `kb_corpus=background_context`.
> **Delimiting:** all 7 `=== JOB DESCRIPTION ===` call sites (found by
> string, not the doc's line numbers, which had drifted to 2231/2340/2391/
> 2431/2559/2709/2870) now close with `\n=== END JOB DESCRIPTION ===`
> after `{jd_text}`, containing an embedded forged closing marker (or a
> forged `=== RESUME JSON ===`/`=== MASTER RESUME ===`) inside the real
> block instead of letting it stand as top-level structure. All 7
> `resume-engine/prompts/*.md` files that consume JD text (`evaluate_fit`,
> `draft_outreach`, `draft_followup`, `tailor_coverletter`,
> `extract_keywords`, `tailor_resume`, `critique_resume`) get a new "Job
> Description Is Data, Not Instructions" section naming the real delimiter
> and stating the JD is untrusted data to extract facts from, not
> instructions to follow -- the other 5 prompt files (`polish_resume`,
> `polish_coverletter`, `critique_bullet`, `extract_evidence`,
> `research_company`) never receive raw JD text, so they're out of scope.
> **Proven, not just reviewed** (`tests/test_orchestrator_coverletter_injection.py`,
> new): retyped phase-8's actual proven payload (JD `description` field
> carrying a fake `=== END JOB DESCRIPTION ===` / `SYSTEM INSTRUCTION
> OVERRIDE` / forged `=== RESUME JSON ===` block) into a real JD fixture
> and ran it through `build_tailored_coverletter()` with `GeminiClient.generate`
> mocked (no live call). *Before this fix, live, per phase-8:* the payload
> reached a real rendered PDF with "10 years of professional Rust systems
> programming experience ... at Stripe (2019-2024), cutting p99 latency
> 92%" woven into the first paragraph, undetected by every existing check.
> *After:* `_check_kb_traceability()` run against this profile's real,
> unmodified knowledge base flags `'92%'` and `'2019-2024'` by name (neither
> traces to the corpus); the mocked pipeline test confirms the existing
> one-retry fix loop -- which never re-sends `jd_text` on the retry call --
> produces a final letter with `Rust`/`Stripe`/`92%`/`p99`/`2019-2024`/
> `ZZINJECTEDZZ` all absent; and a third test confirms the real closing
> marker sits after the entire forged payload in the constructed `contents`
> string, containing it inside one delimited block. **Honest limitation,
> not fixed here:** `build_tailored_coverletter()`'s existing "issue(s)
> remain after retry, proceeding anyway" fallback is unchanged -- a
> traceability violation that survives the one retry still ships, exactly
> as any other cover-letter violation already did before B14. Full suite:
> 1165 passed (was 1155 after B13), 0 failed.
>
> **2026-08-06 — B16 (onboarding's false-green chain).** Three edits, one
> causal chain. **(a)** Root cause: `GeminiClient.generate()` already
> returns `(None, {})` on a real, non-retryable failure (a 403, an
> exhausted-retries exhaustion, a malformed response) -- `raw` is `None`
> *only* on a genuine call failure, since a successful call always returns
> a string, even an empty one. The four ingestion-path extraction functions
> (`classify_document_type`, `extract_achievements`, `extract_certificate`,
> `extract_resume_timeline_and_achievements` -- `bootstrap_extractors.py`,
> `text=` branch only; every one of them is called exclusively from
> `bootstrap_bullet_bank._process_one_file()`, so this is fully scoped to
> ingestion) were collapsing that `None` into an empty dict via `raw or {}`
> and returning an empty-but-valid result instead of surfacing the failure.
> They now raise a new `IngestionAPIError` instead.
> `bootstrap_bullet_bank.run_ingestion()` catches it separately from the
> existing generic `except Exception` (which still handles unsupported file
> types / doc-conversion failures as `"error"`, unchanged) and checkpoints
> `{"status": "failed", "reason": str(e)}` -- not `"done"`, so the very
> next `run_ingestion()` call retries it instead of skipping it (only
> `"done"` is ever skipped). `run_ingestion()`'s summary dict gained a
> `failed` count, and `print_ingestion_summary()` now prints "N document(s)
> failed to process (API error...)" when nonzero. The upload path
> (`_generate_from_upload`, used for PDF/image source docs) was left alone
> -- the google-genai SDK it calls already raises on a real API error
> rather than swallowing it, so that path was never part of this bug.
> **(b)** `bootstrap_menu.py`'s two wizard call sites that invoke
> `collect_secrets()` (`_run_phase0()` before `run_ingestion()`,
> `_run_phase05()` before `run_profile_setup()`) now check its returned
> `gemini_key_set` and stop with a clear message instead of proceeding --
> previously both discarded the dict and ran the API-calling step
> regardless of whether the key was actually set. **(c)** `_run_phase05()`
> now gates on `_phase0_status()` returning `"Up to date"` before running
> at all (previously enforced only by a body comment in
> `bootstrap_profile.py`'s module docstring, which nothing read).
> `_phase05_status()` returns a new `"Locked"` state when Phase 0 isn't
> complete, rendered in the same status table `bootstrap_menu.py` already
> shows (unmapped statuses fall through to `cli_art.py`'s existing `[dim]`
> style, so no rendering changes were needed).
> **Proven, not just reviewed:** `tests/test_bootstrap_extractors_llm.py`
> mocks `GeminiClient.generate` to return `(None, {})` (the exact shape a
> 403 produces) for each of the four functions and asserts
> `IngestionAPIError` -- before this fix, three of them asserted an empty
> result instead. `tests/test_bootstrap_bullet_bank_ingestion.py`'s new
> `TestRunIngestionAPIFailure` reproduces the real repro end-to-end:
> `extract_resume_timeline_and_achievements` raises `IngestionAPIError`,
> confirms the checkpoint says `"failed"` (never `"done"`) with a `reason`
> field, confirms `summary["failed"] == 1`, then clears the mock's
> `side_effect` (simulating the key being fixed) and calls
> `run_ingestion()` again -- confirms the mock is invoked a **second**
> time (`call_count == 2`), proving a `"failed"` entry is retried, not
> permanently skipped the way `"done"` is. `tests/test_bootstrap_menu.py`
> adds `TestRunPhase0DeferredKey` and `TestRunPhase05Gating`: deferred key
> stops both steps before their API-calling function is ever called;
> `_run_phase05()` is also blocked when `_phase0_status()` isn't
> `"Up to date"`, even with a key already set, and even when `profile.yml`/
> `cv.md` already exist from an earlier completed run (the "Locked" state
> can re-trigger after a later partial re-ingestion, and Phase 0.5 must not
> read "Up to date" ahead of it). Full suite: 1178 passed (was 1165 after
> B14), 0 failed -- 13 new tests, no regressions.
>
> **2026-08-06 — B17 ("Pipeline complete!" printed for a PDF that doesn't
> exist).** Root cause per the doc: `validate_pdf_text()` collapsed a hard
> "the PDF is missing/unparseable" failure and soft "line not found intact"
> advisories into one warnings list, so a caller had no way to tell them
> apart. It now returns `(fatal, advisories)` -- `fatal` non-empty only when
> `extract_text()` itself couldn't read the file (the exact "Could not parse
> generated PDF ... No such file or directory" case from the real captured
> log). `build_tailored_resume()`'s call site returns `{}` immediately on a
> non-empty `fatal`, before the "Pipeline complete!" print or the
> `_output_paths` assignment. Belt-and-suspenders per the doc's own fix list:
> the success print and `_output_paths` are now *also* gated on
> `os.path.exists(pdf_out)` directly, independent of what
> `validate_pdf_text()` reports. `run_pipeline()`'s tracker row -- previously
> `has_pdf=bool(output_paths.get("pdf"))`, the truthiness of a path *string*,
> always true once a build decides on a filename whether or not it wrote
> anything -- now stats the file: `has_pdf=os.path.exists(output_paths.get("pdf", ""))`.
> Scoped to the resume path only: `ResumeDesignSystem.md:57`'s guarantee
> names "a resume" specifically, and the concrete harm chain (`run_pipeline`
> moving a JD to `completed/`, logging `mark_completed`, appending a tracker
> row) is wired only to `build_tailored_resume()` -- `build_tailored_coverletter()`
> has the identical "success print not gated on the file" shape
> (`validate_coverletter_pdf_text()` still returns one plain warnings list),
> but it isn't called from `run_pipeline()` and nothing moves a JD or writes
> a tracker row on its behalf, so it's outside this item's scope as filed.
> Left as a known, undocumented-elsewhere gap for whoever picks up the
> cover-letter side of this pattern.
> **Proven, not just reviewed:** `tests/test_orchestrator_build_checkpoint.py`
> adds `test_pdf_text_layer_fatal_is_not_reported_as_pipeline_success`
> (mocks `validate_pdf_text.validate_pdf_text` to return the real captured
> fatal message; confirms `build_tailored_resume()` returns `{}` and stdout
> never contains "Pipeline complete!") and
> `test_pdf_missing_on_disk_is_not_reported_as_pipeline_success` (text-layer
> check reports clean, but `os.path.exists(pdf_out)` says the file isn't
> there -- confirms the independent gate catches it too). The existing
> `test_skips_keyword_extraction_and_mining_when_checkpointed` happy path now
> also asserts "Pipeline complete!" prints and `_output_paths["pdf"]` is
> truthy, confirming no regression. `tests/test_orchestrator_main_batch.py`
> adds `test_tracker_row_has_pdf_false_when_pdf_path_is_set_but_file_is_missing`
> (a set-but-nonexistent `"p.pdf"` path now writes `❌` to the tracker, not
> `✅`) and `test_tracker_row_has_pdf_true_when_the_pdf_file_actually_exists`
> (a real on-disk PDF still writes `✅`, no regression).
> `tests/test_validate_pdf_text.py`'s resume-side test class is updated for
> the new `(fatal, advisories)` return shape throughout; the cover-letter
> test class is untouched, matching the scoping decision above. Full suite:
> 1182 passed (was 1178 after B16), 0 failed -- 4 new tests, no regressions.
>
> **Next up, per §6:** B19 (the rest of Tier 1). B24's page-2 layout work
> is now unblocked by B60, but re-run `resume sample` first, since restoring
> the missing employers changes what page 2 contains.
>
> **2026-08-06 — B19 (`workday` provider discarding every job on every
> run).** Root cause confirmed exactly as filed: `workday.mjs`'s pagination
> loop built the full jobs array before returning, `run_provider.mjs` only
> writes stdout after `fetch()` resolves, and `scripts/scan_boards.py`'s
> `NODE_TIMEOUT_SECONDS = 30` kills the subprocess well before a ~100-page,
> 94-second run (NVIDIA, live) ever gets there -- 100% of collected jobs
> discarded, every Workday company, every scan. Fix is entirely inside
> `board-scanners/providers/workday.mjs` (no `scripts/` changes -- B17 was
> concurrently in progress there): pagination now runs through a new
> exported `paginateWorkdayJobs()` bounded by three independent guards --
> a page cap (`WORKDAY_MAX_PAGES = 50`, mirroring `smartrecruiters.mjs:13`),
> a wall-clock time budget (`WORKDAY_TIME_BUDGET_MS = 20_000`, leaving
> headroom under the 30s parent kill) checked every iteration, and an
> inter-page delay (`WORKDAY_PAGE_DELAY_MS = 300`) for politeness -- any of
> which now yields whatever jobs were already collected instead of the
> loop silently running until the parent kills the whole process. Requests
> route through `_http.mjs`'s `ctx.fetchJson` (the `_ctx` parameter --
> previously received and ignored -- is now used, consistent with every
> other provider), which both applies its own timeout and throws on a
> non-ok response; a 429 or any other paginated-request failure is now
> caught and stops the loop cleanly, returning pages already gathered
> rather than losing them to an uncaught throw. `const limit = data?.limit
> ?? 20` is replaced by an exported `resolveWorkdayLimit()` using `||`, so
> a board reporting `limit: 0` (which `??` let through, turning `offset +=
> limit` into an infinite loop bounded only by the 30s kill) now falls back
> to the same default of 20. **Left alone, out of scope:** the *initial*
> page load's own `page.goto()` (30s) and XHR-intercept (20s) timeouts --
> separate call sites the doc's fix list doesn't name; the new 20s budget
> governs only the paginated-fetch phase that follows.
> No Node test harness exists for `board-scanners/providers/*.mjs`
> (confirmed: no `package.json` test script, no other `*.test.mjs`/
> `*.spec.mjs` file in the directory) -- added
> `board-scanners/providers/workday.test.mjs` using Node's built-in
> `node:test` + `node:assert`, mirroring `smartrecruiters.mjs`'s existing
> pattern of exporting a pure function for unit testing rather than
> exercising a live network call. 8 tests, all passing, mocking
> `ctx.fetchJson`: normal pagination to completion; the page cap stopping a
> huge `total` at exactly `maxPages` calls; a `limit: 0` bounded by the cap
> instead of spinning forever; a mid-loop 429 (`ctx.fetchJson`-shaped
> thrown error) returning the 2 pages already collected rather than 0; and
> a past deadline returning immediately with nothing fetched. No live
> Workday call made. Python suite unaffected, as expected (no Python file
> touched): 1178 passed (same count as after B16), 0 failed.
>
> **2026-08-06 — Session 1 of `fix-pass-plan.md` (B24, B49, B50, B51, B52,
> B53, B54, B18).** Critique/rubric wiring cluster, done together since all
> but B18 land in the same `orchestrator.py` critique region.
>
> **B24 (template family mismatch).** Three edits, verified against a real
> rendered PDF. `cv-template.html`'s `.header h1` was `42pt`/`line-height:
> 0.75in`; `ResumeDesignSystem.md:113` and the cover-letter template both
> say `32pt` -- brought the resume down to `32pt`/`0.5in` (matching the
> cover letter's ratio, not just the font-size number) rather than
> reinterpreting the spec, since two independently-built templates agreeing
> with the written spec was the strongest signal of which one was the
> outlier. `coverletter-template.html`'s `.contact-row .separator` was
> `#000000`; spec says separators are `#9aa3af` only -- fixed to match
> `cv-template.html`'s copy of the same rule, which already had it right.
> `.career-note strong` (the bold "Career Note:" label) inherited
> `font-style: italic` from its `.career-note` parent while also being
> `font-weight: 800` -- no italic-800 face exists, so Chromium was
> synthesizing a Type3 font for it. Added `font-style: normal` to the
> `strong` rule, which is what `ResumeDesignSystem.md:330-331` already
> specifies (bold label, italic note -- not an italic label). **Verified,
> not just reviewed:** ran `resume sample` before touching anything to get a
> baseline, then after -- page count held at 2 (resume) / 1 (cover letter),
> no regression; a `pypdf` scan of every font resource on every page of the
> freshly-rendered resume PDF found zero `/Subtype /Type3` fonts (was
> present before, from the career-note label).
>
> **B49/B50/B51 (rubric attachment, schema, and hard-failure gate --
> treated as one item since B50/B51 are strictly downstream of B49's attach
> point).** `critique_resume.md`'s own "Load and Apply" list named 18
> files; only 2 (`summary_score.yaml`, `top_third_score.yaml`) were ever
> attached to the critique call in `orchestrator.py`, so its 9-step
> evaluation sequence was scoring against rubrics it never received for
> Steps 1-6. Attached the remaining 16 -- `profile.yml` (item 1) via
> `static_prefix`, already built earlier in the same method for the bullet
> audit loop and therefore free to reuse (it also carries `voice-anchors.md`
> and the verified_* KB files as a bonus, which get to the critique step
> for the first time too), and the other 15 raw via
> `json.dumps(self.load_yaml(...))` -- **not** hand-curated per file the
> way `audit_and_refine_bullets()` curates its rules bundle, a deliberate
> scope decision: that curation exists because the audit loop multiplies
> its cost across every bullet in a resume, and critique runs exactly once
> per build, so the extra ~80KB doesn't compound the way a per-bullet cost
> would. `ResumeCritiqueSchema` gained the 11 fields the prompt's steps
> already named with nowhere to return them (`primary_identity`,
> `secondary_identity`, `tertiary_identity`, `competing_narratives`,
> `unsupported_positioning`, `recruiter_takeaway`, `strongest_alignment`,
> `weakest_alignment`, `ungrouped_skills`, `unsupported_skills`,
> `archetype_mismatch`), plus a new `hard_failures_triggered: List[str]`
> field for B51's gate. **The gate itself:** any `hard_failures_triggered`
> entries get prefixed (`"Fix rubric hard failure -- {reason}"`) and folded
> into `critique_data["recommendations"]` before Step 5.5 runs, so a rubric
> hard-failure re-enters the pipeline through the exact same
> apply-and-validate-with-discard loop every other recommendation already
> uses -- deliberately not a new blocking mechanism, since the safe,
> grounded path already exists and a hard failure is not categorically
> different from any other recommendation once it's phrased as one. Chose
> "wire a gate" over "delete `reject_if`" per the item's own two listed
> options, since the fields are honest content Phase 10 confirmed rubric
> authors intended to be load-bearing. **Verified, not just reviewed:** a
> real `resume sample` run against the live `morgan` profile returned
> `identity: Content Strategist & Operations Specialist / Lifecycle
> Marketing Specialist` (new field, populated), scores of 94-96 across all
> four dimensions, flags drawn from rubric vocabulary
> (`strong_jd_alignment`, `verified_metrics_present`, `archetype_aligned`,
> `no_ai_risk_patterns`) that wasn't available to the model before this
> session, `hard_failures_triggered` empty (this resume cleared every
> attached rubric's bar -- the gate exists but had nothing to catch this
> run), 3 recommendations correctly routed through Step 5.5 (1 applied, 2
> skipped as non-resume-content), and the pipeline completed normally with
> no schema-validation or parsing errors on the larger response.
>
> **B52 (archetype vocabulary) -- checked, not fixed: already resolved.**
> Read the four files the item named before touching anything.
> `style_rules.yaml:304` already has a full `archetype_ordering` block
> (`lifecycle`, `copywriter`, `enablement`, `marketing_ops` -- exactly the
> four `style_rules_archetype` values `professional_identity_score.yaml`
> references), and that file already has a complete `archetype_aliases`
> table (lines 25-69) mapping its own six identity keys to those same four
> `style_rules_archetype` values. `ats_match.yaml`'s five
> `archetype_overrides` keys now match `profile.yml`'s five archetype
> names exactly (`git log` traces this to `57075b3f`, predating this
> session). The specific dangling reference the item was filed against
> (`professional_identity_score.yaml:386`'s `style_rules_archetype` lookup
> having nowhere to resolve) does not exist in the current codebase --
> resolved between Phase 10's review and now, by whom or exactly when isn't
> recoverable from this pass. `role_dna.yaml`'s separate snake_case
> vocabulary (`email_lifecycle`, `sales_enablement`, `marketing_ops_crm`,
> `generalist_coordinator`) remains genuinely distinct, but its own header
> comment states it's "used by `tailor_resume.md` and the evidence ranker
> to match bullets to roles by evidence type" -- a different job
> (JD-keyword-to-evidence matching) from `style_rules_archetype`'s job
> (skills-section ordering), not a second copy of the same concept that
> needs reconciling. No code change made; re-litigating this in a future
> session should start from this note, not from the original P10F8 finding.
>
> **B53 (banned-word lists).** `tailor_resume.md:74` (single words) and
> `summary_score.yaml`'s `buzzword_openers` (specific 2-word phrases) were
> still genuinely divergent -- verified by grep immediately before editing,
> not assumed from the doc. Merged the six phrases the builder's list
> didn't already substring-cover (`accomplished professional`, `highly
> motivated`, `dedicated professional`, `seasoned professional`, `proven
> track record`, `strategic thinker`) into `tailor_resume.md`'s BANNED
> line, plus the two exact phrase forms (`results-driven`, `dynamic
> professional`, `visionary leader`) for a future reader's clarity even
> though their root words were already banned. Added a comment naming
> `summary_score.yaml` as the source of truth so the two can't drift apart
> silently again. Not exercised by `resume sample` in a way that isolates
> it (the builder call ran as part of the same sample build above, no
> banned-phrase violation surfaced either before or after -- a null
> result, not confirming evidence).
>
> **B54 (cover letter has no rubric).** `polish.py`'s `generate_candidate()`
> loaded `polish_coverletter.md` with nothing attached beyond the prompt
> itself -- `style_rules.yaml` was loaded afterward but only for the
> post-hoc validator, never for the generation call. Attached
> `believability.yaml` + `ai_risk.yaml` (the item's own "smallest useful
> version") to the cover-letter generation branch only (`doc_type !=
> "resume"`), which `ai_risk.yaml` reachable per B49. **Not exercised by
> `resume sample`** -- `polish.py` is a separate interactive command
> (`resume polish`) with no existing test coverage of its live Gemini call,
> so this is reviewed and syntax/import-checked but not run end-to-end this
> session; flagging honestly rather than claiming verification that didn't
> happen.
>
> Also added 5 new unit tests for B18's `check_keyword_coverage()` (all-
> matched/excellent, some-missing/weak, zero-keywords-doesn't-divide-by-
> zero, case-and-word-boundary matching, below-weak-threshold/poor) --
> the only new tests this session, since the rest of the cluster is
> prompt-assembly/schema plumbing exercised more meaningfully by the real
> `resume sample` run above than by mocking Gemini's response. Full suite:
> 1187 passed (was 1182 after B16/B17/B19), 0 failed.
>
> **B18 (JD-keyword coverage) is its own item, not folded into the rubric
> cluster above, since its fix lives in `validate_resume.py` +
> `orchestrator.py`'s Step 7, not the critique region.** New
> `validate_resume.check_keyword_coverage()`: deterministic, exact-match-
> only (case-insensitive, word-bounded) comparison of the already-extracted
> Step 1 `jd_keywords` (`tools`/`hard_skills`/`core_functions`) against the
> finished resume's Summary/Skills/Why/bullets/titles, scored and banded
> using `ats_match.yaml`'s own `thresholds` -- the exact "weights exist,
> logic doesn't" gap Phase 10 diagnosed. Deliberately a report, not a
> `validate()` violation: a missing keyword the candidate doesn't actually
> have is not something the pipeline should invent to close, so it's
> printed (matching the item's own "reported before the pipeline claims
> success" wording) rather than triggering the automated fix-and-revalidate
> loop the way a real violation does -- that loop exists for objective
> formatting rules, not for tempting a model to fabricate a skill under
> pressure to hit 100%. Wired into `build_tailored_resume()` right after
> the PDF text-layer check, before the "Pipeline complete!" print. **Verified
> live:** the same `resume sample` run reported `JD-keyword coverage: 79%
> (good_match, 15/19)` and named the 4 missing keywords by name
> (`Cybersecurity`, `Integrated marketing`, `Content operations`, `Messaging
> alignment`) -- all four are genuinely absent from this candidate's real
> background, so the report is accurate, not a false positive.
>
> **2026-08-06 — Session 2 of `fix-pass-plan.md` (B28, B29, B30, B20).**
> Voice/summary quality + bullet-bank integrity cluster. Two items landed
> differently than the plan's literal fix text, both caught by running the
> real pipeline rather than trusting the test suite alone -- worth reading
> before touching either check again.
>
> **B28 (`validate_resume.py` blind to `career_note`/EDUCATION).**
> `_all_bullets()` now also pulls `EDUCATION[i]["bullets"]`, so all 14
> bullets get length/forbidden-phrase/verb-uniqueness/pronoun checks, not
> 9. The `career_note` half of the item's own fix text ("include
> career_note in the pronoun check") was **not** implemented as written --
> `career_note` is hand-authored fixed content
> (`fixed_content.CAREER_NOTE`), unconditionally reapplied by
> `normalize_resume.normalize()` on every pass including inside the
> fix-retry loop, so flagging its deliberate first-person pronouns would
> hard-fail every build touching the Treering Yearbooks entry, forever --
> the LLM has no power to change fixed content. Asked Morgan; she chose
> "document it as a second allowed exception" over "rewrite the personal
> note" or "silently skip the check." `tailor_resume.md`'s three pronoun
> rules (Summary, Why, the blanket Work-Experience-and-elsewhere list) now
> all name `career_note` as the second exception alongside Why --
> `ResumeDesignSystem.md:332` already documented this as intentional, so
> `tailor_resume.md` was the one out of sync, not the design intent.
> **Verified live:** `resume sample` built a clean 2-page PDF with the
> Treering career note intact.
>
> **B29 (Summary specificity + voice-anchors into critique/apply).**
> Prompt half: `tailor_resume.md`'s Summary Rules no longer offer
> "Specializes in..."/"Transforms..." as copyable exemplars (the model was
> parroting them verbatim) and now explicitly require a concrete, checkable
> specific; both it and `critique_resume.md`'s Voice Calibration Reference
> now name `voice-anchors.md` and what its `>` blockquotes are for --
> previously present in `static_prefix`/`kb_context` but never explained
> in prose anywhere a builder or critique call could read. `orchestrator.py`'s
> Step 5.5 recommendation-apply call (`system_instruction=build_prompt`,
> unchanged since it was deliberately bare for cost) now gets
> `static_prefix` appended -- small (~5-10k tokens), not the full ~105k
> `kb_context` -- so content-quality edits are voice-grounded the same way
> Step 5's critique already is (via `static_prefix` reuse, landed in B49
> last session). Validator half landed differently than written: a first,
> blocking `validate_resume.py` check for "≥1 metric beyond the
> years-of-experience figure" **caused a real `resume sample` build to fail
> outright** -- the retry loop's `fix_contents` only ever contains
> `resume_data` + already-selected bullets (deliberately, for cost), and
> those bullets' metrics are already claimed by `metrics_rules`' own
> "appears at most ONCE across the CV" rule, so the model oscillated
> between "no metric" / "duplicate metric" for all 4 attempts with no way
> out. Asked Morgan; she chose non-blocking over "feed the retry loop more
> material" or "accept occasional failures." `check_summary_specificity()`
> is now a standalone report (same precedent as `check_keyword_coverage()`)
> printed alongside JD-keyword coverage in Step 7, not gated on. **Verified
> live, twice** -- the blocking version's failure, then the non-blocking
> version's success (2-page PDF + cover letter, specificity gap correctly
> surfaced as a warning, not a failure).
>
> **B30 (`voice-anchors.md` mostly paraphrase).** `build_voice_anchors.py`
> now emits only rows with a genuine "Quote Worth Pulling" (`### <topic>` +
> `> <verbatim quote>`), dropping "Themes & Highlights" third-person
> paraphrase entirely and skipping the 4/14 rows in
> `application-answers-index.csv` that have no quote at all -- nothing to
> demonstrate, so nothing kept. Regenerated the real
> `profiles/morgan/knowledge_base/voice-anchors.md`: 4,100 -> 1,426 bytes,
> now pure verbatim specimens. **Verified live:** `resume sample` completed
> normally (resume + cover letter PDFs both generated) with the new file.
>
> **B20 (embedding/clustering can silently misalign the bank).** New
> `scripts/bullet_bank_hash.py` (`bullets_sha()`, SHA256 of the bullet-text
> column in row order) shared by the write side
> (`embed_bullet_bank.py`/`cluster_bullet_bank.py`) and read side
> (`orchestrator.py`'s `mine_bullet_bank()`) -- a staleness check only
> means something if both sides compute the hash the same way, so this is
> one function, not three copies. `embed_batch()` in both embedder scripts
> now raises if the API returns fewer embeddings than texts sent (was
> `.get("embeddings", [])` silently contributing zero rows). Both scripts'
> checkpoints now carry `bullets_sha` and discard-and-restart on mismatch;
> `cluster_bullet_bank.py`'s checkpoint also now verifies `total` on
> load -- it already persisted `total`, per the item's own note, and simply
> never read it back. `cluster_bullet_bank.py`'s `VECTOR_CACHE` gained a
> `.meta` sidecar (it had none before) so a same-shape cache with changed
> content is caught, not just a shape mismatch. `mine_bullet_bank()` now
> reads `bullet_vectors_ge2_d768.meta`, computes the bank's current hash,
> and skips mining (same graceful-skip pattern as its existing
> missing-file/row-count checks) on any mismatch or unreadable/missing
> `.meta` -- enforced at read time per H26, not only at write time.
> `embed_bullet_bank.py`'s NaN handling changed from `.astype(str)` (NaN ->
> `"nan"`) to `.fillna("").astype(str)` (NaN -> `""`) to match
> `mine_bullet_bank()`'s `.fillna("")` -- the two sides must agree on this
> or an unrelated NaN would produce a spurious hash mismatch even with no
> real content change. **Backfilled, not regenerated:** the real
> `profiles/morgan/knowledge_base/bullet_vectors_ge2_d768.meta` predates
> `bullets_sha` and the underlying CSV hadn't changed since it was written,
> so patched the field in directly rather than burning API calls/time on a
> needless re-embed. 26 new tests across `test_bullet_bank_hash.py`
> (new), `test_embed_bullet_bank.py` (new), `test_cluster_bullet_bank.py`,
> and `test_mine_bullet_bank.py` (which also needed its two existing
> fixtures updated to write a matching `.meta`, or they'd have started
> failing under the new read-time check). **Verified live:** `resume
> sample` mined 30 bullets (23 from guaranteed per-company minimums)
> against the real, backfilled `.meta` with zero staleness warnings.
>
> Full suite: 1218 passed (was 1187 after session 1), 0 failed.
>
> **2026-08-06 — Session 3 of `fix-pass-plan.md` (B26, B27, B36).**
> Board-scanner hygiene cluster — all three fixes land inside the same
> provider-request loop, so they were worked together as planned. B36 turned
> out to be materially larger than its "small" sizing: two of its six
> providers (SmartRecruiters, Workday) only expose a real description via a
> *second*, per-posting API call, not the list call the rest of the fix
> touches. Asked Morgan whether to do that properly now or defer it as its
> own item; she chose "full fix now." That decision is the reason this
> session touches `scripts/scan_ats.py`, which isn't in this session's
> stated file list — `scan_ats.py` already imports and reuses
> `scan_boards.py`'s other helpers (`_run_node_provider`,
> `_passes_title_filter`, `_html_to_text`, `_fetch_posting_text` — see its
> own module docstring), and two of B26/B36's fixes are only real if they
> reach the callers that actually hit `websearch.mjs` more than once
> sequentially or the four ATS-only providers, both of which live in
> `scan_ats.py`, not `scan_boards.py`. Noted here since it's a real
> deviation from the plan's file list, made deliberately rather than missed.
>
> **B26 (no rate limiting, retry, backoff, or honest identity).**
> `_http.mjs` is now the policy layer the item asked for, not just a fetch
> wrapper: `fetchWithTimeout` retries 429/5xx/network errors (not
> `AbortError` — a timeout already spent its budget once, and every call
> here runs inside `run_provider.mjs`'s own 30s subprocess timeout, so
> doubling a slow request's wait does more harm than good) with exponential
> backoff, honoring a real `Retry-After` header over a guessed delay.
> `makeHttpCtx(providerId)` now takes the calling provider's id and applies
> a `PROVIDER_HTTP_CONFIG` entry (currently `hackernews`, `smartrecruiters`,
> `workday`, `workable`) as that ctx's default `timeoutMs`/`minGapMs` — a
> `minGapMs` provider's calls through that ctx fully serialize (one in
> flight at a time, at least that far apart) via a closure-local queue,
> which is what turns `hackernews.mjs`'s 60-simultaneous `Promise.all` into
> 60 paced calls with **zero changes to `hackernews.mjs` itself** — the
> pacing lives entirely in the shared layer. Default UA is now
> `resume-builder/1.0 (+https://github.com/moreganooooo/resume-builder)` —
> this repo, this version, no browser-impersonation prefix.
> `websearch.mjs` was the one provider bypassing `ctx` entirely (a raw
> `fetch()` call, confirmed by grepping every provider for bare `fetch(` —
> the only hit outside `_http.mjs` itself); routed through `ctx.fetchJson`
> now, and its own dead module-level rate-limit queue is deleted (it was
> genuinely inert: `run_provider.mjs` spawns one fresh Node process per
> call, so the queue never held more than one item across the entire
> subprocess boundary, and it was tuned to 100ms — 10× over the free tier's
> real 1 req/sec). Real pacing for that Brave call now lives where it
> actually needs to: `scan_ats.py`'s `search_queries.yml` sweep loop is the
> only place this repo calls `websearch.mjs` more than once in the same
> process, so it now measures wall-clock time since the *previous* call's
> start (not a blind fixed sleep) and only sleeps the remaining gap.
>
> **B27 (scan failures indistinguishable from "no jobs today").** Scoped to
> the Node-side half explicitly named in this session's file list — the
> Python-side `_ScanWarningCollector`/last-resort-handler half and
> `render_scan_report`'s "give it a place to put the reason" (H29) are
> `scan.py`/`cli_art.py` render-layer work belonging to a later session, not
> reopened here. `run_provider.mjs` now writes a JSON error envelope —
> `{"error":{"kind":"auth"|"quota"|"network"|"config","message":"…"}}` — to
> stdout on every failure path (module load, bad `entry_json`, `fetch()`
> throwing or returning a non-array), classified by a new `classifyError()`
> (HTTP status wins when present; falls back to message-text pattern
> matching; unrecognized errors are conservatively `"config"` rather than a
> guessed `"network"`, so a real bug doesn't get misread as a transient
> blip). `scan_boards.py._run_node_provider` parses that envelope for a
> specific `kind`/`reason` on a non-zero exit, falling back to the old
> stderr-last-line heuristic when stdout isn't that shape (e.g. the `node`
> binary itself is missing). `cli_art.py`'s `_WARNING_KIND_LABELS` gained
> entries for the four new kinds plus B36's `thin_description` — the
> dict already had a `.get(kind, kind)` fallback, so this was optional
> polish, not a requirement, but cheap and consistent with the existing
> two entries.
>
> **B36 (6 of 24 providers never emit a description; highest-value
> company-direct postings arrive with no body text).** `_types.js`'s `Job`
> typedef now documents `description`/`posted_at` as optional-but-expected,
> explaining why (this repo's tailor stage needs real JD text up front,
> unlike career-ops's own downstream). Per-provider, verified against real
> API docs/behavior before writing code rather than guessed:
> **websearch.mjs** — the Brave snippet was already being computed for
> `extractLocation()` and then discarded; now also mapped into
> `description`. **recruitee.mjs** — confirmed via Recruitee's own API
> reference that `/api/offers/` already returns `description`/
> `requirements` (HTML) on the same list call; mapped directly, no second
> fetch needed. **workable.mjs** — the per-posting `[View](...).md` link
> was already being computed and then stripped down to the public URL;
> kept as `_detailUrl` and fetched (it's already plain markdown, no HTML
> extraction needed), bounded to the first 40 postings / 15s. **
> smartrecruiters.mjs** — confirmed via SmartRecruiters' own API docs that
> the list endpoint is summary-only; description lives behind
> `GET /postings/{id}`'s `jobAd.sections.{companyDescription,
> jobDescription,qualifications,additionalInformation}.text`, joined and
> fetched the same bounded way. **workday.mjs** — confirmed the detail
> pattern (`.../cxs/{tenant}/{site}/job/{externalPath}` →
> `jobPostingInfo.jobDescription`) against a real reference implementation;
> this is also the actual root-cause fix, not just an enhancement — a
> Workday posting's public page is a JS SPA (the reason this provider
> drives Playwright at all), so `scan_boards.py`'s plain-GET page-fetch
> fallback could never have scraped one anyway. Detail-fetches run after
> `browser.close()` (plain JSON over `ctx`, no Playwright needed) and share
> the existing `WORKDAY_TIME_BUDGET_MS` deadline with pagination rather
> than adding a second budget. All three detail-fetch providers are
> best-effort per posting (a failure returns `""`, never throws — one bad
> posting doesn't drop the whole board) and bounded by both a count cap
> (40) and a wall-clock budget, the same graceful-degradation shape B19
> already established for Workday's own pagination. **Safety net:** a new
> `scan_boards._flag_thin_description()`, shared by `fetch_board_jobs()`
> and (via the existing `scan_ats.py` → `scan_boards` reuse pattern)
> `_normalize_raw_job()`, sets a `_scan` metadata key (per CLAUDE.md's
> underscore convention, same family as `_liveness`/`_evaluation`) and
> raises a `_scan_warning` (kind `thin_description`) on any posting under
> 200 chars — catches whatever's still thin after the provider-level fixes
> above (a detail-fetch failing, a source with genuinely nothing) instead
> of it silently shipping unflagged.
>
> **Not run against a live scan** — this session's board-scanner changes
> touch external APIs (Brave, SmartRecruiters, Workday, Workable,
> Recruitee) this checkout has no live credentials/tracked-company data to
> exercise safely, and a real scan run wasn't part of this session's scope.
> Every new code path is unit-tested with a mocked `ctx`/`fetch` instead
> (40 new `node:test` cases across 6 files — `_http.test.mjs`,
> `run_provider.test.mjs`, and one new test file per touched provider —
> plus 13 new Python tests), and every detail-fetch degrades safely to the
> pre-existing behavior (empty description → Python-side fallback) on any
> failure, so a wrong assumption about an undocumented API shape fails
> quietly rather than breaking a scan. **Flagging honestly:** this is
> reviewed and tested in isolation, not verified end-to-end the way
> `resume sample` verified Sessions 1 and 2 — there's no equivalent
> `resume sample` fixture for the board-scanner path.
>
> Full suite: 1231 passed (was 1218 after session 2), 0 failed — 13 new
> Python tests + 40 new `node:test` cases (previously 8, all in
> `workday.test.mjs`; this repo had no other `*.test.mjs` file before this
> session).

Ranked by (goals served × severity ÷ effort). **Tier 0 is everything where the
severity is major-or-worse and the fix is roughly one edit** — do these first
regardless of glamour; together they are a few hours and they close one blocker,
nine majors, and the single worst first impression in the product.

### Tier 0 — high severity, trivial effort (do these first)

**B1. Ligature corruption in every PDF ever produced.** BLOCKER · goal 2 ·
2 lines × 2 files.
`P3` BLOCKER 1 + `P2F1` + `P4F7` (layer resolved, see C1). 8 corrupted tokens in
the resume, 7 in the cover letter, including `Certiﬁcation` twice and
`workﬂows` — a verbatim phrase from the JD the pipeline correctly mirrored and
the renderer then broke. Invisible to PyMuPDF, total to pypdf/pdfminer-class
extractors, which is what real ATS stacks are built on.
*Fix:* add `font-variant-ligatures: none; font-feature-settings: "liga" 0,
"clig" 0;` to the `body` rule of `cv-template.html` **and**
`coverletter-template.html`. Re-run `P3`'s pypdf scan; require zero hits on both.

**B2. The launch banner spends ~27s replaying a 1.6s animation.** MAJOR ·
goals 1, 3, 4 · one line moved.
`P2F3` + `P0 §3`. `render_frame()` calls `_stats_line_text()` on every one of 31
frames; each call walks 1,144 JD files (0.88s). 100% of the time is recomputing
a constant. It is the first thing every user experiences.
*Fix:* hoist one `_stats_line_text()` call above `render_frame` and close over
the string.

**B3. `evaluate_fit()` scores candidate-fit while knowing nothing about the
candidate.** MAJOR · goals 1, 2 · a few lines.
`P8F4` + H34. `evaluate_fit.md:9-10` tells the model to consult "`target_roles`
and `archetypes` … in your knowledge base context." There is no knowledge base
context — the call is `eval_prompt` alone, no `load_knowledge_base()`, no
`profile.yml`. **Every fit score this tool has ever produced was computed
against no candidate profile**, and those scores rank the entire 1,144-JD
Browse & Manage queue. Proven by injection: the evaluator wrote paragraphs about
"a decade of systems engineering experience" that the JD had simply asserted.
*Fix:* pass the same KB/profile context the builder gets.
**Phase 10 confirms, from the rubric side:** the prompt does not merely omit
the profile — `evaluate_fit.md:10` directs the model to a knowledge-base context
block the call site (`orchestrator.py:2143-2150`) has never constructed, and
then forbids the predictable fallback ("not any example list"). **No `scoring/`
rubric is attached to `evaluate_fit` either**, and `role_dna.yaml` — the
archetype library, the one file that could supply "archetypes" independently of
`profile.yml` — is loaded by nothing (B49). Every `archetype` value ever written
into a JD's `_evaluation` was picked by a model that had seen neither the
candidate's archetype list nor the archetype library. *Fix scope:* attaching
`profile.yml`'s `target_roles`/`archetypes` is the minimum; attaching
`role_dna.yaml` too is what makes the returned `archetype` a controlled
vocabulary instead of freeform. See also B52 — four archetype vocabularies.

**B4. `SustainedFailureError` is swallowed by the batch loop.** MAJOR · goal 1 ·
one `except` clause.
`P4F5`. The exception exists to say "this is quota, not weather," and
`rewrite_bullets.py:1385` honors it. `run_pipeline`'s blanket
`except Exception` (`orchestrator.py:3064`) does not — so a revoked key produces
1,144 sequential full retry cycles (6 attempts, backoff capped at 90s) and hours
of sleeping, with the one useful instruction scrolling past 1,144 times.
*Fix:* catch it explicitly before the blanket handler, break, report how many
JDs remain untouched, surface the "swap `GEMINI_API_KEY`" line once.

**B5. A file that isn't a job description proceeds into the most expensive
step.** MAJOR · goal 1 · one branch.
`P4F4` + `P0 §4`. `orchestrator.py:2447` detects empty keyword extraction —
a strong, already-computed signal — prints "Proceeding with empty keywords," and
walks into a 30-bullet Gemma audit at `GEMMA_MIN_INTERVAL_SECS = 65`: over half
an hour of wall clock and real spend before anything JD-specific happens.
Pointing the tool at the wrong file is an ordinary mistake.
*Fix:* make the branch a stop. Interactive single-file mode may offer to
continue; batch marks failed and moves on.

**B6. Reflective questions are auto-applied as resume copy.** MAJOR · goal 2 ·
one condition (stopgap) / one schema field (real fix).
`P3` MAJOR 3. `critique_resume.md:129-135` deliberately phrases voice
recommendations as questions aimed at Morgan. Step 5.5 feeds them to an LLM that
edits the resume, and the `needs_personal_input` guard only catches *emotional*
questions. A strategic-sounding question was "applied" the only way a model can
apply a question — by paraphrasing its own noun phrases into the document,
producing the flattest sentence in the resume. Design intent exactly inverted.
*Fix (stopgap):* widen the guard to "any recommendation ending in `?`".
*Fix (real):* emit voice questions into a separate schema field Step 5.5 never
sees, surfaced to Morgan to answer.

**B7. "Drop New Knowledge" locks out every fully-configured profile.** MAJOR ·
goals 1, 3 · share an existing predicate.
`P0 §3` (its highest-severity finding) + `P4F3`. `menu.py:213` gates on the
presence of `bootstrap/checkpoint.json` — evidence of *how* a profile was
created — when the question is *whether* it exists. `morgan`'s checkpoint is
absent; the 628-bullet, 1,144-JD profile is told it hasn't been set up.
*Fix:* `_handle_new_user` twelve lines earlier already computes `is_existing`
from a real `knowledge_base/`. Extract it into one helper both entries call.
*Also touches B7's neighbourhood:* `P6`'s H25 note — fixing
`score_keeper_gems.py` to temp-file-plus-rename preserves
`bullet_bank_menu.py:184`'s in-place contract but changes the mtime-based status
logic at `:225-228`. Check it in the same pass.

**B8. `triage_needs_review.py` writes keeper rows into the wrong columns and
destroys provenance.** BLOCKER · goal 2 · header-aware append.
`P6F1`. `KEEP_FIELDS` is 14 columns; the real header is 16 and diverges from
index 9. `append_rows` opens `"a"` and writes the header only if the file is
absent, so `DictWriter` emits values positionally under a mismatched header — no
exception, still well-formed CSV. Reproduced: `source` = `'77'`,
`rewrite_date` = `'KEEPER'`, last two columns empty. **Irreversible** — `:180`
deletes `needs-review.csv` in the same run. Live on every accepted rewrite fed
back from a real JD run.
*Fix:* when the target exists, read its header and write against that, raising
on a missing required field. Apply to the `REWRITE_QUEUE`/`RETIRED_PATH` appends
at `:164`/`:168` too — they match today by luck.

**B9. The cover-letter PDF is never text-layer checked.** MAJOR · goal 2 · one
call site.
`P3` post-review patch finding + H18. `validate_pdf_text` runs at
`orchestrator.py:2990` on the resume only. The cover letter carries 7
ligature-corrupted words of its own. Half the application package ships with no
ATS verification whatsoever.
*Fix:* call it on the cover-letter PDF too. (After B1 the ligature warnings go
to zero, but the check should exist regardless.)

**B10. Cluster representative election is order-dependent.** MAJOR · goal 2 ·
one sort.
`P6F3`. `elect_representative` uses `idxmax()`, which returns the *first*
maximum; `accuracy_score` is a 0–100 integer over near-duplicate cluster members,
so ties are the common case and "first" means raw-CSV row order. This is the
exact positional instability that `stable_cluster_ids()` /
`_cluster_content_hash()` solves one function above — the fix was simply not
carried down. Appending a row silently changes which bullet reaches the resume.
*Fix:* break ties on normalized content, matching the existing hash approach.

**B11. `.gitignore` protects profile data by hardcoded per-name lines.** MAJOR ·
goals 1, 3 · three glob patterns.
`P8F5` + H36. `.gitignore:59-62` lists `profiles/dominick/`, `profiles/morgan/`,
`data/dominick/`, `data/morgan/`. `create_new_profile()` never touches
`.gitignore`. Verified: a third profile's `.env` and signature stay safe (caught
by `*.env` / line 18), but its **entire knowledge base, every saved job posting,
and `data/<name>/` are untracked-and-not-ignored** in a repo whose workflow is
`git pull` from GitHub. Compounded by H36: `git_update`'s
`has_uncommitted_changes()` counts untracked files, so the update flow actively
nudges that user toward committing their own PII.
*Fix:* `profiles/*/`, `data/*/`, `jds/*/` globs (keeping the existing negations
for tracked scaffold YAML). Note this also means git is not a recovery path for
`morgan`'s KB — see B13.

**B12. `websearch`'s `isJobUrl()` returns `true` on both branches.** MAJOR ·
goals 1, 2 · delete one line.
`P7bF5`. `JOB_PATH_SIGNALS` (20 entries) has no effect on any decision — the
function is really "not a blocked domain and not a blog post," so
`acme.com/team/leadership` passes as a job posting, becomes a JD file, and
becomes a paid Gemini tailoring call against a page that isn't a job. Related:
two `BLOCKED_DOMAINS` entries have the wrong TLD (`workingnomads.com` vs the
live `.co`, `remoteok.com` vs `.io`) and block nothing.

---

**B47. Five rubrics' `flags:` blocks parse as one run-on string, and two of
them are live today.** MAJOR · goal 2 · ~27 lines, no code.
`P10F3`. `flags:` is written as a bare indented block with no `- ` markers, so
`yaml.safe_load` returns a space-joined scalar instead of a list, in
`summary_score.yaml:98-105`, `top_third_score.yaml`,
`experience_structure_score.yaml`, `professional_identity_score.yaml`,
`skills_scoring.yaml`. The first two are **the only two `scoring/` files
attached to a live API call** (`orchestrator.py:2696-2697`), so `json.dumps()`
serialises the mangled scalar straight into the critique prompt — the model is
shown a run-on token string where a controlled flag vocabulary was intended.
Verify: `python3 -c "import yaml;print(type(yaml.safe_load(open('resume-engine/scoring/summary_score.yaml'))['flags']))"`.
*Fix:* add `- ` to each item in all five files. Do this before B48 — the other
three become live the moment the critique is rewired.

**B48. `scoring/README.md` has two false "Used by" rows.** MINOR · goal 5 ·
2 lines.
`P10F10`. `README.md:13` claims `ai_risk.yaml` is used by `orchestrator.py` (it
appears in no Python file); `:18` claims `role_dna.yaml` is used by
`tailor_resume.md` (it appears only in `critique_resume.md:24,86`). Every other
row is correct and `:33-42`'s status section is honest — which is exactly why
these two matter: an auditor tracing reachability from this table clears both
files and misses B49. *Fix:* correct the two cells. **Do not delete the status
section** — it is the only written record of the wiring gap.

**B60. Nothing requires the builder to emit one `EXPERIENCE` entry per role —
three employers are silently missing from the shipped resume.** BLOCKER ·
goals 1, 2, 4 · one validator function + one prompt line.
`P11` trace 1, diagnosing `P2F7`/H9 (**closes the first half of B25**).
`profile.yml` declares six roles; the live artifact
`output/morgan/json/MorganEscott_ContentStrategist_AbnormalAI_Resume.json`
contains three. `Element 8 / Strategy LLC`, `VML` and `Callahan Creek` — the
entire page-2 work history, 15 years of agency experience — are absent, which
is also the direct cause of `P2F7`'s 7.33in of dead space.
**Ruled out by evidence, not argument:** the trim loop cannot remove a company
(`orchestrator.py:2915-2980` only drops client rosters and bullets-toward-Min,
and never fired here — the PDF was already 2 pages); mining supplied all three
(the live checkpoint's 30 `bullet_tuples` include exactly 3 each for Element 8,
VML and Callahan Creek, their guaranteed `min_bullets` floor); the normalizer
maps `EXPERIENCE` 1:1 (`normalize_resume.py:59-94`); `fixed_content.py` has all
three fully configured.
**Root cause:** the roster reaches Gemini as prose only
(`build_role_rules_block()`, `orchestrator.py:1129-1179`), and
`tailor_resume.md:159-168` governs *bullet counts within roles that exist* —
never "every company in this table must appear." The only clause that says so
lives in a schema `description` (`orchestrator.py:967-970`), and
`sanitize_schema()` strips descriptions before they reach the API, so it is not
merely weak — **it is never sent**. Then `validate_resume.validate()` has no
roster check: `_check_experience_completeness()` (`:275-281`) validates fields
on entries that are present and cannot see an absent company. Zero violations,
PDF renders, JD moves on.
*Fix:* add `_check_role_roster()` to `validate_resume.py` — every
`profile.yml` `roles:` name (situational roles excluded) must appear in
`EXPERIENCE`, violation naming the missing company; it is already wired into
both the post-build and post-trim validation gates. Add one explicit line to
`tailor_resume.md`'s Per-Role Bullet Count Targets section: every company in
the table gets an entry, no exceptions. Re-run `resume sample` and require six
employers. **Do not pad page 2 with CSS** — `P2` was right, and B25's layout
half resolves itself once the content is back.

**B61. "Resumes Customized All-Time" counts a directory, not the work done.**
MAJOR · goals 1, 4 · small.
`P11` trace 2, diagnosing H10 (**closes the second half of B25**). The premise
in B25 was wrong: `jds/morgan/completed/` really is empty, `jd_tracker_log.csv`
does not exist, and both `get_completed_jds()` (`jd_manager.py:629-645`) and
`run_pipeline`'s move (`orchestrator.py:3070-3072`) are correct as written.
Every resume this profile has produced came from `resume sample`, which by
documented design skips the move and the tracker write. **The defect that
remains** is that `_stats_line_text()` (`cli_art.py:135-141`) derives an
"All-Time" figure from `len(get_completed_jds())` — a mutable directory count.
`archive_jd()` (`jd_manager.py:648-660`) moves files *out* of `completed/`, so
archiving an old application silently decrements an all-time total; two real
resumes and a cover letter sit in `output/morgan/` while the banner reads zero,
with no path by which that number can recover them.
*Fix:* count rows in `jd_tracker_log.csv` (append-only, one per
`mark_completed()`) instead — the honest ledger, and it already exists for this
purpose. **Do this with B2** (same line of the same banner: B2 makes it fast,
B61 makes it true). **Not the same bug as B17** — B17 is the move firing when
no PDF exists; this is the counter reading a directory instead of a ledger.
Neither fix implies the other.

**B62. Pre-profile `output/` writes and a test teardown that misses three of
four sync roots.** MINOR · goals 4, 5 · small.
`P11` trace 3, picking up H6 — never owned by any phase. Both halves land
outside `profile_paths.sync_roots()`, so anything they write is invisible to
Syncthing, in a repo whose CLAUDE.md names `profile_paths.py` the single source
of truth for every profile-scoped path.
**(a)** `ingest.py` was the *visible* offender (already in B44), not the only
one. `detect_blank_scores.py:34,206-207` is **live** and `mkdir(parents=True)`s
a shared `output/json/` to write `unscored_bullets.json` — real profile-derived
bullet-bank data on a path a second profile would overwrite.
`liveness.py:22,92-93` writes `output/liveness_input_tmp.json` at the repo root
(cleaned up in a `finally`, so it only persists if the process is killed
mid-check). The four empty top-level `output/{checkpoints,html,json,pdf}/`
directories are all dated Jul 18, four days before the profile migration —
pre-migration residue, not evidence of a current writer; only `output/json/`
has a live writer that recreates it.
**(b)** `tests/test_menu_bootstrap.py:53-57` creates a real profile, but
`tearDown()` removes only `profiles/<name>/` while `create_new_profile()` seeds
all four `sync_roots()` — leaving `jds/`, `output/` and `data/`
`test_guest_trigger_profile_xyz/` orphaned since 2026-07-22, each holding a
stray `.stignore`.
*Fix:* route `detect_blank_scores.py` and `liveness.py` through
`profile_paths.output_dir()`; iterate `profile_paths.sync_roots(name)` in the
teardown (and assert on it in the test — the leak sits next to a real coverage
gap, since nothing currently verifies the other three roots were created);
delete the four empty pre-migration directories and the three residue ones.

---

### Tier 1 — blockers and near-blockers with real work behind them

**B13. Knowledge-base durability: 17+ truncating writes, no backup, no recovery,
no conflict awareness.** MAJOR (compound blocker) · goals 1, 2 · one helper +
call sites + a policy decision.
Merges `P8F8` + `P8F9` + `P8F10` + `P6F2` + `P6F7` + `P4F6`.
`grep -rn "os.replace\|os.rename\|tempfile\|NamedTemporary" scripts/*.py`
returns **nothing** — there is no atomic-write helper in this codebase and no
call site implements one by hand. Measured: `open(path,"w")` truncates to 0
bytes at open, before any work happens.
- `score_keeper_gems.py` rewrites the 844-row / 658 KB keeper bank in place
  every 5 bullets — ~170 truncate windows across a multi-hour run (`P6F2`).
- `retire_rewrite_queue.py:79` truncates the only copy of the *active* queue,
  and its `extrasaction="ignore"` against a hardcoded 19-column header silently
  deletes any column upstream adds (`P6F7`).
- `bullet_feedback._ensure_schema()` is the widest window: read all, close,
  reopen `"w"`, re-serialise (`P8F8`).
- `jd_manager.save_checkpoint` is non-atomic, `load_checkpoint` catches the
  resulting `JSONDecodeError` and returns `{}` — indistinguishable from "no
  checkpoint," so the next run silently re-spends the entire pipeline. And
  `output/<profile>/` is a Syncthing sync root, so a `.sync-conflict-*`
  checkpoint is an outcome nothing anticipates (`P4F6`).
- **No recovery path exists.** Git: no (B11 / commit `261047e2`). `.bak` or
  snapshot: none. Syncthing: worse than nothing — truncation propagates, and
  file versioning is off unless configured by hand (`P8F9`).
- Nothing in the codebase knows `.sync-conflict-*` files exist. The *dangerous*
  version of this is absent — `KB_ALLOWLIST` is an explicit filename list, not a
  glob, so a conflict copy is never ingested into the builder's context — but
  `doctor`'s KB check is existence-only and passes a zero-byte conflicted
  `bullet-bank.md` (`P8F10`).
*Fix, in order:* (a) one `atomic_write` helper, applied at all 17+ sites plus
`save_checkpoint`; (b) log a corrupt checkpoint instead of returning `{}` —
worth having *before* (a); (c) a rotating pre-run snapshot of the KB; (d) a
size/mtime sanity check plus a `.sync-conflict-*` sweep in
`check_kb_allowlist()`, so the place users already look reports both this and
(a)'s aftermath.

**B14. A job posting can dictate the contents of the cover letter Morgan
sends.** BLOCKER · goals 1, 2 · medium.
Merges `P8F1` + `P8F3` + `P8F4`, per `P8`'s own Phase 9 instruction.
Proven end to end: a payload appended to a JD's `description` produced a real
rendered PDF whose first paragraph claims *"10 years of professional Rust
systems programming experience and led the Rust rewrite of a distributed
payments ledger at Stripe (2019-2024), cutting p99 latency 92%."* The model did
not paste it — it **wove** it into the argument ("This technical foundation,
combined with…"), so the fabrication is not visually separable from real
content. `validate_coverletter.validate()` checks forbidden phrases, paragraph
count, and third-person slips; there is no factual-grounding check of any kind.
Any JD source Morgan didn't hand-type — `scan_jobright`, `scan_linkedin`, all 24
board scanners — is a delivery channel.
**The fix pattern is already in the repo.** `P8F2`: the same payload was
*resisted* by the resume path, because bullets are mined from the bullet bank
and the builder is constrained to that corpus. Grounding beat prompt-level
pleading, in this codebase, on this payload.
Two layers, both needed:
- **Grounding (primary):** give the cover letter a corpus constraint analogous
  to the bullet bank, and add a KB-traceability check to
  `validate_coverletter.py`.
- **Delimiting/hierarchy (defense in depth, all 7 call sites —
  `orchestrator.py:2147, 2235, 2286, 2326, 2442, 2575, 2704`):** every JD-bearing
  call is `f"=== JOB DESCRIPTION ===\n{jd_text}"` — **opening marker only**, so
  the JD can forge its own boundary (which is exactly what the payload's
  `=== END JOB DESCRIPTION ===` did) and can forge the *other* sections too
  (`=== RESUME JSON ===`). No prompt in `resume-engine/prompts/` contains any
  instruction-hierarchy language — grepping all 12 for `ignore` / `untrusted` /
  `do not follow` / `data, not` returns nothing. `read_jd_text()` is a metadata
  filter, not a sanitiser, and its docstring is honest about that; the gap is
  that nobody built the second half.
*Reported honestly, from `P8F4`:* the **numeric** attack failed — `fit_score`
came back 3.65, no subscore maxed. The 1–5 structured output plus
`temperature=0.0` held. The **prose** fields, which have no structure to hold
them, did not. Structure is load-bearing here; use more of it.

**B15. Every PDF depends on a stray `node_modules` in the home directory.**
BLOCKER · goal 1 · small, but blocked on installing `npm`.
`P4F1` + `P1 Corrections` + C2. This repo has no `node_modules/`. Rendering
works only because Node's resolution walks up to `/Users/morganescott/` and
finds an unrelated Playwright install. Three consequences: `rm -rf
~/node_modules` breaks every PDF this tool produces; **on any other machine —
including the second Syncthing machine — this fails immediately**, since sync
carries data and deliberately not code; and the version actually loaded is
1.60.0, which does not satisfy the declared `^1.61.1`. The documented remedy
cannot be run: `npm` is not on PATH (`P1F8` — Node is a standalone
`/usr/local/bin/node` with no npm sibling; npm exists only under `~/.nvm/...`).
*Fix:* install npm → `npm install` in the repo → confirm
`require.resolve('playwright')` points inside the repo. Then make the failure
loud: resolve Playwright explicitly relative to the repo and fail with an
actionable message rather than silently accepting an ancestor directory.

**B16. Onboarding's false-green chain: a failed ingestion is recorded as "done"
and can never be retried.** BLOCKER for goal 3 · small.
Merges `P1F1` + `P1F2` + `P1F3` — one causal chain, three edits.
Observed on a real fresh profile with no API key: a 403 scrolls past, exit code
0, checkpoint written `"status": "done"` with `"work_experience": []`, and the
progress table reports **`Phase 0: ('Up to date', '1 document(s) processed')`**.
Nothing was extracted. And it is **sticky** — `run_ingestion()` skips anything
marked `done`, so re-running after fixing the key attempts no HTTP call at all.
The only escapes are `--force-overwrite-clean-bank` (exposed nowhere) or
deleting `checkpoint.json` by hand.
The wizard walks the user into it: `_collect_secret_now_or_later()` warmly
offers to add the key "later" and returns `False`; **both call sites discard the
return value** and immediately run the step that needs it. "Later" means about
four seconds.
And step 0.5 has a documented hard dependency on step 0 in its own body comment,
with nothing enforcing it — pick "0.5 Set Up Profile" first (an entirely
reasonable read) and `generate_tag_taxonomy()` makes a **real, paid** Gemini call
against an empty achievements string, then reports "Up to date." A second false
green on top of the first.
*Fix:* (a) checkpoint the *outcome*, not the attempt — `"status": "failed"` with
a reason, counted as pending, retried next run; return a failure count so the
summary says "1 document failed (API key rejected)" instead of a row of zeros.
(b) Honor `collect_secrets()`'s existing `{"gemini_key_set": bool}` return and
stop before the pipeline. (c) Gate `_run_phase05()` on `_phase0_status()` and
render dependent steps as visibly locked — the status table is already there.

**B17. "Pipeline complete!" is printed for a PDF that does not exist.** MAJOR ·
goals 1, 2 · small.
`P4F2`. This is `ResumeDesignSystem.md:57`'s explicit guarantee, and **it does
not hold** — captured from a real test run, the log prints "Could not parse
generated PDF … No such file or directory" and then `✔ Pipeline complete!`.
Downstream that success is not cosmetic: `run_pipeline` moves the JD to
`completed/`, logs `mark_completed`, and appends a tracker row with
`has_pdf=bool(output_paths.get("pdf"))` — the *path string*, always truthy,
never a check that a file exists. The user is told a resume exists, the JD leaves
the queue, and the tracker records a document that was never written.
Root cause: `validate_pdf_text()` returns two categorically different things
through one channel — soft advisories and hard "the PDF is missing" errors.
*Fix:* split the result classes (raise, or return `(fatal, advisories)`); gate
the success print and `_output_paths` on `os.path.exists(pdf_out)`; make
`has_pdf` stat the file.

**B18. Nothing verifies JD-keyword coverage of the finished resume.** MAJOR ·
goal 2 · medium. **Architecture gap, no owner.**
`P3` Handoff (H16), never picked up. Keyword placement against the JD is the
tool's core value proposition. `validate_resume.py` checks lengths, title case,
verb uniqueness and banned words — every check in it is a *copyeditor's* check.
To the plan's question — does it catch what a real ATS would reject? — `P3`'s
answer is **no**, and the two things an ATS actually rejects on (keyword coverage
and text-layer parseability) are checked nowhere. B1/B9 close the parseability
half. This item is the other half: a coverage check comparing the extracted JD
keywords against the finished resume, reported before the pipeline claims
success.
**Phase 10 answers the plan's question — yes, `ats_match.yaml` is meant to be
this check, and it is wired to nothing.** `critique_resume.md:25` and `:86-91`
place it in exactly that role; no Python file loads it (B49). Even attached it
is only half the check: pure weighting (`exact_match: 1.0 / semantic_match: 0.7
/ partial_match: 0.4`, section multipliers, a `-25` hard-requirement penalty)
with no keyword-extraction step, and `extract_keywords.md`'s output is not
routed to it. Its own comment (`:23-27`) admits the archetype weights are "a
first-pass guess" to be tuned "based on what critique_resume.md actually flags
over time" — a feedback loop that cannot close while the file never reaches the
model. *So this item stays open as written*: the coverage check has to be built,
and `ats_match.yaml` supplies its weights, not its logic.

**B19. `workday` fires ~100 unthrottled POSTs, blows the parent timeout, and
returns nothing. Every run.** BLOCKER (for that source) · goal 1 · small.
`P7bF1` + `P7bF2` + H32. Measured live against NVIDIA: 94 seconds, ~100
back-to-back POSTs, 2000 jobs collected — and the Python caller kills it at
`NODE_TIMEOUT_SECONDS = 30`, while `run_provider.mjs:62` only writes stdout
*after* the full array is built. **100% of collected jobs discarded.** The user
sees "no jobs"; the target saw 30 seconds of unthrottled API traffic for
nothing, on every scan, for every Workday company — and Workday is one of the
seven ATS providers in the recognition table, so every tracked Workday company
silently contributes zero. Secondary: `const limit = data?.limit ?? 20` uses
`??`, so a board returning `limit: 0` with non-zero `total` gives `offset += 0`
— an infinite POST loop bounded only by the 30s kill. Same provider's pagination
`fetch()` never checks `res.ok`, so a 429 throws and discards the page-1 jobs
already in hand.
*Fix:* cap pages (`smartrecruiters.mjs:13` already does, at 50), add an
inter-page delay, route through `_http.mjs`, and either raise the budget for
this provider or emit what was collected before the cutoff. `workday.fetch()`
already receives `_ctx` and ignores it.

---

**B49. 14 of the 18 rubrics `critique_resume.md` requires are never attached,
and the guard against that cannot fire.** BLOCKER · goals 1, 2 · medium.
`P10F1` + `P10F2`. `critique_resume.md:14-37` lists 18 scoring files to "load
and apply"; `orchestrator.py:2698-2702` attaches exactly two
(`summary_score.yaml`, `top_third_score.yaml`) — not `profile.yml`, not
`style_rules.yaml`, not the other 14. **12 of the 16 files in
`resume-engine/scoring/` are read by no code anywhere in this repo.** The
prompt's 9-step sequence then orders steps that are impossible: Step 1 "Using
`professional_identity_score.yaml`", Step 2 "Run all 7 `alignment_checks` with
their `pass_threshold` values", Step 6 "use `ats_match.yaml`'s
`archetype_overrides`". What the model returns for steps 1–6 is invention
conditioned on a filename, and it feeds the recommendation-rewrite pass at
`:2763`. `critique_resume.md:39-40` anticipates exactly this ("If a file is
listed here but not attached, flag it as missing rather than proceeding") and
is inert: `flags` is the resume-issue channel the recommendation loop consumes,
and nothing on the Python side inspects it for a plumbing signal.
*Fix:* attach the rubrics' real content, following
`orchestrator.py:1686-1720`'s curation pattern rather than dumping them raw —
all 14 unabridged is ~80KB per critique call. **Ships with B50 or it buys
nothing.**

**B50. `ResumeCritiqueSchema` cannot hold what the critique prompt computes.**
MAJOR · goal 2 · small, but coupled to B49.
`P10F4`. The schema (`orchestrator.py:901-918`) is 4 ints + 4 string lists. The
prompt names these outputs with no field to return them in: `primary_identity`,
`secondary_identity`, `tertiary_identity`, `competing_narratives`,
`unsupported_positioning`, `recruiter_takeaway`, `strongest_alignment`,
`weakest_alignment`, `ungrouped_skills`, `unsupported_skills`,
`archetype_mismatch`. Structured output means the surplus is never generated
rather than truncated with a warning. Fixing B49 alone would attach the
rubrics, evaluate them, and discard the results at the schema boundary.
*Fix:* extend the schema alongside B49, and add the hard-failure/threshold
field B51 needs.

**B51. No threshold in any rubric is implemented anywhere.** MAJOR · goals 1, 2
· small once B50 lands.
`P10F5`. `reject_if.score_below` appears in 5 `scoring/` files;
`pass_threshold` in `resume_cohesion_score.yaml` and
`professional_identity_score.yaml`; `ats_match.yaml:15-18` defines
excellent/good/weak bands; `summary_score.yaml:15-21` defines 5
`hard_failures`. `grep -rn "reject_if\|score_below" scripts/` returns nothing
outside `scripts/archive/`. The critique's four scores are printed
(`:2716-2720`) and stored; only `recommendations` and `distinctive_moments`
re-enter the pipeline. **A resume can score 10/100 on every dimension and
ship.** Concretely: `P10F9` hand-scored the shipped AbnormalAI Summary at
≈53/100 against `summary_score.yaml` — a rubric that *is* attached — and the
pipeline could not tell 53 from 85.
*Fix:* either wire a gate on the critique scores, or delete the `reject_if`
blocks. Leaving them is how the next reader concludes the scores mean
something.

---

### Tier 2 — majors, moderate effort

**B20. Embedding and clustering can silently misalign the bank.** MAJOR ·
goal 2 · small. Merges `P6F4` + `P6F5` + `P6F6` + H26.
Checkpoints resume by *index* with no verification the input is unchanged — edit
the bank during a rate-limit pause (exactly what a multi-hour stall invites) and
row *i* of the matrix stops corresponding to bullet *i*, permanently and
silently. `cluster_bullet_bank.py` is one line from catching this: it persists
`total` and never reads it back. `embed_batch` never checks it got as many
vectors as it sent, and `.get("embeddings", [])` means a response with no
`embeddings` key contributes zero rows against a recorded end index. And nothing
detects a stale `.npy` against a changed bank — the `.meta` sidecar records
enough to (`model`, `dim`, `rows`, `csv`) but nothing verifies it; the only
safeguard is a docstring saying "re-run this script," which is precisely the
tribal knowledge goal 3 exists to eliminate.
*Fix:* store a SHA of the bullet-text column in both checkpoints and in `.meta`;
discard on mismatch; `if len(vecs) != len(texts): raise`. **Enforce the `.meta`
check at `orchestrator.mine_bullet_bank()`'s read of
`bullet_vectors_ge2_d768.npy`, not only at write time** (H26). The robust
pattern is already in the repo — `audit_bullet_bank.py:56-69` resumes by bullet
*text*, not index, and is immune.

**B21. Liveness subprocess lifecycle: no timeout, fake progress, orphaned
children, lost results.** MAJOR · goal 1 · small. Merges `P7F2` + `P7F3` +
`P7F4` + `P7F11` + `P4F8`.
No `timeout=` on the `subprocess.run`, and downstream `chromium.launch()` has
none either, so the ceiling is `candidates × ~16s`, unbounded, inside one
blocking call — a 100-JD queue is a ≥27-minute call. The progress indicator
*cannot* work as written: `subprocess.run(stderr=PIPE)` buffers the whole stream,
so the loop replays a finished transcript — and the Node side deliberately
writes `[i/N]` lines to stderr specifically to enable this. The user sees a rule,
then nothing, for minutes. When they kill it, the Node child survives:
CPython's `run()` deliberately does not kill on `KeyboardInterrupt` (bpo-25942),
assuming process-group delivery — verified, `kill -INT` and `kill -KILL` on the
Python PID both leave Node alive, still making outbound requests to employer
sites. *(`P7F4` also verified what is **not** broken: Chromium is not separately
orphaned — Playwright's browser watches its parent pipe and self-terminates.)*
Finally, `browser.close()` is not in a `finally`, so any throw outside
`checkUrlLiveness`'s own catch discards **every result collected so far** — a
90-JD run failing on JD 89 returns nothing.
*Fix:* `Popen` in `try/finally` with `kill()` + `wait()`; iterate `proc.stderr`
line by line; `timeout=` sized from candidate count; explicit
`chromium.launch()` timeout; `browser.close()` in `finally`. Same class:
`generate-pdf.mjs`'s two `subprocess.run` calls have no `timeout=` either, and
`page.evaluate(() => document.fonts.ready)` has **no default Playwright
timeout** — a font that never settles hangs forever with `capture_output=True`
swallowing every hint (`P4F8`). Wrap it in `Promise.race` and add `timeout=180`.

**B22. TUI tables are unreadable below ~120 columns.** MAJOR · goals 3, 4 ·
small. `P2F4` + `P0 §3` + `P1F7` (see C4).
At 80 columns the *column headers themselves* truncate (`Recom…`, `Compa…`,
`Liven…`); at 100 they still do. Nine columns, no `no_wrap`, no width ratios, no
priority ordering, so Rich divides the deficit evenly and eats the headers. 80
and 100 are ordinary widths; the design currently works only at 160.
*Fix:* fixed widths for `#`/`Score`/`Posted`, `Title` absorbs the remainder,
drop `Last Liveness` + `Follow-up` below ~110 columns rather than shrinking
everything past legibility. **Also close H5:** re-test under
`RESUME_BUILDER_ICONS=unicode`, whose fallback set contains 4 double-width emoji
and 5 ambiguous-width glyphs (`P1F7`) — an independent alignment breaker that
lands only on the stranger's path, and that additionally defeats the theme,
since emoji carry baked-in color and ignore ANSI foreground. Replace those with
narrow U+2xxx symbols from the `✓ ✗ ⚠ ⚙` family already in use.

**B23. The palette has no contrast contract; the selection pointer is the least
legible element in the app.** MAJOR · goals 3, 4 · small. `P2F2` + `P2F9`.
Measured WCAG across all seven tokens on both backgrounds: **no token passes AA
on both**, so the palette silently assumes a dark terminal without saying so.
The sharpest consequence: `BRAND_ACCENT #673ab7` is the single lowest-contrast
color in the system on the background the palette actually assumes (**2.27:1**),
and it drives `QUESTIONARY_STYLE`'s `pointer`/`highlighted` — the cursor showing
which row you're on — plus `TABLE_HEADER_STYLE`, so every column header in every
table inherits it. `WARNING #f5c542` at **1.62:1 on white** is effectively
invisible on a light terminal. The banner's gradient endpoints are only 2.96:1
from each other, so "BUILDER" is measurably dimmer than "RESUME."
*Fix:* move `BRAND_ACCENT` light enough to clear 4.5:1 on dark (~`#a583e0`–
`#b39ddb`), or reassign the pointer/header role to `BRAND` (6.73 on dark).
**Then immediately fix `P2F9`:** the six brand hexes are hand-copied into
`dashboard/internal/theme/resumebuilder.go` with comments claiming they match
their Python constants. Changing `BRAND_ACCENT` makes those comments lie and
nothing detects the drift — emit the Go block from `theme.py`, or have both read
one JSON. Low effort, and it becomes load-bearing the moment this item ships.
*(`P5 #5` and `P2`'s handoff both note the honest long-term fix is two ramps
selected by background, which the Go side already implements correctly.)*

**B24. The resume and cover letter are visibly not one document family.** MAJOR ·
goal 4 · small. `P2F5` + `P2F6` + `P2F7`.
The two halves of one application to one recruiter disagree on their most
prominent element: `h1` is **42pt** on the resume and **32pt** on the cover
letter, and `ResumeDesignSystem.md:113` says 32 — so the resume is 31% larger
than its own design system and there is no way to tell which is stale. The cover
letter's contact separator is `#000000` against the spec's "`#9aa3af` only."
Body size and line-height differing is defensible; the wordmark changing size is
not. Also: "Career Note:" embeds a **Type3 synthesized font** (empty BaseFont)
because `.career-note` is italic and `.career-note strong` is weight 800 with no
ExtraBold-Italic face declared — the exact failure the template's own comment
documents baking static instances to avoid. Text still extracts (verified), so
it's typography plus modest residual risk, and **one edit fixes both it and the
spec**: drop `font-style: italic` from the `strong`, which
`ResumeDesignSystem.md:330-331` already calls for.
*Fix:* pick one name size and put it in both templates (updating the design
system if 42 is intended); separator to `#9aa3af`; drop the italic on the strong.
Do **not** pad page 2 — see B25.

**B25. Three employers the design system places on page 2 are missing from the
rendered resume.** MAJOR · goals 2, 4 · **DIAGNOSED 2026-08-05 by `P11` —
superseded by B60 (employers) and B61 (banner counter). Kept for the trail; fix
those two, not this.**
`P2F7` + `P2`'s Handoff (H9), never picked up by Phase 3 (already run) or Phase
4 (didn't address it). Page 1 runs dense to its last line (0.86in bottom
whitespace); page 2 holds only Training & Certifications and Education and stops
with **7.33in of free vertical space**. `ResumeDesignSystem.md:130-133` places
Element 8 / Strategy LLC, VML, and Callahan Creek on page 2 and they are absent.
With that much room this cannot be space-driven trimming — either the trim logic
is over-firing or those employers are dropped upstream. `P2` deliberately did not
propose a CSS fix, because padding it out visually would paper over the content
question. **First action is diagnosis, not a fix.** Related and also unowned:
`get_completed_jds()` returns 0 against the live `morgan` profile, so the banner
advertises "0 Resumes Customized All-Time" on a tool that has demonstrably
produced resumes (H10) — either the counter or the move-to-completed step is
wrong.

**B26. The board-scanner layer has no rate limiting, retry, backoff, or honest
identity.** MAJOR · goals 1, 5 · medium. Merges `P7bF3` + `P7bF7` + `P7bF4`.
`grep -rn "retry\|backoff\|Retry-After\|429" board-scanners/` returns **nothing**.
`_http.mjs` is a fetch wrapper, not a policy layer: one global 10s timeout no
provider overrides, no inter-request delay on any of the three multi-request
providers, and `hackernews.mjs` fires **60 simultaneous** requests via
`Promise.all` with no chunking. Everything else is polite by luck — 18 of 24
providers make exactly one request per run, which is the only reason nothing has
been blocked. `websearch`'s own rate limiter is **dead code across the subprocess
boundary**: the queue is module-level state in a process that handles one query
and exits, and it's tuned to 100ms against a documented free-tier limit of
1 req/sec — 10× over the plan its own docstring tells the user to sign up for.
Identity: the default UA is `Mozilla/5.0 (compatible; career-ops/1.3)` — it
leads with the browser-impersonation prefix *and* names a different project at a
version this repo doesn't have, so an operator who wants to allowlist or contact
this traffic cannot. `workday.mjs:66` sends a full Chrome 124 fingerprint. This
is the same split `P7` found on the Python side (`scan_boards.py:239` honest vs
`scan_jobright.py:19-27` fake Chrome); this layer inherits both conventions and
picks neither. *(`usajobs.mjs:28` sending the user's email as UA is correct —
that's USAJOBS's documented auth requirement.)*
*Fix:* retry-with-backoff + `Retry-After` handling + per-provider
`timeoutMs`/`minGapMs` in `_http.mjs`; make `makeHttpCtx()` the only route to
the network; `resume-builder/1.0 (+<repo url>)` as the shared default UA; delete
`websearch`'s queue and pace on the Python side instead.

**B27. Scan failures are indistinguishable from "no jobs today," at both
layers.** MAJOR · goals 1, 3 · small-medium. Merges `P7F1` + `P7bF8` + H29 + H32.
**Python side:** `_ScanWarningCollector.emit()` appends only records carrying
`scan_warning=True` and drops everything else — and attaching any handler to the
root logger takes over from Python's last-resort handler, so plain
`logging.error` calls vanish entirely. Runtime-proven: 0 captured, nothing
printed. Destroyed messages include the only actionable guidance the subsystem
has — "No live li_at cookie found. Log into LinkedIn in Chrome," "JobRight cookie
may be expired," "LinkedIn scraper run failed: `<exception>`." The user sees
`linkedin  0 fetched` and cannot learn why. The class docstring asserts the exact
opposite of what it does.
**Node side:** every failure mode exits 1 with empty stdout, and the Python
caller collapses non-zero exit, timeout, and invalid JSON into `return []`.
Quota exhaustion is byte-for-byte identical to a quiet Tuesday. *(Good news
worth preserving: the stderr text itself is genuinely informative, and the
key-gated providers throw rather than returning `[]`, so `P7F1`'s shape does not
reproduce there. One residual silent path: the twelve providers using
`Array.isArray(json?.jobs) ? json.jobs : []` return `[]` on a 200 carrying an
error object.)*
*Fix:* fall through to a real handler for uncollected records (or route the two
scanners through `_scan_warning()`); write a JSON error envelope to stdout on
failure — `{"error":{"kind":"auth"|"quota"|"network"|"config","message":"…"}}`
— parse it in `scan_boards.py`; and give `render_scan_report` a place to put the
reason (H29), since fixing the logging alone doesn't help if the renderer has
nowhere to display it.

**B28. `validate_resume.py` inspects 9 of 14 bullets and never looks at
`career_note`.** MAJOR · goal 2 · small. `P3` MAJOR 5.
The shipped resume returns **0 violations** while containing three pronouns in
`career_note` ("**I** took time in 2024–25… **I'm** excited to return") against
`tailor_resume.md:213`'s rule that the Why section is "the ONLY section where
pronouns are allowed" — so the document ships with a third-person summary and a
first-person career note, two voices on one page. And `_all_bullets()` iterates
`EXPERIENCE` only, so **5 EDUCATION bullets get no length, forbidden-phrase,
verb-uniqueness, or pronoun check at all.**
*Fix:* include `career_note` in the pronoun check and EDUCATION in
`_all_bullets()`. (The deeper "it checks style, not ATS" critique is B18.)

**B29. The Summary is generic by explicit instruction, and its own quality rule
is unenforced.** MAJOR · goal 2 · small. `P3` MAJOR 4 + `P3F8`.
Four consecutive sentences of identical shape — `[Verb]s [abstract noun phrase]
to [abstract outcome]` — interchangeable with any competent candidate's. That is
not model laziness: `tailor_resume.md:67` supplies "Specializes in…" /
"Transforms…" as exemplars, and the output's second sentence begins literally
"Specializes in…". The same line requires "1–2 most relevant proof points
(metrics or scope, not adjectives)" — measured: **zero** metrics in sentences
2–5. Nothing checks it.
The contrast proves the mechanism: bullets in the same document are concrete
("Recovered $3M+ in stale Salesforce pipeline…") because they go through the
voice-anchor-fed audit path. `P3F8` traced the plumbing — voice-anchors reaches
the bullet audit and the cover letter, reaches the builder **diluted** (1 of 19
undifferentiated KB files in a ~105k-token blob, with no instruction anywhere in
`tailor_resume.md` saying what it's for), and **does not reach Step 5 critique
or Step 5.5 apply at all**. The two stages that most directly rewrite the Summary
are voice-blind. The field with the most latitude is the flattest thing in the
document.
*Fix:* replace the exemplars with a requirement for one concrete checkable
specific; add a `validate_resume.py` check for ≥1 metric or named scope beyond
the years-of-experience figure; pass voice-anchors to the critique and apply
calls, and tell the builder what the file is for.
*Related, and cheap:* `P3F6` — the resume says "129 Outreach sequences," the
cover letter says "over 120." `129` is throughout the KB; `120 sequences`
appears nowhere. Nothing validates consistency *between* the two documents; they
are separate calls with no cross-check. And `P3F7` — the cover letter opens
"I am writing to express my interest in…", with three `I am [adjective] to`
constructions in three paragraphs; `tailor_resume.md` has a BANNED-words list
and a forbidden-openers rule, `tailor_coverletter.md` has no equivalent.
**Phase 10 answers the plan's question — yes, `summary_score.yaml` already
encodes the rule, and it is one of only two rubrics actually attached.** Hand-
scored against the shipped AbnormalAI Summary: `relevance_to_jd` ~15/30 (opener
says "Campaign & CRM Strategist" against a Content Strategist JD →
`no_target_role_signal`), `specificity_and_evidence` ~8/25 (**zero platforms
named**, despite Outreach.io and HubSpot being verified profile tools),
`role_alignment` ~10/20, `credibility` ~13/15, `readability` ~7/10 —
**≈53/100**, with `generic_professional_summary` arguably tripped. The rubric
independently reproduced `P3` MAJOR 4. The failure is downstream: the rubric
declares 5 `hard_failures` and `ResumeCritiqueSchema` exposes
`summary_alignment_score: int` and nothing else, so 53 and 85 are the same
object to the pipeline (B50, B51). *Implication for the fix:* the missing piece
is not a new rule — it is a return path and a gate. Also see B53, the diverging
banned-word lists.

**B30. `voice-anchors.md` mostly *describes* the voice instead of demonstrating
it.** MAJOR · goal 2 · small (and it feeds B29). `P3F8b` + `P6` (verified sound).
~70% of the file is third-person paraphrase ("Describes agency internship
experience; emphasizes creativity…"), which teaches a model nothing. The actual
signal is confined to the `>` blockquotes and is excellent and unmistakable —
*"I've been in WYSIWYG editors since the Geocities and Angelfire days, back when
your cursor sparkled and your background auto-played MIDI files."* None of that
register survives into either generated document. Root cause is upstream in
`build_voice_anchors.py`, which projects `application-answers-index.csv` into
thematic summaries. **`P6` verified the file regenerates byte-for-byte from the
script (4070 bytes in, 4070 out)** — so this is a design choice in the
projection, not drift, and it is safe to change the projection.
*Fix:* make the output mostly verbatim specimens. Note `P6 #9` — the script is
reachable from no menu or CLI, so `voice-anchors.md` has **no automated
regeneration path**; whoever changes it must also wire it up (see B34).

**B31. The stranger's setup path has no CLI entry point and no packaging.**
MAJOR · goals 3, 5 · medium. `P1F6` + `P1`'s step table + `P5 #6`.
`cli.py` registers eleven commands and **none of them set anything up** —
onboarding exists only inside the interactive menu, so `resume help` (a natural
first move) lists nothing relevant, setup cannot be scripted or documented as a
copyable command, and the only way in costs ~20–25s of banner (B2). Counting
discrete actions from `git clone` to one finished PDF: **~22, four of which
leave the tool entirely**, against roughly four for the web platforms this is
measured against. `P1` is explicit and fair that the gap is not itself a defect —
steps 13–21 are what make the output non-fabricated — but **steps 1–11 are pure
setup tax and are where the compression lives.** No `pyproject.toml` or
`setup.py` exists; both `uv tool install` and `pipx` need one with a
`[project.scripts]` table, and adopting it is additive metadata over the existing
`requirements.txt`, not a replacement for the venv dev flow.
*Fix:* `resume bootstrap` aliasing `bootstrap_menu.run_bootstrap_menu()`, listed
in `HELP_ENTRIES` and named in README's Setup section; plus one
`pyproject.toml` + entry point wrapping `cli.py:main()`.

**B32. `resume doctor` tells a correctly-fresh profile it has 2 problems.**
MAJOR · goal 3 · small. `P1F4` + `P1F8` + `P1F9` + `P1F14`.
Doctor is the tool a stranger reaches for to answer "did I set this up right?"
On a brand-new profile it answers "2 problem(s) found" and prints a 19-line wall
of truncated filenames, with the actual instruction — *run bootstrap* — as the
last clause of a sentence that opens with a warning about silently shrunk
context. Plus: `check_node()` verifies `node` but nothing verifies `npm`/`npx`,
while both Playwright fixes prescribe them (**this machine is the failure case**
— see B15); and `check_venv`'s detail line hardcodes `"ready to use"`, so a
missing venv renders as `.venv/ missing, ready to use` while `passed=False`.
*Fix:* detect the unbootstrapped case first and collapse it to one line
("Profile `x` isn't set up yet — run `resume` → New User? Start Here! (0 of 19
knowledge-base files present)"), keeping per-file detail for the genuinely
*partial* case; check `npm` alongside `node` and make the Playwright fix
conditional on it; build the venv detail from the same booleans as the verdict.
Also `P1F14`: README runs steps 1–7 then jumps to "take it for a spin" — add
`resume doctor --skip-tests` as step 8, "confirm the install before you spend an
API call."

**B33. The Nerd Font default fails silently and is undiagnosable from inside the
tool.** MAJOR · goal 3 · small. `P1F5`.
`theme.py:86` defaults to Nerd Font glyphs and deliberately "fails toward the
enhanced default" on an unset or typo'd env var. A repo-wide grep finds
`RESUME_BUILDER_ICONS` in **exactly one runtime code path — its own definition.**
No help text, no doctor check, no menu hint, no error message mentions it.
A stranger without a Nerd Font sees a menu of tofu boxes and has one recovery
route: notice README step 6, filed under "Optional," and already connect it to
what they're seeing. `P1` is right that flipping the default to Unicode is also
wrong (it silently downgrades everyone, and font support genuinely cannot be
probed from a TTY).
*Fix — `P1`'s, and it's the right one:* on first launch in a real terminal,
print one sample row of each set and ask once; persist the answer in the
profile's config; never ask again; default to Unicode when there's no answer and
stdin isn't a TTY. Deterministic, needs no font introspection, and gives
`doctor` something real to report.

**B34. A stranger's first scan is unbounded, unfiltered, and browser-verified.**
MAJOR · goals 1, 3 · small. `P7F5`.
`run_scan(verify=True)` is the default *and the only mode the menu offers*, and
it runs liveness over **every** newly written JD with no cap and no confirmation.
The `scan_filters.yml` scaffold ships with `title_filter.positive: []`, and an
empty positive list means everything passes — permissive by design and correctly
documented, but it means a new profile's first scan writes *every* remote listing
from 17 aggregator boards into `jds/`, then sequentially opens each in a headless
browser. Each component is defensible alone; together, step one of a stranger's
workflow is a multi-hour hang producing hundreds of junk JDs.
*Fix:* cap or confirm the verify pass above a threshold; seed the scaffold's
`positive:` from `profile.yml`'s `target_roles.primary`.

**B35. Dedup re-walks the entire JD corpus once per candidate.** MAJOR (perf) ·
goal 1 · small. `P7F7` + H11 + H30.
`job_key_known()` is called once per candidate and each call `os.listdir`s four
directories and runs `compute_job_key()` — a file open and parse — on every file
found. Cost is `candidates × total_JD_files` file opens; on a mature profile
that's six figures of syscalls attributed to nothing the user can see, reading as
yet another hang on top of B34 and B21. `run_scan()` correctly hoists the
`JDTracker` out of the loop; the directory walk was not hoisted.
*Fix:* build the known-key index once per `run_scan()` and match in memory. Same
shape as B2 — `get_pending_jds()` parsing 1,144 files per `_stats_line_text()`
call still costs ~1s on every launch even after B2 removes 30 of the 31 calls
(H11).

**B36. Scanners write JD files with a null or empty description.** MAJOR ·
goal 2 · small. `P7F6` + `P7bF6`.
`_write_jd_file()` writes whatever the fetcher produced with no validation.
`scan_linkedin.py:184` falls back to `extras["backup_description"]`, which is
`None` whenever `_fetch_personalized_extras()` fails — and it fails *silently*,
logging at `logging.debug`, below the collector's threshold and discarded by B27
anyway. Result: `"description": null` with no trace of why.
`P7b` found the upstream source: **6 of 24 providers never emit `description` in
any code path** (`workday`, `smartrecruiters`, `recruitee`, `workable`,
`fourdayweek`, `websearch`), and `_types.js` doesn't document the field at all,
which is why the divergence went unnoticed. Those are exactly the paths producing
company-direct postings — so the highest-value listings arrive with no body text.
*Fix:* add `description`/`posted_at` to the `Job` typedef as
optional-but-expected; give the six a description source (`greenhouse.mjs:66-67`'s
`?content=true` trick already solved this for its own provider); and validate in
`_write_jd_file()`, recording a `_scan` metadata key (per CLAUDE.md's underscore
convention) and flagging sub-threshold postings in the scan report.

---

**B52. Four incompatible archetype vocabularies, terminating in a key that
does not exist.** MAJOR · goal 2 · medium.
`P10F8`. `profile.yml` uses job titles (`Lifecycle Marketing Specialist`);
`ats_match.yaml:28-56` uses job titles but includes `Customer Onboarding &
Implementation Specialist`, which is not a `profile.yml` archetype, so that
override can never match; `role_dna.yaml` uses snake_case
(`email_lifecycle`, `b2b_content_copywriter`, `marketing_ops_crm`);
`professional_identity_score.yaml` uses a fourth set (`marketing_ops`,
`enablement`, `lifecycle`, `copywriter`). No mapping table between any pair.
The chain then dangles: `professional_identity_score.yaml:386` says
`style_rules_archetype: string # maps to style_rules.yaml archetype_ordering
key`, and **`style_rules.yaml` has no `archetype_ordering` key** — its top-level
keys are `version, philosophy, writing_style, bullet_structure, verb_rules,
vague_verbs, verb_upgrades, forbidden_openers, forbidden_phrases,
punctuation_rules, metrics_rules, pronoun_rules, tool_mention_rules,
redundancy_rules, tagline, skills_section, ats_rules, layout_rules,
typography`. `critique_resume.md:52-53` makes every later step depend on
resolving that lookup. *Fix:* pick one vocabulary (`profile.yml`'s names are
the only user-authored set), and either add the `archetype_ordering` block to
`style_rules.yaml` or drop the concept from `professional_identity_score.yaml`.

**B53. Builder and scorer ban different words.** MINOR · goal 2 · one list.
`P10F9`. `tailor_resume.md:70` bans `passionate, driven, results-oriented,
dynamic, synergy, best-in-class, seeking opportunities, visionary`;
`summary_score.yaml:23-33` treats `results-driven, dynamic professional,
accomplished professional, highly motivated, dedicated professional, seasoned
professional, proven track record, strategic thinker, visionary leader` as
`buzzword_opener` hard failures. Neither is a superset: the builder may write
five phrases the scorer hard-fails, and the scorer permits three the builder
bans. Live today — `summary_score.yaml` is attached. *Fix:* one shared list,
sourced from the rubric.

**B54. The cover-letter path has no rubric at all.** MAJOR · goal 2 · medium.
`P10` staleness check. `resume-engine/scoring/` predates the cover-letter path
and nothing was added for it. `tailor_coverletter.md` and
`polish_coverletter.md` run with `style_rules.yaml` only — no believability, no
AI-risk, no specificity scoring on the document that is *more* prone to generic
AI voice than the resume is. Interacts with B9 (cover-letter PDF never
text-layer checked): between them the cover letter has neither a content gate
nor an output gate. *Fix:* smallest useful version is attaching
`believability.yaml` + `ai_risk.yaml` to the polish call — after B49 makes
`ai_risk.yaml` reachable at all.

---

### Tier 3 — minors, hygiene, and modernization

**B37. Truncated generations are treated as success and silently salvaged.**
`P4F9`. `finishReason == "MAX_TOKENS"` is accepted alongside `STOP`; the partial
JSON then fails `json.loads` and `_salvage_fields` regex-scrapes surviving
top-level pairs. The caller gets a well-formed dict it cannot distinguish from a
complete response, and `if not trimmed` passes on a truthy fragment. The salvage
behavior is defensible — what's missing is the signal. *Fix:* return
`finishReason` / a `truncated: True` flag in the usage dict, and mark salvaged
results.

**B38. Page count is a regex over raw PDF bytes, and a zero silently disables
the 2-page rule.** `P4F12`. Verified correct today against both shipped PDFs, so
this is fragility, not a wrong number — but `is_final = page_count is None or
page_count <= 2 or …` means a `0` short-circuits the trim loop *and* skips the
`> 2` guard, so **the entire 2-page enforcement switches off and a 4-page resume
ships**, silently. The regex depends on Chromium emitting an uncompressed page
tree. *Fix:* count pages from `pdf_out` with pypdf (already a dependency); at
minimum, treat `None` as a failure to verify rather than as "fine."

**B39. Log and diagnostic noise.** `P4F10` — network errors are reported as
`str(e).split()[-1]`, so a genuine offline failure prints `known')).` and
discards the diagnostic content; use `type(e).__name__` plus the first ~120
chars. `P4F11` — two unattributed pdfminer `FontBBox` warnings on every run
(`P0 §2a`, root-caused): one line,
`logging.getLogger("pdfminer").setLevel(logging.ERROR)` at module scope in
`validate_pdf_text.py`, and it's this module's warning to own since it's the only
caller. `P3`/H15 — `validate()` returns a bare list and the pipeline prints
nothing on success, so "0 issues" and "budget exhausted after 4 attempts" are
indistinguishable in the log; print the passing case explicitly.

**B40. The empty-string achievement-key warning.** `P0 §2b` → `P4` → Phase 1
(already run) → **orphan, H21.** `WARNING: unrecognized KU achievement key '',
falling back to first option.` prints twice for every recommendation application,
regardless of which recommendation. `P4` traced it: the enum is merged at
`orchestrator.py:2949` via `extra_schema_properties`, but the key *options* come
from the profile's bootstrap-written `profile.yml`, so a blank option is being
written into that file at bootstrap time. Needs an owner.

**B41. Multi-user credential and PII hygiene.** `P1F13` — `collect_secrets()`
short-circuits on `GEMINI_API_KEY` being exported in the shell and **never
writes the new profile's `.env`**, defeating the docstring's own stated goal
("two people sharing this checkout never share credentials"). This machine has it
exported, so a second person bootstrapping here is silently billed to Morgan's
key. *Fix:* prompt when the profile's own `.env` lacks the key; offer the shell
value as a default rather than assuming it. Pairs with B11. Also `P8F6` /
H37 — no `subprocess` call in the scanning or liveness paths passes `env=`, so
all 24 provider modules and every Chromium process run with `GEMINI_API_KEY` and
the JobRight cookie in their environment though none needs either; an explicit
`env=` allowlist makes the question moot. And `P7bF10`/H33 — `adzuna.mjs` puts
`app_key` in the query string; it doesn't leak through this layer's error
messages (`_http.mjs` reports status + body only), but any Python-side logging of
the invocation or URL would expose it.

**B42. Liveness and scan correctness minors.** `P7F8` — `--no-verify` leaves the
optimistic `_liveness: active` seed uncorrected, and the 24-hour recency check
then skips it, so a dead posting stays in the active queue for a day with a
persisted claim it was confirmed alive. `P7F9` — `LIVENESS_INPUT_PATH` is a fixed
`output/liveness_input_tmp.json`, bypassing `profile_paths` (CLAUDE.md's single
source of truth), so two profiles overwrite each other and the file sits outside
`sync_roots()`. `P7F10` — `_fetch_personalized_extras()` fires ~60 back-to-back
authenticated GETs carrying Morgan's real `li_at` cookie, entirely outside the
scraper's deliberate 5-second `slow_mo` pacing; **this is the one place in the
subsystem with genuine account-risk exposure**, on the account she job-searches
from, and a matching `time.sleep()` costs five minutes on a scan that already
takes longer. `P7F12` — report entries are removed by value, so two same-company
same-title postings drop the wrong row. `P7F13` — `expired_paths` returns
pre-move paths that no longer exist (today's only consumer works by
coincidence). `P7F14` — the liveness catch branch omits `code`, so every
navigation failure writes `code: undefined`, indistinguishable from a genuine
classification. `P7F15` — `go run` returns non-zero on interrupt, so quitting the
dashboard normally reports "Dashboard exited with an error (code 1)."

**B43. Board-provider minors.** `P7bF9` — `_recognition.mjs` has drifted from its
hand-mirrored Python copy in **both** directions: missing `recruitee` (so a
sweep-discovered Recruitee company can never be promoted to its direct-API
provider, the exact path a prior fix was meant to restore), and still listing
`bamboohr`/`jobvite`/`icims`/`jazzhr`, none of which have provider modules — a
promotion on one resolves to a missing file and exits 1. Better than syncing by
hand: have the Python side read the `.mjs` rules. `P7bF10` — `themuse` and
`himalayas` request a single unpaginated page (20 rows) and filter `search_term`
client-side, so both return **0 jobs whenever a search term is set**; both APIs
accept server-side filters, and `remotive`/`adzuna` already pass the term
through. `P7bF11` — `ashby` is the only provider with no output filter, so a
posting missing `jobUrl` is emitted with `url: ''`, and `url` is the dedup key.
`P7bF12` — doubled provider prefix in every error message
(`adzuna: adzuna: missing…`), affecting ten providers.

**B44. Bullet-bank hygiene.** `P6 #8` — `score_keeper_gems.py:45` loads a
project-root `.env` that does not exist; a no-op that works only because
`gemini_client.py` independently loads the right path, but it's a second wrong
source of truth for secrets in a file that makes API calls. `P6 #9` — four of the
15 scripts are reachable from no menu, CLI, or script; **`build_voice_anchors.py`
is the one that matters** (see B30). `P6 #10` — two scripts write
`hidden-gems.csv` with different schemas, harmless only because one is
unreachable. `P6 #11` — `ingest.py` is dead, hardcodes a path that doesn't exist,
imports `profile_paths` without using it for that lookup, and writes to
project-root `output/txt`/`output/json` (colliding across profiles, outside
`sync_roots()`). `P6 #12` — `audit_bullet_bank.py:111` writes exception text into
the `weaknesses` column, which `decide_action()` reads as a quality signal;
contained today because score columns stay empty, but the string persists.
`P6 #13`, `#14` — `tag_bullet_bank.py`'s 3-column restriction raises an unhelpful
`ValueError` on a richer CSV; `embed_bullet_bank.py`'s docstring claims 4s/~4min
against `EMBED_SLEEP = 20` (~20 min).

**B45. Shell, menu, and cosmetic residue.** `P1F10` — `printf '  %s\n' $names`
doesn't word-split under zsh (macOS default), so only the first profile is
indented; fires on exactly the shared-checkout scenario the function exists to
serve. `P1F11` — `resume()` calls `_resume_ensure_profile` unguarded; degrade it
to inert (see C3). `P1F12` — `did_something = True` runs unconditionally, so
backing out of an empty step 0 still fires the "what's next?" prompt. `P0 §3` —
confirming the JD picker with 0 selections returns to the main menu with no
feedback at all. `P2F8` — two hardcoded color leaks: `[yellow]` in `menu.py:848`
(a named ANSI color, the exact thing `theme.py:13-16` warns against) and
`"white"` as the tier fallback in `cli_art.py:289,331,356`. **Emoji sweep
residue** (see C6): `generate-pdf.mjs:123-125,150,199-201,211`,
`bootstrap_bullet_bank.py:352`, `check-liveness.mjs:41,74`, `ingest.py:82,93` —
`liveness.py` is already done.

**B46. Modernization.** `P5 #1` — pin `thinkingLevel` explicitly on the five
`gemini-3.1-flash-lite` call sites; the Gemma branch already makes a deliberate
choice, flash-lite rides an undocumented default that has already shifted once.
Trivial, and it stabilizes cost/latency. `P5 #2` — **instrument one run for
cache-hit token counts before building anything**; implicit caching may already
be capturing the audit loop's fixed rules-file prefix for free, which decides
whether explicit caching (32,768-token minimum, 90% discount, deterministic) is
worth the lifecycle work. `P5 #3` — Batch Mode is 50% off with ≤24h turnaround
and doesn't stack with cache hits; it fits unattended `resume run` sweeps and not
single-file mode or checkpoint-resume, so **the decision needs whoever owns
`orchestrator.py` to separate "calls a human is waiting on" from "calls inside an
unattended batch"** — not visible from outside the orchestration logic. `P5 #4` —
collapse three colorizers to two by routing the bare-`print()` call sites through
a shared `Console`; the questionary/Rich split is inherent, the `print()` branch
is not, and `colorize_icon_ansi()`'s own docstring flags itself as the
workaround. `P5 #7` — `rewrite_bullets.py:67`'s docstring example cites
`gemini-2.5-pro`, which shuts down October 2026. `P5`/H38 — fold the caching,
batch, and packaging items into `IDEAS.md` (Medium tier), since that file is the
living backlog and `phase-5-modernization.md` is a snapshot.
**Decided, no action:** keep both the Go dashboard and the Python TUI (`P5 #5`) —
porting either direction buys nothing; close the theme asymmetry instead (B23).
Structured output is already current (`P5 #8`).

**B55. The Playwright e2e scaffold is dead and points at the wrong site.**
MINOR · goal 5 · delete two files.
`P12`. `e2e/example.spec.ts` + `playwright.config.ts` are the unedited output of
`npm init playwright@latest` — both tests call `page.goto('https://playwright.dev/')`
and assert on that site's own title/heading, not anything this app renders.
`playwright.config.ts` has no `baseURL` and its `webServer` block is commented
out, so there is no path by which it was ever pointed at this repo. Verified
unreachable from every angle: `package.json`'s `"scripts"` is `{}` (no `test`
entry), `.github/` contains only `dependabot.yml` — no workflow ever invokes
`playwright test` — and `node_modules/` doesn't exist in this repo at all (see
B15), so `npx playwright test` cannot even resolve the `@playwright/test`
import today. `git log` shows exactly one commit touching either file
(`4984907c`), the same commit that added them. This is also the reason
`package.json` misleadingly looks like a test project: `@playwright/test` is
its only `devDependency`. Nothing in this app has a browser-navigable UI to
e2e-test in the Playwright sense — the "web" surface is a rendered PDF/HTML
file opened by Chromium as a renderer, not a page the app serves — so there is
no natural target to wire this up *to*.
*Fix:* delete `e2e/` and `playwright.config.ts`; drop `@playwright/test` from
`package.json`'s `devDependencies` (leave the `playwright` runtime dependency,
which `generate-pdf.mjs` genuinely uses to drive Chromium).

**B56. `dependabot.yml` is the unfilled template — it updates nothing.** MINOR
· goal 5 · a few lines.
`P12`. `.github/dependabot.yml:8` reads `package-ecosystem: ""` — the literal
empty-string placeholder from GitHub's default scaffold, never replaced with a
real value (`pip`, `npm`, `gomod`, etc.). An empty `package-ecosystem` fails
Dependabot's schema validation, so the one `updates:` entry present is inert;
functionally this file configures zero ecosystems. The repo actually has
three: `requirements.txt` (pip), `package.json`/`package-lock.json` (npm), and
`dashboard/go.mod` (gomod) — none is covered.
*Fix:* three `updates:` entries, one per ecosystem, each with its own
`directory:` (`/`, `/`, `/dashboard`).

**B57. `scripts/archive/` is confirmed dead — safe to delete.** MINOR · goal 5
· delete 5 files.
`P12`, closing the "confirm nothing imports them first" check `PLAN.md` asked
for. `grep -rn` across every tracked `.py` file for each archived module's
name (`backfill_cluster_ids`, `detect_blank_scores`, `fix`,
`merge_queue_to_cluster_map`, `rewrite_bullets_backup`) returns no import or
`archive/`-relative reference anywhere outside the files themselves. `P6 #9`'s
observation still holds and is now quantified: `scripts/archive/detect_blank_scores.py`
diverges completely from the live `scripts/detect_blank_scores.py` — different
purpose (rewrite-queue population vs. a blank-score report), different CSV
paths, different CLI surface — confirmed by direct diff, not just "differs."
*Fix:* delete the directory. Nothing in the fix pass depends on it.

**B58. `webdriver-manager` is an orphaned dependency in `requirements.txt`.**
MINOR · goal 5 · one line.
`P12`. `grep -rn "webdriver_manager"` across every tracked `.py` file returns
nothing — no direct import, and nothing else in `requirements.txt` requires it
transitively (`pip show webdriver-manager` lists no `Required-by`). Contrast
with `selenium`, also unimported directly but a genuine transitive dependency
of `linkedin-jobs-scraper` (`pip show linkedin-jobs-scraper` → `Requires:
selenium`) — that one earns its place; `webdriver-manager` does not.
*Fix:* remove the line; re-run `resume doctor` to confirm nothing regresses.

**B59. A board-scanner title filter silently cancels itself on one keyword.**
MINOR · goal 1 · one line.
`P12`. `profiles/morgan/board_scanner/scan_filters.yml`'s `title_filter` lists
`Curriculum` in **both** `positive` (index 47) and `negative` (index 210).
`scan_boards._passes_title_filter()` (`scan_boards.py:135-147`) checks
`negative` unconditionally after `positive`, and a negative hit always
rejects regardless of any positive match — verified by reading the function,
which has no precedence rule for an overlapping term. Any job title
containing "curriculum" (e.g. "Curriculum Strategist," a title shape that
fits several of the profile's own target archetypes) is therefore silently
dropped from every scan despite being listed as a wanted signal, with the
`positive` entry existing as dead weight. Lower-value, same file: 8 duplicate
entries within `positive` (of 104) and 3 within `negative` (of 332) — harmless
but sloppy.
*Fix:* drop `Curriculum` from `negative` (the profile's target roles include
enablement/education-adjacent titles, so `positive` is the intended list);
dedupe both arrays while there.

---

## 4. Ownership residue — the mechanical check

Enumerated the repo's tracked directories first, per the plan's explicit
instruction not to check only the six it happened to name.

**Tracked directories:** `.claude/`, `.github/`, `.vscode/`,
`ImprovementConcepts/`, `board-scanners/`, `dashboard/`, `docs/`, `e2e/`,
`fixtures/`, `profiles/`, `resume-engine/`, `scripts/`, `tests/`, plus 13
top-level files.

**`scripts/` is now fully owned.** 62 tracked files; 57 appear in a phase
ownership list (P1: 8, P2: 6, P3: 5, P4: 7, P6: 15, P7: 16), the remaining 5
being `scripts/archive/`. The `plan-gaps.md` finding of "~25 scripts owned by no
phase" has been fully closed by Phases 6, 7, and 7b. `board-scanners/` was closed
by 7b.

**Still unowned — reviewed by nobody:**

| Path | Files | Assessment |
|---|---|---|
| **`resume-engine/rules/*.yaml`** | 6 | **Real gap, goal 2.** `hard_failures`, `truthfulness_rules`, `style_rules`, `language_quality`, `verb_taxonomy`, `verb_intent_mapping` — these are concatenated into the audit loop's system prompt (`P5 #2` describes exactly this). Phase 3 owns `resume-engine/prompts/` only. **The rubric the bullet audit scores against was never read.** |
| **`resume-engine/scoring/*.yaml`** | 18 + README | **Real gap, goal 2.** `ats_match`, `believability`, `specificity`, `recruiter_score`, `summary_patterns`, `role_dna`, … — the scoring rubrics behind `evaluate_fit` and the critique. Given B3 (the evaluator sees no candidate context) and B29 (the summary rule is unenforced), these are exactly the files that would say whether the *rubrics* are sound. Unread. |
| **`e2e/example.spec.ts` + `playwright.config.ts`** | 2 | **Real gap, goal 5.** A Playwright test scaffold in no phase's list. `P4` measured 1,091 unittest tests and never mentions this; it is almost certainly an unrun stub, and `playwright.config.ts` is the only reason `package.json` looks like a test project. Decide: wire it up or delete it. |
| `dashboard/`'s non-visual Go code | ~all | `PLAN.md` scopes Phase 2 to "`dashboard/` (visual layer **only**)". Its tracker-parsing and data logic is unreviewed — the same carve-out shape that left `menu.py`'s onboarding logic unowned until Phase 4 claimed it. `P0 §5` exercised it at runtime with no defect, which is the only coverage it has. |
| `scripts/archive/` | 5 | Explicitly archived. `P6 #9` noted `archive/detect_blank_scores.py` differs from the live copy. Low value; recommend deleting rather than reviewing. |
| `.github/dependabot.yml` | 1 | Goal 5 adjacent; unreviewed. One-line check during B46. |
| `package.json` / `package-lock.json` / `requirements.txt` | 3 | Touched incidentally (`P4F1` read the Playwright pin, `P5 #6` noted no `pyproject.toml`) but owned by nobody as dependency manifests. Folded into B15/B31. |
| `profiles/morgan/board_scanner/*.yml` | 3 | Tracked config. `P7F5` reviewed the *scaffold's* behavior; the committed files themselves are unreviewed. Low risk. |
| `fixtures/sample_jd.txt` | 1 | The QA fixture every phase depends on. Read by 3 and 8; no owner. Immaterial. |
| `docs/superpowers/`, `ImprovementConcepts/`, `.vscode/`, `.hintrc`, `.claude/`, `IDEAS*.md`, `resume_example.pdf`, `rewrite_bullets_fixes.md` | many | Historical/editorial. `P5` scanned `IDEAS.md` and `ImprovementConcepts/` and correctly declared the latter out of scope. No action. |

**Disposition — all of the above is now assigned.** `PLAN.md` was amended
2026-08-05 with three follow-on phases, so nothing in this table is left
unowned:

- **Phase 10 — Scoring rubrics & rule files.** `resume-engine/rules/` (6) and
  `resume-engine/scoring/` (19). The only residue touching goal 2, and
  substantial. B3, B18, and B29 all ask questions those files answer, so Phase
  10 should run before those three are fixed.
- **Phase 11 — Unexplained artifacts & path residue.** Not an ownership gap but
  a diagnosis gap: the three orphaned handoffs below that no phase ever
  root-caused (H9, H10, H6 → B25 and the pre-profile path question).
  **Run 2026-08-05 — all three root-caused; see `phase-11-orphans.md`. B25 is
  superseded by B60/B61; H6 is now B62.**
- **Phase 12 — Remaining unowned residue.** `e2e/` + `playwright.config.ts`,
  `dashboard/`'s non-visual Go, `scripts/archive/`, the dependency manifests,
  `.github/dependabot.yml`, `profiles/*/board_scanner/*.yml`, `fixtures/`, and
  an explicit out-of-scope record for the editorial directories. Disposition per
  item: keep / wire up / delete / out of scope.

All three append their items to **this file**, continuing the `B<n>` numbering —
there is no second synthesis phase.

---

## 5. `PLAN.md` corrections — **applied 2026-08-05**

These were factual errors in the plan itself, surfaced by phases that could not
edit it or that ran after it was written. All five have since been applied to
`PLAN.md` and `phase-0-smoke.md`; the list stays as the record of what changed
and why.

1. **`PLAN.md:266-270`** — the raw `❌` at `liveness.py:211` is **already fixed**
   (commit `348fe628`). `P7F16`.
2. **`PLAN.md:242-245`** — `generate-pdf.mjs:211` is **not** "the last un-swept
   instance in the repo." At least four other locations remain. `P1F15`,
   `P6 #11`, `P7F16`, and `P4F13` (which found `generate-pdf.mjs` itself carries
   seven more emoji, not one). See B45.
3. **`PLAN.md:354-356`** — the Phase 6 instruction to "round-trip a messy input"
   through `ingest.py` / `normalize_resume.py` **is not executable and the
   pairing is a mistake**. `ingest.py` is dead with a hardcoded nonexistent path;
   `normalize_resume.py` is not an ingestion component at all — it post-processes
   the *builder's output* mid-run and never sees a user's resume. The underlying
   question is answered by `bootstrap_extractors.py`/`bootstrap_bullet_bank.py`
   (Phase 1's files). `P6`'s "Correction to the phase brief."
4. **`PLAN.md`'s Phase 9 residue-check wording** listed six directories by name,
   which is exactly what let `board-scanners/` go unowned through Phase 7. The
   wording was already amended to require enumerating tracked directories first;
   this run did that, and it is what surfaced `resume-engine/rules/`,
   `resume-engine/scoring/`, and `e2e/`. Keep the amended wording.
5. **`phase-0-smoke.md:26-33`** should carry an inline correction that the
   Playwright doctor warning is not a false positive (C2), so a later reader does
   not dismiss it again. Same for `phase-0-smoke.md:18-20` re C3.

---

## 6. Suggested execution order for the fix pass

1. **Tier 0 in one sitting** (B1–B12). One blocker, nine majors, roughly a
   handful of edits each. B1 alone repairs every document the tool has ever
   produced; B2 alone changes the entire first impression.
2. **B15 next**, because it gates verification of everything else — until `npm
   install` runs in the repo, no PDF fix can be proven on any machine but this
   one.
3. **B13 and B14** — the two compound blockers. B13 first if a KB write is
   imminent; B14 first if any un-hand-typed JD is about to be processed.
4. **B16, B17, B19** — then the remaining Tier 1.
5. **Diagnose B25 before touching page-2 layout** in B24. Three missing
   employers is a content bug wearing a whitespace costume.
6. Tier 2 by goal: B18/B28/B29/B30 for goal 2 (Morgan as a candidate),
   B22/B23/B24 for goal 4 (portfolio), B31/B32/B33 for goal 3 (strangers).
7. **Add the two regression tests `P4` names as highest-value** while B13 and
   B17 are open: a corrupt-checkpoint test, and a "PDF missing ⇒ pipeline must
   not report success" test. `P4`'s coverage table shows the pattern precisely —
   the code paths that *detect* trouble are well tested; the decisions made
   *after* detection are not pinned anywhere.
8. **Decompose `build_tailored_resume` while B5, B17, and B38 are open**, since
   all three edits land inside it. `P4` answered the plan's question with
   evidence: `orchestrator.py`'s 3,125 lines are "just large" (a seventh is flat
   Pydantic schemas, the helpers are already decomposed and separately tested),
   but **`build_tailored_resume` at ~614 lines is the real number** — seven
   sequential steps, four checkpoint save points, an interactive gate, and a
   nested trim loop. Findings B5, B17 and B38 all live in it, and that is not a
   coincidence: each step's error branch is 300 lines from the success print that
   contradicts it. The seams are already marked by its own `--- Step N ---`
   comments. Not worth a standalone refactor; worth doing while you're in there.

---

## 7. What the review found working — do not "fix" these

Consolidated from every phase's "verified as NOT defects" section, so the fix
pass doesn't spend on them.

- **No fabrication in the normal pipeline** (`P3F9`). Every quantitative claim
  in both shipped documents traces to a KB file. The `needs_personal_input`
  channel is genuinely good anti-fabrication architecture — it instructs the
  model to *refuse* rather than invent, and it is why B6 produced bland copy
  instead of invented copy. The guard held on fabrication even while the routing
  failed. (Caveated only by C7 and by `P3F6`'s "over 120" rounding.)
- **The resume path resists prompt injection** (`P8F2`) — because it is grounded
  in a corpus. That is the fix pattern for B14, already proven in this codebase.
- **No secret reaches disk, logs, URLs, or crash output** (`P8F7`). Auth is
  header-only, no `?key=` anywhere, byte-scan of `output/`, `jds/`, `data/`,
  `profiles/`, `.git/` for both live secrets returned **0 hits**, doctor reports
  presence and location only, and there is no `traceback.print_exc()` in
  `scripts/`. No `.env` or `signature.*` is tracked and no commit in `--all`
  history contains the current key.
- **`KB_ALLOWLIST` is an explicit filename list, not a glob** (`P8F10`) — so a
  Syncthing conflict copy is never silently ingested into the builder's context.
  That is the dangerous version of that bug and this codebase does not have it.
- **JD metadata does not leak into prompts** (`P4`). `read_jd_text()` strips any
  underscore-prefixed key generically; CLAUDE.md's convention is actually
  enforced.
- **Profile switching is not stale** (`P4`). `set_active_profile()` explicitly
  `importlib.reload`s dependent modules and raises a clear `ValueError` on an
  unknown profile.
- **Duplicate detection is solid** (`P7`). Three independent match strategies
  across four directories; a re-scan does not re-apply to a completed job or
  create duplicate files. The only cost is B35's performance.
- **`git_update.py` / `maintenance.py` cannot destroy anything unrecoverable**
  (`P7`). Gated on `has_uncommitted_changes()` at both call sites; the
  `career-ops` clobbering precedent does not apply, since nothing here writes
  into a profile.
- **SSRF defence is real and consistent** across the four ATS providers that
  accept a user-supplied URL (`P7b`) — host allowlists or a tenant-slug regex,
  each paired with `redirect: 'error'`. `workday` is the exception.
- **`normalizeTextForATS`'s masking step holds** (`P4F7d`) — `P4` tried to
  corrupt a mask boundary and could not. *(Two of its substitutions should still
  change: `—` → `-` unspaced turns `strategy—not tactics` into the invented
  compound `strategy-not`, and `·` → ` | ` mangles `Jean·Luc`. `£`→`GBP` and
  `•`→` | ` should stay.)*
- **`create_new_profile()` is well-behaved** (`P1`) — raises rather than
  overwriting, scaffolds valid empty YAML, seeds `.stignore` into all four sync
  roots. Verified by real invocation.
- **`stable_cluster_ids()` / `_cluster_content_hash()`** is the correct solution
  to positional instability, with an unusually good comment (`P6`). B10 is that
  it wasn't applied one function further down.
- **`audit_bullet_bank.py:56-69` resumes by bullet text, not row index** — the
  pattern B20 should be fixed toward, already in the repo.
- **Every LLM scoring call uses `temperature=0.0`** (`P6`). The drift found in
  this review is all ordering and schema; none of it is LLM non-determinism.
- **`voice-anchors.md` regenerates byte-for-byte** (`P6`) — 4070 bytes in, 4070
  out. B30 is a design choice in the projection, not drift.
- **Relative `./fonts/` paths in the templates are correct** (`P2`) —
  `generate-pdf.mjs:130-141` rewrites them to absolute `file://` before writing
  the temp HTML, and both PDFs embed real subsets. *(The rewrite regex only
  matches `url('./fonts/`, so CLAUDE.md's absolute-`file://` rule still stands
  for any new asset type.)*
- **PDF margins (0.5in, measured exactly) and page count (2) are correct**
  (`P2`).
- **The optional-dependency doctor checks are correctly non-fatal** (`P1`) —
  `check_go`, `check_jobright_cookie`, `check_signature_image` all return
  `passed=True` with an explanatory line, and the comments say why.
- **`followup.py` and `situational_roles.py` are clean** (`P7`) — pure date math
  and keyword matching, defensive against malformed input.
- **The board-scanner vendoring notes are excellent** (`P7b`) — each documents a
  real bug found and fixed while porting, with live evidence. That is why 7b
  could tell "ported broken" from "deliberate." **21 of 24 providers are alive
  and fast**, all returning parseable results under 1s.
- **Structured output is already current** (`P5 #8`) — real `responseSchema`
  derived from Pydantic, plus `responseMimeType: application/json`.
- **`Ctrl-C` handling in `run_pipeline` is correct** (`P4`) — `except Exception`
  does not catch `KeyboardInterrupt`. The checkpoint-write race (B13) is the real
  interrupt risk, not the handler.
- **Aesthetically, do not touch:** the block-letter banner, the Rich panel
  language, the recommendation-tier color legend, and the cover letter's
  typography — `P2` singles out the cover letter (real signature image, correct
  margins, clean rhythm) as **the strongest single artifact this system
  produces**. The gap between it and the resume is the most fixable quality
  difference in the project.

---

## 8. Already done — verify, don't redo

`scripts/validate_pdf_text.py` and `tests/test_validate_pdf_text.py` carry
**uncommitted** working-tree changes implementing `P3` MAJOR 2 (approved
separately, 2026-08-05). `_normalize` now strips emphasis markup and expands
ligatures; a new `_check_ligatures()` reports ligature corruption as its own
named warning listed first, naming the affected words and the CSS fix; the test
fixture was corrected to carry the `**Label:**` markdown real output always has
(its absence is why the bug shipped), plus 7 new tests.

Measured on the real artifacts: resume **5 warnings → 1**, and that one names the
actual defect. `P4` re-ran it against the live shipped resume and against 48
tests in the affected modules — **OK** — and its verdict was "it does what Phase
3 asked. Ship it."

**DONE — committed 2026-08-05** as `1455b787`, after a full-suite verification
run (1098 tests, OK). It is the instrument that will report zero ligature hits
once B1 lands, and it is a prerequisite for B9.
