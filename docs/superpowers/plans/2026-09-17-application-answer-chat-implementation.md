# Application Answer Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From any job, open a themed chat that drafts answers to application questions. Answers are grounded in the job, the recruiter evaluation, company research, and the candidate's verified record and voice. Answers are checked for invented facts and saved on the job.

**Architecture:** A Python engine (`scripts/application_answers.py`) owns all data access, prompt assembly, the model call and the grounding checks. It speaks a one-request/NDJSON-response protocol. A Go Bubble Tea screen (`dashboard/internal/ui/screens/answers.go`) renders the chat and spawns the engine once per turn, the same way the dashboard already calls `dashboard_actions.py`.

**Tech Stack:** Python 3.10+, stdlib `unittest`; Go, Bubble Tea v2, bubbles v2 (viewport, textarea, spinner), Glamour, Lip Gloss v2.

**Spec:** `docs/superpowers/specs/2026-09-17-application-answer-chat-design.md` (see §10 for resolved decisions).

---

## Global Constraints

- JD text only through `jd_manager.read_jd_text()`; jobs resolved through `jd_source.resolved_jd()` so database-only ids work.
- Tests never touch the network or a real profile: mock `gemini_client.generate`; use `profile_paths.isolate_for_tests()` and `tests/persona.py`.
- Persisted keys go through an explicit allowlist, like `save_evaluation`.
- Go styles come from theme tokens only (`go run ./tools/lint_colors.go`); truncate with `ansi.Truncate(…, "…")`; handle `WindowSizeMsg`, the 80x24/35x12 minimums and reduced motion.
- The prompt file stays field-neutral (no profile vocabulary).
- Model-written text never enters the knowledge base without an explicit user choice.
- Run the full suite after every task: `python -m unittest discover -s tests`, and `go test ./...` in `dashboard/`.

---

## Phase 1: Engine (usable from the command line)

### Task 1: Question classifier

**Files:** Create `scripts/answer_questions.py`, `tests/test_answer_questions.py`

**Interfaces:**
- `classify_question(text: str) -> QuestionKind`, where `QuestionKind` is a `str` enum: `eeo`, `legal`, `salary`, `why_company`, `why_role`, `behavioral`, `experience_with_tool`, `general`.
- `sensitive_response(kind, profile_yaml: dict) -> str | None`: the fixed text for `eeo`; the `profile.yml` value or a "please answer this yourself" notice for `legal`; `None` otherwise.

- [ ] Write failing tests with a table of ~40 real-style questions per kind, including traps: "Tell me about a time you disagreed" → behavioral; "Are you legally authorized…" → legal; "Do you identify as…" → eeo; "What are your compensation expectations?" → salary; "Why Acme?" → why_company; "How many years with Salesforce?" → experience_with_tool.
- [ ] Implement ordered regex rules, evaluated in order eeo → legal → salary → specific kinds → general (sensitive kinds first so a question that is both kinds cannot slip into drafting).
- [ ] Add `application_answers:` keys to the `profile.yml` schema docs (`work_authorization`, `requires_sponsorship`), both optional.
- [ ] Run the suite; commit.

### Task 2: Persistence

**Files:** Modify `scripts/jd_manager.py`; create `tests/test_application_answers_store.py`

**Interfaces:**
- `save_application_answers(jd_path: str, answers: dict) -> None`
- `read_application_answers(jd_path: str) -> dict | None`
- Shape per spec §5; allowlisted item keys: `question`, `kind`, `char_limit`, `final`, `history` (`role`, `text`, `warnings`, `created_at`).

- [ ] Failing tests: round-trip; unknown keys dropped; `read_jd_text()` does not include `_application_answers`; a non-dict JD no-ops; atomic write.
- [ ] Database-only job test: save through `jd_source.resolved_jd()` and confirm the row's `metadata_json` has the answers and its **status is unchanged** (the sync-back trap in CLAUDE.md).
- [ ] Implement, mirroring `save_evaluation`/`read_evaluation`.
- [ ] Run the suite; commit.

### Task 3: Context assembly

**Files:** Create `scripts/application_answers.py` (context part), `tests/test_application_answers_context.py`

**Interfaces:**
- `@dataclass AnswerContext`: `job_id, title, company, jd_text, evaluation_summary, research_summary, research_source, voice_anchors, compensation_context, roster`.
- `build_context(job: str) -> AnswerContext`: `job` is a path or a database id.
- `evidence_for(context, question, kind) -> Evidence`: `search_bullet_bank(question, top_k=8)`; plus `search_behavioral_stories` for `behavioral`, `search_negotiation_levers` for `salary`, and a verified-ledger lookup for `experience_with_tool`.
- `context_cache_path(job_id) -> str`: a temp file under the system temp dir, keyed by job id + JD content hash, reused for 24h.

- [ ] Failing tests with everything mocked: evaluation fields pulled (strengths, `capability_gaps`, `experience_blockers`); research comes from the cache without an API call; the research-summary budget is trimmed (≤ 2,500 chars); a missing evaluation or research yields empty sections, not errors; the evidence helpers are chosen by kind.
- [ ] Reuse `orchestrator.build_compensation_context()` for salary; reuse `ResumeEngine.research_company()` (never re-implement the tiers).
- [ ] Implement; run the suite; commit.

