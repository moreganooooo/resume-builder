# Phase 4 — Reliability & architecture

Model: Opus 5. Date: 2026-08-05. **Goal served: 1** (root causes behind Phase
0's symptoms), with three findings serving goal 2.

**Owned this phase:** `scripts/orchestrator.py`, `scripts/jd_manager.py`,
`scripts/gemini_client.py`, `scripts/profile_paths.py`, checkpoint/resume
logic, `tests/`, `scripts/validate_pdf_text.py`, `scripts/generate-pdf.mjs`,
and `scripts/menu.py:186-215` only (the onboarding-logic carve-out).

No code changed. Every finding below was reproduced by running something, not
inferred from reading. Where a claim rests on source reading alone it says so.

**Working-tree note:** `scripts/validate_pdf_text.py` and
`tests/test_validate_pdf_text.py` carry uncommitted changes implementing Phase
3's Finding 2. That file is Phase 4 territory, so I reviewed and verified the
pending state rather than the committed one. **It works** — see Finding 11.

---

## Answer to the phase question

> *What breaks on the unhappy path?*

**The unhappy paths are detected almost everywhere and acted on almost
nowhere.** That is the single pattern behind this whole report.

This codebase is unusually good at *noticing* trouble. It counts failure
streaks, it swaps models mid-call, it salvages truncated JSON, it verifies its
own PDF text layer after rendering, it defines a `SustainedFailureError` whose
entire purpose is to say "stop, this is quota, not weather." The instrumentation
is genuinely better than most projects this size.

Then, at the decision point, it prints a warning and continues. `orchestrator.py:2447`
detects that a file is not a job description and says "Proceeding with empty
keywords" on the way into a 30-minute paid audit. `orchestrator.py:2990-2997`
receives "this PDF does not exist" and prints `Pipeline complete!`.
`orchestrator.py:3064`'s blanket `except Exception` catches the quota signal
that exists to halt the batch, and moves to the next of 1,144 JDs.
`jd_manager.py:585` catches a corrupt checkpoint and silently returns `{}`,
re-spending the entire run.

So the failure mode is not missing detection and not crashes. It is that
**almost nothing can stop the pipeline**, and the two things that *should* be
advisory-only (a PDF text mismatch, a transient blip) share a return channel
with the things that should be fatal.

Separately and more urgently: **the PDF renderer currently works by accident on
this machine only** (Finding 1). That is not an unhappy-path question — it is
the happy path resting on a file in Morgan's home directory.

---

## Findings

### 1. BLOCKER — Every PDF depends on a stray `node_modules` in the home directory; `npm` isn't installed

`scripts/generate-pdf.mjs:13`, `package.json`. **Goal: 1.** This also resolves
Phase 0 §1's "Playwright doctor false-positive" — **the doctor was correct and
Phase 0 misread it.**

Measured, just now:

```
$ ls node_modules                     -> No such file or directory
$ node -e "require.resolve('playwright')"
                                      -> /Users/morganescott/node_modules/playwright/index.js
$ command -v npm                      -> MISSING from PATH
$ node -e "...playwright/package.json).version"
                                      -> 1.60.0
$ grep playwright package.json        -> "playwright": "^1.61.1"
```

**The failure.** This repo has no `node_modules/`. `import { chromium } from
'playwright'` succeeds only because Node's module resolution walks *up* from
`resume-builder/scripts/` to `/Users/morganescott/` and finds a Playwright
install sitting there next to `autoprefixer`, `browserslist` and
`caniuse-lite` — leftovers from some unrelated project run in the home
directory. Nineteen packages, none of them this project's.

Three consequences, in order of severity:

1. **`rm -rf ~/node_modules` breaks every PDF this tool produces**, with no
   warning, from an action that has nothing to do with this repo.
2. **On any other machine this fails immediately** — including the second
   machine in the Syncthing setup, since sync carries `profiles/`, `jds/`,
   `output/` and `data/` and deliberately not code or `node_modules/`.
3. **The version actually loaded is 1.60.0, which does not satisfy the declared
   `^1.61.1`.** Every PDF ever produced here was rendered by a Playwright the
   project says it does not support.

And the documented remedy cannot be run: CLAUDE.md and the README both say
`npm install && npx playwright install chromium`, but **`npm` is not on PATH**
(Node is — `/usr/local/bin/node`, v22.16.0). So the setup instruction as
written fails on the machine it was written on.

This is the same class of bug as CLAUDE.md's documented "bare `python3` may
resolve to an unrelated stray venv" hazard, in the other ecosystem, and it is
currently live rather than guarded against.

**Concrete fix.** Install npm, run `npm install` in the repo, re-run the
render, and confirm `require.resolve('playwright')` points inside the repo.
Then make the failure loud instead of silent: `generate-pdf.mjs` should resolve
Playwright explicitly relative to the repo and fail with an actionable message
rather than silently accepting whatever ancestor directory supplies. Phase 0's
"false positive" line in `phase-0-smoke.md:26-33` should be corrected.

---

### 2. MAJOR — "Pipeline complete!" is printed for a PDF that does not exist

`scripts/orchestrator.py:2990-2997`, `scripts/validate_pdf_text.py:107-110`.
**Goals: 1, 2.** This is the `ResumeDesignSystem.md:57` guarantee the plan asked
me to verify. **It does not hold.**

Real output, captured from `tests.test_orchestrator_build_checkpoint`:

```
  ⚠ PDF text-layer check found 1 potential issue(s) ...
    - Could not parse generated PDF for verification: [Errno 2]
      No such file or directory: '.../MorganEscott_Resume.pdf'
  ✔ Pipeline complete! PDF → .../MorganEscott_Resume.pdf
```

**The failure.** `validate_pdf_text()` returns *two categorically different
things through one channel*: soft advisories ("bullet not found intact",
genuinely "go look") and hard errors ("the PDF is missing or unreadable",
`:107-110`). `orchestrator.py:2991` treats the whole list as "potential
issue(s)", prints them, and falls through to the unconditional success print at
`:2997`.

Downstream, that success is not cosmetic. `run_pipeline` sees a truthy result
and: moves the JD into `completed/` (`:3072`), logs `mark_completed` (`:3073`),
and appends an application row with **`has_pdf=bool(output_paths.get("pdf"))`**
(`:3084`) — which is the *path string*, always truthy, never a check that a
file is there. The user is told a resume exists, the JD leaves the queue, and
the tracker records a document that was never written.

**Concrete better version.** `validate_pdf_text()` should distinguish its two
result classes — either raise on the unreadable-PDF case or return
`(fatal, advisories)`. `orchestrator.py` should gate the success print and the
`_output_paths` return on `os.path.exists(pdf_out)` plus a non-fatal validation
result, and `has_pdf` at `:3084` should stat the file rather than test a string.

---

### 3. MAJOR — "Drop New Knowledge" gates on a bootstrap artifact, not on whether the profile is set up

`scripts/menu.py:213`. **Goals: 1, 3.** This is Phase 0's highest-severity
finding (`phase-0-smoke.md:135-141`), now root-caused.

```python
if not os.path.exists(bootstrap_bullet_bank.CHECKPOINT_PATH):
    cli_art.console.print(
        "This profile hasn't been set up yet -- use \"New User? Start Here!\" first.")
    return False
```

Measured on the real `morgan` profile:

```
CHECKPOINT_PATH: profiles/morgan/knowledge_base/bootstrap/checkpoint.json
exists?        : False        <-- the gate trips on this
kb_dir exists? : True
bullet bank?   : True         <-- 628 bullets, 1144 tracked JDs
```

**The failure.** The gate asks *"did this profile go through the bootstrap
wizard and leave its checkpoint file behind?"* when the question it means to
ask is *"is this profile set up?"* A profile that was configured before the
bootstrap wizard existed — or whose checkpoint was cleaned up after completing —
is permanently locked out of the feature. Morgan's own profile is in exactly
that state, which is why a fully-configured user with a 628-bullet bank is told
she hasn't set up yet.

**Concrete better version.** `_handle_new_user` twelve lines earlier already
computes the correct signal — `is_existing`, derived from the presence of a
real `knowledge_base/` (`menu.py:~170`). Gate `_handle_update_knowledge` on that
same predicate, extracted into one shared helper so the two menu entries can
never disagree again. The bootstrap checkpoint is evidence of *how* a profile
was created, never of *whether* it exists.

*(I read one constant — `bootstrap_bullet_bank.py:47` — to resolve the path
`menu.py:213` depends on. That file is Phase 1's; I read nothing else in it.)*

---

### 4. MAJOR — The pipeline detects "this is not a job description" and proceeds anyway, into the most expensive step

`scripts/orchestrator.py:2447-2448`. **Goal: 1.** Root cause of Phase 0 §4
(`phase-0-smoke.md:194-209`).

```python
jd_keywords = GeminiClient.parse_json(keyword_text or "")
if not jd_keywords:
    print("  WARNING: JD keyword extraction returned empty. Proceeding with empty keywords.")
```

**The failure.** Step 1 is a cheap single call whose empty result is a strong,
already-computed signal that the input is not a JD. The code names that signal,
prints it, and walks straight into Step 2 (mining) and Step 3 (the bullet
audit). Phase 0 pointed the tool at a file containing `this is not valid JSON
or a real job description at all {{{ broken` and watched it start GEM-scoring
and rewriting real bullets against the paid API.

The cost is not small. With `GEMMA_MIN_INTERVAL_SECS = 65`
(`gemini_client.py:93`), the audit paces one Gemma call per 65 seconds — a
30-bullet audit is **over half an hour of wall clock and real spend** before
anything JD-specific happens. Pointing the tool at the wrong file is an ordinary
mistake, and it is currently expensive.

**Concrete better version.** Make that branch a stop, not a shrug: abort with
"No keywords could be extracted from `<path>` — this doesn't look like a job
description. Nothing was spent beyond the initial keyword call." In interactive
single-file mode, offer to continue anyway; in batch, mark failed and move on.
The detection already exists — only the decision is wrong.

---

### 5. MAJOR — `SustainedFailureError` is swallowed by the batch loop, so a dead quota burns the full retry budget on all 1,144 JDs

`scripts/orchestrator.py:3064-3066`, `scripts/gemini_client.py:379-388`.
**Goal: 1.**

`SustainedFailureError`'s docstring says it is "a signal this is a quota-level
issue, not a transient blip," and its message tells the user to swap the API
key. `rewrite_bullets.py:1385` handles it. `run_pipeline` does not:

```python
except Exception as e:
    result = None
    print(f"  ✖ Unhandled exception building resume for {path}: {e}")
```

**The failure.** A `SustainedFailureError` is an `Exception`. In batch mode it
is caught per-JD, printed as one line among many, the JD is marked failed, and
the loop advances to the next one — which fails the same way. On a queue of
1,144 pending JDs, a revoked or exhausted key produces 1,144 sequential full
retry cycles. Each is up to 6 attempts with exponential backoff capped at 90s
(`gemini_client.py:313, 334`), so the floor is hours of sleeping before the run
gives up, and the one message that explains what to actually do scrolls past
1,144 times.

**Concrete better version.** Catch `SustainedFailureError` explicitly in
`run_pipeline`'s loop, before the blanket handler, and break — reporting how
many JDs remain untouched and surfacing the "swap `GEMINI_API_KEY`" instruction
once. The exception type already exists for exactly this; only the batch loop
declines to honor it.

---

### 6. MAJOR — Checkpoint writes are non-atomic, corruption is discarded silently, and the folder is inside a Syncthing sync root

`scripts/jd_manager.py:578-593`. **Goal: 1.**

```python
def load_checkpoint(job_key):
    ...
    except (json.JSONDecodeError, OSError):
        return {}                      # silent

def save_checkpoint(job_key, data):
    with open(_checkpoint_path(job_key), "w", encoding="utf-8") as f:
        json.dump(data, f, ...)        # truncate-then-write, not atomic
```

Measured:

```
CHECKPOINTS_DIR: output/morgan/checkpoints
sync roots     : profiles/morgan, jds/morgan, output/morgan  <-- contains it, data/morgan
```

**The failure, three ways into one hole.** `open(..., "w")` truncates first and
writes second, so any interruption between those — Ctrl-C, crash, power loss —
leaves a truncated JSON file. `load_checkpoint` then catches the resulting
`JSONDecodeError` and returns `{}`, which is indistinguishable from "no
checkpoint exists." The next run silently restarts from Step 1 and re-spends
the entire pipeline, telling the user nothing.

CLAUDE.md's promise — "Interrupted runs resume from `output/<profile>/checkpoints/`
instead of restarting" — is exactly what a mid-write interruption breaks, and
interruption is the case the feature exists for.

The Syncthing exposure compounds it: `output/<profile>/` is one of the four
sync roots (`profile_paths.sync_roots()`), so checkpoints replicate between
machines. A non-atomic write is precisely what a file syncer can catch
mid-flight, and a `.sync-conflict-*` copy of a checkpoint is an outcome nothing
here anticipates.

**Concrete better version.** Write to `<path>.tmp` and `os.replace()` onto the
final name — atomic on POSIX, and the standard fix. Separately, log when a
checkpoint exists but fails to parse ("checkpoint for `<job_key>` was corrupt
and has been discarded; this run starts fresh") rather than returning `{}` as
though it were absent. The two are independent; the logging change is worth
having even before the atomicity one.

---

### 7. MAJOR — `normalizeTextForATS()` runs on the wrong layer: it is blind to HTML entities, and structurally cannot see ligatures

`scripts/generate-pdf.mjs:35-89`, with `scripts/render_html.py:40-50` as the
tell. **Goal: 2.** This is the plan's "pick a side" question at
`PLAN.md:211-216`. **I pick CSS. Do not extend the normalizer.**

I extracted `normalizeTextForATS` and ran it directly. Results:

```
REWRITTEN  em-dash unspaced      "strategy—not tactics"    -> "strategy-not tactics"
UNCHANGED  HTML entity em-dash   "strategy&mdash;not"      -> "strategy&mdash;not"
UNCHANGED  HTML entity nbsp      "Series&nbsp;A"           -> "Series&nbsp;A"
UNCHANGED  numeric entity arrow  "lead&rarr;close"         -> "lead&rarr;close"
REWRITTEN  middot in a name      "Jean·Luc Picard"         -> "Jean | Luc Picard"
REWRITTEN  pound in salary       "£120k package"           -> "GBP 120k package"
REWRITTEN  bullet char in prose  "the • marker itself"     -> "the | marker itself"
```

**a) It is entity-blind, and something already depends on that.** Every
substitution matches raw codepoints only. `&mdash;`, `&nbsp;`, `&rarr;` sail
through untouched and render as exactly the characters the normalizer exists to
eliminate. `render_html.py:40-50` emits `&rarr;` *specifically* so this regex
cannot match it — a workaround that only functions because the normalizer is at
the wrong layer. Any future content path that emits entities silently opts out
of ATS normalization, and nothing reports it.

**b) It cannot see ligatures, and never could.** Verified against the shipped
artifacts:

```
HTML source (what the normalizer inspects) : "workflows"   (plain, 1 occurrence)
PDF text layer (what an ATS reads)         : "workﬂows"    (U+FB02)
```

The ligature is created by the font shaper **at render time**, inside Chromium,
after `generate-pdf.mjs` has finished transforming the source and handed the
file over. There is no character in the normalizer's input to match. Adding
`ﬁ`/`ﬂ` to `sanitizeText()` would be dead code.

So the answer to the plan's question is unambiguous: **the CSS fix that Phase 2
pinned (`phase-2-visual-design.md` Finding 1) is the only one of the two that
can work,** and the normalizer stays scoped to source text. Phase 2 and Phase 3
already agreed on the location; this closes the layering argument behind it.

**c) The lossy substitutions that do fire can damage real content.** Two are
worth acting on:

- **`—` → `-` with no spacing** (`:67`). Unspaced em-dashes are standard US
  house style, so `strategy—not tactics` becomes `strategy-not tactics`, and an
  ATS tokenizes `strategy-not` as one invented compound word. This is the same
  keyword-damage failure as the ligature bug, from a different direction, and it
  is currently a *silent rewrite of Morgan's prose*. `— ` → ` - ` (spaced) fixes
  it.
- **`·` → ` | `** (`:80`). Fine as a separator, wrong inside a name
  (`Jean·Luc` → `Jean | Luc`). Narrow the pattern to require surrounding
  whitespace, so it only fires where the character is actually acting as a
  separator.

`£` → `GBP ` and `•` → ` | ` I'd leave: the ATS benefit outweighs the rare
prose collision, and `£` is already handled thoughtfully (the `¥` comment at
`:82-85` shows the tradeoff was reasoned about).

**d) The masking step is sound.** `:40-47` masks `<style>`/`<script>` bodies
with ` MASK<n> ` before substitution and restores them at `:61`. The
token contains no `<` or `>`, so the tag-walker treats it as text; no
substitution touches NUL or digits; and the restore uses a function replacement,
so `$&` sequences in CSS/JS cannot be reinterpreted. I tried to corrupt a mask
boundary and could not. **No finding here** — the plan asked, and the answer is
that it holds.

