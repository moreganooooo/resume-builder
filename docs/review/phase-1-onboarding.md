# Phase 1 — Onboarding & new-user path

Model: Opus 5. Date: 2026-08-05. **Goal served: 3** (adoptable by strangers).

**Question asked:** can someone who is not Morgan get from `git clone` to a
finished resume without asking her anything?

**Answer: no.** Not because any single step is hard, but because the path has
three silent traps (Findings 1–3) that leave a new profile in a broken state
that *reports itself as healthy*, and no in-app signal distinguishes "not set
up yet" from "set up and failing."

## Ownership note — claimed an unowned file

Per `PLAN.md`'s "Unowned files" rule: **`scripts/bootstrap_menu.py` belonged to
no phase.** It is the "New User? Start Here!" submenu — the literal entry point
to everything Phase 1 asks about. I claimed it and added it to Phase 1's
ownership list in `PLAN.md`.

Not claimed, deliberately: `scripts/menu.py:186-215` holds the **new-profile
creation** flow (`create_new_profile()` call site) and the "This profile hasn't
been set up yet" gate. `menu.py` is Phase 2's file, reviewed there as a visual
layer only. The functional onboarding logic inside it is unreviewed by anyone —
see Handoffs.

## Method

Runtime evidence over source reading, per the operating rules. I created a real
throwaway profile (`phase1probe`) via the real `create_new_profile()`, ran the
real `doctor` and the real `run_ingestion()` against it with no API key
configured, then deleted all four of its sync roots. Working tree verified
unchanged afterward. No code changes.

---

## Findings

### Finding 1 — A failed ingestion is recorded as "done," reports "Up to date," and can never be retried through the UI — BLOCKER

`scripts/bootstrap_bullet_bank.py:367-369` (skip-if-done),
`scripts/bootstrap_menu.py:38-42` (`_phase0_status`). **Goal: 3.**

This is the single worst thing on the new-user path.

**Observed.** Fresh profile, one source document, no `GEMINI_API_KEY` — the
exact state of a stranger who chose "add it later" at the secrets step:

```
WARNING: HTTP error 403: 403 Client Error: Forbidden for url:
https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent
SUMMARY: {'extracted': 0, 'attributed': 0, 'flagged': 0, 'certificates': 0}
```

Exit code 0. The checkpoint written:

```json
{ "resume.txt": { "status": "done", "doc_type": "resume",
                  "work_experience": [], "certificates_found": [] } }
```

The onboarding progress table then reports:

```
Phase 0  : ('Up to date', '1 document(s) processed')
```

**Nothing was extracted. The step is marked complete and green.**

**And it is sticky.** `run_ingestion()` skips any file already marked `done`
(`:367-369`). Re-running step 0 after fixing the API key does nothing at all —
I confirmed this by re-running: no HTTP call was even attempted the second
time, and it returned the same zeros. The only escapes are
`--force-overwrite-clean-bank` (not exposed anywhere in the menu) or manually
deleting `checkpoint.json` — neither of which a stranger knows exists.

**Concrete failure:** a new user defers the API key, runs step 0, sees a 403
scroll past, sees "Up to date," moves on to step 0.5, and ends up with a fully
"complete" onboarding and an empty bullet bank. Every later step succeeds
against nothing.

**Better version:** `status` must record the *outcome*, not the attempt. A file
whose extraction returned zero achievements — or whose API call failed — should
be checkpointed `"status": "failed"` with the reason, counted as pending by
`_phase0_status()`, and retried on the next run. `run_ingestion()` should also
return a failure count so `print_ingestion_summary()` can say "1 document
failed (API key rejected)" instead of a row of zeros.

---

### Finding 2 — The wizard offers to set the API key "later," then immediately runs the step that requires it — MAJOR

`scripts/bootstrap_profile.py:806-831` (`_collect_secret_now_or_later`),
`scripts/bootstrap_menu.py:69-71` and `:75-76`. **Goal: 3.**

