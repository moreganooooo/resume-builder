# Bootstrap & First-Run Remediation

**Date:** 2026-08-23
**Status:** COMPLETE (2026-08-23). F1–F16 closed, plus the follow-on
profile-rename and test-depersonalisation work below.

Suite green in all three scenarios:

| Scenario | Result |
|---|---|
| The author's own checkout | **2,315 passing** |
| A second user (`dominick`), own profile | **2,315 passing** (3 skipped) |
| A fresh clone with **no profile at all** | **2,297 passing** (10 skipped) |

Verified by instrumented runs: **0 stray directories** created in the
checkout, **0 outbound API calls** (was 78/run), **0 operator identity**
in tracked `scripts/` or `tests/`.

---

**Scope:** 14 findings from the 2026-08-23 bootstrap/first-run audit,
plus F15 (end-to-end test) and F16 (test-suite network calls) opened during the work.

---

## Problem statement

A new user cannot successfully bootstrap this project. Four independent
defects each break the path on their own; together they make the
documented onboarding sequence
(`install.sh` → `resume` → "New User? Start Here!") non-functional, and
one of them writes Morgan's real name, phone, and email into a stranger's
rendered resume.

Every finding below was reproduced against a fresh `git clone`, not
inferred from reading.

### What a real new user hits, in order

| Step | Expected | Actual |
|------|----------|--------|
| `bash scripts/install.sh` | env provisioned | pip failure reports `PASS` (F6); existing `.venv` deleted without asking (F7) |
| `resume` | profile picker | works — but offers `morgan`, a phantom profile a clone ships |
| "New User? Start Here!" | Go wizard | **`go: cannot find main module`** → returns False (F1) |
| (no Go installed) | questionary fallback | works, but only reachable *without* Go |
| bootstrap completes | identity captured | `profile.yml` written; `fixed_content.py` left blank (F3) |
| first cover letter | their name | blank name, or **Morgan's PII** (F2) |
| `resume doctor` to debug | diagnosis | works — unless `RESUME_PROFILE` is bad, then it dies too (F4) |

---

## Design decisions

Three forks were resolved before planning:

1. **Identity storage** → `profile.yml` becomes the source of truth.
   `CONTACT_INFO` is *derived* from `candidate`, not separately stored.
2. **Morgan's fallback data** → relocated out of tracked source into
   `profiles/morgan/`, and the fallback functions deleted outright.
3. **Execution** → plan first, then implement Phase 1; Phases 2 and 3
   followed in the same session at the repo owner's direction.

### Decision 1 detail: derive-to-fill, never derive-to-override

The naive reading of "profile.yml is source of truth" is to have
`fixed_content_module()` overwrite `CONTACT_INFO` from `candidate`. That
would be a **silent regression on Morgan's existing output**:

```
profile.yml  candidate.phone : '+1-XXX-XXX-XXXX'   (fully qualified)
fixed_content.CONTACT_INFO   : 'XXX-XXX-XXXX'      (as rendered)
```

Every resume and cover letter she has ever rendered uses the second form.
An override would change the rendered phone format on the next build with
no diff to explain it.

So the contract is:

> An explicitly-set (non-empty) value in `fixed_content.CONTACT_INFO`
> wins. Derivation from `profile.yml` fills only keys that are absent or
> empty-string.

This is what makes the fix free for new users — their scaffold is all
`""`, so every key derives — while being a provable no-op for Morgan,
whose keys are all populated. It also means the two stores can no longer
*silently* drift: a blank in `fixed_content.py` now self-heals from
`profile.yml` instead of rendering empty.

### Decision 2 detail: deletion needs no migration

`profiles/morgan/fixed_content.py` (16.3K) and
`profiles/morgan/knowledge_base/profile.yml` (21.1K) **already exist on
disk**. Verified: `fixed_content_module()` loads the real file today; the
`_make_fallback_*` functions are already dead code on Morgan's machine.
They fire only on a fresh clone or an unbootstrapped profile — i.e. only
where they do harm. Deletion is therefore a pure removal, not a
migration.

---

## Phase 1 — CRITICAL (COMPLETE)

