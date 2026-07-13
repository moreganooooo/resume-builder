# Bootstrap Bullet Bank for New Users — Design

## Problem

Every script built so far in this pipeline (`audit_bullet_bank.py`,
`cluster_bullet_bank.py`, `rewrite_bullets.py`, `tag_bullet_bank.py`, and the
Resume-Bullet-Parser sibling project) assumes a `bullet-bank-clean.csv`
already exists — for Morgan, built up over months from many resume-draft
Google Docs. A new user adopting this system has none of that: they have a
scattered, heterogeneous pile of whatever documents they happen to already
have (a LinkedIn PDF export, a mediocre existing resume, a few letters of
recommendation, some free-form notes on past achievements, a handful of
certificates), no awareness of the multi-stage pipeline that follows bullet
bank creation, and no reason to know which of six-plus standalone scripts to
run in what order.

This design covers a script (and a menu entry point) that takes that
scattered document pile and produces a real `bullet-bank-clean.csv`, then
guides the user through the same existing pipeline Morgan already uses —
without requiring them to understand any of it up front.

## Goals

1. Ingest a folder of arbitrary personal documents: PDF, images/screenshots
   (PNG/JPG/HEIC/WEBP), `.docx`/`.doc`/`.odt`, `.pptx`, spreadsheets
   (`.xlsx`/`.csv`), and plain text/`.md`.
2. Extract achievement-shaped content per document, using a document-type-
   specific extraction prompt (resume, LinkedIn export, recommendation
   letter, achievement notes, certificate) with light cross-document
   inference allowed but no invented metrics, scope, or seniority beyond
   what the source text actually supports.
3. Build one canonical company/role/date-range timeline from whichever
   document is identified as the resume or LinkedIn export, and use it to
   attribute every extracted achievement to a company — falling back to a
   Misc./Unassigned bucket with a review flag when no confident match
   exists.
4. Route certificates to their own credentials file, not into bullet rows —
   a credential isn't an achievement.
5. Auto-tag the result (reusing `tag_bullet_bank.py`'s existing logic
   in-process) and write directly to `bullet-bank-clean.csv` — no manual
   promotion step, since a first-time user has no existing file at risk of
   being overwritten.
6. Chain automatically into the existing six-stage pipeline (`audit_bullet_bank.py`
   → `cluster_bullet_bank.py` → `rewrite_bullets.py` → `audit_keepers.py` →
   `score_keeper_gems.py` → `embed_bullet_bank.py`), calling each unmodified
   script as its own subprocess, with a confirmation gate before each of the
   two API-heavy stages (`audit_bullet_bank.py`, `rewrite_bullets.py`) and a
   `--yes` flag to skip all prompts for an unattended run.
7. Add a highlighted entry point to the existing interactive menu
   (`menu.py`) — `--> New User? Start Here!` — that scans the source
   documents folder and messages accordingly (empty vs. N files found)
   before launching the bootstrap process.
8. Give a zero-context user a plain-language preview of the whole journey
   before it starts, plus a short contextual hint at the start of each
   phase, so they understand what's happening and why at every step.
9. Checkpoint per file during ingestion and rely on each existing
   pipeline script's own checkpoint/resume behavior for the later stages,
   so an interrupted run — at any point — can simply be re-run to continue.

## Non-Goals