`_collect_secret_now_or_later()` explicitly offers deferral, and says so
warmly:

```python
print(f"  No problem -- add it later by editing {env_file} ...")
return False
```

It returns `False`. **Both call sites discard the return value:**

```python
def _run_phase0() -> None:
    ...
    bootstrap_profile.collect_secrets()          # return value dropped
    summary = bootstrap_bullet_bank.run_ingestion()   # needs the key
```

```python
def _run_phase05() -> None:
    bootstrap_profile.collect_secrets()          # return value dropped
    bootstrap_profile.run_profile_setup()        # needs the key
```

So "later" means "about four seconds from now." The user is walked into
Finding 1's trap by the wizard's own happy path, and the only feedback is a raw
`403 Client Error: Forbidden` that never mentions an API key, a profile, or
`.env`.

**Better version:** `collect_secrets()` already returns
`{"gemini_key_set": bool, ...}`. Honor it — if `gemini_key_set` is False, stop
before the pipeline runs and say: *"Step 0 needs a Gemini API key. Add it to
`profiles/<name>/.env` and choose this step again."* Deferral is a legitimate
choice; running anyway is not.

---

### Finding 3 — Eight freely-selectable steps with a real dependency chain and no ordering gate — MAJOR

`scripts/bootstrap_menu.py:74-76`, `:102-130`;
`scripts/bootstrap_profile.py:955-977`. **Goal: 3.**