---

### 8. MINOR — Neither `node` subprocess has a timeout, and `capture_output` hides the hang

`scripts/orchestrator.py:2375-2378` (cover letter), `:2907-2910` (resume).
**Goal: 1.**

```python
pdf_result = subprocess.run(
    ["node", pdf_script, html_out, pdf_out, "--format=letter"],
    capture_output=True, text=True
)
```

No `timeout=`. Inside `generate-pdf.mjs`, `page.goto(..., waitUntil:
'networkidle')` (`:174`) and `chromium.launch()` (`:170`) do inherit
Playwright's 30s defaults, so the plan's specific worry there is covered — but
`await page.evaluate(() => document.fonts.ready)` (`:177`) has **no default
timeout in Playwright**. A font that never settles leaves Node waiting on a
promise that never resolves, and Python waiting on a subprocess that never
exits, with `capture_output=True` swallowing every byte that might have hinted
at it. The user sees a cursor.

**Concrete better version.** `timeout=180` on both `subprocess.run` calls with a
`TimeoutExpired` handler that reports the stage; and wrap the `fonts.ready`
evaluate in `Promise.race` against a timer so the Node side fails loudly first.

Related, same file: **`node` missing entirely raises `FileNotFoundError`**
(reproduced), which no local handler catches — it surfaces via
`orchestrator.py:3064`'s blanket handler as "Unhandled exception building
resume for …: [Errno 2] No such file or directory: 'node'". Correct-ish, but it
should name the actual remedy given Finding 1 makes this reachable.