- Regenerating any of the other Morgan-specific knowledge base content
  (`voice-anchors.md`, `verified_facts.json`, `verified_tools.json`,
  `morgan-background-guide.md`, `cv.md`'s company-keyword mapping, etc.) for
  a new user. Personalizing that content for someone else is a materially
  larger, separate problem than "build a starter bullet bank," and is
  explicitly out of scope here.
- Modifying any of the six existing pipeline scripts. They are invoked
  unmodified, as subprocesses, in the order already proven this session.
- Full `style_rules.yaml`-level bullet polishing at ingestion time (verb
  selection, buzzword removal, exact formatting rules). Ingestion produces
  light, readable bullet-style sentences; the existing `rewrite_bullets.py`
  stage already owns full quality rewriting and runs immediately after.
- Reliable parsing of legacy binary `.doc` files without LibreOffice
  installed. Best-effort only (see Components) — not worth a hard
  dependency on an external binary for one legacy format.
- Real API calls inside the automated test suite. All automated tests run
  against mocked/fixed responses (`--dry-run`); a live end-to-end run stays
  a documented manual validation step.

## Architecture

New files, contained entirely under a dedicated subfolder so nothing
scatters into the existing `knowledge_base/` layout:

```
resume-engine/knowledge_base/
  bootstrap/
    source_documents/          <- user drops raw files here
    timeline.json               <- canonical company/role/date timeline (human-editable)
    checkpoint.json             <- per-file ingestion state, for safe resume
    bullet-bank-draft.csv       <- extracted raw bullets + provenance columns
    review-needed.csv           <- low-confidence / unattributed rows
    certifications.json         <- credential facts (not bullets)
  bullet-bank-clean.csv          <- final tagged output; the ONE file that
                                    "graduates" out of bootstrap/ into the
                                    location the existing pipeline already
                                    expects
```

Three new scripts in `scripts/`, matching the existing flat-file convention
(no new subpackage):

- `scripts/bootstrap_extractors.py`
- `scripts/bootstrap_timeline.py`
- `scripts/bootstrap_bullet_bank.py`

New dependencies (added to `requirements.txt`): `python-docx`, `python-pptx`,
`odfpy`. Spreadsheets and CSV use `pandas`, already installed.

The only thing that ever leaves `bootstrap/` is `bullet-bank-clean.csv`,
written to the exact path the rest of the pipeline already reads from —
`audit_bullet_bank.py`, `cluster_bullet_bank.py`, etc. require zero changes.

## Components

### `bootstrap_extractors.py` — file handling and per-document extraction

- `detect_file_kind(path) -> str` — routes each file to one of: `pdf`,
  `image`, `docx`, `doc`, `odt`, `pptx`, `spreadsheet`, `text`.
- `extract_local_text(path, kind) -> str | None` — for `docx`/`pptx`/`odt`/
  `spreadsheet`/`text`/`.md`/`.csv`, extracts plain text locally via
  `python-docx`/`python-pptx`/`odfpy`/`pandas`/stdlib. Returns `None` for
  `pdf`/`image` — those upload directly to Gemini rather than being
  text-extracted locally, since Gemini's multimodal file understanding
  already handles both text-layer PDFs and OCR-on-images natively (the same
  pattern `ingest.py` already uses for its single-resume parse).
- Legacy `.doc` handling: best-effort only. If `soffice` (LibreOffice) is
  present on `PATH`, convert to PDF first (`soffice --headless
  --convert-to pdf`) and proceed as a normal PDF. If not available, skip the
  file with a clear message telling the user to re-save it as `.docx` or
  `.pdf` — never a hard crash.
- `classify_document_type(filename, text_or_none) -> str` — returns one of
  `resume`, `linkedin_export`, `recommendation_letter`, `achievement_notes`,
  `certificate`, `other`, using filename heuristics first and an LLM
  classification call for ambiguous cases.
- `extract_achievements(file_path_or_text, doc_type) -> list[RawAchievement]`
  — calls `GeminiClient.generate()` with a document-type-specific system
  prompt (different framing per type — a resume's bullets read differently
  from a recommendation letter's third-person praise) and a Pydantic
  response schema:
  ```python
  class RawAchievement(BaseModel):
      raw_text: str
      company_hint: str | None
      date_hint: str | None
      title_hint: str | None
      confidence: Literal["high", "medium", "low"]
  ```
  The system prompt explicitly instructs: light rephrasing for clarity is
  fine; inferring or inventing a metric, scope, or detail not present in the
  source text is not — matching the same truthfulness standard already
  built into `rewrite_bullets.py`'s `RulesBundle`.
- Certificates take a separate extraction path entirely
  (`extract_certificate(file_path) -> Certificate | None`, `{name, issuer,
  date}`) and are written straight to `bootstrap/certifications.json` —
  never forced into a fake achievement bullet. This applies both to
  documents classified whole-file as `certificate`, and to a
  "Certifications" section found embedded inside a `resume` or
  `linkedin_export` document — `extract_achievements()` on those two types
  also runs `extract_certificate()`-style detection over any such section
  it finds, routing those entries to `certifications.json` rather than
  emitting them as achievement bullets.

### `bootstrap_timeline.py` — the anchor and the matcher

- `build_timeline(resume_or_linkedin_docs) -> list[TimelineEntry]` —
  `{company, title, start_date, end_date}`. Runs once, specifically against
  whichever document(s) were classified as `resume` or `linkedin_export`. If
  both exist, entries are merged by fuzzy company-name match: the LinkedIn
  export's date range wins by default when the two overlap but differ
  slightly, but a same-company entry whose date ranges disagree enough to
  suggest genuinely different stints is not silently resolved either way —
  that entry is written to `bootstrap/timeline.json` with a
  `"needs_review": true` flag and both candidate date ranges recorded.
  `review-needed.csv` stays reserved for achievement-level rows (see
  below) — a timeline conflict has an entirely different shape (company +
  competing date ranges, no bullet text), so it belongs with the rest of
  the timeline data, not mixed into a file that's otherwise uniformly
  bullet-shaped. The user can hand-edit `timeline.json` directly (including
  resolving any `needs_review` entries) before the next phase runs.
- `match_to_timeline(raw_achievement, timeline) -> (company, confidence)` —
  uses `company_hint`/`date_hint`/`title_hint` plus fuzzy text matching,
  with an LLM-assisted fallback for ambiguous phrasing (e.g., "while I was
  doing outbound sales" matching a timeline entry whose title contains
  "sales"). Returns `("Misc. / Unassigned", "low")` when nothing fits
  confidently.

### `bootstrap_bullet_bank.py` — orchestrator and pipeline parent

Phase 0 (ingestion, local/fast, no confirmation gate):

1. Scan `bootstrap/source_documents/`, identify resume/LinkedIn doc(s) first
   and run `build_timeline()`.
2. Process every other document, checkpointed per file in
   `bootstrap/checkpoint.json` — a rerun skips files already processed.
3. Run `match_to_timeline()` over every extracted achievement.
4. Write `bootstrap/bullet-bank-draft.csv` (matched rows + `source_file`/
   `source_type` provenance columns), `bootstrap/review-needed.csv`
   (Misc./low-confidence rows), and `bootstrap/certifications.json`.
5. Auto-tag via `tag_bullet_bank.py`'s `assign_tags()` (imported directly,
   not shelled out to) and write `resume-engine/knowledge_base/bullet-bank-clean.csv`.
6. Print a summary: bullets extracted, confidently attributed, flagged for
   review, certificates found.

Phases 1–6 (the existing pipeline, unmodified, called via `subprocess.run`):

- Confirmation gate → `audit_bullet_bank.py` → `cluster_bullet_bank.py`
- Confirmation gate → `rewrite_bullets.py` → `audit_keepers.py` →
  `score_keeper_gems.py` → `embed_bullet_bank.py`
- `--yes` flag skips both confirmation gates for an unattended run.
- Final summary: keeper count, hidden-gem count, embeddings built, and a
  pointer to what to do next (build a tailored resume against a real JD).

### Menu integration (`menu.py`, `cli_art.py`)

- New `cli_art.QUESTIONARY_STYLE` token: `('new_user', 'fg:#4caf50 bold')` —
  reuses the green already tied to "success/go" elsewhere in this app.
- New first entry in `menu._CHOICES`:
  `questionary.Choice(title=[("class:new_user", "--> New User? Start Here!")], value="bootstrap")`,
  followed by a `questionary.Separator()` to visually set it apart from the
  rest of the menu.
- New handler `_handle_bootstrap()`:
  - Creates `bootstrap/source_documents/` if it doesn't exist yet.
  - **Empty folder** → prints: *"Looks like there's nothing in the
    `source_documents` folder yet. Drop in your resume, LinkedIn export,
    certificates, recommendation letters, or notes — then come back and
    select this again when you're ready!"* → returns `False` (no chain,
    straight back to the main menu).
  - **N files found** → prints: *"Looks like you've got N document(s) to
    process. Ready to get started?"*, `questionary.confirm()`. On yes, runs
    `bootstrap_bullet_bank.py` as a subprocess (consistent with how it will
    itself call the six pipeline stages).
  - No `_CHAIN` entry needed afterward — `bootstrap_bullet_bank.py` already
    guides the user through the entire pipeline internally.

