# Bootstrap Profile Personalization — Design

## Problem

The bootstrap feature shipped in `2026-07-12-bootstrap-bullet-bank-design.md` gets a new user from a folder of documents to a working `bullet-bank-clean.csv`. But the rest of the pipeline — `orchestrator.py`, `rewrite_bullets.py`, `ingest.py` — depends on a second set of files that bootstrap never touches: `profile.yml`, `cv.md`, `portals.yml`, `morgan-background-guide.md`, and a "verified-facts ledger" of nine files (`verified_facts.json`, `verified_metrics.json`, `verified_projects.json`, `verified_tools.json`, `verified-claims.csv`, `evidence_graph.json`, `evidence-guide.csv`, `extracted-screenshot-metrics.csv`, `recruiter_memory_patterns.json`).

Today a new user has to hand-write all of these from scratch, several of them multi-hundred-line YAML files with no template or guidance. Some of that content genuinely can be guessed from the documents they already dropped in `source_documents/` during bootstrap; some of it — a person's own career narrative, direct quotes from real references — cannot be guessed without either asking the user directly or risking fabrication.

Auditing each file's actual role (see the "What's tailored to me" investigation this design follows on from) surfaced three tiers:

1. **Objectively extractable** — contact info, target roles, location preference: present in the resume/LinkedIn text already, or a short direct question.
2. **Derivable from already-extracted data** — `verified_metrics/tools/projects.json`: simple lists built from achievements bootstrap already pulled out.
3. **Requires the user's own reflection or real cross-source corroboration** — `profile.yml`'s `narrative`/`superpowers`/`deal_breakers`/`key_recommendations`/`management_evidence`, and the `verified_facts.json`/`verified-claims.csv`/`evidence_graph.json`/`evidence-guide.csv` cluster, which assume multiple independently-verified sources tracked over time.

## Goals

- Extend bootstrap with a new phase that guesses what it honestly can from already-ingested documents, and asks the user directly — inline, in the terminal, guess pre-filled and editable — for anything it can't safely guess.
- Auto-populate `profile.yml`'s `candidate` block and `target_roles`, and `portals.yml`'s `location_filter`/`title_filter`, from a short guess-confirm-or-edit Q&A.
- Auto-derive `verified_metrics.json`, `verified_tools.json`, `verified_projects.json` from the achievements Phase 0 already extracted — no new API calls beyond what ingestion already made, just restructuring already-extracted data.
- Auto-fill `key_recommendations` with real quotes and attribution wherever a recommendation letter was actually uploaded and parsed.
- Draft `cv.md` (a lightly-polished, resume-shaped reformatting of the already-extracted timeline and bullets) and `user-background-guide.md` (a narrative bio synthesized from resume/rec-letter/notes text), each previewed in the terminal with an accept/regenerate/skip-and-edit-later choice.
- Scaffold everything that can't be safely guessed — `profile.yml`'s deeper strategy sections, and the four/five ledger files that assume real cross-source corroboration — with guided inline comments explaining what the section is for, never with invented content.
- Ship a valid, empty `recruiter_memory_patterns.json` so downstream scripts don't warn about a missing file (this file has no producer script even in the existing repo — it accumulates by hand over real use).
- Genericize `morgan-background-guide.md` to `user-background-guide.md` across the whole codebase, including a one-time rename of the existing live file.

## Non-Goals

- Auto-generating `profile.yml`'s `narrative`, `superpowers`, `archetypes`, `background_context`, `industries_of_genuine_fit`, `companies_previously_applied`, `deal_breakers`, `management_evidence`, or `compensation` sections. These require the user's own self-reflection or direct knowledge of real events; guessing them risks putting words in the user's mouth.
- Auto-generating `verified_facts.json`, `verified-claims.csv`, `evidence_graph.json`, `evidence-guide.csv`, or `extracted-screenshot-metrics.csv`. These assume corroboration across multiple independent sources with confidence/verification tracking built up over time — a single bootstrap ingestion pass can't honestly produce that.
- Inventing recommendation quotes for `key_recommendations` when no recommendation letter was uploaded. This section only ever gets auto-filled from real, already-parsed source documents.
- Building `portals.yml`'s `block`/`seniority_boost` sections. These are tuned through real job-search experience over time, not guessable from a document set.
- Changing anything about Phase 0 (document ingestion) or the existing 6-stage pipeline — this design only inserts a new phase between them.
- A repeatable script for `recruiter_memory_patterns.json`. It stays a hand-curated file; bootstrap only ensures it exists in valid, empty form.