---

### 9. MINOR — Truncated generations are treated as success and silently salvaged into partial objects

`scripts/gemini_client.py:365`, `:160-182`, `:193-196`. **Goals: 1, 2.**

Two behaviors compose badly:

- `finishReason == "MAX_TOKENS"` is accepted alongside `STOP` as a normal
  return (`:365`). Truncation is not signalled to the caller.
- When the resulting partial JSON fails `json.loads`, `parse_json` falls back to
  `_salvage_fields` (`:196`), which regex-scrapes whatever top-level string and
  number pairs survived.

**The failure.** The caller receives a well-formed `dict` and cannot tell it
apart from a complete response. `_salvage_fields`' own docstring is candid that
it recovers "the early, valid field(s)" of an answer that "never closes" — which
for `TemplateSchema` means a resume object missing whatever came after the
truncation point. `build_tailored_resume` tests `if not trimmed` (`:2955`) —
a salvaged fragment is truthy, so it passes.

The salvage behavior is defensible; recovering a real answer beats discarding
it. What's missing is the signal. **Concrete better version:** return the
`finishReason`, or a `truncated: True` flag, in the usage dict `generate()`
already returns, and have `parse_json` mark salvaged results so callers can
choose. Today nothing downstream can distinguish a complete resume from half of
one.

