# Application Answer Chat — Design Spec

Status: **Proposed, not implemented** (2026-09-17)
Estimated size: medium. MVP in 1–2 focused sessions; polish in 1–2 more.

## 1. Problem

Application forms ask free-text questions ("Why do you want to work here?",
"Describe a time you…", "What are your salary expectations?"). These answers
can make or break an application, and they need three things the app
already has but does not combine for this purpose:

- the **recruiter's perspective** (`evaluate_recruiter.md`, the stored
  `_evaluation` for the role: fit, gaps, blockers);
- **company research** (`ResumeEngine.research_company()` and its 90-day cache);
- the candidate's **voice and verified record** (voice anchors, narrative,
  bullet bank, verified tools/metrics/projects).

## 2. Goals / Non-goals

**Goals**
- From a specific job, open a chat, paste an application question, and get a
  draft answer grounded in that job, that company and the candidate's record.
- Follow-ups ("shorter", "less formal", "use the Treering project instead").
- Answers stay per job and are reopened later.
- Look like the rest of the app: Charm/Bubble Tea, theme tokens, Crush-like
  layout.

**Non-goals (v1)**
- Auto-filling or submitting application forms.
- Browser extension or scraping questions from the ATS page.
- General-purpose chat not attached to a job.
- Multi-model routing or tool-calling agents.

## 3. User flow

1. **Entry points**
   - Jobs screen: new key `[a]` "Answer application questions" on the
     selected row.
   - Pipeline screen: same key on an application row.
   - CLI menu, Build Documents → "One Role" → "Application Answers" (picks
     a role, then launches the dashboard straight into the chat screen).
2. **Chat screen**
   - Header: role title · company · score badge · research source tier.
   - Scrollable transcript (Glamour-rendered markdown).
   - Multi-line input at the bottom; `enter` sends, `alt+enter` newline.
   - Optional character limit per question (`/limit 500`), shown as a live
     counter against the latest answer.
3. **Actions on an answer**: `c` copy to clipboard, `r` regenerate,
   `s` save as final, `esc` back.
4. On reopen, the saved transcript and "final" answers are shown.

## 4. Architecture

```
Go chat screen (dashboard/internal/ui/screens/answers.go)
   │  spawns per turn (or a long-lived process, see §7)
   ▼
python scripts/application_answers.py  (JSON in on stdin, NDJSON out)
   │
   ├─ jd_source.resolved_jd(job)        → works for files AND db-only ids
   ├─ jd_manager.read_jd_text()         → never raw file reads
   ├─ jd_manager.read_evaluation()      → recruiter view of the fit
   ├─ ResumeEngine.research_company()   → cached company context
   ├─ voice anchors + narrative         → tone
   ├─ vector_store.search_bullet_bank() → evidence relevant to the question
   └─ gemini_client.generate()          → answer (key pool, fallbacks)
```

Follows existing rules: the dashboard never reads SQLite (the Python side
does all data access), and job ids go through `jd_source`.

### 4.1 Python: `scripts/application_answers.py`

Functions:
- `build_context(jd_path_or_id) -> AnswerContext`: collects the pieces above
  once per session, trimmed to a token budget (question-relevant bullets
  via vector search, top N; research summary only, no raw pages).
- `answer(context, history, question, limit=None) -> AnswerResult`
- `check_grounding(answer, context) -> list[Violation]`: see §6.
- `save_answers / read_answers`: persistence, see §5.
- CLI: `python scripts/application_answers.py turn` reads one JSON request
  on stdin and writes NDJSON events: `{"type":"status"}`, `{"type":"chunk"}`
  (if streaming), `{"type":"answer", "text", "warnings":[...]}`,
  `{"type":"error"}`.

### 4.2 Prompt: `resume-engine/prompts/answer_application_question.md`

Sections, in order:
1. Role: "You are the candidate, writing with a hiring recruiter's eye."
2. `=== JOB DESCRIPTION ===`
3. `=== RECRUITER ASSESSMENT ===`: strengths, capability gaps, experience
   blockers from `_evaluation` (how to position gaps honestly, not hide them).
4. `=== COMPANY ===`: mission, products, values, `vocabulary_substitutions`.
5. `=== CANDIDATE EVIDENCE ===`: retrieved bullets + verified metrics only.
6. `=== VOICE ===`: anchors and style rules.
7. Rules: use only facts from the evidence; never invent numbers, employers
   or tools; answer the question asked; respect the character limit; for
   compensation questions, use the configured floor and
   `compensation.py`'s parse of the posting, and say when pay is unstated.
8. `=== CONVERSATION ===` + the new question.

Keep it field-neutral (same rule as `tailor_resume.md`): no profile-specific
vocabulary in the prompt file.

### 4.3 Go: `dashboard/internal/ui/screens/answers.go`

- Components: `bubbles/viewport` (transcript), `bubbles/textarea` (input),
  `bubbles/spinner`, Glamour renderer, `lipgloss` with theme tokens only
  (`go run ./tools/lint_colors.go`).
- Crush-like layout: a slim header bar, messages as left-bordered blocks
  (user = `t.Overlay` border, assistant = `t.Mauve` border), a status line
  showing the model and counters, a footer key legend.
- Handles `tea.WindowSizeMsg`, the 80x24 minimum (35x12 mobile), and
  `RESUME_BUILDER_MOTION=reduced` (no spinner animation).
- Truncation with `ansi.Truncate(..., "…")`.
- Launch: a new `-view answers -job <id>` flag on the dashboard binary, so
  the CLI menu can open it directly.

