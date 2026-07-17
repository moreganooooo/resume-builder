# Engine/Profile Split — Design

## Problem

The resume-builder pipeline is Morgan-specific in both data and logic, not
just data. `scripts/fixed_content.py` is her contact info/company
facts/certifications as Python constants; `resume-engine/knowledge_base/`
is entirely her personal bullet bank, verified facts, and profile data;
and `resume-engine/prompts/tailor_resume.md` (plus a handful of lines in
`resume-engine/rules/style_rules.yaml`) hardcodes real business logic
against her specific companies — per-role bullet-count floors, a
protected-achievements list, page-1/page-2 assignment, a situational-roles
lookup table, fixed credential ordering, and per-company post-processing
overrides.

Morgan has promised Dominick ("Dom") he'll get to try this system, and the
bootstrap wizard (`bootstrap_bullet_bank.py`/`bootstrap_profile.py`, built
2026-07-12/13) already onboards a new user's raw documents into a bullet
bank and profile — but it writes into the exact same single-user file
layout Morgan's own data lives in today. There is no `profiles/<name>/`
split anywhere in the codebase. Running bootstrap for a second real user
today would silently overwrite Morgan's live files.

career-ops has almost this same split on paper (`DATA_CONTRACT.md`'s
System Layer vs. User Layer) and it still failed in practice in June 2026
— an auto-update silently overwrote Morgan's personalization because the
tool's own docs invited hand-editing "system" files directly. The lesson:
this boundary needs to be structurally enforced, not just documented.

## Goals

- Introduce `profiles/<name>/` as the one place per-user data lives —
  `knowledge_base/`, `fixed_content.py`, and a new `situational_roles.yaml`
  — with `profiles/morgan/` as the migrated home for Morgan's existing
  data, zero behavior change for her.
- Add a single, centralized profile-resolution mechanism
  (`scripts/profile_paths.py`, env-var driven, default `"morgan"`) that
  every script routes through instead of each hand-rolling its own
  `PROJECT_ROOT/resume-engine/knowledge_base` path.
- Generalize `tailor_resume.md`'s hardcoded business rules (bullet floors,
  protected bullets, page assignment, fixed credentials, situational
  roles) into profile-supplied data, injected as a dynamic context block
  the same way `situational_roles.py`'s candidate-detection already works
  today — not a rewrite of the underlying allocation logic, just extracting
  the profile-specific data out of the prompt text.
- Extend the same profile-scoping to `jds/`, `output/`, and the tracker
  files (`jd_tracker_log.csv`, `data/applications.md`) so two profiles
  sharing one checkout can never collide, not just the knowledge-base data.
- Give bootstrap a "new profile" entry point so a second user's onboarding
  creates `profiles/<name>/` fresh, with sane scaffolded defaults for the
  new schema fields rather than demanding a fully-tuned setup on day one.

## Non-Goals

- Interactive profile-switching inside `menu.py`. The model is: each
  person sets `RESUME_PROFILE` once in their own shell profile, matching
  the existing `RESUME_BUILDER_ICONS` precedent already documented in
  `CLAUDE.md` — not two people juggling profiles in one session.
- The career-ops/job_automater merge itself (tracked separately in
  `docs/superpowers/plans/2026-07-16-three-repo-merge-punchlist.md`, item
  2) — this spec is that punchlist item's own design.
- Retroactively fixing the pre-existing issue that Morgan's personal data
  (`profile.yml`, `cv.md`, `bullet-bank-clean.csv`, etc.) is currently
  tracked in git, unrelated to this split. Flagged as a separate decision
  for Morgan; not addressed as a side effect of this work.
- A full profile-management CLI (create/list/delete profiles) beyond the
  minimal bootstrap "new profile" entry point.
