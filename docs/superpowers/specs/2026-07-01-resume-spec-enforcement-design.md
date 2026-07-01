# Resume Pipeline Spec Enforcement — Design

## Problem

`ResumeDesignSystem.md` is the canonical, hard-won spec for every rule governing
Morgan's resume content and formatting. Today, compliance with that spec rests
entirely on a single Gemini call (`tailor_resume.md` as system instruction,
temperature 0.0) following a long prose prompt correctly, with no deterministic
check anywhere in the pipeline before a PDF is produced. A follow-up LLM
critique (`critique_resume.md`) scores the result, but nothing gates on that
score, and — per the audit below — most of what it claims to check is never
actually attached to that call.

## Audit findings driving this design

**Silent/broken wiring:**
- `orchestrator.py:1248` loads `"extract_keywords.md"`, which doesn't exist
  (only `extract_keywords.DRAFT.md` does); `load_prompt()` swallows the
  `FileNotFoundError` and silently falls back to the placeholder
  `"Process the text."` — every JD keyword-extraction call runs with no real
  instructions.
- `TemplateSchema.PROJECTS` / `.COMPETENCIES` are Pydantic-required fields for
  sections that don't exist anywhere in `ResumeDesignSystem.md`, forcing
  fabricated content on every resume.
- `formatting_rules.yaml` requires `MMM YYYY` dates, contradicting the spec's
  numeric `MM/YYYY` en-dash format and contradicting `style_rules.yaml` itself.
- `render_html.py` / `TemplateSchema` default `SECTION_SKILLS` to `"Core
  Skills"`; spec requires `"Skills"`.
- `generate-pdf.mjs` hardcodes 0.6in PDF margins; spec requires 0.5in.
- `generate-pdf.mjs` computes a real page count and prints it, but
  `orchestrator.py` only checks the subprocess return code — the "exactly 2
  pages" rule is never enforced.