The menu presents steps `0`, `0.5`, `1`–`6` as an equal, individually
selectable list, and the module docstring frames that as the feature ("lets a
user run any one of them individually"). But `run_profile_setup()` has a
documented hard ordering dependency in its own body comment (`:967-974`), and
step 0.5 reads step 0's outputs throughout.

Nothing enforces it. `_run_phase05()` is three lines with no precondition
check, and `_phase05_status()` (`:45-54`) checks only whether *its own* two
output files exist — never whether step 0 ran.

**Concrete failure:** a stranger picks **"0.5 Set Up Profile"** first — an
entirely reasonable read, since "Set Up Profile" sounds like the beginning and
"0.5" sorts next to "0". Then:

| Call | Input | Result with step 0 unrun |
|---|---|---|
| `_load_checkpoint()` (`:53-57`) | `checkpoint.json` | `{}` |
| `_load_timeline()` (`:60-64`) | `timeline.json` | `[]` |
| `_guess_contact_info({})` (`:112-123`) | loop body never entered | empty `ContactInfo()` |
| `_guess_primary_roles([])` (`:126-132`) | — | `[]` |
| `_achievements_summary_text()` (`:67-74`) | `DRAFT_CSV_PATH` missing | `""` |

`generate_tag_taxonomy()` then makes a **real, paid** Gemini call against an
empty achievements string, `write_cv_md()` drafts a CV from an empty draft CSV,
and `_phase05_status()` afterwards reports **"Up to date."** A second false
green, on top of Finding 1's.

**Better version:** gate it. `_run_phase05()` should refuse (or loudly warn and
confirm) when `_phase0_status()` is not `"Up to date"`, and the menu should
render dependent steps as visibly locked until their prerequisite completes —
the status table is already right there.

---

### Finding 4 — A brand-new profile's first `resume doctor` reports it as broken — MAJOR

`scripts/doctor.py:180-190` (`check_kb_allowlist`). **Goal: 3.**

Verbatim, from the real run against the fresh `phase1probe` profile:

```
2 problem(s) found:
   Playwright npm package: npm install ...
   Knowledge-base allowlist files (phase1probe): Missing files silently shrink
   the builder's context -- restore them into
   /Users/morganescott/resume-builder/profiles/phase1probe/knowledge_base/, or
   re-run bootstrap/Update My Knowledge if this is a fresh or partial profile.
```

...preceded by a 19-line wall of truncated filenames (`article-digest.md`,
`detective-findings-trimmed.cs…`, `recruiter_memory_patterns.jso…`, …).

For a fresh profile **this is the correct and expected state**, and doctor is
the tool a stranger reaches for to answer "did I set this up right?" It answers
"you have 2 problems" and shows them a debris field. The actual instruction —
*run bootstrap* — is the last clause of a sentence that opens with a warning
about silently shrunk context and a path to restore files into by hand.

**Better version:** doctor should detect the unbootstrapped case first and
collapse it to one line: *"Profile `phase1probe` isn't set up yet — run
`resume` → New User? Start Here! (0 of 19 knowledge-base files present)."* Keep
the current per-file detail for the genuinely *partial* case, where knowing
which files are missing is actually useful.

---

### Finding 5 — The Nerd Font default fails silently and is undiagnosable from inside the tool — MAJOR

`scripts/theme.py:81-86`; absence in `scripts/doctor.py:193-206` and in
`resume help`. **Goal: 3.**

The plan asked directly whether this default is right and whether the failure
is detectable. Evidence:

- `theme.py:86` defaults to Nerd Font glyphs; `:83` deliberately "fails toward
  the enhanced default" on an unset or typo'd env var.
- A repo-wide grep for `RESUME_BUILDER_ICONS` finds it in **exactly one runtime
  code path — its own definition at `theme.py:86`.** Every other hit is
  `README.md`, `CLAUDE.md`, `tests/`, or `docs/`. No help text, no doctor
  check, no menu hint, no error message mentions it.
- `doctor` checks the *PDF* fonts (`check_fonts`, `:157-165`) and nothing about
  terminal glyph support.
- `resume help` output contains no mention of icons, fonts, or the env var.

So a stranger without a Nerd Font launches `resume`, sees a menu of tofu boxes,
and has exactly one recovery route: notice README step 6 — filed under
"Optional" — and already connect it to what they're seeing.

**Is the default right?** The comment's reasoning ("a typo'd env var shouldn't
silently degrade someone who does have a Nerd Font active") optimizes for the
already-configured user at the expense of the first-run one. For goal 3 that is
backwards. But flipping the default to Unicode is also the wrong fix — it
silently downgrades everyone, and terminal font support genuinely cannot be
probed from a TTY.

**Better version — ask once, persist the answer.** On first launch in a real
terminal, print one sample glyph and one question:

```
Do these icons render correctly, or do you see empty boxes?
        (Nerd Font)        ✓ ▶ ⚙  (Unicode)
  [1] The first row looks right   [2] I see boxes — use plain symbols
```

Store the answer in the profile's config; never ask again. Default to Unicode
if there's no answer yet and stdin isn't a TTY. This needs no font
introspection, is deterministic, and turns an invisible failure into a
five-second decision. It would also give `doctor` something real to report.

---

### Finding 6 — Onboarding has no CLI entry point and is invisible from `resume help` — MAJOR

`scripts/cli.py:73-328`. **Goal: 3.**

`cli.py` registers `tailor`, `run`, `coverletter`, `evaluate`, `scan`,
`liveness`, `polish`, `sample`, `help`, `doctor`, `dashboard`. There is **no
`bootstrap` / `init` / `new-profile` command.** Onboarding exists only inside
the interactive menu.

Consequences for a stranger:

- `resume help` — a natural first move — lists eleven commands, none of which
  set anything up. Grepping its real output for `new user|bootstrap|start
  here|sample` returns nothing; only `doctor` matches.
- The only way in is `resume` with no arguments, which per Phase 0 §3 costs
  **~20–25 seconds** of animated banner before the menu is usable.
- Setup cannot be scripted, resumed from a shell, or documented as a copyable
  command — README §4 has to describe it in prose as "the `resume` menu's 'New
  User? Start Here!'" instead of a command.

**Better version:** `resume bootstrap` (aliasing straight into
`bootstrap_menu.run_bootstrap_menu()`), listed in `HELP_ENTRIES`, and named in
README's Setup section as the step after `pip install`.

---

### Finding 7 — The "plain Unicode fallback" icon set is neither width-safe nor theme-safe — MINOR

`scripts/theme.py:64-79`, with `_ICON_COLORS` at `:89-104`. **Goal: 3, 4.**

Measured every glyph in `_UNICODE_ICONS`:

| Icon | Glyph | Codepoint | EA width |
|---|---|---|---|
| `evaluate` | 📊 | U+1F4CA | **W** — emoji |
| `skip` | 🚫 | U+1F6AB | **W** — emoji |
| `save` | 💾 | U+1F4BE | **W** — emoji |
| `build` | ⚡ | U+26A1 | **W** |
| `hint`/`gem` | ◆ | U+25C6 | A |
| `discovery` | ◎ | U+25CE | A |
| `bullet_bank` | □ | U+25A1 | A |
| `resume` | ▶ | U+25B6 | A |
| `success`/`error`/`warning`/`utility` | ✓ ✗ ⚠ ⚙ | U+2713/2717/26A0/2699 | N |

Two real consequences, both landing **only on the stranger's path** — the
Nerd Font set is uniformly single-width, so nobody with a Nerd Font ever sees
this:

1. **Alignment breaks.** Four wide glyphs and five ambiguous-width ones mean
   any column layout computed against the default set is wrong on the fallback
   set. (This may be the real cause of what Phase 0 §3 saw as truncation and
   flagged for Phase 2 to re-check — worth testing under
   `RESUME_BUILDER_ICONS=unicode` specifically.)
2. **The theme is defeated.** `_ICON_COLORS` assigns `skip` → `ERROR` red,
   `save` → `SUCCESS` green, `evaluate` → `BRAND_ACCENT` purple. Emoji carry
   their own baked-in color and ignore ANSI foreground in most terminals, so
   those three render off-palette no matter what `theme.py` says.

Also worth noting: the 2026-08-05 "emoji→symbols" consistency sweep replaced
raw emoji everywhere else. These three are the leftovers — and they sit on the
one code path a new user is most likely to be on.

**Better version:** replace the three emoji (and ideally `⚡`) with narrow
U+2xxx symbols, matching the ✓/✗/⚠/⚙ family that's already width-`N`.

---

### Finding 8 — `doctor`'s suggested fixes call `npm` and `npx`, which `doctor` never checks for — MINOR

`scripts/doctor.py:89-114`. **Goal: 3.**

`check_node()` verifies `node`. Nothing verifies `npm` or `npx`, yet both
Playwright checks hand back fixes that require them (`npm install`,
`npx playwright install chromium`).

**This machine is the failure case.** `node` resolves to
`/usr/local/bin/node`, a standalone install with no `npm` sibling — `ls
/usr/local/bin | grep -iE 'node|npm|npx'` returns only `node`. `npm` exists
only under `~/.nvm/versions/node/{v22.20.0,v24.17.0}/bin/`, not on PATH. So
doctor reports Node ✓ and then prescribes a command that fails with `command
not found`.

**Better version:** check `npm` alongside `node` (same `shutil.which` shape),
and make the Playwright fix conditional on it — otherwise say "npm not found on
PATH; if you use nvm, run `nvm use` first."

---

### Finding 9 — `check_venv`'s detail line says "ready to use" even when it isn't — MINOR

`scripts/doctor.py:66`. **Goal: 3.**

```python
detail = f".venv/ {'found' if exists else 'missing'}, ready to use"
```

`ready to use` is unconditional. A missing venv renders as **`.venv/ missing,
ready to use`**; a venv that exists but has no `bin/python` renders as
`.venv/ found, ready to use` while `passed=False`. On the one check most likely
to fail for a stranger who skipped step 2, the detail text contradicts the
verdict.

**Better version:** build the detail from the same two booleans the verdict
uses — `".venv/ found and ready"` / `".venv/ found but has no bin/python"` /
`".venv/ missing"`.

---

### Finding 10 — The multi-profile picker mis-renders under zsh — MINOR

`scripts/resume-cli.sh:34`. **Goal: 3.**

```sh
printf '  %s\n' $names
```

zsh does not word-split unquoted parameters; bash does. The file's own header
claims "Works under both zsh and bash," and zsh is the macOS default. Measured
with three profiles:

```
zsh:                    bash:
  alice                   alice
bob                       bob
morgan                    morgan
```

Only the first entry is indented; the rest are one printf argument containing
newlines. This fires on exactly the shared-checkout, multiple-people scenario
the function exists to serve. **Better version:** `printf '  %s\n'
"${(f)names}"` in zsh, or loop with `while IFS= read -r n` for both shells.

---

### Finding 11 — `resume()` calls a helper with no guard — MINOR

`scripts/resume-cli.sh:45`. **Goal: 3.**

`resume()` calls `_resume_ensure_profile` unconditionally. Any environment that
captures or exports the outer function without the underscore-prefixed helper
breaks the entire command. That is not hypothetical — it is precisely what
produced Phase 0's §1 error (see Corrections below), and it would equally
affect a user who copies the `resume` function into their own dotfiles.

**Better version:** `command -v _resume_ensure_profile >/dev/null &&
_resume_ensure_profile` — the profile prompt is a convenience, not a
precondition, so it should degrade to inert rather than fatal.

---

### Finding 12 — Backing out of an empty step 0 still reports "something happened" — MINOR

`scripts/bootstrap_menu.py:57-67`, `:124-130`. **Goal: 3.**

When `source_documents/` is empty, `_run_phase0()` prints instructions and
returns without doing anything. But `did_something = True` at `:130` runs
unconditionally after the if/elif/else, so `run_bootstrap_menu()` returns
`True` and the caller fires a "what's next?" chain prompt for work that never
occurred. **Better version:** have `_run_phase0()`/`_run_phase05()` return a
bool and assign `did_something` from it.

---

### Finding 13 — The shell-env shortcut defeats `collect_secrets()`'s own per-profile-credentials goal — MINOR

`scripts/bootstrap_profile.py:852-854`. **Goal: 3.**

```python
already_configured = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
if already_configured:
    gemini_set = True
```

The docstring three lines above states the intent: *"Each profile gets its own
`profiles/<name>/.env` ... so two people sharing this checkout never share
credentials."* But if `GEMINI_API_KEY` is exported in the shell, the wizard
skips the prompt entirely and **never writes the new profile's `.env`**.

This machine has it exported — I confirmed `$GEMINI_API_KEY` is set in the
login shell. So a second person bootstrapping a profile in this checkout is
silently billed to Morgan's key, told nothing, and gets no `.env` of their own.
**Better version:** still prompt when the profile's own `.env` lacks the key;
offer the shell value as the default rather than assuming it.

---

### Finding 14 — README never tells a new user to run `resume doctor` — MINOR

`README.md:97-169`. **Goal: 3.**

Setup runs steps 1–7 then jumps to "Take it for a spin" → `resume`. The
obvious "did that work?" checkpoint isn't offered until the "Keeping things
healthy" section ~290 lines later, framed as maintenance rather than
verification. **Better version:** add `resume doctor --skip-tests` as step 8,
described as "confirm the install before you spend an API call."

---

### Finding 15 — One more un-swept raw emoji — MINOR

`scripts/bootstrap_bullet_bank.py:352` prints a raw `⚠️` in the
`force=True` warning. **This corrects a factual claim in `PLAN.md:242-245`**,
which states `generate-pdf.mjs:211` is "the last un-swept instance in the
repo." It is not; this one is in a Phase 1 file. Cosmetic. **Goal: 4.**

---

## Corrections to Phase 0

Both of these are the top items on Phase 0's Phase 4 handoff list. Correcting
them here so Phase 4 doesn't spend a session on them.

### `_resume_ensure_profile: command not found` is a review-harness artifact, not a product defect

Phase 0 §1 reported this on 100% of invocations and handed it to Phase 4.
Reproduced, then root-caused:

```
$ type resume
resume is a shell function from
  /Users/morganescott/.claude/shell-snapshots/snapshot-zsh-...sh
$ type _resume_ensure_profile
_resume_ensure_profile not found
```

Claude Code's shell snapshot captures shell functions, and **filters out
underscore-prefixed ones** (zsh's completion-function namespace): the snapshot
contains `resume ()` but **zero** `^_[a-z_]* ()` definitions. So the agent's
shell has the caller without the callee.

In a real terminal sourcing `~/.zshrc` (which does source
`scripts/resume-cli.sh` at line 144), both functions are defined — confirmed:
`_resume_ensure_profile is a shell function from scripts/resume-cli.sh`.

**A real user never sees this error.** Phase 0 could not have known — it read
no source. The underlying brittleness is still worth the one-line guard in
Finding 11, but it is minor and not the symptom Phase 0 saw.

### The Playwright doctor check is *not* a false positive — the environment is broken but lucky

Phase 0 §1 called it a false positive because PDFs rendered successfully while
doctor flagged `node_modules/playwright` missing. Both facts are true and
doctor is correct:

- `node_modules/` **does not exist in this repo at all** — zero entries. `npm
  install` has never been run here.
- Rendering works because Node's resolution algorithm walks up parent
  directories: `node -e "require.resolve('playwright')"` returns
  **`/Users/morganescott/node_modules/playwright/index.js`** — a stray install
  in the *home directory*, two levels above the project.

So PDF generation on this machine depends on a package outside the project that
nothing installs, documents, or guarantees. Deleting `~/node_modules` breaks
every PDF this tool produces, and `resume doctor` is already telling the truth
about why. `CLAUDE.md` line 12 anticipates this ("don't assume it's there just
because `package.json` is committed") — the anticipation is correct and the
condition is currently live.

**Recommended:** run `npm install` in the project (blocked today by Finding 8 —
`npm` isn't on PATH). Doctor's check is right as-is; if anything it understates
the problem, since it reads as a warning rather than "your renders currently
depend on an accident."

---

## The step count, versus the platforms this should beat

The plan asks for a step count against comparable web platforms. Counting
discrete actions a stranger must take between `git clone` and one finished PDF:

| # | Step | Leaves the tool? |
|---|---|---|
| 1–4 | Install Python 3.10+, `venv`, activate, `pip install -r requirements.txt` | — |
| 5–7 | Install Node, `npm install`, `npx playwright install chromium` | yes (Node) |
| 8 | Get a Gemini API key from Google AI Studio | **yes** |
| 9 | Create `profiles/<name>/.env` | — |
| 10 | Install a Nerd Font (or discover `RESUME_BUILDER_ICONS`) | **yes** |
| 11 | Source `resume-cli.sh` into the shell profile | — |
| 12 | Create their own profile (menu-only; see Handoffs) | — |
| 13 | Gather and copy source documents into `.../bootstrap/source_documents/` | **yes** |
| 14–15 | Bootstrap step 0, then step 0.5 | — |
| 16–21 | Bullet-bank stages 1–6 | — |
| 22 | Add a JD, then `resume run` | — |

**~22 actions, four of which leave the tool entirely.** The web platforms this
is measured against are roughly: sign up → upload existing resume → paste JD →
download. Four.

That gap is not itself a defect — the pipeline genuinely does more, and steps
13–21 are what make the output non-fabricated, which is the whole point. But
two things follow directly:

- **Steps 1–11 are pure setup tax and are where the compression is available.**
  A `pipx`/`uv tool install` package would collapse 1–7 and 11 into one line.
  That's Phase 5's territory (packaging) — flagged there, not costed here.
- **Steps 14–21 must be self-diagnosing, and currently are not.** Eight
  sequential steps where two can silently no-op (Findings 1, 3) and report
  green is the difference between "longer but trustworthy" and "longer and you
  can't tell if it worked." Findings 1–4 are all in this band, and fixing them
  is cheap relative to their cost.

---

## Verified as NOT defects

Recording these so no later phase re-investigates them.

- **No cross-profile API-key leak.** Doctor reporting `GEMINI_API_KEY: set in
  shell environment` for a profile with no `.env` looked like `morgan`'s key
  leaking. It isn't — the key is exported in the login shell. With
  `env -u GEMINI_API_KEY -u GOOGLE_API_KEY`, the fresh profile correctly
  reports `not found` and names its own `.env` path in the fix. (The *wizard's*
  handling of that same shell value is a real issue — Finding 13 — but doctor's
  reporting is accurate.)
- **`create_new_profile()` is well-behaved.** It raises `FileExistsError`
  rather than overwriting (`bootstrap_bullet_bank.py:145-146`), scaffolds valid
  empty `board_scanner/` YAML so `scan_boards.py` can't `FileNotFoundError` on
  first run, and seeds `.stignore` into all four sync roots. Verified by real
  invocation: 9 files across 4 directories, all correct.
- **The optional-dependency checks are correctly non-fatal.** `check_go`,
  `check_jobright_cookie`, and `check_signature_image` all hard-return
  `passed=True` with an explanatory detail line. That's the right shape and the
  comments say why.
- **`collect_secrets()` and `collect_linkedin_search_queries()` write good
  deferral instructions** — they name the exact file and the exact line to add
  (`bootstrap_profile.py:818-820`, `:891-893`, `:934-938`). The text is fine;
  Finding 2 is about what happens *after* it, not the wording.

---

## Handoffs

- **Coverage gap — no phase owns this.** `scripts/menu.py:186-215` contains the
  **new-profile creation flow** (the only caller of `create_new_profile()`) and
  the "This profile hasn't been set up yet" gate that Phase 0 flagged as its
  highest-severity finding. `menu.py` is Phase 2's file and was reviewed there
  as a *visual* layer; its onboarding logic is unreviewed. This is step 12 of
  the table above — how a stranger stops being `morgan` — and Phase 1 could not
  read it. Recommend assigning it explicitly to Phase 4.
- **Phase 2:** re-check the Browse & Manage Jobs column truncation (Phase 0 §3)
  under `RESUME_BUILDER_ICONS=unicode` specifically, not just at a real
  terminal width — Finding 7 shows the fallback icon set contains four
  double-width and five ambiguous-width glyphs, which is a plausible cause
  independent of TTY width.
- **Phase 4:** `git status` shows leftover `jds/test_guest_trigger_profile_xyz/`,
  `output/test_guest_trigger_profile_xyz/`, and
  `data/test_guest_trigger_profile_xyz/` with no matching `profiles/` entry —
  test residue that isn't cleaned up. Also, top-level `output/checkpoints/`,
  `output/html/`, `output/json/`, `output/pdf/` coexist with the profile-scoped
  `output/morgan/...`, suggesting pre-profile paths still in use somewhere.
  Both are `tests/`/`profile_paths.py` territory.
- **Phase 5:** Findings 6 and the step table both point at packaging.
  Collapsing setup steps 1–7 and 11 into `pipx install` / `uv tool install` is
  the single largest available reduction on the new-user path, and Phase 5
  already owns that question.

## PLAN.md changes made

- Added `scripts/bootstrap_menu.py` to Phase 1's ownership list (per the
  "Unowned files" rule).
- Noted in Phase 4's section that `menu.py`'s onboarding logic is a coverage
  gap.
- Corrected Phase 4's note that `generate-pdf.mjs:211` is the last un-swept
  emoji instance (Finding 15).