- Per-user secrets / `.env` per profile (tracked separately as punchlist
  item 2's other half, IDEAS.md item #7).

## Architecture

Two integrated parts:

**Part A — structural isolation.** `profiles/<name>/` becomes the one
location for per-user data. `resume-engine/prompts/`, `rules/`, and
`templates/` stay shared (engine-owned) — Part B is what makes their
remaining Morgan-specific content safe to share. A new
`scripts/profile_paths.py` is the single source of truth for "which
profile is active" (env var `RESUME_PROFILE`, default `"morgan"`) and
exposes every path a script needs — KB, fixed_content, jds, output,
tracker files — so no script computes its own root independently anymore.

**Part B — generalize tailor_resume.md's business rules.**
`orchestrator.py`'s `load_prompt()` does zero templating — prompts are
sent as static text (confirmed by reading the implementation). The
existing, proven mechanism for injecting per-run dynamic data into that
static text is `situational_roles.py`'s `=== SITUATIONAL ROLE
CANDIDATES ===` block, built in Python and inserted alongside the prompt
at request time. This design extends that exact pattern: new `profile.yml`
sections (`roles:`, `protected_bullets:`, `fixed_credentials:`) get read by
a new builder function and injected as a `=== ROLE RULES ===` block.
`tailor_resume.md`'s prose changes from naming companies inline to
generically referencing "the ROLE RULES block for this profile" — the
allocation *logic* (weight highest-signal roles first, additive-title
format rules, trim-priority reasoning) stays in the prompt unchanged.

Two pieces are smaller than they first look: the post-processing overrides
(Mercor's appended descriptor, Element 8's forced title) are *already*
generically implemented in `normalize_resume.py` — they just iterate
whatever's in `fixed_content.py`'s dicts, so Part A's relocation fixes them
for free. And `evaluate_fit.md`'s North Star role-family list and
`critique_bullet.md`'s protected-bullet bonus list can reuse data
structures this design already introduces (`protected_bullets:`) or that
already exist (`target_roles:`/`archetypes:`), rather than needing their
own new schema.

## Components

### New profile.yml schema (per profile)

```yaml
roles:
  - name: "Treering Yearbooks"       # exact name, matches bullet-bank company tag
    min_bullets: 6                   # floor under trim pressure
    target_bullets: 7                # normal target
    page: 1
    flex_priority: 1                 # lower = trimmed first
    must_fit_page_1: true            # generalizes "must never spill to page 2"
  - name: "Inside Sales Team"
    min_bullets: 4
    target_bullets: 5
    page: 1
    flex_priority: 1
    must_fit_page_1: true
  - name: "Mercor"
    min_bullets: 2
    target_bullets: 3
    page: 1
    flex_priority: 3
  - name: "Element 8 / Strategy LLC"
    min_bullets: 3
    target_bullets: 4
    page: 2
    flex_priority: 4
  # ... VML, Callahan Creek, same shape

protected_bullets:
  - "Outreach.io full platform ownership (vendor eval, Salesforce integration, migration, adoption training, ongoing stewardship)"
  - "CRM scrub: scale (thousands of accounts), systematic audit, verified $3M pipeline recovery"
  - "Content Committee: founded and chaired, 100+ assets, 129 sequences, QA process, voice/tone guidelines"
  - "SDR Process Map: 8-step website used as official onboarding asset years after creation"

fixed_credentials:
  certifications:
    - {name: "Email Marketing Software Certification", issuer: "HubSpot", year: 2026}
    - {name: "Video for Sales Certification", issuer: "Vidyard", year: 2021}
    - {name: "Camp Portfolio", issuer: "Bernstein Rein, Kansas City", year: 2008}
  education:
    - {institution: "University of Kansas", credential: "BS, Journalism + Strategic Communication", bullet_count: 2}
    - {institution: "Kansas City Kansas Community College", credential: "AA, Journalism", bullet_count: 2}
    - {institution: "Johnson County Community College", credential: "Coursework, Graphic Design", bullet_count: 1}

voice_calibration_example: "It felt like more than an opportunity -- it felt like alignment."
```

### New situational_roles.yaml schema (per profile, separate file)

`profiles/<name>/situational_roles.yaml` (replaces `situational_roles.py`'s
hardcoded `SITUATIONAL_ROLES` dict, same shape as data instead of code):

```yaml
situational_min_bullets: 2
roles:
  - display_name: "Humane Society of Greater Kansas City"
    bank_tag: "Humane Society of Greater Kansas City"
    trigger_keywords: ["animal welfare", "animal shelter", "animal rescue", "humane society", "veterinary"]
  # ... Unisource, Kansas Colloquies, KU Payroll, DeJoy
  - display_name: "USitek"
    bank_tag: "USitek"
    admin_keywords: ["clerical", "administrative support", "administrative assistant"]
    design_keywords: ["graphic design"]
```

### New files

- **`scripts/profile_paths.py`** — `active_profile()` (reads `RESUME_PROFILE`,
  default `"morgan"`, validates the resolved `profiles/<name>/` directory
  exists), `profile_root()`, `kb_dir()`, `fixed_content_module()` (dynamic
  import via `importlib`), `situational_roles_path()`, `jds_dir()`,
  `output_dir()`, `checkpoints_dir()`, `applications_md_path()`,
  `tracker_csv_path()`. `rules_dir()`/`prompts_dir()`/`templates_dir()`
  return the shared `resume-engine/` paths, unaffected by profile.
- **`profiles/morgan/`** — populated via `git mv
  resume-engine/knowledge_base profiles/morgan/knowledge_base` and `git mv
  scripts/fixed_content.py profiles/morgan/fixed_content.py`, plus the new
  `situational_roles.yaml` extracted from `situational_roles.py`'s current
  dict.

### Modified — mechanical path-redirect only

`audit_keepers.py`, `cluster_bullet_bank.py`, `detect_hidden_gems.py`,
`embed_bullet_bank.py`, `rewrite_bullets.py`, `bootstrap_bullet_bank.py`,
`bootstrap_profile.py`, `render_html.py`, `render_coverletter.py`,
`jd_manager.py` — each swaps its local `KB_DIR`/`APPLICATIONS_MD`/
`TRACKER_CSV`/etc. constant for the equivalent `profile_paths` call.
`render_coverletter.py` also loses its one stray hardcoded `"Morgan
Escott"` fallback (line 45) in favor of `fixed_content.CONTACT_INFO`.

### Modified — orchestrator.py (both parts)

- `self.kb_dir`, `self.jds_dir`, `self.output_json_dir` now resolve via
  `profile_paths`; `self.engine_dir`/`prompts_dir`/`rules_dir`/
  `scoring_dir`/`templates_dir` stay pointed at shared `resume-engine/`.
- New method `build_role_rules_block(profile_data: dict) -> str`, called
  alongside the existing situational-candidates injection in
  `build_tailored_resume()`, formats `roles:`/`protected_bullets:`/
  `fixed_credentials:` into the `=== ROLE RULES ===` block.
- `KB_ALLOWLIST` is filenames, not Morgan-specific values, and likely stays
  as-is (same filenames expected per profile) — confirm during
  implementation. `TREERING_KEYWORDS` is a literal employer name and needs
  to move to profile-scoped data or be confirmed redundant with the
  `fixed_content.py` relocation — flagged for a closer look during
  implementation planning, not fully resolved here.

### Modified — situational_roles.py

`SITUATIONAL_ROLES`/`SITUATIONAL_MIN_BULLETS` module constants deleted;
replaced with `load_situational_roles(profile_name=None) -> dict` reading
the new per-profile YAML. `detect_situational_candidates()`/
`bank_minimums_for()` take the loaded data instead of referencing a module
constant.

### Modified — resume-engine/prompts/tailor_resume.md

The ~9 load-bearing sections (bullet-count floors, protected bullets, page
order, fixed credentials, trim-priority, archetype-evidence anchors)
rewritten to reference the `=== ROLE RULES ===` block generically instead
of naming companies inline; prose logic unchanged. ~9 cosmetic
"Morgan"/"Morgan Escott" mentions become "the candidate."

### Modified — resume-engine/rules/style_rules.yaml

The 7 contaminated lines (duplicate page-assignment/trim-priority data,
the "K-12/Salesforce/Outreach" differentiators example) deleted or
genericized — the ROLE RULES block becomes the single source of truth
instead of two files that could silently diverge.

### Modified — smaller prompt files

`evaluate_fit.md` (North Star role list → profile's
`target_roles`/`archetypes`), `critique_bullet.md` (protected-bullet bonus
→ reuses `protected_bullets:`), `critique_resume.md` (voice quote → new
`voice_calibration_example`), `polish_resume.md`/`polish_coverletter.md`/
`tailor_coverletter.md` (cosmetic "Morgan" mentions → "the candidate").

### Bootstrap additions

`bootstrap_bullet_bank.py` gains a "new profile" entry point: prompt for a
profile name, scaffold `profiles/<name>/` (knowledge_base/,
fixed_content.py, situational_roles.yaml placeholders), print the
`RESUME_PROFILE` export line for the user to add to their shell profile.
The new `roles:`/`protected_bullets:`/`fixed_credentials:` fields get a
sane scaffolded default on first bootstrap (e.g. every detected role
starts at `target_bullets: 4, min_bullets: 2, page: 1`) rather than
demanding a fully-tuned schema on day one, consistent with bootstrap's
existing "light seed, grows over time" philosophy.

## Data Flow

Building a tailored resume for Dom's profile, end to end:

1. Dom sets `RESUME_PROFILE=dominick` once in his shell profile.
2. `orchestrator.py`'s `ResumeEngine.__init__` resolves `self.kb_dir`,
   `self.jds_dir`, `self.output_json_dir` via `profile_paths`, landing on
   `profiles/dominick/...` throughout; `engine_dir`/`prompts_dir`/
   `rules_dir` stay pointed at shared `resume-engine/`.
3. `build_tailored_resume()` loads the (now generic) `tailor_resume.md`,
   his KB context, `situational_roles.load_situational_roles()` (his own
   YAML), and `build_role_rules_block()` (his own `roles:`/
   `protected_bullets:`/`fixed_credentials:`) — all combine into the
   context sent to Gemini alongside the JD.
4. `normalize_resume.py` dynamically imports `profiles/dominick/
   fixed_content.py` instead of Morgan's.
5. Output lands in `profiles/dominick/output/` and his own tracker files —
   zero collision risk with Morgan's data even in a shared checkout.

## Error Handling

- **Unknown profile name is a hard failure, not a silent fallback.**
  `profile_paths.active_profile()` validates `profiles/<name>/` exists; an
  *unset* `RESUME_PROFILE` defaults to `"morgan"` (backward compat), but an
  explicitly-set wrong name errors loudly — silently falling back to
  Morgan's data on a typo would be the exact cross-contamination bug this
  design exists to prevent.
- **Missing new schema fields degrade gracefully, not fatally.** If a
  profile has no `roles:`/`protected_bullets:` yet, `build_role_rules_block()`
  returns nothing and `tailor_resume.md` has a fallback clause ("if no ROLE
  RULES block is present, use general judgment") rather than crashing —
  consistent with bootstrap's "thin first, refine over time" story.
- **Broken `fixed_content.py`** (missing an expected constant) raises a
  clear, profile-named error at the import site rather than a cryptic
  downstream `KeyError` in `normalize_resume.py`.
- **Migration completeness:** grep the whole repo (not just the
  already-inventoried scripts) for any other stray `resume-engine/
  knowledge_base` reference — tests, README, shell scripts — as an explicit
  verification step before considering the migration done.

## Testing

- Existing tests already monkeypatch module-level path constants (e.g.
  `orchestrator.jd_manager.APPLICATIONS_MD` in
  `test_orchestrator_main_batch.py`) — this pattern extends naturally to
  `profile_paths`, so most of the existing suite needs no rewrite, just a
  fixture profile directory.
- New unit tests: `profile_paths.py` (default/override/invalid-name
  behavior, `kb_dir()`/`fixed_content_module()` resolution),
  `build_role_rules_block()` (fixture profile.yml → expected block; empty
  `roles:` degrades gracefully), and a regression test confirming
  `situational_roles`'s YAML-ified loader produces behavior identical to
  today's hardcoded dict for Morgan's actual data.
- New integration test: a minimal `profiles/testuser/` fixture with no
  `roles:`/`protected_bullets:` filled in, confirming a full
  `build_tailored_resume()` run succeeds end-to-end on defaults alone.
- **Acceptance bar:** the full suite (615 tests as of 2026-07-16) stays
  green throughout: plus a manual live-verify against a few real JDs
  confirming Morgan's own output is behaviorally unchanged (same bullet
  counts, page assignment, protected bullets, situational-role gating).

## Migration Sequencing

1. Build `profile_paths.py` + its tests, unwired (safe, additive).
2. `git mv` Morgan's `knowledge_base/` and `fixed_content.py` into
   `profiles/morgan/`; extract `situational_roles.py`'s dict into
   `profiles/morgan/situational_roles.yaml`.
3. Wire the 9 scripts + `jd_manager.py` + `orchestrator.py`'s path
   attributes through `profile_paths`, one at a time, full suite green
   after each step.
4. Build `build_role_rules_block()`, wire it into `build_tailored_resume()`,
   rewrite `tailor_resume.md`'s load-bearing sections, populate Morgan's
   own `profile.yml` with the new sections (her real current values — zero
   behavior change), delete `situational_roles.py`'s hardcoded dict.
5. Update `style_rules.yaml` + the five smaller prompt files.
6. Live-verify against real JDs.
7. Add bootstrap's "new profile" entry point + scaffold defaults.
8. Decide `.gitignore` treatment for `profiles/*/` going forward (separate
   call — Morgan's personal data is currently tracked in git today,
   pre-existing this task, not silently changed as a side effect).

## References

- `IDEAS.md`, item #4 and the "Multi-user support" section.
- `docs/superpowers/plans/2026-07-16-three-repo-merge-punchlist.md`, item 2.