---

### 10. MINOR — Network errors are reported as the last whitespace-delimited token of the exception

`scripts/gemini_client.py:314`. **Goal: 1.**

```python
print(f"    WARNING: Network error ({GeminiClient._timeout}s): "
      f"{str(e).split()[-1].strip()}. Waiting {sleep_dur:.1f}s ...")
```

`str(e).split()[-1]` takes the final token of a `requests` exception string. For
a genuine offline failure, `requests` produces a multi-line
`ConnectionError(... NewConnectionError('... [Errno 8] nodename nor servname
provided, or not known'))` — and the user is shown:

```
WARNING: Network error (180s): known')). Waiting 12.4s before retry 1/6...
```

The diagnostic content is discarded and the punctuation is kept. **Concrete
better version:** `type(e).__name__` plus the first ~120 characters of the
message, which keeps the line short without throwing the error away.

---

### 11. MINOR — Two pdfminer warnings print unattributed on every run (Phase 0 §2a, root-caused)

`scripts/validate_pdf_text.py:108`. **Goal: 1.**

Phase 0 recorded `Could not get FontBBox from font descriptor because None
cannot be parsed as 4 floats`, printed twice, interleaved with unrelated output.
Source confirmed:

```
pdfminer logger effective level: DEBUG
handlers configured by this project: []   propagate: True
```