### F1. Go bootstrap wizard invoked with wrong cwd

**File:** `scripts/menu.py:689`
**Severity:** Blocks the primary new-user entry point on any machine with Go.

`go run ./dashboard/cmd/bootstrap` is executed with `cwd` = project root,
but the Go module lives in `dashboard/` (`dashboard/go.mod`, module
`github.com/moreganooooo/resume-builder/dashboard`). There is no root
`go.mod`.

Reproduced:
```
rc=1
go: cannot find main module, but found .git/config in .../resume-builder
```
`go build -o /tmp/x ./cmd/bootstrap` from `dashboard/` succeeds.

The failure is unrecoverable because the questionary fallback is gated on
`shutil.which("go") is None` — having Go installed *guarantees* you get
the broken path and never the working one.

**Fix**
- `cwd=` the `dashboard/` directory; package stays `./cmd/bootstrap`.
- Prefer the prebuilt `dashboard/bin/bootstrap` when present and build it
  on demand, matching how `scripts/dashboard.py` and
  `scripts/charm_prompt.py` already handle their binaries (per
  `dashboard/CLAUDE.md`) — `go run` recompiles on every launch.
- Treat exit code `130` as user-cancelled, not error: `cmd/bootstrap/main.go:22`
  deliberately exits `130` on `huh.ErrUserAborted`, and the Python side
  currently collapses that into `friendly_subprocess_error`.
- Fall back to the questionary wizard on *any* wizard failure, not only
  on missing Go.

**Regression test:** assert the resolved cwd contains a `go.mod`. This
catches the class (wrong-directory subprocess) without needing Go in CI.

---

### F2. Morgan's PII is the fallback identity for every profile

**File:** `scripts/profile_paths.py:304` (and `:601` for the yaml twin)
**Severity:** PII leak into third-party output.

```python
if name == "morgan" or profile is None:
    return _make_fallback_fixed_content()
```

The `or profile is None` clause defeats the guard. **All nine call sites
use the zero-arg form**, so `profile is None` is always true and the
`ImportError` branch is unreachable:

```
orchestrator.py:310,404,4784   render_coverletter.py:85
rewrite_bullets.py:728,838     render_coverletter_docx.py:54
normalize_resume.py:40
```

Reproduced with a profile named `alice`:
```
{'NAME': '<the repo author>', 'PHONE': '<their real number>',
 'EMAIL': '<their real address>', 'LINKEDIN_DISPLAY': ..., 'LOCATION': ...}
```

Compounding it: a fresh clone ships `profiles/morgan/` (three tracked
`board_scanner/*.yml`) with no `fixed_content.py`, and `RESUME_PROFILE`
unset defaults to `"morgan"` — so the *default* new-user path lands
exactly here.

**Fix**
- Delete `_make_fallback_fixed_content()` and
  `_make_fallback_profile_yaml()` (~250 lines of real career data + PII
  out of tracked source).
- `fixed_content_module()` raises `ImportError` naming the profile and
  pointing at New User Setup; `profile_yaml()` returns `{}`.
- Confirm `profiles/morgan/` retains its real files (it does — verified
  16.3K / 21.1K on disk).

**Note — do not skip:** `render_coverletter.py:99` reads
`contact["LINKEDIN_DISPLAY"]` by **direct subscript**, as do `NAME`,
`PHONE`, `EMAIL`, `LOCATION` on the surrounding lines. Once the fallback
is gone, a `fixed_content.py` missing any one key raises `KeyError` mid-
render instead of degrading. F3's derivation guarantees all five keys
exist, so **F3 must land in the same commit as F2** — they are not
independently shippable.

---

### F3. Nothing populates `CONTACT_INFO`

**Files:** `scripts/bootstrap_profile.py:1398`, `scripts/profile_paths.py:304`
**Severity:** Every bootstrapped user renders a nameless resume.

