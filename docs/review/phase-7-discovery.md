# Phase 7 — Job discovery, liveness & follow-up

Run 2026-08-05, Opus 5. Scope per `PLAN.md` Phase 7. No code changes made.

**Files reviewed:** `scan.py`, `scan_ats.py`, `scan_boards.py`, `scan_jobright.py`,
`scan_linkedin.py`, `company_research.py`, `followup.py`, `situational_roles.py`,
`batch_evaluate.py`, `liveness.py`, `check-liveness.mjs`, `liveness-core.mjs`,
`liveness-browser.mjs`, `maintenance.py`, `git_update.py`, `dashboard.py`.

## Unowned files — recorded, NOT absorbed

`board-scanners/` (the ~26 vendored Node provider modules plus `run_provider.mjs`)
belongs to no phase. It is where every outbound HTTP request in the "boards"/"ats"
sources is actually made — the real answer to this phase's rate-limit question
lives there, not in `scan_boards.py`, which only shells out to it. This phase read
none of it: ~26 modules is a phase-sized job, not a passing absorption, and the
same reasoning Phase 4 applied to `liveness.py` applies here. **Also note it is
outside Phase 9's residue check as written** (`scripts/`, `resume-engine/`,
`dashboard/` — `board-scanners/` is in none of those). Recommend a dedicated
assignment rather than folding it into Phase 9.

---

## Findings

### 1. `_ScanWarningCollector` silently discards every diagnostic the scanners emit
**Severity: major** · `scripts/scan.py:28-48`, installed at `:122-124` · **Goals 1, 3**

Attaching any handler to the root logger takes over from Python's last-resort
handler. `emit()` appends only records carrying `scan_warning=True` and drops
everything else on the floor. Every diagnostic in `scan_linkedin.py` and
`scan_jobright.py` is a plain `logging.error`, so during a scan **none of them
reach the user or any log**.

Runtime evidence — collector installed exactly as `run_scan()` installs it:

```
logging.error("SCANNER SAYS: LinkedIn cookie missing -- log into Chrome")
logging.warning("plain warning from some other module")
→ collector captured: 0     (and nothing printed to the terminal)
```

Messages destroyed this way include the only actionable guidance the subsystem
has:

- `scan_linkedin.py:153` — "No live li_at cookie found. Log into LinkedIn in
  Chrome and keep it open, then retry."
- `scan_linkedin.py:145` — "No linkedin_search_queries or target_roles.primary
  configured in profile.yml"
- `scan_linkedin.py:244` — "LinkedIn scraper run failed: `<exception>`"
- `scan_jobright.py:41` — "JOBRIGHT_COOKIE_STRING not configured"
- `scan_jobright.py:128` — "Auth error -- JobRight cookie may be expired"

The user sees a scan report row reading `linkedin  0 fetched` and has no way to
learn why. For a stranger (goal 3) this is unrecoverable without reading source.

The class docstring at `:37-39` asserts the exact opposite — "so an unrelated
stray warning elsewhere in the app during a scan isn't silently swallowed." It is
swallowed; the second line of the test above proves it.

**Concrete fix:** `emit()` should fall through to a real handler for records it
doesn't collect (`logging.StreamHandler` on the logger, or re-raise via
`logging.lastResort.handle(record)`), *or* the two scanners should route their
failures through `scan_boards._scan_warning()` so `render_scan_report()` surfaces
them as reason lines.

---

### 2. Liveness subprocess has no timeout and no bound on total runtime
**Severity: major** · `scripts/liveness.py:102-105`; `scripts/check-liveness.mjs:31` · **Goal 1**

`subprocess.run(["node", script, ...])` is called with no `timeout=`. Downstream:

- `check-liveness.mjs:31` — `chromium.launch({headless:true})` with no timeout
  (same defect class as Phase 4's `generate-pdf.mjs:170` finding, different file).
- `liveness-browser.mjs:12` — `NAV_TIMEOUT_MS` is **per URL**, not per run.
- `check-liveness.mjs:36-49` — sequential loop over every candidate, no cap.

So the ceiling is `candidates × ~16s`, unbounded, inside one blocking Python call.
`run_liveness_check()` feeds it every pending JD (`liveness.py:207`); `run_scan()`
feeds it every newly written JD (`scan.py:171`). A 100-JD queue is a ≥27-minute
call the user cannot cancel cleanly (see finding 3 for why it also looks frozen,
and finding 4 for what happens when they kill it).

**Concrete fix:** pass `timeout=` sized from the candidate count, and give
`chromium.launch()` an explicit timeout.

---

### 3. The liveness progress indicator is not incremental — it all arrives at the end
**Severity: major** · `scripts/liveness.py:110-113` · **Goals 1, 4**

The comment reads "Print incremental progress from stderr as it arrives." It
cannot. `subprocess.run(stderr=subprocess.PIPE)` buffers the whole stream and
`proc.stderr` does not exist until the process has already exited — the loop at
`:112` replays a finished transcript.

This wastes real effort on the Node side: `check-liveness.mjs:41-46` deliberately
writes `[i/N] <icon> <status> <file>` lines to stderr *specifically* so stdout
stays parseable for progress reporting, and every one of them is withheld.

Combined with finding 2, the actual user experience of a liveness check over a
real queue is a terminal that prints a rule, then nothing, for minutes.

**Concrete fix:** `Popen` with `stderr=PIPE`, iterate `proc.stderr` line by line
printing as it arrives, `communicate()` for stdout at the end.

---

### 4. Orphaned Node child — root cause confirmed, and it is not what it looks like
**Severity: major** · `scripts/liveness.py:102-105` · **Goal 1**
*(Phase 0's finding, `phase-0-smoke.md:233-243`, assigned to this phase.)*

Reproduced, with the mechanism isolated. Two things are commonly assumed here and
one of them is wrong:

**Chromium is NOT separately orphaned.** Verified directly — launched Playwright
chromium from Node, confirmed three `chrome-headless-shell` processes running,
`kill -9`'d the Node parent, and all three terminated within seconds. Playwright's
browser process watches its parent pipe and self-terminates. This is not a leak.

**The Node process itself is orphaned, and `subprocess.run` is the reason.**
CPython's `run()` deliberately does *not* kill the child on `KeyboardInterrupt`
(bpo-25942) — it assumes the terminal already delivered SIGINT to the whole
foreground process group. When the signal reaches only the Python PID, nothing
ever signals Node:

```
python parent → node child
kill -INT  <python pid>  → node still alive
kill -KILL <python pid>  → node still alive
```

Both verified. Real terminal Ctrl-C is therefore usually fine (process-group
delivery covers Node), but every other path leaks: a `kill` from another window,
an IDE stop button, SIGHUP on SSH disconnect, a parent crash — and, most likely
in practice, a user escaping the no-timeout hang from finding 2 the only way
they can. The orphan keeps making outbound requests to employer sites.

**Concrete fix:** replace `subprocess.run` with `Popen` inside `try/finally` that
calls `proc.kill()` + `proc.wait()`, or add `timeout=` (finding 2) so the hang
that provokes a manual kill stops happening.

---

### 5. First scan on a fresh profile is unbounded, unfiltered, and browser-verified
**Severity: major** · `scripts/scan.py:170-171`; `bootstrap_bullet_bank.py:114-129` · **Goals 1, 3**

`run_scan(verify=True)` (the default, and the only mode the menu offers —
`menu.py:264`) runs `liveness.verify_jd_paths()` over **every** newly written JD,
with no cap and no confirmation prompt.

For a stranger that compounds badly. The `scan_filters.yml` scaffold ships with
`title_filter.positive: []`, and `_passes_title_filter` (`scan_boards.py:143`)
treats an empty positive list as "everything passes" — permissive by design, and
correctly documented as such. But it means a new profile's first `resume scan`
writes *every* remote listing from 17 aggregator boards into `jds/`, then
sequentially opens each one in a headless browser.

The three components are each defensible alone; together they make step one of a
stranger's discovery workflow a multi-hour hang producing hundreds of junk JDs.

**Concrete fix:** cap or confirm the verify pass above some threshold, and have
the scaffold ship with `positive:` seeded from `profile.yml`'s
`target_roles.primary` rather than empty.

---

### 6. Scanners can write JD files with a null or empty description
**Severity: major** · `scripts/scan.py:159`; `scan_linkedin.py:184,213` · **Goal 2**

`_write_jd_file()` writes whatever the fetcher produced with no validation.

`scan_linkedin.py:184` sets `final_desc = primary_desc if primary_desc else
extras["backup_description"]`, and `extras["backup_description"]` is `None`
whenever `_fetch_personalized_extras()` fails — which it does silently, because
that function wraps everything in `except Exception` and logs at **`logging.debug`**
(`:86-87`), below the collector's WARNING threshold *and* discarded by finding 1
even if it weren't. Result: `"description": null` in a JD file, with no trace of
why.

`scan_boards._fetch_posting_text()` returns `""` on failure by explicit design
("a thin JD (title/company only) is still written rather than dropping the posting
entirely" — `:229-231`). That is a reasonable choice for the boards path, but
nothing downstream in scan.py distinguishes a thin JD from a complete one, so a
title-only posting reaches the tailor stage looking exactly like a real one.

**Concrete fix:** validate in `_write_jd_file()` — record a `_scan` metadata key
(per CLAUDE.md's underscore convention) marking description length, and either
skip or visibly flag postings below a usable threshold in the scan report.

---

### 7. Dedup re-scans the whole JD corpus once per candidate job
**Severity: major (performance)** · `scripts/scan.py:151-155` · **Goal 1**

`jd_manager.job_key_known()` is called once per candidate. Each call `os.listdir`s
four directories (`jds/`, `completed/`, `archived/`, `expired/`) and runs
`compute_job_key()` — a file open and parse — on every file it finds.

`run_scan()` correctly hoists the `JDTracker` out of the loop (`:114`) so the CSV
is read once. The directory walk is not hoisted, so the cost is
`candidates × total_JD_files` file opens. On a mature profile with several hundred
completed JDs and a few hundred candidates that is six figures of syscalls,
attributed to nothing the user can see — it reads as another hang, on top of
findings 2, 3 and 5.

The fix belongs at this call site (build the known-key index once per `run_scan()`
and match against it in memory); `jd_manager.py` itself is Phase 4's file and is
not the thing that needs changing.

---

### 8. `--no-verify` persists a false "active" liveness claim for 24 hours
**Severity: minor** · `scripts/scan.py:89-93`; `scripts/liveness.py:29-40` · **Goal 1**

`_write_jd_file()` unconditionally stamps `_liveness = {"result": "active",
"reason": "confirmed to exist by scan", "checked_at": now}` in the exact shape
`save_liveness()` writes — correct per CLAUDE.md's metadata convention, and
deliberate.

But the seed is written *before* verification, and `cli.py:260` exposes
`--no-verify`. On that path the optimistic seed is never corrected, and because
`_is_recently_checked()` skips anything stamped within `RECENCY_HOURS` (24), the
next `resume liveness` run also skips it. A dead posting stays in the active queue
for a full day with a persisted claim that it was confirmed alive.

**Concrete fix:** when `verify=False`, either omit the seed or write it with a
`result` the recency check does not treat as settled (e.g. `"unverified"`).

---

### 9. `LIVENESS_INPUT_PATH` is not profile-scoped
**Severity: minor** · `scripts/liveness.py:22` · **Goal 1**

`output/liveness_input_tmp.json` — a fixed path at the `output/` root, bypassing
`profile_paths`. CLAUDE.md names `profile_paths.py` the single source of truth for
every profile-scoped path. Two profiles running liveness concurrently overwrite
each other's candidate list; the file also sits outside `sync_roots()`
(`output/<name>/`), so it is stray relative to every other output artifact.

---

### 10. LinkedIn enrichment fires unpaced authenticated requests on the live session
**Severity: minor** · `scripts/scan_linkedin.py:182`, `:52-89` · **Goal 1**

The scraper itself is paced correctly — `slow_mo=5` at `:235` is five *seconds*
between actions, a deliberate 429 guard. But `on_data` calls
`_fetch_personalized_extras()` for every result, and that is a separate
`requests` GET carrying Morgan's real `li_at` cookie, outside the scraper's pacing
entirely. Three saved searches × 20 results is ~60 back-to-back authenticated
hits to `linkedin.com/jobs/view/*`.

This is the one place in the subsystem with genuine account-risk exposure — it is
her live logged-in session, not an anonymous fetch, and a restriction lands on the
account she job-searches from. A `time.sleep()` matching `slow_mo` costs five
minutes on a scan that already takes longer than that.

---

### 11. Node liveness checker leaves the browser open on any mid-loop failure
**Severity: minor** · `scripts/check-liveness.mjs:31-53` · **Goal 1**

`browser.close()` at `:51` is not in a `finally`. `checkUrlLiveness` catches its
own navigation errors (`liveness-browser.mjs:48`), so the loop is fairly robust,
but any throw outside that — a page crash, an OOM, malformed candidate JSON —
propagates to `main().catch()` at `:105`, which prints and `process.exit(1)` with
the browser still running and **every result collected so far discarded**. A
90-JD run that fails on JD 89 returns nothing.

Same shape at `:66-82` in `runTextMode`.

---

### 12. Report entry removal matches by value, not identity
**Severity: minor** · `scripts/scan.py:179` · **Goal 4**

`result["new_jobs"].remove(new_job_entry)` removes the first dict *equal* to the
target. Entries are `{"company": ..., "title": ...}`, so two postings from the
same company with the same title — routine on aggregator feeds — cause the wrong
entry to be dropped from the scan report. Counts stay right; the named row is
wrong. Cosmetic, but it is the report a user reads to decide what to work on.

---

### 13. `expired_paths` returns pre-move paths
**Severity: minor** · `scripts/liveness.py:172-174` · **Goal 1**

`shutil.move(source_file, dest)` then `expired_paths.append(source_file)` — the
list names the old location, which no longer exists. `scan.py:172` happens to key
`written_paths` by that same pre-move path so today's only consumer works by
coincidence. Any future caller that tries to open a returned path gets
`FileNotFoundError`.

---

### 14. Liveness error path drops the `code` field
**Severity: minor** · `scripts/liveness-browser.mjs:49-54` · **Goal 1**

Every `classifyLiveness()` return carries `{result, code, reason}`. The catch
branch returns only `{result, reason}`, so `check-liveness.mjs:48` writes
`code: undefined` into the results JSON for every navigation failure —
indistinguishable from a genuine classification with no code. Add
`code: 'navigation_error'`.

---

### 15. Normal dashboard quit reports an error
**Severity: minor** · `scripts/dashboard.py:49-51` · **Goals 1, 4**

`go run` returns non-zero when the program it wraps is interrupted, so quitting
the TUI with Ctrl-C surfaces "Dashboard exited with an error (code 1)." to a user
who did the ordinary thing. Treat 130/`signal: interrupt` as a clean exit.

---

### 16. Raw emoji survive the consistency sweep in the Node liveness checker
**Severity: minor** · `scripts/check-liveness.mjs:41`, `:74` · **Goal 4**

`✅ 🟡 ❌ ⚠️ ❓` are hardcoded on both the JSON-mode and text-mode paths, printed
straight to the user's terminal during every liveness check. Everything on the
Python side of the same output routes through `theme.colorize_icon_ansi()`.

**PLAN.md correction for Phase 9:** the `liveness.py:211` raw `❌` recorded in
PLAN.md (`:266-270`) is **already fixed** — commit `348fe628` replaced it, and
`liveness.py` now uses `theme.colorize_icon_ansi()` throughout (`:139-143`,
`:230-235`). The remaining instance in this subsystem is the Node file above.

---

## Questions answered with no finding

**Duplicate detection is genuinely solid.** `jd_manager.job_key_known()` checks
the tracker plus `jds/`, `completed/`, `archived/`, and `expired/`, via three
independent match strategies (job_key; source_url + company_name; normalized
company + title). `scan.py:150` correctly falls back to `source_url` as the key
for board/ATS jobs that carry no `source_job_id`, and `scan_ats.py:164` skips
aggregator-pinned entries that previously produced 31 duplicate-URL groups. A
re-scan does not re-apply to a completed job and does not create duplicate files.
The only cost is performance (finding 7).

**`git_update.py` and `maintenance.py` cannot destroy anything a user can't get
back.** `pull_updates()` is gated on `has_uncommitted_changes()` at both call
sites (`menu.py:675`, `:702`), `git status --porcelain` counts untracked files too,
and git itself refuses to clobber modified or untracked working-tree files. The
`career-ops` clobbering precedent does not apply: nothing here writes into a
profile. `maintenance.py` touches only its own timestamp log and swallows failures
deliberately, which is right for what it is. One latent edge, not worth a finding
today: `check_for_updates()` hardcodes `main..origin/main` and `pull_updates()`
runs `git pull origin main` onto whatever branch is checked out.

**JD files written by scanners are consumable by the pipeline.** Shape matches
what `jd_manager` reads, and the `_liveness` seed follows CLAUDE.md's
underscore-prefixed metadata convention exactly (`scan.py:87-93`), so
`read_jd_text()` strips it before any prompt sees it. Finding 8 is about *when*
the seed is written, not the convention.

**`followup.py` and `situational_roles.py` are clean.** Pure date math and pure
keyword matching, no network, no LLM, defensive against missing/malformed dates
and a missing config file. Nothing to report.

---

## Handoffs

- **Phase 2** (`cli_art.render_scan_report`): the report has no way to show *why* a
  source returned zero. Pairs with finding 1 — fixing the logging alone won't help
  if the renderer has nowhere to put the reason.
- **Phase 4** (`jd_manager.py`): `job_key_known()`'s per-call four-directory walk
  (finding 7) is the underlying cost; the caller-side fix is this phase's, but the
  function is worth a look for other callers.
- **Phase 8**: `JOBRIGHT_COOKIE_STRING` and the live `li_at` cookie are held in
  memory and set onto a `requests.Session` (`scan_linkedin.py:62`); worth
  confirming neither can reach a traceback, log line, or the tracker CSV.
- **Phase 9**: the `liveness.py:211` emoji note in PLAN.md is stale — already
  fixed (see finding 16). Also `board-scanners/` is unowned *and* outside the
  residue check as PLAN.md words it (see top of this doc).