## Architecture

A new **Phase 0.5** runs after Phase 0 (document ingestion) and before the existing 6-stage pipeline. It reuses Phase 0's timeline and extracted achievements as guess sources, runs a short interactive guess-confirm-or-edit Q&A for the fields that need it, then writes all five file categories in an order where later steps can draw on earlier ones (e.g. `cv.md`'s polish pass runs after `profile.yml`/`verified_*.json` already exist, so it has real context to draw on).

```
Phase 0:   Ingest documents -> bullet-bank-clean.csv, timeline.json
Phase 0.5: Guess + confirm profile.yml, portals.yml, verified_*.json,
           then draft cv.md and user-background-guide.md
Phase 1-6: audit -> cluster -> rewrite -> audit_keepers ->
           score_keeper_gems -> embed  (existing, unchanged)
```

Phase 0.5's interactive prompts always run, regardless of `--yes` (which continues to only skip the six-stage pipeline's confirmation *gates*, not this phase's data-collection prompts) — because these are correctness-critical data the pipeline needs right, not a proceed/don't-proceed checkpoint. `--dry-run` remains a true no-input preview for Phase 0.5: it prints every guess and every file that would be written, calls no API, and prompts for nothing, preserving the existing automated-smoke-test path.

## Components

### `bootstrap_extractors.py` — two new extraction functions (extends the Task 3 pattern)

- `class ContactInfo(BaseModel)` — `full_name`, `email`, `phone`, `location`, `linkedin_url`, `portfolio_url`, all `Optional[str]`.
- `extract_contact_info(*, text: str | None = None, upload_path: str | None = None, dry_run: bool = False) -> ContactInfo` — pulls whatever contact/header block is present in the already-ingested resume/LinkedIn text. Same exactly-one-of-text-or-upload_path contract as the existing Task 3 extraction functions.
- `draft_background_guide(source_texts: list[str], dry_run: bool = False) -> str` — synthesizes a narrative bio (career-path prose, in the shape of the existing `morgan-background-guide.md`/`user-background-guide.md`) from resume-summary + recommendation-letter + achievement-notes text already gathered in Phase 0. Uses the same "light inference allowed, never invent specifics not supported by the source" rules already governing `extract_achievements`.

### `bootstrap_profile.py` — new file, the Phase 0.5 orchestrator