`create_new_profile` writes a scaffold with all five contact fields as
`""` (`bootstrap_bullet_bank.py:55,171`). `run_profile_setup()` collects
real identity via `collect_identity()` → `_guess_contact_info()` and
writes `profile.yml`, `portals.yml`, `scan_filters`, the verified ledger,
the background guide, voice anchors, and `cv.md` — **never
`fixed_content.py`**. Grep confirms the scaffold is that file's only
writer. The renderers then read `fixed_content_module().CONTACT_INFO`.

Identity is captured into one store and read from another.

**Fix** — implement derive-to-fill in `fixed_content_module()`:

| `CONTACT_INFO` key | `profile.yml` `candidate` key |
|---|---|
| `NAME` | `full_name` |
| `PHONE` | `phone` |
| `EMAIL` | `email` |
| `LOCATION` | `location` |
| `LINKEDIN_DISPLAY` | `linkedin` |

Fill only where the existing value is missing or empty. Guarantee all
five keys are present on the returned module so the direct-subscript
renderers cannot `KeyError`.

**Verification:** Morgan's rendered contact block must be byte-identical
before and after — the phone-format trap above is the specific thing to
check.

---

### F4. A bad `RESUME_PROFILE` bricks every entry point

**File:** `scripts/jd_manager.py:27`, `scripts/profile_paths.py:32`
**Severity:** No escape hatch; the documented recovery tool is itself dead.

`jd_manager.py:27` resolves `JDS_DIR = profile_paths.jds_dir()` at
**import** time, and `active_profile()` raises on an unknown profile.
`cli_art` imports `jd_manager`, so `resume`, the menu, and `resume doctor`
all die with a raw traceback *before* any gate or handler runs:

```
ValueError: RESUME_PROFILE is set to 'typo', but profiles/typo/ does not exist.
  Check for a typo, or create it via the bootstrap 'New Profile' flow.
```

The message names a recovery flow that cannot be reached. `_resume_ensure_profile`
(`scripts/resume-cli.sh:150`) **exports** `RESUME_PROFILE` for the whole
terminal session, so the broken state is sticky across every subsequent
command.

**Fix**
- Catch `ValueError` at the top-level entry points (`cli.py`, `menu.py`)
  and render a friendly message + recovery options rather than a
  traceback.
- `resume doctor` must run *regardless* of profile validity — it is the
  recovery tool and cannot depend on the thing being recovered. Treat an
  unresolvable profile as a reported problem with a suggested fix.
- Add a case-insensitive resolution pass against the real on-disk listing
  before raising, following the `menu._confirm_active_profile()` pattern
  CLAUDE.md already prescribes.

**Related, same root:** `active_profile()`'s `os.path.isdir` check is
case-insensitive on macOS but case-sensitive on Linux. Confirmed live:
`RESUME_PROFILE=Morgan` resolves to `profiles/morgan/` here and would
fail on a Syncthing peer running Linux.

---

### F15. End-to-end bootstrap test (new work)

The single highest-value item in this plan. A test that bootstraps a
throwaway profile into a temp dir and asserts the rendered contact block
matches the entered identity would have caught **F1, F2, and F3
simultaneously**.

Requirements, per the isolation rules in CLAUDE.md:
- Patch `profile_paths.PROFILES_DIR` to a `TemporaryDirectory` so the
  `db._is_unisolated_test_write` guard is satisfied and nothing touches a
  real profile.
- Stub the Gemini calls — this must not spend API credits or need network.
- Assert: profile scaffolded → identity written to `profile.yml` →
  `CONTACT_INFO` derives all five keys → **no string from Morgan's
  identity appears anywhere in the rendered output.**

That last assertion is the permanent regression guard for F2.

---

## F16 (CLOSED) — the test suite made 78 real Gemini API calls

**Severity:** HIGH. Costs real money per run, makes the suite slow and flaky.

Measured by instrumenting `requests.Session.request` and `httpx.Client.send`
across a full discover run:

```
=== OUTBOUND CALLS BY HOST ===
    78  generativelanguage.googleapis.com

=== TESTS MAKING NETWORK CALLS (12) ===
    28  test_orchestrator_coverletter_voice.TestOrchestratorCoverletterVoice
          .test_voice_violations_trigger_retry_with_issues_block
    11  test_orchestrator_coverletter_injection … test_fabricated_content_is_gone…
    10  test_orchestrator_coverletter_injection … test_real_closing_marker_comes_after…
    4×6 test_orchestrator_coverletter_enrichment.TestAtsClassificationAndKeywordFrontLoading
    2×2 test_orchestrator_coverletter_enrichment.TestReferralInjection
     1  test_remediation_protections … test_vector_store_stale_hash_trigger
```

`scripts/websearch_ddg.py` already has the right guard for this class
(`_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"` + `"unittest" in
sys.modules`), and CLAUDE.md documents the same pattern for
`liveness._gather_db_candidates` and `db.upsert_job`.
**`scripts/gemini_client.py` has no equivalent guard**, so any test that
reaches it calls the real API.

Symptoms this explains: intermittent `HTTP 429 ... Waiting 17.4s (retry
2/2)` and `Pacing Gemma call: waiting 55.0s (16k TPM cap)` in test output,
suite wall-clock swinging from 127s to 274s between runs, and ~11
intermittent errors under load.

**Fix:** give `gemini_client` the same fail-closed guard `websearch_ddg`
has — raise (or return a canned response) under `unittest` unless
`RESUME_ALLOW_TEST_NETWORK` is set — then update those 12 tests to mock
the client explicitly. Fail-closed matters: a guard that silently returns
empty would make these tests pass while asserting nothing.

---

## Phase 2 — HIGH (COMPLETE)

**F5. `resume doctor` writes test fixtures into a real working tree.**
Doctor runs the full suite; on a fresh clone that created
`jds/testprofile/`, `jds/testuser/`, `output/testprofile/`, plus
`profiles/morgan/data.db` and `maintenance_log.json` for the phantom
profile. Same class as the guards CLAUDE.md documents, but `testprofile`
and `testuser` escape them. *(Positive finding: 2,279 tests passed on a
clean clone — the old "a clean clone can't run the suite" constraint no
longer holds and that memory should be updated.)*

**F6. `install.sh:114` checks the wrong exit status.** The last command
before the check is `npx playwright install chromium` (or a `printf`),
not `pip install -r requirements.txt`. A failed pip install reports
`PASS — Python dependencies installed cleanly`. No `set -e`, so it
continues. Capture pip's status directly.

**F7. `install.sh:76-79` silently `rm -rf .venv`.** No prompt. Destroys a
working environment on any re-run. Prompt, or reuse in place.

**F8. `FileExistsError` uncaught in the bootstrap handler.**
`menu.py:712` catches only `ValueError`; `create_new_profile` raises
`FileExistsError` for an existing name
(`bootstrap_bullet_bank.py:165`). Re-running setup and retyping a name
crashes the menu.

---

## Phase 3 — MEDIUM (COMPLETE)

- **F9.** Lite Mode's hand-maintained package list (`install.sh:96`) omits
  `python-docx` (used at `bootstrap_extractors.py:47` for ingestion),
  `pdfminer.six`, `Pillow`, `openpyxl`, `odfpy`, `ddgs`, `pandas`,
  `numpy` — it cannot run bootstrap, and will drift from
  `requirements.txt`. Derive it from a `requirements-lite.txt` instead.
- **F10.** Express setup swallows the traceback
  (`bootstrap_menu.py:262`): one line for an 8-stage LLM pipeline, with
  partial state on disk and no stage attribution.
- **F11.** Express setup dead-ends on a missing API key instead of calling
  `collect_secrets()`'s own interactive prompt, which already exists and
  handles exactly this.
- **F12.** `_profile_is_set_up()` (`menu.py:598`) only checks two
  directories exist. `create_new_profile` makes `knowledge_base/`
  immediately, so an empty profile reports "set up", lifting the
  guest-mode guard.
- **F13.** `install.sh`'s "Next Steps" never mentions creating a profile —
  the actual first action is unnamed.