### Task 4: Prompt + answer generation

**Files:** Create `resume-engine/prompts/answer_application_question.md`; extend `scripts/application_answers.py`; create `tests/test_application_answers_generate.py`

**Interfaces:**
- `render_prompt(context, evidence, history, question, kind, char_limit) -> str`
- `answer(job, question, history=(), char_limit=None) -> AnswerResult` (`text`, `kind`, `warnings`, `blocked: bool`)

- [ ] Prompt sections per spec §4.2, plus per-kind guidance blocks (why_company leans on research and vocabulary; behavioral uses STAR from the stories; experience_with_tool must say "adjacent" when the tool is not verified).
- [ ] Failing tests: an `eeo` question never calls `generate` (mock asserts not called); the prompt contains no underscore metadata; history is included newest-last and capped at the last 10 turns; `char_limit` appears in the rules.
- [ ] Model `gemini-3.5-flash-lite` via `GeminiClient.generate()`.
- [ ] A field-neutrality test that fails if any profile's `tagline_descriptor` or employer name appears in the prompt file (same approach as `test_tagline_descriptors`).
- [ ] Implement; run the suite; commit.

### Task 5: Grounding checks + retry

**Files:** Create `scripts/answer_grounding.py`, `tests/test_answer_grounding.py`; wire into `answer()`

**Interfaces:**
- `check_answer(text, context, evidence, char_limit) -> list[Violation]`, where `Violation(kind: str, detail: str, soft: bool)`
- Checks:
  - `foreign_number` (reuse `rewrite_bullets.foreign_numbers` against JD + research + evidence + compensation context);
  - `unknown_tool` (reuse the resume hallucinated-tool matcher against the verified ledger);
  - `unknown_employer` (an employer-like name not on the roster and not the target company; soft);
  - `vague_magnitude` (adapt `validate_resume._check_vague_magnitudes`; soft);
  - `too_long` (over `char_limit`).

- [ ] Failing tests using persona data: an invented "40%" is flagged; a percentage present in a bullet passes; the target company's name is not flagged as an employer; a salary figure from the posting passes.
- [ ] `answer()`: if any hard violation, one retry with the violations stated (same shape as the resume fix loop); keep the better of the two (fewer hard violations); remaining violations are returned as `warnings`, and nothing is rewritten silently.
- [ ] Run the suite; commit.

### Task 6: CLI + NDJSON protocol

**Files:** extend `scripts/application_answers.py` (`__main__`); create `tests/test_application_answers_cli.py`

**Protocol:**
- `python scripts/application_answers.py turn` reads one JSON object from stdin: `{"job", "question", "item_index"?, "char_limit"?, "action": "ask"|"regenerate"|"shorten"}`.
- It writes NDJSON to stdout: `{"type":"status","text":"Researching Acme…"}`* then exactly one of `{"type":"answer","text","kind","warnings":[…],"blocked":bool,"item_index"}` or `{"type":"error","text"}`. Logs go to stderr only.
- The engine saves the turn itself (so a crashed UI loses nothing).
- `python scripts/application_answers.py load --job X` prints the saved answers JSON.
- `python scripts/application_answers.py finalize --job X --item N [--library]` marks an answer as final.
- `interactive --job X`: a plain terminal loop for Phase 1 use without the dashboard.

- [ ] Failing tests: stdout is valid NDJSON with exactly one terminal event; an exception becomes an `error` event with exit code 1; `regenerate` replaces the last assistant turn instead of appending.
- [ ] Implement; run the suite; commit.

### Task 7: Answer library (opt-in)

**Files:** Create `scripts/answer_library.py`, `tests/test_answer_library.py`

**Interfaces:**
- `add_to_library(question, answer, job_title, company, quote: str | None) -> None`: appends a row to `knowledge_base/application-answers-index.csv` using the existing columns (`Filename` = `app-chat:<job_id>`, `Prompt / Topic` = question, `Answer Length` = word count, `Quote Worth Pulling` = `quote` or empty); atomic write; then rebuild `voice-anchors.md` only if `quote` was given.

- [ ] Failing tests in an isolated profile: the header is preserved; a quote-less row does not change `voice-anchors.md`; duplicate question + job is not re-added.
- [ ] Implement; run the suite; commit.

**Phase 1 exit check:** `python scripts/application_answers.py interactive --job <real id>` answers three real questions of different kinds, with sensible warnings. Record the notes in the spec.

---

## Phase 2: Chat screen

### Task 8: Screen model and layout

**Files:** Create `dashboard/internal/ui/screens/answers.go`, `answers_test.go`

**Structure:**
- `AnswersModel`: `job model.JobRow`, `items []AnswerItem`, `active int`, `viewport viewport.Model`, `input textarea.Model`, `spinner spinner.Model`, `busy bool`, `status string`, `width, height int`, `theme theme.Theme`.
- Layout, top to bottom:
  - header bar: title · company · score badge · `research: website|search|jd`;
  - transcript viewport;
  - warnings line;
  - input (3 lines, grows to 6);
  - status line: kind · chars `412/500` · model;
  - key legend.
- Messages: user blocks with a left border in `t.Overlay`; assistant blocks with a `t.Mauve` border, Glamour-rendered; warnings in `t.Peach` with "⚠"; blocked (EEO) notices in `t.Subtext`.