- `critique_resume.md`'s "Load and Apply" list names 17 scoring YAML files;
  none are ever attached to that API call. The critique model infers
  compliance with rubrics it never sees. Its own stated integrity rule ("flag
  a file as missing rather than proceed") is unenforceable — the schema has no
  field for it.
- `summary_score.yaml` / `summary_patterns.yaml` score the Summary by word
  count (and disagree with each other on the ceiling); the spec's actual rule
  is a 5-line max — wrong metric.
- `style_rules.yaml`, `language_quality.yaml`, `verb_taxonomy.yaml`, and
  `verb_intent_mapping.yaml` get concatenated into the same bullet-audit
  prompt and directly contradict each other on banned/preferred verbs
  ("facilitated", "oversaw", "developed", "created", "supported",
  "utilized"/"leverage").
- Banned-phrase lists differ across `style_rules.yaml`, `summary_score.yaml`,
  and the spec itself.
- `ats_match.yaml` invents its own keyword-weighting model with no basis in
  the spec's ATS section.

**Dead/orphaned:** `diagnose_resume.md`, `hiring_manager_scan.md`,
`rank_bullets.md`, `recruiter_scan.md` (prompts never loaded by
`orchestrator.py`); `summary_score.yaml`, `education_score.yaml`,
`top_third_score.yaml` (scoring rubrics never wired in);
`resume-engine/scoring/README.md` is stale documentation.

## Scope and sequencing

**Phase 1 — Bug fixes** (tasks #1–#9 in the tracker): fix the silent-fallback
and contradiction bugs above. Independent, low-risk, no design judgment
required.

**Phase 2 — Cleanup** (task #10): resolved salvage plan —
- Delete `diagnose_resume.md`, `recruiter_scan.md` outright (superseded
  duplicates, nothing unique).
- Retire `rank_bullets.md` as a prompt; port its sort logic (manager_test
  pass/fail → ai_risk → metric presence) into a plain Python sort function —
  it operates on data the pipeline already computes, so it never needed an
  LLM call.
- Fold `hiring_manager_scan.md` + `top_third_score.yaml`'s first-impression /
  top-third-of-page-one evaluation into `critique_resume.md`'s schema as one
  additional advisory score, rather than running a second critique call.
- Fix `summary_score.yaml`'s word-count bug (switch to line-count) and
  actually attach it to the critique call, closing the "nothing attached"
  finding for at least this file.
- Retire `education_score.yaml` as an LLM rubric — the spec's Education rules
  are fully deterministic (see Phase 3), so there's nothing left for an LLM
  rubric to judge.
- Rewrite `resume-engine/scoring/README.md` to reflect what's actually wired
  in once Phase 3 lands.

**Phase 3 — Deterministic enforcement layer** (task #11): detailed below.

## Phase 3 design

### Principle: split every output field by whether it varies

**Fixed content — Python owns it, LLM never generates it:**
- Certifications: exactly 3 entries, fixed order, fixed title/org/year. Supplied
  as a Python constant, injected directly into the rendered output. Removed
  from `TemplateSchema` as an LLM-generated field.
- Education: institution name, degree, order, and GPA line are Python
  constants (3 schools, fixed order, per spec). The one "action-verb
  achievement bullet" per school is the sole per-resume variable: the LLM
  selects (does not write) one bullet per school from a short pre-approved
  list maintained per school, so it can lean into whichever fits the JD
  archetype. The selection is still validated (must be one of the approved
  options, not free text).
- Section header labels (`SECTION_SUMMARY`, `SECTION_SKILLS`, etc.), tagline
  uppercase-forcing, date formatting (`MM/YYYY` en-dash), and ampersand
  substitution in headings/labels/category names: Python enforces these
  unconditionally as a post-processing pass over the LLM's output, rather than
  hoping the prompt is followed. Removes an entire category of "did the LLM
  remember the formatting rule" risk.

**Generated content — LLM writes it, Python validates it:**
- Summary, Skills selection/ordering, Bullets (selection, wording, count per
  role), Why section. This is the genuinely judgment-based part of the spec:
  which evidence to foreground, tone-mirroring, archetype detection, JD
  vocabulary mirroring.
- A new validator module (`scripts/validate_resume.py`) runs after the builder
  call and before rendering. Checks include: banned words/phrases (single
  canonical list), verb uniqueness across all bullet openers, bullet/skills
  character-length bounds, pronoun bans by section, metric uniqueness across
  the whole document, section list/order matches the spec exactly (no
  Projects/Competencies or anything else), tagline length, per-role bullet
  count targets, Why-section italics/pronoun rules.
- Violations feed a **targeted retry**: only the specific flagged fields/bullets
  and their violation reasons go back to Gemini in a small follow-up call
  ("fix only these N issues, change nothing else") — not a full regenerate.
  Re-validate after each attempt. Cap at 3 attempts.
- If still violating after 3 attempts: do not render a PDF and do not mark the
  JD complete. Call `jd_manager.JDTracker.mark_failed(job_key, ...)` (existing
  mechanism, already used for unreadable-JD failures) with the remaining
  violations as the reason, so the batch loop moves on and the failure is
  visible in the tracker rather than silently shipping bad output — consistent
  with the spec's own rule that the system "must not claim a resume exists
  when PDF generation fails."

**Page count — the other hard gate:**
- Capture the real page count `generate-pdf.mjs` already computes (currently
  discarded) by parsing its stdout in `orchestrator.py`.
- If count > 2: run the spec's exact trim-priority sequence as its own
  targeted retry — (1) trim Summary/Why to their line limits, (2) tighten
  bullets, (3) remove least-relevant bullets starting with Treering, (4) drop
  the Why section — as successive small follow-up calls, re-rendering and
  re-checking page count after each step. Cap at 4 attempts (one per trim
  step). If still over 2 pages after all four: same hard-fail path as above.

**Rules consolidation (feeds both the validator and the builder prompt):**
- `style_rules.yaml` becomes the single canonical machine-readable rules
  source. `formatting_rules.yaml` and `ats_rules.yaml` are retired (their
  correct content already exists in `style_rules.yaml`; their contradictory
  content is simply wrong).
- The three verb-rule files (`language_quality.yaml`, `verb_taxonomy.yaml`,
  `verb_intent_mapping.yaml`) get reconciled into one table inside
  `style_rules.yaml`: every verb appears in exactly one tier (banned /
  acceptable / elite), resolving the "facilitated", "oversaw", "developed",
  "created", "supported", "utilized"/"leverage" contradictions by picking one
  answer per verb.
- The validator module and the builder prompt both read from this same file,
  so there is exactly one place these rules are defined, instead of five.

### What stays advisory (not hard-gated)

Tone-mirroring quality, archetype-detection correctness, the "who cares" test,
believability/credibility judgment, and the folded-in top-third/first-impression
score all remain in `critique_resume.md` as scored, logged, human-read
feedback — not auto-retried. These require holistic judgment a deterministic
checker can't make, and auto-retrying on an LLM's own quality opinion of
itself is a less predictable trigger than a hard rule.

## Out of scope for this design

- Rewriting `tailor_resume.md`'s prose (it's largely accurate; Phase 3 narrows
  what it's responsible for rather than rewriting its wording).
- Changes to the bullet-bank curation pipeline (`rewrite_bullets.py`,
  `audit_keepers.py`, etc.) beyond the rules-file consolidation in Phase 2/3 —
  that pipeline is offline and out of scope here.
- Any change to `jd_manager.py`'s checkpoint/tracker mechanics beyond calling
  the existing `mark_failed()`.