- **F14.** Shell nits: `mode_choice` compared with `-eq` (lines 92, 228)
  errors on non-numeric input; shell-rc detection prefers `~/.zshrc` by
  existence rather than actual shell; the quoted heredoc at lines 198-202
  writes literal `\` into `termux.properties`; `pkg install termux-api`
  reports PASS unconditionally.

---

## Sequencing & risk

```
F2 ─┬─> must ship together (F2 removes the fallback that
F3 ─┘   currently masks F3's empty CONTACT_INFO)
F1 ──> independent
F4 ──> independent
F15 ─> lands last in Phase 1; guards F1+F2+F3 permanently
```

**Riskiest change:** F3's derivation, because it touches the render path
for Morgan's real output. Mitigated by derive-to-fill (a provable no-op
when all keys are populated) plus a before/after byte comparison of her
rendered contact block.

**Lowest risk:** F2's deletion — already dead code on the only machine
with a real profile.

### Definition of done for Phase 1

1. Full suite green (baseline: 2,279 passing).
2. New end-to-end bootstrap test passing and genuinely isolated
   (no writes to `profiles/`, `jds/`, `data/`, `output/`).
3. `resume doctor` runs and reports a *diagnosis* under a bogus
   `RESUME_PROFILE` instead of a traceback.
4. Morgan's rendered contact block byte-identical to pre-change output.
5. `grep -ri "escott\|716-352" scripts/` returns nothing outside
   `profiles/`.

---

## Final verification (2026-08-23)

| Check | Before | After |
|---|---|---|
| Test suite | 2,279 passing | **2,302 passing** |
| Stray dirs created in checkout per run | 8 named test profiles | **0** |
| Outbound API calls per suite run | 78 | **0** |
| PII in tracked `scripts/` | ~474 lines | **0** |
| New-user path (Go installed) | broken at step 1 | works |
| `resume doctor` w/ bad RESUME_PROFILE | raw traceback | actionable diagnosis |

Both audits were instrumented, not read:
- **Leak audit** wraps `os.makedirs`/`os.mkdir`/`os.replace`/`os.rename` and
  attributes each creation to the running test. `os.replace` matters —
  `atomic_write` renames into place and never `open()`s the destination, so
  watching `open()` alone misses those writes entirely.
- **Network audit** wraps `requests.Session.request` and `httpx.Client.send`
  (google-genai may use either transport) and counts calls per host per test.

### Deliberately not changed

- Tests that read and write Morgan's own `Morgan`/`morgan` profile. Many do
  so by design, and `db._is_unisolated_test_write` already drops the
  dangerous writes. Converting them is a separate piece of work with its
  own risk, not part of this remediation.
- `profiles/Morgan/` vs git's `profiles/morgan/`. The case-insensitive
  fallback in `active_profile()` now handles the mismatch, but the
  underlying inconsistency is real and will surface on any Linux peer.
  Renaming the directory to match git is a one-line fix the repo owner
  should make deliberately.
- `tests/` still contains real contact details as fixture data (~20 files).
  Lower severity than the tracked-source PII (test fixtures are not
  rendered into anyone's resume) and some legitimately assert on Morgan's
  own profile rendering.

---

## Follow-on: profile rename, and de-operator-coupling the tests (2026-08-23)

Two requests after the remediation above.

### 1. Profile rename vs. Syncthing and git

Four defects found in the rename flow (`menu._handle_manage_profiles`):

| | Problem | Fix |
|---|---|---|
| **Name validation** | Rename checked only non-empty/non-duplicate, so a name containing `/` or `..` reached `os.rename()` and could move a profile anywhere on disk. `create_new_profile()` has rejected those since it was written. | `profile_paths.rename_profile()` applies the same `_VALID_PROFILE_NAME` regex both entry points share. |
| **Crash on the active profile** | `target == active_profile()` was evaluated AFTER the directories moved, at which point `active_profile()` can no longer find them and raises — uncaught, straight out of the menu. | Resolved before the move. |
| **Partial rename** | Destinations were checked per-root as it went, so a collision on the third root left a half-renamed profile. | All four destinations validated before any move. |
| **Silent external breakage** | Nothing told the user that Syncthing and git both track these directories by path. | `rename_side_effects()` returns the three warnings, shown before a confirm prompt. |

**Syncthing is the dangerous one.** Each of a profile's four directories is a
*separate* Syncthing folder configured by absolute path on every paired
device. Renaming locally does not rename them there: the old paths go
missing, and Syncthing can interpret that as a deletion and propagate it.
The flow now says so explicitly and tells the user to pause the folders on
every device, repoint them, then resume.

**A real `.gitignore` bug surfaced here.** The intent was to track
`profiles/*/board_scanner/*.yml` for every profile — the comment even says
"it needs both the directory re-included and the file re-included". But the
pattern was `profiles/*/`, which excludes the DIRECTORY, and git cannot
re-include a file whose parent directory is excluded. Both negations were
dead. `profiles/morgan/`'s three files survived only because they were
already tracked, and gitignore does not apply to tracked files — which is
why nobody noticed. **A new or renamed profile's board_scanner config was
silently un-committable.** Fixed to `profiles/*/*` (contents, not the
directory) and verified with `git check-ignore -v --no-index` that
`knowledge_base/`, `.env`, `data.db` and `signature.png` all stay ignored.
That also made timestamped `*.bak-*` backups visible, so those are now
ignored explicitly.

### 2. Tests no longer depend on who is operating the checkout

Starting point: 17 test files carried the author's real name, email, phone,
home town and ZIP; 31 hardcoded her profile name.

- **`tests/persona.py`** — one neutral identity (RFC 2606 `example.com`,
  NANP `555-01xx`, a real-but-unrelated geocodable city) plus fictional
  employers, education, situational roles, a tag taxonomy and scanner
  filters, all structurally identical to the real thing.
  `persona.sandbox_profile()` builds a complete throwaway profile.
- **`tests/test_no_operator_identity.py`** — reads the ACTIVE profile's
  `profile.yml` at runtime and fails if those values appear anywhere in
  `tests/`. It protects whoever is running it, so it will catch the next
  person hardcoding their own details. Values in reserved-for-fiction
  ranges are excluded (fixtures legitimately use them).

**A code bug this surfaced:** `active_profile()` returned a hardcoded
`"morgan"` whenever `RESUME_PROFILE` was unset — so any other user silently
got paths to a profile that does not exist on their machine. Nothing
raised; every derived path was simply wrong. `_default_profile()` now uses
the only profile when there is exactly one, prefers the legacy name when
several exist (unchanged for existing setups), and falls back to the legacy
name only when there are none.

### Verification: a second user's run

Measured by building a profile named `dominick` via the real
`create_new_profile()` flow in a copy of the working tree, with
`RESUME_PROFILE` unset:

| | Failures + errors |
|---|---|
| Before | **233** |
| After | **0** |

And with no profile at all (the state a brand-new user is in when
`resume doctor` runs the suite for them): **52 → 0**.

The single largest cause was a leaked `RESUME_PROFILE`: a `tearDown` fell
back to a hardcoded profile name when nothing was set, raised inside
`set_active_profile()` because that profile does not exist for a second
user, and — because the raise happened in teardown — left the variable
poisoned for every subsequent test. 129 cascading errors from one line that
passes on any machine where the variable is always exported.

### Nothing knowingly left

Every remaining failure was closed. Two patterns did the work:

- **Sandbox the class.** Anything constructing `ResumeEngine()`,
  `KnowledgeBase()`, or otherwise resolving the active profile now enters
  `persona.sandbox_profile()` in `setUp`/`setUpClass`.
- **Skip when there is genuinely nothing to check.** `test_fixed_content`
  and `test_profile_yml_schema` validate whichever profile is configured,
  and skip cleanly when none is.

One subtlety worth recording: `patch("menu.os.listdir", return_value=[])`
patches the attribute on the real `os` module, so it answers for EVERY
caller — including `profile_paths.available_profiles()`. That made
`_default_profile()` see zero profiles, fall back to the legacy name, and
report the profile as not set up, so `_handle_update_knowledge()` returned
at its first gate and four tests silently exercised nothing. The stub is
now scoped to the source-documents directory. Broad `os.*` patches in a
codebase with a filesystem-derived config are a trap worth watching for.