It is pdfminer's own logger, emitted from `extract_text()` at `:108`, reaching
the root logger unconfigured and unlabelled. Harmless to correctness — the text
extraction succeeds — but it reads as the tool malfunctioning.

**Concrete better version.** `logging.getLogger("pdfminer").setLevel(logging.ERROR)`
at module scope in `validate_pdf_text.py`. One line, and it is this module's
warning to own since it is the only caller.

---

### 12. MINOR — Page count is a regex over raw PDF bytes, and a zero silently disables the 2-page rule

`scripts/generate-pdf.mjs:196-197`, consumed at `scripts/orchestrator.py:2916`.
**Goal: 1.** This is the plan's "is an approximation load-bearing anywhere?"
question — **yes.**

```javascript
const pdfString = pdfBuffer.toString('latin1');
const pageCount = (pdfString.match(/\/Type\s*\/Page[^s]/g) || []).length;
```

Verified correct today against both shipped PDFs (`approx=2 real=2`,
`approx=1 real=1` vs pypdf). The concern is not the current number, it is what
happens when it is wrong:

```python
is_final = page_count is None or page_count <= 2 or trim_attempt >= max_trim_attempts
```

A `0` or `None` short-circuits to `is_final = True`, the trim loop breaks
immediately, and the guard at `:2981` (`page_count is not None and > 2`) does not
fire. **The entire 2-page enforcement silently switches off and a 4-page resume
ships.** The regex depends on Chromium emitting an uncompressed page tree; if a
future Chromium writes the page objects into an object stream, the count becomes
0 and nothing anywhere reports the difference between "1 page" and "I could not
tell."