- `run_profile_setup(dry_run: bool = False) -> dict` — the phase's single entry point, called from `bootstrap_bullet_bank.py` between `run_ingestion()` and `run_full_pipeline()`. Returns a summary dict analogous to `run_ingestion()`'s.
- Interactive guess-confirm-or-edit prompts, each a pre-filled `questionary.text()` (press Enter to accept the guess, or edit in place) for: full name, email, phone, location, LinkedIn URL, and a generic "any other portfolio/work-sample link? (optional)" replacing the Morgan-specific `process_map_url`. Target roles (primary/secondary) use `questionary.checkbox()` over Gemini-suggested candidates (recent job titles verbatim, plus 2-3 adjacent-title suggestions), with an "add your own" free-text follow-up.
- A short remote/location-preference question feeds `portals.yml`'s `location_filter`.
- Writes `profile.yml`: `candidate` and `target_roles` filled from the confirmed answers; `archetypes`/`narrative`/`superpowers`/`background_context`/`industries_of_genuine_fit`/`companies_previously_applied`/`deal_breakers`/`management_evidence`/`compensation` written as a scaffold with guided inline comments (e.g. `# List 2-3 things you're uniquely good at that show up in your work`) and empty values; `key_recommendations` auto-filled with real quote+attribution for every recommendation letter Phase 0 actually parsed, otherwise left as a commented scaffold.
- Writes `portals.yml`: `location_filter` from the confirmed preference; `title_filter` seeded from the confirmed target roles; `block`/`seniority_boost` scaffolded empty with guided comments.
- Derives `verified_metrics.json`, `verified_tools.json`, `verified_projects.json` directly from the achievements Phase 0 already extracted (numbers/tools/named-projects mentioned) — no new API calls, pure restructuring.
- Writes empty/starter-template scaffolds for `verified_facts.json`, `verified-claims.csv`, `evidence_graph.json`, `evidence-guide.csv`, `extracted-screenshot-metrics.csv`, and a valid empty `recruiter_memory_patterns.json`.
- Assembles a `cv.md` draft: a header built from the confirmed `ContactInfo`, followed by one section per timeline role (title/company/dates + that role's extracted bullets). Each bullet is run once through `rewrite_bullets.py`'s existing `process_bullet()`/`KnowledgeBase` — reused as-is, not reimplemented — for a light first-pass polish. This runs after `profile.yml`/`verified_*.json` are already on disk, so `KnowledgeBase`'s context has real content to draw on rather than degrading to its missing-file blanks.
- Calls `draft_background_guide()`, prints the result to the terminal, and offers accept / regenerate / "I'll edit it myself later" before writing `user-background-guide.md`.

### Rename: `morgan-background-guide.md` → `user-background-guide.md`

- `git mv resume-engine/knowledge_base/morgan-background-guide.md resume-engine/knowledge_base/user-background-guide.md`.
- Update the hardcoded path constant (currently pointing at the old filename) in `orchestrator.py` and `rewrite_bullets.py`, and in `KB_ALLOWLIST`/any other literal string reference to the old name.

## Data Flow

1. Phase 0 runs unchanged, producing `timeline.json` and the extracted achievements/certificates.
2. Phase 0.5 starts: `extract_contact_info()` runs over the same resume/LinkedIn text Phase 0 already has in memory; target-role candidates are drawn from the timeline's most recent title(s) plus a short Gemini adjacent-title suggestion call.
3. Interactive prompts run in order: identity fields -> portfolio-link -> location/remote preference -> primary roles (checklist) -> secondary roles (checklist). Each guessed value is pre-filled and directly editable.
4. `profile.yml` and `portals.yml` are written immediately once confirmed.
5. `verified_metrics/tools/projects.json` are derived from Phase 0's achievements and written; the five cross-source-verification files are scaffolded empty.
6. `cv.md` is assembled and its bullets lightly polished via the reused `process_bullet()` call, now that `profile.yml`/`verified_*.json` exist to inform `KnowledgeBase`'s context.
7. `draft_background_guide()` runs; its output is previewed in the terminal with an accept/regenerate/skip choice before `user-background-guide.md` is written.
8. `run_full_pipeline()` proceeds exactly as it does today.

## Error Handling

Any single extraction or API call failing in Phase 0.5 logs a warning and falls back to a blank guess (never crashes the phase) — the same convention already established in Phase 0. `--dry-run` prints every guess, every prompt that would be shown, and every file that would be written, without calling any API or touching disk. Missing or unparseable source documents simply mean thinner guesses (more blank pre-filled prompts for the user to type into directly), never a hard failure.

## Testing

- Unit tests for `extract_contact_info()` and `draft_background_guide()` mocking `GeminiClient.generate`/`_generate_from_upload`, following the existing pattern in `test_bootstrap_extractors_llm.py`.
- Unit tests for the ledger-derivation logic (`verified_metrics/tools/projects.json` built from a fixed set of achievements) with no mocking needed, since it's pure data restructuring.
- Unit tests for `run_profile_setup()`'s file-writing logic (profile.yml/portals.yml scaffolding, `key_recommendations` auto-fill when a recommendation letter is present vs. absent), redirecting path constants to a temp directory the same way `test_bootstrap_bullet_bank_ingestion.py` already does.
- Interactive-prompt tests mocking `questionary.text`/`questionary.checkbox`, following the exact pattern already used in `test_menu_bootstrap.py` and `test_bootstrap_bullet_bank_pipeline.py`.
- A `--dry-run` end-to-end fixture test extending `test_bootstrap_end_to_end.py`'s existing pattern, asserting Phase 0.5's guesses print and its file set would be written, with zero API calls and zero prompts.
- A regression test confirming `orchestrator.py`/`rewrite_bullets.py` correctly reference `user-background-guide.md` post-rename, and that the existing test suite still passes with the renamed file in place.