- [ ] Failing golden-style tests: renders at 80x24 and 35x12 without panic or overflow (every line ≤ width); the char counter turns `t.Red` over the limit; an empty state shows a hint ("Paste an application question…").
- [ ] Implement the view; `go run ./tools/lint_colors.go`; commit.

### Task 9: Engine bridge

**Files:** Create `dashboard/internal/answers/bridge.go`, `bridge_test.go`

**Interfaces:**
- `Turn(ctx, pythonPath, projectRoot string, req TurnRequest) tea.Cmd`: streams `StatusMsg` values then one `AnswerMsg` or `ErrorMsg` (read stdout line by line; stderr captured for the error text).
- `Load(...) ([]AnswerItem, error)`, `Finalize(...) error`.

- [ ] Failing tests with a fake script that emits NDJSON: statuses are delivered in order; malformed lines are skipped; non-zero exit → `ErrorMsg` with the stderr tail; context cancel kills the process.
- [ ] Implement; commit.

### Task 10: Keys, actions, clipboard

**Files:** extend `answers.go`; create `dashboard/internal/answers/clipboard.go` and its tests

**Keys:**
- `enter`: send;
- `alt+enter`: newline;
- `ctrl+r`: regenerate;
- `ctrl+s`: shorten;
- `c`: copy (when the input is empty);
- `f`: mark final, then a prompt "Add to answer library? (y/N)", then an optional quote pick from the answer's sentences;
- `p`: plain view (full-screen, unstyled);
- `[` / `]`: previous / next question;
- `/limit N`: set the character limit;
- `esc`: back (confirms if a turn is running).

- **Clipboard:** `tea.SetClipboard` (OSC 52), plus a native tool if found; the status line reports the method.
- **Reduced motion:** a static "Thinking…" instead of the spinner.

- [ ] Failing tests: key routing with a textarea focus (`c` types a "c" when there is text); `esc` during busy asks for confirmation; `/limit` parsing.
- [ ] Implement; commit.

### Task 11: Entry points

**Files:** Modify `dashboard/main.go` (new `-view answers -job <id>` flags), `screens/jobs.go`, `screens/pipeline.go`, the help overlay, `scripts/dashboard.py`, `scripts/menu.py` (Build Documents → One Role → "Application Answers"), `tests/test_menu.py`

- [ ] `[a]` on Jobs and Pipeline opens the screen for the selected row; `esc` returns with the cursor preserved.
- [ ] The menu item picks a role with the existing picker, then launches `dashboard -view answers -job <id>`.
- [ ] Tests: Go key → view switch; menu builder includes the choice under the "One Role" heading; the handler maps the value.
- [ ] Update the help overlay and footer legends; run both suites; commit.

### Task 12: Docs + recording

- [ ] `dashboard/tapes/answers.tape` (VHS) and one capture via `scripts/capture_tui_visuals.py` for a visual check.
- [ ] CLAUDE.md architecture note: the engine owns persistence; the grounding checks; sensitive-question handling; the library is opt-in.
- [ ] README: short usage section.
- [ ] Commit and push.

**Phase 2 exit check:** open a real job from Jobs, answer a why_company, a behavioral and a salary question; copy one to the clipboard; mark one final and add it to the library; reopen and see history.

---

## Phase 3: Polish (optional, each task independent)

### Task 13: Streaming
- Engine: `GeminiClient` streaming (`streamGenerateContent`), emitting `{"type":"chunk"}`; grounding checks still run on the full text and warnings arrive with the final `answer` event. The screen renders chunks as plain text, then re-renders with Glamour when done.

### Task 14: Long-lived engine
- `application_answers.py serve`: one process per chat session; the request id is echoed on every event. The bridge keeps the process alive and restarts it on crash. Only worth it if Phase 2 turn latency feels slow.

### Task 15: "You answered something similar"
- Embed the library's `Prompt / Topic` column (primary embedding model only, its own cache file). On a new question with a match ≥ the 95th percentile of library self-similarity (measured, not guessed, per the skill-matrix lesson), show a dismissible suggestion card with the old answer; `u` uses it as the starting draft.

### Task 16: Per-kind helpers
- Salary: show the parsed posting range and floor in the header.
- Tool questions: show verified / adjacent / missing status.
- Why-company: show the research source and date, with `R` to refresh research.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Plausible but invented facts | Hard grounding checks + one retry + visible warnings; evidence limited to the verified record |
| Voice drifts toward the model's voice | Library/voice writes are opt-in, with quotes picked by the user |
| Sensitive questions answered by AI | Deterministic classifier before any model call; covered by tests |
| Database-only job status reverted on save | Explicit test in Task 2 |
| Prompt picks up one profile's vocabulary | Field-neutrality test in Task 4 |
| Cost creep from repeated research | Research cache + per-session context cache |

---

# Review Revisions (2026-09-17)

A review of the plan for test coverage, UX, fragility, context, models and
rate limits. **These revisions override the tasks above where they conflict.**
Each item names the task it changes.

## A. Model, rate limits and failure handling