**Concrete better version.** This is a hard design requirement per
`ResumeDesignSystem.md`, so it should not rest on a byte regex when
`pypdf`/`pdfminer` are already dependencies on the Python side — count pages
after the fact from `pdf_out`. Minimum viable alternative: treat `page_count is
None` as a failure to verify rather than as "fine," so it can never be the
reason a long resume passes.

---

### 13. MINOR — Raw `❌` emoji at `generate-pdf.mjs:211`

Noted by the plan (`PLAN.md:247-251`) as cosmetic and out of remit. Confirmed
present, along with `📄📁📏🧹✅📊📦` at `:123-125`, `:150`, `:199-201` — the whole
file predates the 2026-08-05 symbol sweep, not just that one line. Left
unfixed per the no-code-changes rule. It is a Phase 2 concern (themed symbols),
handed off below.

---

## Test coverage: which unhappy paths are actually pinned?

1,091 tests pass (Phase 0), and 48 of the ones covering my files pass against
the current working tree including the uncommitted `validate_pdf_text.py`
changes — I ran them:

```
$ python -m unittest tests.test_validate_pdf_text tests.test_gemini_client \
                     tests.test_orchestrator_build_checkpoint
Ran 48 tests in 9.728s
OK
```

The suite is substantial and the checkpoint tests in particular are thorough
(`test_orchestrator_build_checkpoint.py`, 1,053 lines). But the specific
failures this phase is about are the ones not pinned:

| Unhappy path | Finding | Test coverage |
|---|---|---|
| Corrupt/truncated checkpoint discarded silently | 6 | **none** — no test writes invalid JSON to a checkpoint |
| `node` missing / `FileNotFoundError` on render | 1, 8 | **none** |
| `MAX_TOKENS` truncation treated as success | 9 | **none** |
| `_salvage_fields` partial-object recovery | 9 | **none** |
| Success claimed when PDF absent | 2 | **none** — the test that *exhibits* it asserts nothing about it |
| `SustainedFailureError` reaching `run_pipeline` | 5 | only raised in `test_gemini_client.py:120`; batch-loop behavior untested |
| PDF subprocess timeout | 8 | **none** |

The pattern matches the findings: the code paths that detect trouble are well
tested; the decisions made *after* detection largely are not. The highest-value
additions are a corrupt-checkpoint test (cheap, and pins a real data-loss path)
and a "PDF missing ⇒ pipeline must not report success" test (pins Finding 2
against regression).

---

## `orchestrator.py` at 3,125 lines — real problem, or just large?

**Just large, with one genuine hotspot.** The plan asked for evidence, not
reflex.

Measured composition:

| Region | Lines | Character |
|---|---|---|
| Constants, path/model setup | 1–260 | flat, low risk |
| Module-level helpers (~20 fns) | 262–617 | small, individually testable |
| Pydantic schemas (~25 classes) | 618–1043 | **~425 lines, declarative** |
| `class ResumeEngine` (26 methods) | 1060–3002 | the substance |
| `run_pipeline` / `main` | 3005–3125 | thin |

Roughly a seventh of the file is schema declarations, which are flat by nature
and carry no branching. The helpers are small and already have dedicated test
files (`test_orchestrator_output_stem.py`, `_load_prompt`, `_fit_composite_score`,
and others) — evidence that the module has in fact been decomposed where
decomposition helped.

The real number is not 3,125. It is **`build_tailored_resume` at ~614 lines**
(`:2388-3002`), a single method carrying seven sequential steps, four checkpoint
save points, an interactive approval gate, and a nested trim loop with its own
retry accounting. The second-largest is ~360 lines (`:1639-1999`).

That method is where Findings 2, 4 and 12 all live, and that is not a
coincidence: the reason "detects the problem, proceeds anyway" recurs is that
each step's error branch is 300 lines away from the success print that
contradicts it, with no intervening structure to make the inconsistency visible.