### User-facing hints (`cli_art.py`, `bootstrap_bullet_bank.py`)

- New style constant: `HINT = "[bold cyan]💡[/bold cyan]"`, matching the
  existing `SUCCESS`/`ERROR`/`WARNING` pattern.
- New `cli_art.display_bootstrap_intro(doc_count)` — a `Panel`, shown once
  right after the user confirms "Ready to get started?", giving a
  plain-language preview of the whole journey: what's about to happen,
  roughly how many phases, and a heads-up that two of the phases make real
  API calls and can take a few minutes.
- One short `HINT`-prefixed line printed at the start of each phase,
  explaining in plain language what that phase does and why (e.g., before
  the quality-audit phase: *"Quality check time — every bullet gets scored
  the way a skeptical hiring manager would read it. This is the first
  API-heavy step."*). These sit above and are visually distinct from each
  underlying script's own detailed progress output.
- A closing summary at the very end (keeper count, hidden-gem count, next
  step) uses the same `HINT`/`SUCCESS` styling for consistency.

## Data Flow

```
bootstrap/source_documents/*.{pdf,png,jpg,heic,webp,docx,doc,odt,pptx,xlsx,csv,txt,md}
  │
  ├─ [resume/LinkedIn doc(s) processed first] → build_timeline() → bootstrap/timeline.json
  │
  ├─ [every other document, checkpointed] → extract_achievements() per doc
  │      → raw achievements (raw_text, hints, confidence, source_file, source_type)
  │
  ├─ [certificates] → extract_certificate() → bootstrap/certifications.json
  │
  ├─ [consolidation] → match_to_timeline() per raw achievement
  │      → confident matches, or Misc./Unassigned + low confidence
  │
  ├─ bootstrap/bullet-bank-draft.csv   (all matched rows + provenance)
  ├─ bootstrap/review-needed.csv       (Misc./low-confidence rows)
  │
  ├─ [auto-tag via tag_bullet_bank.assign_tags(), in-process]
  │      → resume-engine/knowledge_base/bullet-bank-clean.csv
  │
  ├─ [confirm] → audit_bullet_bank.py (subprocess) → cluster_bullet_bank.py (subprocess)
  │
  └─ [confirm] → rewrite_bullets.py (subprocess) → audit_keepers.py (subprocess)
         → score_keeper_gems.py (subprocess) → embed_bullet_bank.py (subprocess)
         → final summary
```

## Error Handling

- **Per-file extraction errors** (corrupt PDF, unreadable document): wrapped
  in try/except per file; logged and skipped, never aborts the whole
  ingestion run — the same resilience pattern `audit_bullet_bank.py`
  already uses per-bullet.
- **Unsupported file types** (legacy `.doc` with no LibreOffice available):
  clear, actionable message telling the user what to do; skip and continue.
- **Gemini API errors** during extraction or matching: reuse
  `GeminiClient`'s existing retry/backoff — no new retry logic invented.
- **Checkpointing**: `bootstrap/checkpoint.json` is saved after every file
  during ingestion, not only at the end, so an interrupted run loses at
  most one file's worth of progress.
- **Pipeline-stage failures**: if any of the six existing scripts exits
  non-zero when called via `subprocess.run`, the parent orchestrator stops
  immediately with a clear "Stage X failed — re-run this same command to
  resume" message. It never silently continues to the next stage on a
  failure. Since each stage already checkpoints internally, re-running the
  same command picks back up correctly without redoing completed work.
- **Confirmation prompts**: bare Enter defaults to yes; an explicit `n`
  is required to abort; `--yes` skips both gates entirely for an
  unattended run.

## Testing

Unit tests (no API calls, via the existing `tests/test_*.py` + stdlib
`unittest` convention):

- `detect_file_kind()` — correct routing across every supported extension.
- Local text extraction (`.docx`/`.pptx`/`.odt`/spreadsheet) against small
  fixture files checked into `tests/fixtures/bootstrap/`.
- `match_to_timeline()` — given a canned timeline and canned raw
  achievements with varying hint combinations, verify correct company
  assignment and correct fallback to Misc./low-confidence.
- Output-file schema correctness for the draft CSV, review-needed CSV,
  timeline JSON, and certifications JSON.
- `_handle_bootstrap()`'s empty-vs-has-files branching, mocking
  `questionary` and `subprocess` calls.
- The pipeline-parent sequencing logic — mocking `subprocess.run` to verify
  stages run in the correct order, a non-zero exit stops the chain
  immediately, and `--yes` actually skips both confirmation gates.

`--dry-run` mode for every Gemini-calling code path, matching the exact
pattern already used in `rewrite_bullets.py`/`audit_bullet_bank.py`: fixed
mocked responses stand in for real API calls, so the entire flow —
extraction → timeline → consolidation → tagging → write — can be
smoke-tested end-to-end for free before ever pointing it at real documents.

One small fixture-based integration test: a synthetic document set (a
1-page fake resume PDF, a short fake recommendation letter, a plain-text
notes file) checked into `tests/fixtures/bootstrap/`, run through the whole
pipeline once in `--dry-run` mode as part of the automated suite. Running
it for real (a small number of live API calls) stays a documented manual
validation step, not part of the automated suite.

Out of scope for new tests: the six existing pipeline scripts are already
proven this session — testing responsibility here covers only the new
ingestion/timeline/consolidation/menu/sequencing code, not the internals of
scripts this design calls unmodified.
