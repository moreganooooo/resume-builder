# Master Audit Document — Comprehensive Multi-Persona System Audit

**Date:** 2026-08-16
**Method:** 3-pass audit (Scout & Survey → Deep Verification → Blind-Spot Probe) per `assets/comprehensive_audit.md`, executed inline against the repository at commit `b49be9bf` (working tree clean except this audit's own output).
**Scope:** All 9 domains, all 7 personas. Every finding below was verified by reading the actual source at the cited file:line — this is not a generated/hypothetical list.

---

## ⛳ RESOLUTION STATUS — verified 2026-08-23 (read this before acting on anything below)

Every finding below was re-checked against live code on 2026-08-23. **This
document is a 2026-08-16 snapshot; most of it is closed.** It had already
caused two rounds of duplicated re-triage because nothing recorded that.

| Status | Findings |
|---|---|
| ✅ **Closed** | F2 · F3 · F4 · F5 · F6 · F9 · F10 · **F11** · F13 · F14 · F15 · F16 · F17 · F18 · **F20** · F22 |
| ⬜ **Open** | **F1** (god module) · F12 (minor) · F19 · F21 |
| 🚫 **Won't fix, by design** | F7 (POSIX-only locking) · F8 (no keyring) |

**Notable closures, with the evidence:**
- **F11 (the only Critical)** — fixed *and* pinned. `vector_store.py`'s
  row-count branch now re-embeds instead of returning early, and
  `test_remediation_protections.py::test_vector_store_row_count_mismatch_triggers_reembed`
  names F11 in its docstring.
- **F9 / F22** — the grader is no longer arithmetically unpassable.
  `_check_bullet_star_quality` gained `QUALITATIVE_EVIDENCE_PHRASES` and a
  graduated penalty: no metric *and* no qualitative evidence costs 40, but
  qualitative evidence with no number costs only 15, so such a bullet scores
  85 and passes.
- **F10** — `company_research._extract_visible_text()` now strips
  `_BOILERPLATE_TAGS` and `_BOILERPLATE_SELECTORS`.
- **F6** — `db.py` has an explicit `wal_checkpoint(TRUNCATE)` whose docstring
  names the Syncthing staleness gap this finding raised.
- **F18** — both instances closed. `test_star_quality_grader.py` now covers
  the middle case (strong verb + outcome, no metric) it structurally missed.

**F20 was closed on 2026-08-23, and it had gone live in the meantime.** The
audit filed it as "aspirational, not shipped" because mobile Lite Mode did not
exist yet. `requirements-lite.txt` has since shipped and deliberately omits
pandas/numpy — while `orchestrator.py` still imported both at module level, and
every entry point imports `orchestrator`. A Lite install therefore died on plain
`resume` with `ModuleNotFoundError: No module named 'numpy'`, before printing
anything. Both imports are now lazy in the seven functions that use them (plus
`rewrite_bullets.py`, `bullet_bank_menu.py`, `bootstrap_profile.py`, all reached
transitively), `pd.DataFrame` annotations are quoted so they do not evaluate at
def time, and `tests/test_lite_mode_imports.py` blocks both packages at import
and asserts every entry point still loads. **That test is the only thing
standing between a future module-level `import pandas` and a wholly broken Lite
Mode — the failure is invisible on a normal desktop, where both are installed.**

**Still open, and why:**
- **F1** — `orchestrator.py` was 4,205 lines at audit time and is now
  **5,507**. The only Major left, and it grew. Needs a planned decomposition,
  not a patch.
- **F12** — Minor. Re-embedding prints progress via `cli_art` now, but the call
  is still synchronous.
- **F19 / F21** — documentation integrity in `docs/gemini_files/`, not code.
  `refactoring_plan.md` still carries 22 `[COMPLETED]` markers including the two
  this audit disproved (the icon default, and pandas/numpy removal — the second
  is now *half* true: removed from the import path, still used inside
  functions), and still contradicts `audit_report.md` on mobile compatibility.

---

## How to read this document

Each finding has:
- **ID** — stable reference used by `onboarding_and_remediation_guide.md`.
- **Persona(s)** — which of the 7 audit personas this matters to.
- **Category** — domain tag from the audit's 9 subsystems.
- **Severity** — Critical (data loss / security / silent corruption) · Major (real bug, wrong behavior, no data loss) · Minor (design gap, hygiene, low-probability edge case).
- **Root cause**, **Impacted files/lines**, **Architectural impact**.

Findings are numbered continuously across domains (F1–F15). A **Verified Clean** section documents things the audit explicitly asked about that were checked and found to already be correctly implemented — reporting "no bug here" with evidence is as much a part of an honest audit as reporting bugs. A **Coverage Limitations** section at the end lists what this pass did *not* reach, per the audit's own Pass-3 mandate to name blind spots.

---

## Domain 1 — Big-Picture Architecture & Technical Debt

### F1. `orchestrator.py` is a 4,205-line god module; `ResumeEngine` alone is a ~2,600-line god object
- **Persona(s):** 🏗️ Senior Staff Architect
- **Severity:** Major
- **Files/lines:** `scripts/orchestrator.py:1412–4035` (`class ResumeEngine`); 64 top-level functions and 22 Pydantic schema classes share the same file.
- **Root cause:** Organic growth — prompt construction, PDF-result parsing, checkpoint-review UI, trim/widow repair logic, scoring math, company-research formatting, and pipeline orchestration were all added as methods on one class or functions in one module, rather than being split as the pipeline grew.
- **Architectural impact:** Every schema class (`ResumeSchema`, `JDKeywordSchema`, `FitEvaluationSchema`, `CoverLetterSchema`, `CompanyResearchSchema`, etc.) lives inside `orchestrator.py`, so any other module that only wants a *type* (e.g. for a future API layer, or `db.py` wanting to validate a job record) must import the entire 4,205-line module and its full dependency chain (`pandas`, `numpy`, `requests`, `questionary`, `pydantic`, `subprocess`, `dotenv`). This is the exact "God object" pattern the audit's architecture persona was asked to search for.

### F2. Dead module-level `API_KEY` in `orchestrator.py` recreates the exact stale-credential hazard its own comment warns about
- **Persona(s):** 🏗️ Architect, ⚡ SRE
- **Severity:** Minor
- **Files/lines:** `scripts/orchestrator.py:52` — `API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")`, immediately below a 10-line comment (lines 22–32) explaining that `gemini_client.py` used to read the key once at import time, silently latching onto a stale/wrong key across profile switches, and that `gemini_client._get_auth_headers()` was built specifically to fix this by resolving `GEMINI_API_KEY` **per call**.
- **Root cause:** Leftover from before the dynamic-credential fix was built; `API_KEY` is assigned once here and never referenced again anywhere in the file (verified via `grep -n "API_KEY" scripts/orchestrator.py` — only the definition line matches).
- **Architectural impact:** Purely cosmetic today (dead code), but it is a landmine: a future contributor skimming `orchestrator.py` who wants "the API key" has an unused module constant sitting right there, named exactly like the thing the comment above it says not to do. Using it would silently reintroduce the original bug.

### F3. `validate_resume.py`'s hallucination-guard falls back to a hardcoded `profiles/morgan/` path on any exception
- **Persona(s):** 🏗️ Architect, 🔒 Security/Privacy
- **Severity:** Major
- **Files/lines:** `scripts/validate_resume.py:704–721` (`_check_hallucinated_tools`)
  ```python
  try:
      import profile_paths
      kb_dir = profile_paths.get_kb_dir()
  except Exception:
      script_dir = os.path.dirname(os.path.abspath(__file__))
      project_root = os.path.dirname(script_dir)
      kb_dir = os.path.join(project_root, "profiles", "morgan", "knowledge_base")
  ```
- **Root cause:** A safety-net fallback was written for the case where `profile_paths.get_kb_dir()` throws, but the fallback hardcodes the single-user-era profile name instead of failing loudly.
- **Architectural impact:** Directly violates CLAUDE.md's own stated architecture rule ("`scripts/profile_paths.py` is the single source of truth for every profile-scoped path; route new code through it rather than hand-rolling a `profiles/<name>/...` join"). For any profile other than `morgan`, a transient failure in `get_kb_dir()` (e.g. a broken `RESUME_PROFILE` env var, an import hiccup) makes the hallucination checker silently validate against a *different person's* `verified_tools.json`/`profile.yml` — a profile-isolation leak, not merely a missing feature. The bare `except Exception` also means this never surfaces to the user.

---

## Domain 2 — State Persistence, Concurrency & Syncthing Synchronization

### F4. `data.db` goes stale on the most common status transition: moving a JD to `completed/`/`expired/` doesn't re-sync the DB
- **Persona(s):** 🏗️ Architect, ⚡ SRE
- **Severity:** Critical
- **Files/lines:** `scripts/jd_manager.py:88–124` (`_sync_jd_to_db`) vs. `scripts/jd_manager.py:285` (`move_jd_to`)
- **Root cause:** `_sync_jd_to_db()` is called from `save_evaluation`, `save_research`, `save_coverage`, `save_liveness`, and `save_application_status` (5 call sites, confirmed via `grep -n "_sync_jd_to_db(" scripts/jd_manager.py`) — but **not** from `move_jd_to()`, the function that physically relocates a JD's file into `jds/<profile>/completed/` or `expired/` per CLAUDE.md's documented lifecycle. `_sync_jd_to_db`'s own status inference partly depends on the file path (`"completed" in jd_path`, `"expired" in jd_path` — lines 98–103), so it needs to run *after* the move to pick up the new status, but nothing triggers it then.
- **Architectural impact:** This is exactly the "dual-source-of-truth bug" the audit's Domain 2 asked to check for. A JD can sit in `jds/<profile>/completed/` on disk indefinitely while `data.db`'s `jobs.status` column still reads `pending` or `evaluating` — silently, with no error. Any future feature built against `data.db` (the dashboard, a reporting view, `migrate_filesystem_to_db.py`'s inverse) will see wrong data for every JD that was moved without a subsequent `save_*` call.

### F5. DB-sync failures are swallowed at `debug` level with no user-visible signal
- **Persona(s):** ⚡ SRE, 🏗️ Architect
- **Severity:** Major
- **Files/lines:** `scripts/jd_manager.py:123–124`
  ```python
  except Exception as e:
      logging.debug(f"SQLite db sync skipped/failed for {jd_path}: {e}")
  ```
- **Root cause:** The DB sync was deliberately made best-effort (so a broken `data.db` never blocks the JSON-file pipeline, which is reasonable), but the failure is logged at `debug` — invisible in default output — rather than `warning`.
- **Architectural impact:** A disk-full condition, a locked/corrupted `data.db`, or a schema error would make the SQLite mirror silently stop updating forever while the rest of the tool keeps working normally. Nothing in `resume doctor` (per CLAUDE.md, the designated environment-health entry point) currently surfaces this — see F13 for the related test-coverage gap on `db.py` itself.

### F6. WAL sidecar exclusion avoids sync *corruption* but creates a silent sync *staleness* gap
- **Persona(s):** 🏗️ Architect, ⚡ SRE
- **Severity:** Minor
- **Files/lines:** `scripts/profile_paths.py:216–244` (`sync_roots`, `_SYNC_STIGNORE_CONTENT`); `scripts/db.py:22–30` (`get_db` sets `PRAGMA journal_mode=WAL`)
- **Root cause:** `data.db` lives under the `"profile"` Syncthing sync root, and `.stignore` correctly excludes `data.db-wal`/`data.db-shm` — the right call, since syncing a live WAL journal's 3 files independently is a real corruption risk (the same class of hazard CLAUDE.md already documents for `.git/`). But excluding `-wal` means any write sitting in the local WAL that hasn't been checkpointed back into `data.db` **never reaches the second machine** — not corrupted, just invisible.
- **Architectural impact:** Today this is mostly masked because every `db.py` call site (`upsert_job`, `get_jobs_by_status`, `update_job_status`) opens its own connection and closes it after each operation (`close_conn` pattern), and a clean SQLite close in WAL mode does checkpoint. But there's no explicit `PRAGMA wal_checkpoint` anywhere, so a crash mid-write, or any future long-lived connection (e.g. a dashboard feature that keeps a connection open across a session), would silently desync the two machines with zero warning.

### F7. (Minor, cross-platform) `fcntl`-based CSV locking degrades silently — and correctly — on native Windows, but that's worth naming
- **Persona(s):** 🏗️ Architect (cross-platform)
- **Severity:** Minor
- **Files/lines:** `scripts/jd_manager.py:611–625`, `730–737`
- **Root cause:** `fcntl` is POSIX-only; the code already wraps both `flock`/`unlock` calls in `try/except (ImportError, OSError): pass`, so it degrades gracefully rather than crashing.
- **Architectural impact:** On native Windows (PowerShell/CMD, not WSL2 — which the audit explicitly lists as a target platform), concurrent CSV appends to `jd_tracker_log.csv`/`applications.md` lose their locking protection entirely. Low real-world risk for a single-user CLI, but worth a one-line doc note since the audit's cross-platform goals name native Windows explicitly.

---

## Domain 3 — Security, Secrets Hygiene & Privacy

### F8. No OS keyring/vault integration — secrets are plaintext files by design
- **Persona(s):** 🔒 Security/Privacy
- **Severity:** Minor (given documented, single-user context)
- **Files/lines:** `scripts/profile_paths.py:164–167` (`.env` path doc), `scripts/scan_linkedin.py:74` (`.linkedin_cookie` plaintext file)
- **Root cause:** Deliberate, documented design (CLAUDE.md's "Multi-computer sync" section) — `.env` and `.linkedin_cookie` are plaintext so Syncthing can propagate them device-to-device without the user hand-typing an API key on every machine.
- **What was verified clean:** Both are correctly covered by the blanket `profiles/*/` rule in `.gitignore` (line 67), so there is **no** git-leak risk — a live LinkedIn session cookie or Gemini API key cannot be accidentally committed. No accidental `print()`/log exposure of raw cookie or key values was found in `scan_linkedin.py`, `menu.py`, or `bootstrap_profile.py` (all references print masked placeholders like `g_state=...; SESSION_ID=...`).
- **Architectural impact:** The `keyring` module (which the audit's security persona explicitly asks about) is genuinely absent — secrets sit as plaintext on disk on both ends of the Syncthing link, readable by any local process/user with filesystem access. Reasonable for a personal tool on trusted machines; worth naming because the audit asked directly.

---

## Domain 4 — Scrapers, Liveness & Third-Party Reliability

**No new findings — see Verified Clean below.** This subsystem was already hardened against the exact failure modes the audit asked about.

---

## Domain 5 — Resume Tailoring, Google XYZ & Recruiter Impact

### F9. The STAR/XYZ quality grader makes it *mathematically impossible* for a purely qualitative bullet to pass — the exact over-rigid-metric issue the audit named
- **Persona(s):** 🎯 Recruiter/Hiring Manager, 🤖 AI/ML Engineer
- **Severity:** Major
- **Files/lines:** `scripts/validate_resume.py:833–959` (`_check_bullet_star_quality`), specifically the scoring at lines 931–958 and the pure-regex metric extractor at `_extract_metric_signatures` (lines 420–447)
- **Root cause:** Each bullet starts at 100 and loses points on three independent checks: verb (−30), metric (−40), outcome language (−30); a violation is raised below 70. `_extract_metric_signatures()` only matches numeric patterns (`_METRIC_PATTERN`) with no qualitative-evidence fallback. Do the arithmetic: a bullet with a perfect verb and perfect outcome language but **zero numbers** scores exactly 100 − 40 = **60**, and 60 is always < 70. There is no combination of verb quality and outcome language that can compensate for a missing number.
- **Architectural impact:** This directly contradicts the grader's own docstring, which frames itself as implementing "the Google XYZ formula (Accomplished [X] as measured by [Y] by doing [Z])" — in the real XYZ framework, "Y" is "as measured by," which can be qualitative evidence (a promotion, a testimonial, a scope change), not strictly a percentage or dollar figure. Every genuinely qualitative-but-real accomplishment in a candidate's history gets auto-flagged as a "STAR structure" violation and pushed back into the LLM rewrite loop, which can only respond by inventing or contorting a number — the exact hallucination risk the audit's Domain 5 ask was worried about elsewhere.

### F10. Scraped company-site text isn't stripped of nav/boilerplate before reaching the LLM prompt
- **Persona(s):** 🤖 AI/ML Engineer, 🎯 Recruiter
- **Severity:** Minor
- **Files/lines:** `scripts/company_research.py:58–63` (`_extract_visible_text`)
  ```python
  def _extract_visible_text(html: str) -> str:
      soup = BeautifulSoup(html, "html.parser")
      for tag in soup(["script", "style"]):
          tag.decompose()
      text = soup.get_text(separator=" ")
      return re.sub(r"\s+", " ", text).strip()
  ```
- **Root cause:** Only `<script>`/`<style>` are stripped; `<nav>`, `<header>`, `<footer>`, `<aside>`, and cookie-consent banner containers (OneTrust/Cookiebot-style `<div>`s) are left in and flattened into the same text blob.
- **Architectural impact:** The company-research block that feeds `tailor_resume.md`/`research_company.md` prompts can be diluted with boilerplate ("Home About Careers Contact Privacy Policy Accept All Cookies...") ahead of or interleaved with the actual company content, wasting prompt attention exactly as the audit's Domain 7 concern about "attention degradation" describes, and specifically the boilerplate-noise issue Domain 5 named by name.

### What was verified clean in Domain 5
- `_escape_typst()` (`scripts/render_typst.py:20–31`) correctly escapes all of Typst's special markup characters (`#`, `$`, `@`, `_`, `[`, `]`) on every field it's applied to (name, tagline, contact fields, summary, skills, job fields, bullets, education). One minor gap noted but not filed as a standalone finding given how unlikely it is: literal backslashes in source text aren't escaped before the function adds its own backslash-escapes, which could theoretically produce a malformed escape sequence if a JD or resume field ever contained a raw `\`.
- `render_html.py` uses stdlib `html.escape` (imported explicitly), consistent with `render_typst.py`'s approach — no unescaped-injection path found in either renderer during this pass.

---

## Domain 6 — UI/UX, TUI Ergonomics & Charm.sh Design

**No new findings.** See Verified Clean — this domain was already well-hardened, likely due to the prior `.impeccable/critique/` design passes visible in the repo (`2026-08-11`, `2026-08-15`).

---

## Domain 7 — Algorithms, Vector RAG & Prompt Engineering

### F11. Vector-search cache invalidation is unreachable on the single most common bullet-bank edit
- **Persona(s):** 🤖 AI/ML Engineer, ⚡ SRE
- **Severity:** Critical
- **Files/lines:** `scripts/vector_store.py:35–72` (`search_bullet_bank`)
  ```python
  if "Bullet Point" not in df.columns or len(df) != len(embs):
      return []                                    # <-- early return, no re-embed

  if os.path.exists(meta_path):
      ...
      current_sha = bullets_sha(df["Bullet Point"].fillna("").tolist())
      if meta.get("bullets_sha") != current_sha:
          ... embed_bullet_bank.main() ...          # <-- the actual auto-reembed logic
  ```
- **Root cause:** There are two independent staleness checks: a row-count check (line 55) and a content-hash check (lines 58–72). Only the hash check triggers re-embedding. But adding or removing a bullet — the single most common real edit, via the mine/audit bullet-bank workflow this whole product is built around — changes the row count, hits the early `return []` on line 56, and **never reaches the hash-based auto-reembed logic a few lines below that was specifically written to handle exactly this case.**
- **Architectural impact:** After any bullet is added or removed from the bank, vector RAG search for that profile silently and permanently breaks (falls back to `[]`/keyword search) until someone manually reruns `embed_bullet_bank.py` — there's no error, no warning, just quietly worse bullet retrieval for every future tailoring run. This is precisely the "automatic cache invalidation triggers when bullet bank CSV hashes change" mechanism the audit's Domain 7 asked to verify — the mechanism exists but is unreachable in the common case. Compounded by F13 (zero test coverage on this file), this would ship silently.

### F12. (Minor) Auto-reembedding is synchronous and blocking with no progress feedback
- **Persona(s):** 🧠 ADHD Job-Seeker, ⚡ SRE
- **Severity:** Minor
- **Files/lines:** `scripts/vector_store.py:64–70`
- **Root cause:** When the hash mismatch *does* correctly trigger (same-row-count content edits), `embed_bullet_bank.main()` runs inline and blocking, calling the Gemini embedding API for the bank, with only a bare `print()` on failure and no progress indicator on the success path.
- **Architectural impact:** Whatever workflow calls `search_bullet_bank()` mid-pipeline would appear to "hang" for the duration of a full re-embed, directly against the ADHD-persona's "real-time progress feedback" requirement — especially notable since this same codebase already has a good pattern for this (the liveness-check subprocess streams JSON progress events — `scripts/liveness.py:193–207`) that just wasn't reused here.

---

## Domain 8 — Test Suite, SRE Resilience & Error Recovery

### F13. Zero test coverage on the four newest, highest-risk modules
- **Persona(s):** ⚡ SRE
- **Severity:** Critical
- **Files/lines:** `scripts/db.py`, `scripts/render_typst.py`, `scripts/vector_store.py`, `scripts/migrate_filesystem_to_db.py` — confirmed via both exact-name and prefix match against `tests/test_*.py` (67 scripts vs. 105 test files; these 4 have none, exact or prefixed).
- **Root cause:** All four are recent, in-flight additions (new/untracked at the start of this session) — new persistence infrastructure, a new Typst-based PDF engine, a new RAG search module, and a one-way filesystem→SQLite data migration.
- **Architectural impact:** This is the highest-severity finding in the audit specifically *because* of what it's adjacent to:
  - `migrate_filesystem_to_db.py` is a **one-way data migration** over a real user's job-application history — exactly the kind of code where an untested bug means silent data loss or corruption, with no test to have caught it before a real run.
  - `db.py` underlies findings F4–F6 (dual-source-of-truth drift, silent sync failures) — none of that is caught by CI today.
  - `vector_store.py`'s cache-invalidation bug (F11) is a textbook example of a bug a single test (`add a bullet, assert re-embed fires`) would have caught immediately.
  - `render_typst.py`'s escaping logic (verified clean above) has no regression test pinning it down, so a future edit could silently reintroduce an unescaped-character PDF-compile failure.

### What was verified clean in Domain 8
- **`time.sleep()` usage (~30+ call sites across `orchestrator.py`, `rewrite_bullets.py`, `gemini_client.py`, `cluster_bullet_bank.py`, `embed_bullet_bank.py`, scan scripts):** appropriate, not a bug. This is a single-process, sequential batch CLI deliberately rate-limiting itself between LLM/API calls — there's no concurrent request-serving requirement to justify async backoff queues. The Go dashboard TUI correctly isolates any long-running Python subprocess behind `exec.CommandContext` + `tea.Cmd` (`dashboard/internal/ui/screens/jobs.go:361–433`) — async, cancellable via Esc, with streamed stdout progress — so none of this blocking ever freezes the TUI event loop.
- **Circuit breakers exist and are bounded:** `max_fix_attempts = 4` for the validator repair loop (`orchestrator.py:3362`) and `max_trim_attempts = len(trim_instructions)` for the PDF page-budget trim loop (`orchestrator.py:3848`) — matches CLAUDE.md's documented hill-climbing retry design exactly, with clear user-facing messaging when attempts are exhausted.

---

## Domain 9 — Developer Experience & Documentation

### F14. No single-command quickstart exists
- **Persona(s):** 🧠 ADHD Job-Seeker
- **Severity:** Minor
- **Files/lines:** Confirmed absent via `grep -rn "quickstart" README.md CLAUDE.md scripts/resume-cli.sh scripts/menu.py` (zero matches).
- **Root cause:** Onboarding is well-documented (CLAUDE.md's Setup section is thorough) but inherently multi-step: create venv, install Python deps, install Node deps, install Playwright's Chromium, populate `.env`, run `resume doctor`.
- **Architectural impact:** Directly matches the gap the audit's persona 1 explicitly named by command name (`resume quickstart`). Not a bug, but a real, nameable onboarding-friction gap for a new profile/new machine.

### F15. Standard CLI flags (`--version`, `--verbose`, `--dry-run`) are absent from the Click entrypoint
- **Persona(s):** 🏗️ Architect, 🧠 ADHD Job-Seeker
- **Severity:** Minor
- **Files/lines:** `scripts/cli.py` — full flag inventory pulled via `grep -n "@click.option"` (14 options across all subcommands): `--profile`, `--master`, `--output`, `--pick`, `--yes`, `--source`, `--no-verify`, `--refresh`, `--skip-tests`. None of `--version`/`--verbose`/`--dry-run`.
- **Root cause:** Flags were added incrementally per-feature rather than against a standard checklist; `--help` is free via Click so wasn't separately added.
- **Architectural impact:** Minor DX inconsistency. `--profile` also isn't universal — most standalone scripts (outside `cli.py`/`tune_rubrics.py`) rely on the `RESUME_PROFILE` env var instead, which is intentional per CLAUDE.md but means the two mechanisms coexist without a documented rule for which to use where.

---

## Verified Clean (explicitly checked, no issue found)

Reporting these with the same rigor as findings, per the audit's own standard:

| # | Area | What was checked | Result |
|---|---|---|---|
| V1 | Domain 4 | `liveness-core.mjs` classification of HTTP 403/429/5xx/timeouts | Only 404/410 (or explicit expired-body/redirect text) map to `expired`; everything else falls to `uncertain`/`likely_active` and is never destructively moved. Exactly the conservative behavior the audit worried might be missing. |
| V2 | Domain 4 | `generate-pdf.mjs` Playwright child-process error contract | Single top-level `.catch()`, clear stderr message, non-zero exit — checkable by the Python caller. |
| V3 | Domain 6 | Nerd Font / Unicode icon fallback, Python↔Go agreement | `theme.py` resolves `RESUME_BUILDER_ICONS`, passes the resolved name to the Go binary via env var; `dashboard/internal/theme/icons.go` reads the same variable. Both sides agree by construction. |
| V4 | Domain 6 | Hardcoded 80-column terminal width assumption | Not present — `cli_art.py` uses live `console.width` breakpoints (110/130/150 cols) with an explicit comment referencing a prior bug (B22) about fixed widths. Already hardened. |
| V5 | Domain 7 | Scoring-weight math (spot check) | `recruiter_score.yaml` (25+30+20+25=100) and `believability.yaml` (30+25+25+20=100) both sum correctly. Only 2 of ~13 scoring YAMLs spot-checked — see Coverage Limitations. |
| V6 | Domain 8 | Whether SQLite writes use WAL mode / busy_timeout | `db.py:26-27` — `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` both set on every connection. Correct baseline concurrency handling. |
| V7 | Domain 2 | Atomic file locking on CSV appends | `fcntl.flock` used correctly on POSIX (see F7 for the Windows caveat). |
| V8 | Domain 1 | Circular imports / import-time coupling | No evidence of circular-import workarounds (function-local `from scripts.X import Y` patterns) in `orchestrator.py`, `menu.py`, or `cli.py` — plain flat module imports throughout. |

---

---

## Addendum — Empirical Verification & Cross-Reference Against Prior Antigravity/Gemini Sessions

Added after the original pass, per follow-up request: (1) run the suite baseline plus repro scripts for the two Critical findings, (2) cross-reference against recent audit/plan `.md` files in `/Users/morganescott/.gemini/antigravity-cli/brain/` (several prior Gemini/Antigravity sessions worked this same codebase on 2026-08-15/16), (3) watch specifically for hallucinated "complete" claims, and hunt for additional test gaps.

### Baseline test run

```
python -m unittest discover -s tests -v
Ran 1520 tests in 75.516s
OK
```
Clean baseline, zero pre-existing failures.

### F9 repro — empirically confirmed

```
verb ok: spearheaded | metrics found: [] | violation raised: True
STAR/XYZ Quality Grader (Score 60/100) inside [Acme]: Bullet lacks sufficient STAR structure
(reasons: no quantified metric or numeric evidence found). ...
```
A bullet with a strong verb *and* outcome language *and* zero numbers scores exactly 60/100 — never enough to clear the 70 threshold, confirming the "mathematically impossible" claim is not hyperbole.

### F11 repro — empirically confirmed, zero risk to real data

Repro used throwaway copies of the real 844-row bullet bank in a temp directory (never touched `profiles/morgan/`), with `embed_bullet_bank.main` mocked to a call counter rather than hitting the real embedding API:

```
--- Scenario A: row count changed (844 -> 845) ---     [simulates adding a bullet]
search_bullet_bank() returned: 0 results
embed_bullet_bank.main() calls so far: 0   <- bug: re-embed never fires

--- Scenario B: same row count, hash mismatch only ---  [simulates editing a bullet's text]
embed_bullet_bank.main() calls so far: 1   <- this path works correctly
```
Confirms precisely: the add/remove-a-bullet case (the core bullet-bank workflow) silently bypasses re-embedding; the edit-in-place case does not.

### Cross-reference: this audit was not the first one

`future_comprehensive_audit_prompt.md` in the Antigravity brain (session `6b79fddb…`, written 2026-08-16 20:55) is **word-for-word identical** to `assets/comprehensive_audit.md` — the prompt template used to run this whole audit originated from a prior Gemini/Antigravity session. That session (`6b79fddb…`, 18:10–18:12) had already produced its own `master_audit_document.md` (35 findings) and `onboarding_and_remediation_guide.md` against this same codebase, earlier the same day. Tracing the fuller history in that brain directory surfaces at least four separate 2026-08-15/16 sessions that touched this repo (implementation, scoring-engine upgrade, a critical-audit-and-implementation-plan cycle, and this final re-audit) — several of which map directly to real commits:

| Commit | Time | What |
|---|---|---|
| `032153ca` | 12:19:50 | Introduced the Fit/Interview-Odds scoring upgrade — and the "Bayesian probability converter" branding (matches session `7ddbf599…`'s 11:47–12:29 work) |
| `a0eabe8e` | 18:27:54 | **"refactor: remediate core architectural, storage, security, and TUI issues (35-point audit)"** — applies Gemini's `6b79fddb…` remediation matrix. This is the commit that was sitting **uncommitted in the working tree** when this audit's Pass 1 began (explains the `M`/`??` files in the session-start git status) and landed mid-audit. |
| `69f017da` | 18:32:21 | DB connection-lifecycle fix in `db.py`/`migrate_filesystem_to_db.py` |
| `9d32f6f3` | 18:38:27 | Added `tests/test_remediation_protections.py` — regression tests for several of the above fixes |

**Practical implication:** this audit's own Domains 1–9 were conducted against code that already had most of `a0eabe8e` applied, which is why several things Gemini's `master_audit_document.md` flagged (5-way CHECK-constraint IntegrityError, `subprocess.run(["which"...])` on Windows, missing `fcntl.flock`, hardcoded `/usr/local/bin/python3.13`) read as **already fixed** in this document's "Verified Clean" table — those weren't hallucinations, they were real findings from an earlier read that a real commit had since resolved. Directly verified fixed via `git show a0eabe8e` + live-code grep: SQLite CHECK constraint (all statuses present), `shutil.which("typst")`, `fcntl.flock` in `jd_manager.py`, no hardcoded Python path in `doctor.py`, `cli_art.scrub_pii()` (PII redaction), full Typst special-character escaping, and `skills_menu.py`'s Ctrl+C/Esc guards (all `.ask()` calls check for `None` before use) — all confirmed present and correct in the current codebase, each backed by a real test in `tests/test_remediation_protections.py`.

### F16 (NEW) — The "Bayesian" mislabeling fix was incomplete, not hallucinated: one occurrence was fixed, an identical second occurrence wasn't

- **Persona(s):** 🏗️ Architect, 🤖 AI/ML Engineer
- **Severity:** Minor
- **Files/lines:** `scripts/orchestrator.py:2621–2625` (`ResumeEngine.evaluate_fit()` docstring — **not yet fixed**) vs. `scripts/orchestrator.py` inline comment near the `estimated_interview_probability` calculation (**fixed by `a0eabe8e`**, per its diff: `- # D. Advanced Bayesian Probability Converter (piecewise linear interpolation)` → `+ # D. Empirical Score Calibration Converter`)
- **What's still live right now** (confirmed via `grep -n -i bayesian scripts/orchestrator.py`):
  ```python
  def evaluate_fit(self, jd_path: str) -> dict:
      """
      Ultra-Premium grounded two-stage fit evaluation check for a JD.
      Loads profile.yml dynamically to apply custom deal-breaker skips and
      advanced Bayesian calculations in Python.
      """
  ```
- **Root cause:** `a0eabe8e`'s commit message explicitly claims "Terminology Alignment: Updated documentation to reflect Piecewise Probability Scale" — and it did, for the *inline comment* directly above the actual calculation. But the exact same false claim ("Bayesian calculations") also appears in the *docstring* at the top of the same method, ~300 lines earlier in the file, and that occurrence was missed — a partial find-and-replace, not a fabricated fix. Notably, `tests/test_deal_breaker_overrides.py`'s own test method is named `test_bayesian_piecewise_linear_interpolation` with the docstring "Verify the exact piecewise linear mapping..." — even the test suite correctly describes the math as piecewise linear, one file away from source code that still calls it Bayesian in one spot.
- **Architectural impact:** Low — this is a documentation-accuracy issue, not a behavioral bug (`estimated_interview_probability`, `ghost_job_probability`, and `fit_composite_score` are all confirmed, via direct read, to be plain weighted averages and piecewise linear interpolation — zero priors, likelihoods, or posterior updates anywhere in the file). Worth fixing precisely because it's the kind of stale claim that misleads a future contributor (or a future audit) into thinking there's real probabilistic modeling here when there isn't.

### F17 (NEW) — A 5th module has zero test coverage: `skills_menu.py`
- **Persona(s):** ⚡ SRE
- **Severity:** Minor
- **Files/lines:** `scripts/skills_menu.py` — confirmed via `grep -rl "skills_menu" tests/*.py` (zero matches, any naming convention).
- **Root cause:** Never had a dedicated test file written, unlike its sibling `bullet_bank_menu.py`/`bootstrap_menu.py`.
- **Architectural impact:** Minor on its own, but notable because this file contains exactly the kind of edge-case-handling logic (the `.ask() is None` → clean-cancel guard on every prompt, verified correct by direct reading) that's most likely to silently regress without a pinning test.

### F18 (NEW, the most interesting one) — Two independent test suites both test the "it works" path and structurally cannot catch their own bug's edge case
- **Persona(s):** ⚡ SRE, 🤖 AI/ML Engineer
- **Severity:** Major (as a pattern — explains why F9 and F11 both shipped undetected despite adjacent tests existing)
- **Instance 1:** `tests/test_star_quality_grader.py` has exactly two cases — `test_flawless_star_bullet_passes_grader` (verb + metric + outcome, all present) and `test_weak_bullet_lacking_metric_and_outcome_triggers_star_violation` (nothing present). It never tests the middle case — strong verb + strong outcome language + **no metric** — which is exactly the case F9 shows can never score ≥70. The test suite validates both extremes and misses the exact boundary where the bug lives.
- **Instance 2:** `tests/test_remediation_protections.py::test_vector_store_stale_hash_trigger` (added in `9d32f6f3`, the same commit series as this whole remediation) constructs a CSV with exactly 1 row and an `.npy` with exactly 1 embedding row — i.e. it only ever tests the same-row-count / hash-mismatch path (F11's "Scenario B," which works correctly). It never constructs a row-count mismatch (F11's "Scenario A," which is broken). This is confirmed by direct inspection of the test file — the row counts are hardcoded to match.
- **Architectural impact:** Both bugs are one-line-different from a test that already exists and already passes. This is a pattern worth naming explicitly in the remediation guide, not just fixing the two instances: when writing a regression test for "X triggers on condition C," add a sibling test for the most common *real-world* trigger of C, not just the most convenient one to construct.

---

---

## Second Cross-Reference Pass — All 24 `docs/gemini_files/` Session Documents

The full curated set of prior Antigravity/Gemini session outputs (audits, plans, walkthroughs, UX reviews) was read in full and cross-checked against live code. This is broader than the addendum above (which sampled ~9 files from the raw `~/.gemini/antigravity-cli/brain/` directory) — this pass covers all 24 files the user copied into `docs/gemini_files/`.

### Confirmed TRUE (claims that check out against current code — listed so nothing here reads as "everything Gemini said was wrong")

| Claim | Source doc | Verified how |
|---|---|---|
| `gemini_client.py` computes auth headers dynamically per call, not once at import | `resume_builder_critical_audit.md` §2.3 (flagged as a bug), fixed per `implementation_plan.md` | Direct read: `_get_auth_headers()` called at every request site |
| `doctor.py` has a standalone `if __name__ == "__main__":` entry point | `resume_builder_critical_audit.md` §10.2 (flagged as missing) | `grep` confirms present at line 383 |
| `skills_menu.py` cleanly aborts on Ctrl+C/Esc without writing partial records | `resume_builder_critical_audit.md` §11.3 (flagged as broken) | Direct read: every `.ask()` call is guarded with an `is None` check |
| SQLite `CHECK` constraint includes all pipeline statuses (`interview`, `offer`, `rejected`, `discarded`, `skip`) | `audit_report.md` (flagged as broken, IntegrityError claimed) | Direct read of `db.py:44` |
| `fcntl.flock` used for CSV tracker locking | `audit_report.md`, `resume_builder_critical_audit.md` §9.1 (both flagged as missing) | Direct read of `jd_manager.py` |
| `shutil.which("typst")` used instead of `subprocess.run(["which"...])` | `master_audit_document.md` (Gemini's own) §1.4 | Direct read of `render_typst.py:128` |
| `cli_art.scrub_pii()` redacts emails/phones from tracebacks | `resume_builder_critical_audit.md` (flagged as missing), `implementation_plan.md` (proposed) | Direct read + `tests/test_remediation_protections.py::test_pii_scrubbing` passes |
| Typst escaping covers all of `# $ @ _ [ ]` | Multiple docs (flagged as incomplete) | Direct read of `_escape_typst()` + passing test |
| `ensure_writable_dtypes()` pandas dtype workaround exists in `rewrite_bullets.py` | `resume_builder_critical_audit.md` §11.2 | Confirmed present, 3 call sites |
| Liveness `hasApplyControl()` check runs before hard-expired body-pattern matching | `refactoring_plan.md` Step 3.1 | Confirmed via direct read of `classifyLiveness()`'s check order |
| Go test suite passes cleanly | `refactoring_plan.md` #14, `audit_report.md` | **Empirically re-run this session**: `go test ./...` → all `ok`, no failures |
| `doctor.py` + full test suite: 100% pass | `final_ux_visual_polish_pass.md` | **Empirically re-run this session**: 16/16 checks ✓, 1520/1520 tests OK |

### F19 (NEW) — Two of `refactoring_plan.md`'s 20 "[COMPLETED]" dimensions are false, not just stale

Unlike the Bayesian-docstring case (F16, a real partial fix), these two are claims of work that was never done at all:

- **Icon default ("#1 TUI/UX... clean Unicode glyphs as the universal default icon standard... unless `RESUME_BUILDER_ICONS=nerd` is set"):** FALSE for the case that matters — a normal interactive terminal session. Direct read of `theme.py`'s `_resolve_icon_set_name()`:
  ```python
  if sys.stdin.isatty():
      return "nerd"      # <- still the default for real terminal use
  return "unicode"        # only for non-interactive/piped contexts
  ```
  This exactly matches CLAUDE.md's own (unedited) documentation — nerd-by-default, unicode-opt-in — the opposite of what the plan claims to have flipped. (On this machine, `doctor.py` shows `unicode` — but that's because a *persisted per-profile choice* was made at some point, which `_resolve_icon_set_name()` checks before falling back to the isatty default; it doesn't mean the default itself changed.)
- **Pandas/NumPy removal ("#10 Bullet Bank Engine: ...pure Python clustering algorithms", "#13 Dependencies: Pure Python/Go entry points with standard library fallbacks"):** FALSE. `grep -n "^import numpy\|^import pandas" scripts/cluster_bullet_bank.py scripts/orchestrator.py` shows both still unconditionally imported at module level in both files, unchanged.
- **Severity:** Minor on their own (the plan is aspirational for these two items, not a shipped regression), but see F20 below — the icon claim is cosmetic, but the pandas/numpy claim has a real, concrete consequence for a *different* document in the same session batch.

### F20 (NEW, more important) — The Mobile/Termux install plan would crash on first real use, because of the very claim F19 disproves

- **Persona(s):** 🧠 ADHD Job-Seeker, 🏗️ Architect
- **Severity:** Major (if mobile/Termux deployment is ever actually attempted — currently aspirational, not shipped)
- **Files/lines:** `mobile_and_install_setup_plan.md` §3 ("Mobile-Lite Footprint Option... excluding compiling heavy C-libraries like Pandas, NumPy, and Selenium, it shrinks the environment size from 250 MB down to less than 15 MB") vs. `scripts/orchestrator.py:12-13` (`import numpy as np` / `import pandas as pd`, unconditional, module-level, no try/except).
- **Root cause:** The mobile setup plan assumes a "Mobile Lite Mode" of `install.sh` can skip installing `pandas`/`numpy` because nothing on the critical path needs them. That's false as of the current codebase — `orchestrator.py` (the module every single pipeline entry point imports) imports both unconditionally at the top of the file. Any environment that installed the "lite" dependency set and then ran `resume run`, `resume tailor`, or any command touching `orchestrator.py` would fail immediately with `ModuleNotFoundError: No module named 'pandas'`, before any actual pipeline logic runs.
- **Architectural impact:** This is the most concrete example in this whole cross-reference of a plan whose *narrative* ("Now, Dom is fully configured... It represents the absolute pinnacle of modern, decentralized multi-device workflow design!") outran the *actual state of the code it depends on*. If mobile deployment becomes a real near-term goal, `orchestrator.py`'s pandas/numpy usage would need to be actually removed or made lazy/optional first — not assumed already done.
- **Aside, not a code issue:** this same document consistently refers to the user as "Dom" and "his Pixel 10" throughout, rather than Morgan — worth a quick look at that session in isolation, since it doesn't match anything about the actual user/profile ("morgan"). Most likely a leftover generic placeholder from a template, but flagging it since an identity mismatch in a planning doc is worth a second look regardless of cause.

### F21 (NEW, minor) — `refactoring_plan.md` and `audit_report.md` directly contradict each other on Mobile Compatibility

`refactoring_plan.md` marks dimension "#17 Mobile Compatibility" as `[COMPLETED]` ("Cross-platform CLI entry points and responsive terminal layout scaling"). `audit_report.md`, evaluating the same repo around the same time, rates the identical dimension 🔴 **CRITICAL**: "Playwright Chromium and Selenium ChromeDriver binaries fail on Android ARM (Termux)." These can't both be right, and the second is a well-known, real platform constraint (Playwright doesn't ship Android/ARM builds) that a refactor alone can't resolve — it needs an actual architectural answer (e.g. the desktop-compiles/mobile-views-only split `mobile_and_install_setup_plan.md` separately proposes), not a checkbox. Filed here as a discrepancy between two prior-session documents, not something this session independently verified against a real Termux install.

### F22 (NEW, low severity) — STAR/XYZ grader shipped narrower than its own design doc specified

`resume_writing_audit_report.md` (the proposal that led to F9's grader) specifies a **4-factor** check (action verb, methodology/tool, metric, business outcome) with a **75%** pass threshold and explicitly calls the metric check just one of four signals ("Scans for percentage, currency, or unit symbols"). The shipped `_check_bullet_star_quality()` implements only **3 factors** (verb 30 / metric 40 / outcome 30, no separate tool-mention check) at a **70%** threshold. Collapsing 4 factors into 3 concentrated more relative weight onto the metric check specifically — a plausible contributing cause to F9 (the metric check alone can sink a bullet by 40 points, more than it would have in the original 4-factor design where each factor would carry ~25). Not a hallucination — the design doc was never claimed "as-built" — but useful context for Task 2.1's fix: restoring a 4th factor (methodology/tool mention, checkable against `verified_tools.json` the same way `_check_hallucinated_tools` already does) is a plausible alternative or complement to the qualitative-evidence fallback already proposed there.

### Historical note: `profiles/morgan/fixed_content.py` (PII in executable Python source)

`resume_builder_critical_audit.md` §2.1 flags PII (name/phone/email) hardcoded into an executable `.py` file as a vulnerability. Confirmed real via `git log -- "**/fixed_content*"`: it existed and was git-tracked (commits `9e316a29`, `91b4d392`), then commit `261047e2` ("Remove all profile-scoped data from git; sync via Syncthing instead") removed it from git tracking along with the rest of `profiles/<name>/`, which is now covered by the blanket `profiles/*/` `.gitignore` rule verified earlier in this document. `tests/test_fixed_content.py` confirms the module still exists and is dynamically loaded via `profile_paths.fixed_content_module()` — and it exists specifically to lock down certifications/education as Python constants the LLM can't hallucinate (`test_template_schema_has_no_free_form_certifications_or_education_fields`), which reframes this from "sloppy PII exposure" to "a deliberate anti-hallucination mechanism that happens to store PII in `.py` rather than `.yaml`." The original "accidental git commit" risk cited is already mitigated by the existing gitignore rule — this is a style critique (why `.py` instead of a data file), not a live secrecy gap.

---

## Coverage Limitations (Pass 3 blind-spot disclosure)

Per the audit's own Pass 3 mandate, named explicitly rather than left implicit:

- **`docs/review/*.md`** (13 existing phase-review documents already in this repo) were **not** cross-referenced against these findings. Some of F1–F15 may already be known/tracked there; treat this document as additive, and reconcile before triaging.
- **`dashboard/cmd/bootstrap/`, `dashboard/internal/ui/bootstrap/wizard.go`** (the new-profile bootstrap TUI flow) were not examined.
- **`.github/workflows/*.yml`** (CI configuration, dependency-review, pylint) were not audited for coverage gaps or misconfiguration.
- **`resume-engine/templates/*.html`** were not checked for injection risk via JD-derived or LLM-generated content beyond what F9/F10 cover upstream.
- **11 of ~13 `resume-engine/scoring/*.yaml` files** were not weight-audited (only `recruiter_score.yaml` and `believability.yaml` were spot-checked — see V5).
- **`board-scanners/providers/*.mjs`** (22 individual job-board scraper providers) were surveyed at the directory level only; per-provider brittleness (DOM selector fragility, etc.) was not individually verified beyond confirming `run_provider.mjs` has a documented 4-bucket error-classification scheme.
- **Full `python3 -m unittest discover` / `go test ./...` execution** was not run as part of this audit pass — findings here are static-analysis-verified (read the exact code), not dynamically confirmed by a failing test. The remediation guide requires this before any fix is marked complete.