## 5. Data model

Following the JD JSON metadata convention (`_evaluation`, `_liveness`…):
`_application_answers` on the JD, with a
`jd_manager.save_application_answers` / `read_application_answers` pair
(an allowlist, like `save_evaluation`).

```json
"_application_answers": {
  "updated_at": "2026-09-17T12:00:00",
  "items": [
    {
      "question": "Why do you want to work at Acme?",
      "char_limit": 500,
      "final": "…",
      "history": [
        {"role": "user", "text": "…"},
        {"role": "assistant", "text": "…", "warnings": []}
      ]
    }
  ]
}
```

- `read_jd_text()` already strips underscore keys, so answers never leak into
  other prompts.
- Database-only jobs: saved through `jd_source.resolved_jd()` sync-back.
  Check the "sync-back overwrites status" trap noted in CLAUDE.md.
- Tailoring moves JDs to `completed/`: answers travel with the file.

## 6. Accuracy guardrails (the part that matters most)

Deterministic checks after generation, reusing existing ones where possible:
- **Foreign numbers:** any multi-digit number not present in the evidence,
  JD or research → warning (same idea as `rewrite_bullets.foreign_numbers()`).
- **Unknown tools:** tool names not in the verified ledger → warning
  (reuse the resume hallucinated-tool check).
- **Employer names:** only employers from the profile roster.
- **Vague magnitudes:** reuse `validate_resume._check_vague_magnitudes()` as
  a soft nudge.
- **Length:** over `char_limit` → one automatic shorten retry, then a warning.

Warnings show inline under the answer (a `t.Peach` "⚠ check: 38% not in your
record"); v1 never silently rewrites. One automatic retry that states the
violation, the same shape as the resume fix loop.

## 7. Performance & cost

- Build context once per chat session and cache it in a temp JSON file keyed
  by job id; later turns send only history + question.
- MVP: one Python process per turn (~1–2s startup) plus a spinner.
  Upgrade path: long-lived process speaking NDJSON over stdin/stdout.
- Model: `gemini-3.5-flash-lite` default via `generate()` (not a scoring
  call, so the `SCORING_FALLBACKS` rule does not apply). Company research
  hits the cache after the first time.
- Roughly one API call per turn, plus research on a cache miss.

## 8. Testing

- `tests/test_application_answers.py`: context assembly (mocked
  `gemini_client.generate`), grounding checks with fabricated numbers/tools,
  save/read round-trip, db-only job path under `isolate_for_tests`, NDJSON
  protocol. Identities from `tests/persona.py`. No network (the test guard
  fails closed).
- Assert every save key goes through the allowlist.
- Go: `answers_test.go` for layout at 80x24 and 35x12, key handling, NDJSON
  parsing, warnings rendering; add to `lint_colors`.
- Manual: VHS tape `dashboard/tapes/answers.tape`.

## 9. Phases

| Phase | Scope | Size |
|---|---|---|
| 1. Engine | `application_answers.py`, prompt, grounding checks, persistence, tests; usable via CLI | 1 session |
| 2. Chat screen | Go screen, `[a]` entry points, spinner, copy/save, char counter | 1 session |
| 3. Polish | streaming, long-lived process, "reuse a similar past answer" (embed saved questions), per-question-type hints (salary, sponsorship, "why us") | 1–2 sessions |

## 10. Decisions (resolved 2026-09-17)

1. **Clipboard:** OSC 52 first (Bubble Tea v2 `tea.SetClipboard`), which works
   over SSH and in most modern terminals. Also try the native tool
   (`pbcopy` / `wl-copy` / `xclip` / `termux-clipboard-set`) when present.
   Always offer `p` "plain view", which shows the answer unwrapped and
   unstyled for manual selection. A copy never fails silently: the status
   line says which method ran.
2. **Final answers and voice:** yes, but opt-in and curated. Saving a final
   answer asks "Add to your answer library?" (default no). Library entries
   are appended as rows to the existing
   `knowledge_base/application-answers-index.csv` (the file
   `build_voice_anchors.py` already projects into `voice-anchors.md`), with
   `Quote Worth Pulling` filled only when the user picks a line. Model-written
   text never feeds the voice automatically, or the voice drifts toward the
   model's voice.
3. **Answer library:** the same CSV, not a new store. It is already
   per-profile, in the knowledge base (synced), and curated. Phase 3 embeds
   the `Prompt / Topic` column to suggest "You answered something similar for
   Acme" as a starting point, which is shown to the user and not pasted silently.
4. **Sensitive questions:** a deterministic classifier (`classify_question`)
   runs before any model call. **EEO/self-identification** questions
   (disability, veteran, race/ethnicity, gender, sexual orientation, age)
   return a fixed notice with no draft. **Legal/eligibility** questions
   (work authorization, sponsorship, criminal history) return the value from
   `profile.yml` if one is set, otherwise "answer this yourself". **Salary**
   uses the compensation context (floor + posting parse) and drafts a range
   strategy, never a number below the configured floor.
5. **(New) Question types.** The same classifier tags `why_company`,
   `why_role`, `behavioral` (adds `search_behavioral_stories`), `salary`
   (adds `search_negotiation_levers`), `experience_with_tool` (checks the
   verified ledger first, so the answer honestly says "adjacent experience" when
   the tool is not in it, like the existing Salesforce Marketing Cloud
   answer), and `general`.
6. **(New) Process model:** one process per turn for Phase 2. The context is
   cached on disk, so startup cost is only Python import time.