Facts from `gemini_client.py` that shape this:
- `generate()` returns `(None, {})` on failure rather than raising.
- It defaults to `max_retries=6` with backoff, which is the same ~150s wait
  ladder that stalled re-scoring on 2026-09-13.
- On failure it falls back through `MODEL_FALLBACKS` (3.5-flash-lite →
  3.1-flash-lite → gemma-4-31b-it).
- After repeated failures it raises `SustainedFailureError`.
- Refusals come back as a `finishReason` (`SAFETY`, etc.).

- **A1 (Task 4): an interactive latency budget.** Call with `max_retries=2`.
  A person is watching a spinner, so fail fast with a clear message instead
  of a silent 2-minute wait. The key pool still rotates keys on a 429
  immediately (no retry spent), so extra keys help here for free.
- **A2 (Task 4): one model per turn, reported.** Record which model actually
  answered (the fallback may land on Gemma) and emit it in the `answer` event
  as `model`. The status line shows it, so a lower-quality answer from a
  fallback isn't a mystery. The model is configurable in `profile.yml` as
  `application_answers.model` (a candidate preference, not a scan filter), validated against
  `MODEL_FALLBACKS` keys, defaulting to `gemini-3.5-flash-lite`.
- **A3 (Task 6): typed errors in the protocol.** The `error` event gains
  `code`:
  - `rate_limited`: every key cooling down; include `retry_after` seconds
    taken from the soonest key cooldown;
  - `refused`: a `finishReason`; show the mapped explanation;
  - `offline`: connection errors;
  - `no_api_key`;
  - `sustained_failure`;
  - `context_error`: the job file is missing or unreadable;
  - `internal`.

  The UI maps each code to friendly text and an action. For example, on
  `rate_limited` it shows "Gemini is rate-limited; try again in 40s" with an
  auto-enabled `ctrl+r` countdown.
- **A4 (Task 6): the question is never lost.** The user's turn is saved
  BEFORE the model call, with `status: "pending"`, and marked `failed` or
  `answered` afterward. A failure leaves the question in history with a
  "retry" affordance, and the input is not cleared until the engine
  acknowledges receipt.
- **A5 (Task 3): research is never on the hot path of the first turn
  without notice.** On a cache miss, a website scrape plus grounded search can
  take 20–60s. Instead:
  - emit `status` events per tier ("Checking acme.com…");
  - on miss, start research, but after 15s continue with a JD-only context
    and flag `research: pending` in the header;
  - prefetch research when the screen opens (a `warm` command) rather than
    when the first question is sent.
- **A6 (new, Task 4b): cost/usage visibility.** Count calls per chat in the
  saved item (`calls`, `models`). No token counting UI in v1; the calls
  count is enough to notice a runaway retry loop.

## B. Context management

- **B1 (Task 3): an explicit token budget, measured.** The system prompt is
  built from fixed sections with per-section character caps:
  - JD 12,000 (head+tail truncation with a marker, since requirements often
    sit at the end);
  - evaluation 1,500;
  - research 2,500;
  - voice anchors 2,000;
  - evidence 8 bullets + ≤3 stories;
  - history (see B2).

  Add a test that a maximum-size JD + full history stays under a
  `MAX_PROMPT_CHARS` (60,000) constant, and assert which section was trimmed.
  Gemma's context is smaller than Gemini's, so the budget targets the
  smallest model in the fallback chain.
- **B2 (Task 4): history is per question, not per chat.** Each question
  item carries its own short history (refinements such as "shorter"), capped
  at the last 6 turns. Other questions in the same job appear only as a
  one-line list of question + final answer (≤ 300 chars each), so answers
  stay consistent without repeating the full transcripts. This replaces
  "last 10 turns of the whole chat".
- **B3 (Task 3): evidence is retrieved from the question, not the chat.** For
  follow-ups ("make it about the Treering project"), re-retrieve with
  `question + follow-up`.
- **B4 (Task 3): stale-context detection.** The cache key includes the JD
  content hash, the `evaluated_at` timestamp, the research cache timestamp,
  and the mtimes of `bullet-bank-keepers-audited.csv` and `voice-anchors.md`.
  Any change rebuilds the cache. Test each invalidation source.
- **B5 (Task 3): embedding fallback.** `search_bullet_bank` can re-embed
  synchronously when the bank changed, which is slow. Detect `needs_reembed()`
  first and, if true, fall back to keyword evidence (the verified ledger +
  the top bullets by token overlap) with a warning "evidence search is
  rebuilding; answers may be less specific", instead of blocking a chat turn
  on a re-embed. The backup-index fallback (`backup_index_for`) applies as
  well.

## C. Fragile areas

- **C1 (Task 2): concurrent writes.** The dashboard and a CLI `interactive`
  session can write to the same JD. Use a read-modify-write under the same
  `fcntl.flock` approach as `_append_row` (graceful on Windows), and merge by
  item id rather than overwriting the whole `_application_answers` block. Items
  get a stable `id` (uuid4), which replaces `item_index` in the protocol, since
  indexes shift.
- **C2 (Task 2): the JD moves while the chat is open.** Tailoring moves a JD
  to `completed/`, and archive/purge can move or delete it. The engine
  resolves by **job id** every turn, never by a path cached in the UI. Add
  `jd_source` resolution by id across `jds/`, `completed/`, `archived/` if it
  doesn't already exist. If the job was purged, return
  `context_error` "This job was removed; your answers are exported to
  `output/<profile>/answers/<job>.md`". Also add a purge hook: see C3.