**So: splitting the file would buy little. Splitting that method would buy the
findings above.** The natural seams are already marked by its own `--- Step N ---`
comments, and each step already has a checkpoint boundary — which is to say the
decomposition is latent in the code and just never extracted. Worth doing when
Findings 2 and 4 are fixed, since both edits land inside it anyway; not worth a
standalone refactor.

---

## Things I checked that turned out fine

Recording these so a later phase doesn't re-spend on them:

- **JD metadata leaking into prompts.** `jd_manager.read_jd_text()` (`:302-321`)
  correctly strips any underscore-prefixed key generically before returning, and
  passes non-JSON JDs through untouched. The convention CLAUDE.md documents is
  actually enforced. No finding.
- **Profile switching staleness.** I expected module-level constants like
  `jd_manager.JDS_DIR` to go stale after `set_active_profile()`. They don't —
  `profile_paths.set_active_profile()` (`:71`) explicitly `importlib.reload`s
  dependent modules, and it raises a clear, actionable `ValueError` for an
  unknown profile. Better than expected.
- **`normalizeTextForATS`'s mask boundaries.** Finding 7(d) — I tried to corrupt
  one and could not.
- **Page count correctness today.** Finding 12 — verified matching against pypdf
  on both shipped PDFs; the finding is about fragility, not a current wrong
  number.
- **`Ctrl-C` handling.** `run_pipeline`'s blanket handler is `except Exception`,
  which does not catch `KeyboardInterrupt` — consistent with Phase 0's observed
  clean interrupt. The checkpoint-write race (Finding 6) is the real interrupt
  risk, not the handler.
- **The pending `validate_pdf_text.py` fix.** Run against the real shipped
  resume, it collapses 5 warnings (3 false positives) into 1 that names the
  actual defect and points at the CSS fix. It does what Phase 3 asked. Ship it.

---

## Handoffs

- **Phase 1 — `resume-cli.sh`:** Phase 0's `_resume_ensure_profile: command not
  found` on every single invocation (`phase-0-smoke.md:18-20`) is in
  `scripts/resume-cli.sh`, which is Phase 1's file. I did not read it. It is a
  shell-function definition/ordering bug, and it is the first thing any user
  sees on every run.
- **Phase 1 — `doctor.py`:** no change needed to the Playwright check itself
  (Finding 1 confirms it is correct), but doctor should probably also fail when
  `npm` is absent, since the remedy it recommends can't be run without it.
  Phase 1 owns the wording.
- **Phase 1 — `bootstrap_bullet_bank.py`:** Phase 0 §2b's `unrecognized KU/KCKCC
  achievement key ''` warning on every recommendation application originates in
  the education achievement-key enum merged at `orchestrator.py:2949`
  (`extra_schema_properties`), but the key *options* come from the profile's
  bootstrap-written `profile.yml`. The empty-string key means the enum contains
  a blank option. The generation side is Phase 1's territory.
- **Phase 2 — `liveness.py` / `check-liveness.mjs`:** Phase 0's orphaned-child
  process on interrupt (`phase-0-smoke.md:233-243`) is a `subprocess` call in
  `liveness.py`, which no phase owns and I do not. Same class as Finding 8 (no
  timeout, no process-group cleanup); worth claiming under the unowned-files
  rule.
- **Phase 2 — emoji sweep:** `generate-pdf.mjs` was missed entirely by the
  2026-08-05 consistency sweep — `:123-125`, `:150`, `:199-201`, `:211`. Finding 13.
- **Phase 2 — ligature CSS fix:** Finding 7 closes the layering question in
  Phase 2's favor. The fix belongs in both templates, exactly as
  `phase-2-visual-design.md` Finding 1 specifies, and nothing should be added to
  `generate-pdf.mjs` for it.
- **`PLAN.md` correction:** `phase-0-smoke.md:26-33` records the Playwright
  doctor check as a false positive. It is not; see Finding 1. Worth correcting
  in place so a later reader doesn't dismiss the warning again.