- **C3 (new, Task 2b): answers survive a purge.** `purge_terminal_jobs.py`
  deletes expired/archived JDs, and answers stored only on the JD would be
  lost. Before deleting, export any `_application_answers` with a `final` to
  `output/<profile>/answers/<company>-<title>.md`. Add a test for this
  alongside the purge tests.
- **C4 (Task 1): classifier false positives are costly for EEO, false
  negatives more so.** Bias toward `eeo`/`legal` when in doubt, but always
  show the classification as a chip on the question with `k` to change the
  kind (e.g. a "Why do you want to work in veteran services?" question
  misread as EEO). Add tests for these traps and for non-English/emoji input
  falling to `general` without crashing.
- **C5 (Task 5): grounding false positives.** Numbers that are safe to use
  but not in the evidence would otherwise be flagged:
  - years of experience derived from the roster dates;
  - dates;
  - the character limit itself;
  - numbers quoted from the question ("in 250 words").

  Build `allowed_text` from JD + question + research + evidence +
  compensation + a roster summary with computed tenure years. Tests for each.
  Spelled-out numbers ("forty percent") are normalized before comparison.
- **C6 (Task 9): Python environment.** The bridge must use the same
  interpreter the dashboard already receives (`-python-path` from
  `scripts/dashboard.py`, i.e. `.venv`), never bare `python3`, which can
  resolve to a stray venv on this machine. Add a test that the bridge uses the
  configured path.
- **C7 (Task 9): stdout pollution.** Any `print` from an imported module
  (cli_art banners, warnings) corrupts NDJSON. In `turn` mode, redirect
  `sys.stdout` to stderr for the duration and write events to the saved
  original stdout. Test: a module that prints during import doesn't break
  parsing. The Go side still skips non-JSON lines (already in Task 9).
- **C8 (Task 11): profile preflight.** The `turn` entry point calls
  `profile_paths.preflight_profile()` before profile-scoped imports, per the
  entry-point rule in CLAUDE.md, and maps failure to `context_error`.
- **C9 (Task 8): paste handling.** Pasting a multi-paragraph question into a
  textarea can trigger `enter` = send mid-paste. Enable bracketed paste
  (`tea.PasteMsg` in v2) and insert pasted text wholesale. Test with a
  simulated paste containing newlines.
- **C10 (Task 10): the `c` key conflicts with typing.** Rather than depending
  on "input empty", use focus modes: typing in the input vs. `tab` into the
  transcript, where single-letter keys act. Show the mode in the status line.
  This matches Crush and removes a class of mis-keys.

## D. User friendliness and polish

- **D1 (Task 8): the question list.** A slim left sidebar (collapsible below
  100 cols, hidden on mobile) lists the job's questions with state dots:
  final, drafted, failed. Friendlier than `[`/`]` alone, and it makes "I have
  7 questions for this application" manageable.
- **D2 (Task 10): batch paste.** `ctrl+b` "Paste several questions": split on
  blank lines or numbering, create one item per question, and draft them
  sequentially with a progress bar. Many applications have 5–10 questions,
  so this is a big effectiveness win. Rate-limit aware: pause on
  `rate_limited` and resume.
- **D3 (Task 4): answer options, not just one answer.** For `why_company`/
  `why_role`/`behavioral`, draft once, then offer quick refinements as chips:
  shorter · warmer · more concrete · use a different example · match the
  character limit. These map to fixed instructions, so the prompts are tested,
  not free-form.
- **D4 (Task 4): "why this answer".** Each answer has an expandable
  "Sources" footer listing the bullets/stories/research facts it drew on
  (the engine returns evidence ids used). This builds trust and makes the
  grounding warnings actionable.
- **D5 (Task 8): counters that match forms.** Show characters AND words;
  let `/limit 250w` set a word limit. ATS forms count characters including
  newlines, so count the same way.
- **D6 (Task 10): export.** `e` exports all final answers for the job to
  `output/<profile>/answers/<company>-<title>.md` (the same format as C3), so
  answers are handy when filling the form in a browser.
- **D7 (Task 11): discoverability.** After a tailoring run completes, the
  CLI's success message suggests "Press [a] in Jobs to draft application
  answers". The Pipeline detail pane shows "3 answers drafted, 2 final".
- **D8 (Task 8): the first-run empty state** shows three example questions
  as selectable chips, and indicates whether research and an evaluation exist
  for this job ("No evaluation yet: answers will be less targeted. Evaluate
  now? [E]").
- **D9 (Task 10): undo.** `ctrl+z` restores the previous draft after a
  regenerate/refinement (keep the prior assistant turns; regenerate no longer
  *replaces*, it appends and marks the previous one superseded). This
  overrides Task 6's "regenerate replaces".

## E. Effectiveness of answers

- **E1 (Task 4): recruiter self-review pass (optional, off by default in
  v1).** A second, cheap call scores the draft against the recruiter rubric:
  answers the question, specific, and relevant to the posting's top 3
  requirements. It returns one sentence of feedback shown under the answer.
  Behind `application_answers.self_review: true`, since it doubles calls.
- **E2 (Task 4): gaps handled honestly.** When the question touches a
  `capability_gap` or `experience_blocker`, the prompt instructs the
  "adjacent experience + learning plan" framing and the UI shows the chip
  "addresses a gap". Test: a question mentioning a gap tool pulls the gap
  into the prompt.
- **E3 (Task 7): library quality.** When a past library answer exists for a
  similar topic, include it in the prompt as a voice/content reference
  (≤ 1 answer) even before Phase 3's suggestion card. Past answers the
  candidate wrote themselves are the strongest voice signal available.
- **E4 (Phase 1 exit): a small evaluation set.** Create
  `tests/fixtures/answer_eval/` with ~12 persona questions across kinds, plus
  a manual `scripts/eval_application_answers.py` (real calls, not CI, same
  pattern as `eval_role_track.py`). It reports grounding violations per
  answer, limit compliance, and classification accuracy. Run it before and
  after any prompt change, and measure noise across separated runs.

## F. Complete test inventory

**New Python test files**
- `test_answer_questions.py`: kind table, sensitive-first ordering, traps,
  empty/huge/non-English input, `sensitive_response` with and without
  profile values.
- `test_application_answers_store.py`:
  - round-trip; allowlist; `read_jd_text` exclusion; non-dict no-op;
  - db-only job keeps its status;
  - concurrent writers merge by item id (two processes);
  - pending → answered/failed transitions.
- `test_application_answers_context.py`:
  - section caps and the `MAX_PROMPT_CHARS` bound;
  - head+tail JD truncation;
  - cache invalidation for each of the 5 sources;
  - missing evaluation/research;
  - research timeout falls back to JD-only;
  - `needs_reembed` keyword-evidence fallback;
  - evidence helpers by kind; follow-up re-retrieval.
- `test_application_answers_generate.py`:
  - EEO never calls the model;
  - no underscore metadata in the prompt;
  - per-question history cap and the cross-question summary;
  - refinement chips map to fixed instructions;
  - gap framing included;
  - library exemplar included;
  - model override validation;
  - `max_retries=2` passed;
  - the model actually used is reported;
  - field-neutrality.
- `test_answer_grounding.py`:
  - foreign numbers;
  - allowed sources (question, tenure years, dates, compensation);
  - spelled-out numbers;
  - unknown tools/employers;
  - target company allowed;
  - limit (chars and words);
  - retry keeps the better draft.
- `test_application_answers_cli.py`:
  - one terminal event;
  - every error `code` mapping (`rate_limited` with `retry_after`,
    `refused`, `offline`, `no_api_key`, `sustained_failure`,
    `context_error`);
  - stdout pollution guard;
  - preflight failure;
  - regenerate appends + supersedes;
  - batch creation from pasted text;
  - job resolved by id after a move to `completed/`.
- `test_answer_library.py`: header preserved; quote-less row leaves voice
  anchors alone; dedupe; isolated profile.
- `test_answer_export.py`: markdown export format; purge exports finals first.

**Existing Python tests to update**
- `test_menu.py`: the "Application Answers" choice under "One Role", its
  handler mapping, and a unique value.
- `test_purge_terminal_jobs` (or its current file): finals exported before
  deletion.
- `test_jd_manager` / `test_jd_discovery_and_moves`: `_application_answers`
  survives `move_jd_to` and `archive_jd`.
- `test_dashboard_actions` / the export tests: if the export gains
  `answers_drafted`/`answers_final` counts, `model.JobRow` needs the matching
  fields (per the CLAUDE.md warning that an unknown field fails the whole
  decode) and a decode test.
- `test_no_operator_identity.py` covers the new fixtures automatically.
  Confirm the eval fixtures use `tests/persona.py`.

**New Go tests**
- `answers_test.go`:
  - layout at 80x24 / 120x40 / 35x12 with no line over the width;
  - sidebar collapse thresholds;
  - counters (chars/words, over-limit colour);
  - empty state and chips;
  - focus modes and key routing;
  - bracketed paste;
  - `esc` during a running turn;
  - error code → message/action mapping, including the `retry_after`
    countdown;
  - superseded drafts and undo;
  - reduced motion (no spinner ticks);
  - the unicode icon set.
- `bridge_test.go`:
  - ordered statuses;
  - non-JSON lines skipped;
  - stderr tail on failure;
  - cancel kills the process;
  - configured interpreter path used.
- `clipboard_test.go`: the OSC 52 sequence; native-tool detection with a fake
  PATH; the reported method.
- `jobs_test.go` / `pipeline_test.go`: `[a]` opens answers and the cursor is
  preserved on return; the help overlay lists `[a]`; the detail pane shows
  answer counts.
- `main` flag test: `-view answers -job` routes to the screen, and a missing
  job id shows an error card, not a panic.
- `theme` lint: `tools/lint_colors.go` passes for the new files.

## G. Revised phase order

1. **Phase 1:** Tasks 1–7 plus A1–A4, B1–B5, C1–C8, E2–E4, and the export (D6/C3).
2. **Phase 2:** Tasks 8–12 plus C9–C10, D1, D3–D5, D7–D9.
3. **Phase 3:** Tasks 13–16 plus D2 (batch paste), E1 (self-review), A5
   prefetch (`warm`) if it isn't already covered by Phase 2 latency.

Estimated size after the revisions: Phase 1 ≈ 1.5 sessions, Phase 2 ≈ 1.5
sessions, Phase 3 ≈ 2 sessions. The revisions add roughly half a session in
total, mostly in tests.

---

# Crush Alignment Review (2026-09-17)

Checked against Crush v0.95.0, the version installed here: first from
Crush's source (`internal/ui/`, including its `AGENTS.md`), then against the
running app at 130×40 once a provider was configured (section K). **These
notes override earlier layout and key choices where they differ; K overrides
H and I where they disagree.**

## H. What Crush actually does, and what we adopt

| Crush behavior (source) | Our plan before | Change |
|---|---|---|
| **One top-level model.** Chat, list and sidebar are plain structs with imperative methods (`SetMessages`, `ScrollBy`) and no `Update`. No IO in `Update`; all work goes through `tea.Cmd` (`internal/ui/AGENTS.md`). | `AnswersModel` with nested bubbles models | Keep a single `AnswersModel.Update`; transcript, sidebar and composer are render helpers with methods. The bridge runs only inside `tea.Cmd`s. |
| **User messages:** a thin left border in the primary color + 1 padding; a *thicker* border when focused. **Assistant messages:** no border, 2 padding; a subtle success-colored border only when focused (`styles/quickstyle.go`). | User `t.Overlay` border, assistant `t.Mauve` border always | User: `t.Mauve` normal left border. Assistant: plain, indented 2; focused: `t.Green`-subtle thick left border. Less chrome and easier to read. |
| **An info line under each assistant reply:** icon · model · provider · duration, in subtle/muted text. | Model shown in the status line only | Add a per-answer footer: `◇ gemini-3.5-flash-lite · 3.2s · 2 sources · ⚠ 1`. The fallback model is visible exactly where it matters. |
| **Header:** full logo on the landing screen; in chat, a one-line compact header: small logo, `╱╱╱` diagonal fill, then details on the right. | A header bar with title · company · score | One-line header: app wordmark, `╱` fill in `t.Surface`, then `Title · Company · 4.2 · research: website` right-aligned. |
| **Responsive:** sidebar 32 cols; **compact mode below 120 cols or 30 rows**, where the sidebar collapses into a details overlay toggled with `ctrl+d`. | Sidebar collapses under 100 cols | Use Crush's breakpoints (120×30) and width (32). In compact mode, `ctrl+d` opens the question list/details as an overlay. The mobile limit (35×12) still applies below that. |
| **Keys:** `enter` send; `shift+enter` / `ctrl+j` newline; `ctrl+o` open `$EDITOR`; `tab` change focus; in chat focus `c`/`y` copy, `space` expand/collapse, `g`/`G` home/end; `esc` cancel; `ctrl+p` commands; `ctrl+g` more help; `ctrl+s` sessions. | `alt+enter` newline, `ctrl+s` shorten, `/limit`, etc. | Adopt Crush's keys verbatim: `shift+enter`/`ctrl+j` newline (drop `alt+enter`); `ctrl+o` edits the question in `$EDITOR`; `tab` focus (already C10); `c`/`y` copy; `space` expands a Sources footer; `esc` cancels a running turn; **`ctrl+p` command palette** holds the less common actions (shorten, warmer, set limit, export, mark final, change kind), so they don't each need a hotkey; `ctrl+g` expands help; **`ctrl+s` opens the question list** (Crush's "sessions" slot). Refinement chips remain for mouse/touch users. |
| **Help/status bar:** short key hints at the bottom; **transient notifications draw over the hints** with a colored indicator (info/success/warn/error) and clear after a TTL. | A separate status line + warnings line | Merge into Crush's model: one bottom bar with hints, and events such as "Copied via OSC 52", "Rate-limited, retry in 40s" or "Saved as final" shown as timed notifications over it. Per-answer warnings stay in the answer footer. |
| **Paste:** pastes over **10 lines or 1,000 columns** become an attachment chip rather than flooding the editor. The editor is 3–15 lines tall. | Bracketed paste, input 3–6 lines | Keep bracketed paste. A paste over those thresholds offers a batch split into several questions (D2) instead of inserting raw text. Composer is 3–15 lines. |
| **Spinner:** a gradient character-scramble animation at 20 fps with an animated label (`anim` package). | bubbles spinner | Use a gradient label animation (`t.Mauve`→`t.Peach`) like "Drafting…" at a lower fps. It shows one line of status text from the engine. Reduced motion shows static text. Mobile mode disables the ticking. |
| **Landing view:** before the first message, show context (working dir, model, LSP/MCP status). | An empty-state hint + example chips | The landing view shows the job header, model, and three readiness badges (Evaluation ✓, Research ✓ website / … pending, Voice ✓), plus example question chips. The same "context before chatting" pattern. |
| **Dialog overlays** stack over the chat (commands, models, quit confirm). | Inline y/N prompts | "Add to answer library?", quote picking, "cancel running turn?" and the command palette use one overlay component styled like Crush's (bordered, centered, `t.Surface` background). |
| **Rendering:** markdown is cached per width and rendered incrementally while streaming (`streaming_markdown.go`). | Glamour re-render on every View | Cache rendered answers by (id, width); re-render only on resize or content change. Streaming (Task 13) renders plain text until done, as planned. |

## I. Deliberately different from Crush

- **No model picker dialog.** Crush is multi-provider; this app has one
  provider and a tested fallback chain. The model is a `profile.yml` setting,
  shown in the answer footer.
- **`/` opens the palette only from an empty composer.** Live Crush shows
  "/ or ctrl+p commands" while the editor is empty and drops the `/` hint as
  soon as text is typed, so `/` inside a question stays literal. We adopt
  exactly that. There are no typed slash commands: the earlier `/limit N`
  becomes a palette command ("Set character limit…").
- **No full ASCII logo** in chat. The dashboard has its own brand. The
  compact header uses the existing dashboard wordmark in the same one-line
  diagonal layout.
- **Colors come from our theme tokens**, not Crush's palette, to stay
  consistent with the rest of the dashboard.

## J. Tests added by this review

Added to `answers_test.go`:
- Compact mode switches at width < 120 or height < 30. `ctrl+d` toggles the
  overlay only in compact mode.
- `shift+enter` and `ctrl+j` insert a newline; `enter` sends; `alt+enter` is
  not bound.
- `ctrl+o` launches `$EDITOR` through `tea.ExecProcess` and puts the edited
  text back (fake editor script).
- `ctrl+p` palette lists the actions and runs "Shorten" against the focused
  answer.
- A notification replaces the hints and clears after its TTL. The error type
  uses the error indicator style.
- A paste over 10 lines offers the batch split; 10 lines or fewer inserts
  normally.
- The answer footer shows model · duration · sources · warning count, and
  `space` expands the sources.
- User vs. assistant message prefixes (border present or absent, focused
  thicker) at each width.
- The markdown render cache is hit when only focus changes.
- Landing readiness badges show for evaluation and research present,
  missing and pending.

Update to Task 10's key list: remove `alt+enter`, `ctrl+s` shorten and
`/limit` (moved to the palette); add `ctrl+o`, `ctrl+p`, `/` (empty composer
only), `ctrl+d`, `ctrl+g`.

## K. Live check (Crush running, one short prompt)

What the running app showed that the source reading missed or got wrong:

| Observed live | Change to the plan |
|---|---|
| In the wide layout the **logo sits at the top of the sidebar**, not in a one-line header. The chat column has no header at all. The one-line diagonal header is compact mode only. | Wide: the sidebar starts with the wordmark + `╱` fill, then Title · Company · score. Compact (<120×30): the one-line header from H. |
| The sidebar shows an **auto-generated session title**, the model, **context usage ("1% (16.3K) $0.00")**, then ruled sections (Modified Files, LSPs, MCPs), each reading "None" when empty. | Sidebar: short question title (the question text, truncated; no extra model call), model, **prompt size vs. `MAX_PROMPT_CHARS`** (e.g. "31% of context"), then ruled sections Questions / Sources / Warnings with "None" empty states. |
| The **info line** is `◇ <model> via <provider> in 1s` followed by a `───` rule filling the column, which visually closes the reply. | Footer: `◇ gemini-3.5-flash-lite in 3.2s · 2 sources · ⚠ 1 ───…`, rule to width. |
| A **focused assistant message** gets a `▌` bar down every line of the body; the info line stays outside the bar. The user message keeps its thin `│`. | Same: `▌` in `t.Green` on body lines only. |
| The **unfocused composer** swaps its `>` prompt for `:::` on every line; the placeholder is "Ready...". | Composer prompt `>` when focused, `:::` when not; placeholder "Paste an application question…". |
| **Help hints change with focus**: the editor shows `tab focus chat • / or ctrl+p commands • …`; the chat shows `tab focus editor • ↑↓ scroll • shift+↑↓ scroll one item • b/pgup page up …`. | The hint bar is built per focus mode (C10), not one static list. |
| **Full help (`ctrl+g`)** is a multi-column grid replacing the hint bar: `u`/`d` half page, `b`/`f` page, `g`/`G`, `shift+↑↓` one item, `c/y` copy, `esc` clear selection, `l/→` focus sidebar, `ctrl+n` new session, `ctrl+s` sessions. | Adopt the grid and these scroll keys. `ctrl+n` = new question, `l/→` focuses the sidebar question list (as well as `ctrl+s`). |
| **Palette:** centered bordered box, "Commands" title with `╱` fill, a "Type to filter" input, shortcuts right-aligned, footer `tab switch selection • ↑/↓ choose • enter confirm • esc cancel`. Includes "Toggle Sidebar". | Same layout; add "Toggle Sidebar" and show shortcuts beside each command. |
| `shift+tab` switches **mode** (Crush's agent modes). | Not applicable. `shift+tab` stays reverse focus (C10). |
| A short **reasoning summary** is shown above the reply. | Not applicable (no thinking output from our calls); skip. |

Tests added for K (`answers_test.go`): `/` opens the palette only when the
composer is empty; hint text differs between editor and chat focus; the
composer prompt is `:::` when unfocused; the wide layout puts the wordmark in
the sidebar and compact mode puts it in the header; the sidebar shows the
context percentage and "None" empty states; `u`/`d`/`b`/`f` scroll the
transcript.
