# Phase 11 — Unexplained artifacts & path residue

Run 2026-08-05, Opus 5. Cross-cutting diagnosis phase; owns no files. Read
narrowly along the three traces `PLAN.md:649-702` names, and files findings
only inside them. All three were observed by a phase that could not diagnose
them and handed to a phase that had already run — they are the orphans of
`phase-9-backlog.md`'s **B25**/H6 ledger.

**Result: three traces, three root causes, all three confirmed against live
artifacts on the `morgan` profile — no speculation carried into the backlog.**

---

## Trace 1 — three employers are missing from the rendered resume

**H9 / `P2F7` / B25. Root cause: nothing in the pipeline requires the model to
emit one `EXPERIENCE` entry per role. The roster is 100% LLM-discretionary and
its loss is silent at every downstream layer.**

### What was ruled out

- **Not the trim loop.** The loop (`orchestrator.py:2915-2980`) has exactly two
  levers: drop non-essential client rosters (`normalize_resume.normalize(...,
  include_optional_clients=False)`) and apply `trim_instructions[n]`, whose
  bullet-removal step works roles *toward* their `min_bullets` floor. **No path
  in it removes a company.** It also never fired here — page count was already 2.
- **Not bullet-bank starvation.** `mine_bullet_bank()`'s per-company floor
  (`orchestrator.py:2093-2112`) matched cleanly: the company names in
  `profile.yml` `roles:` are byte-identical to the `Role / Company` values in
  `bullet-bank-keepers-audited.csv` (`Element 8 / Strategy LLC` 84 rows, `VML`
  49, `Callahan Creek` 43). The live checkpoint
  `output/morgan/checkpoints/6a06fec9152f493123c4bc6c.json` proves it —
  its 30 `bullet_tuples` are
  `{Treering 13, Inside Sales 4, Element 8 3, VML 3, Callahan Creek 3, Mercor 2,
  Kansas Colloquies 2}`. **All three missing employers were fully supplied to
  the builder with their guaranteed minimum of material.**
- **Not the normalizer.** `normalize_resume.py:59-94` maps over `EXPERIENCE`
  1:1 — it enriches entries (`COMPANY_META`, rename notes, fixed titles,
  clients) and never appends or filters one.
- **Not `fixed_content.py`.** All three are present and fully configured there
  (`:38-40`, `:62-64`, `:76-97`, `:130-132`) — size/revenue, location, industry
  tags, client rosters, fixed titles.

### What is actually true

`profile.yml` declares **six** roles — `Mercor`, `Treering Yearbooks`, `Inside
Sales Team` (page 1) and `Element 8 / Strategy LLC`, `VML`, `Callahan Creek`
(page 2, `min_bullets: 3` each). The shipped artifact
`output/morgan/json/MorganEscott_ContentStrategist_AbnormalAI_Resume.json`
contains **three**: `Mercor`, `Treering Yearbooks`, `Inside Sales Team (Now
Alleyoop)`. The entire page-2 work-history block is absent — which is also the
direct cause of `P2F7`'s 7.33 inches of dead space on page 2.

The roster reaches the model as prose only: `build_role_rules_block()`
(`orchestrator.py:1129-1179`) renders a Per-Role Bullet Count Targets table and
a "Section Order (Page 1 → Page 2)" line. `tailor_resume.md:159-168` says
"do not over-fill or under-fill any role" and "Never drop any role below its
Min" — both of which govern *bullet counts within a role that exists*, and
neither of which says **every company in that table must appear**. The nearest
thing to that instruction is one clause in a schema field description
(`orchestrator.py:967-970`, `"One entry per company"`), and
`GeminiClient.sanitize_schema()` **strips every `description` before the schema
reaches Gemini** — the same mechanism documented at
`orchestrator.py:1198-1210` as the reason education keys had to become real
enums. So that clause is not merely weak; it is *not sent*.

Then nothing catches the loss. `validate_resume.validate()` (`:284-296`) runs
nine checks; `_check_experience_completeness()` (`:275-281`) only validates
`title`/`company`/`period` and non-empty bullets **on entries that are
present**. A missing company is indistinguishable from a roster that was never
supposed to include it. Zero violations, zero warnings, PDF renders, JD moves
on.

**This is a data-loss defect, not a layout defect** — Phase 2 was right to
decline the CSS fix. → **B60**.

---

## Trace 2 — `get_completed_jds()` returns 0 on a profile with completed JDs

**H10 / B25. Root cause: the premise is wrong. `jds/morgan/completed/` is
genuinely empty, and both the counter and the move are correct code. The real
defect is that the counter measures *directory occupancy* rather than any
record of work done — so it cannot see the resumes that exist and it silently
decrements when a JD is archived.**

### The measurements

- `jds/morgan/` — **1,147** pending JD files. `jds/morgan/completed/` — **0**
  files. The banner's "0 Resumes Customized All-Time" is an *accurate* read of
  the directory.
- `jd_tracker_log.csv` **does not exist** on this profile. Nothing has ever been
  logged through `tracker.mark_completed()`.
- Yet `output/morgan/pdf/` and `output/morgan/json/` each hold a real
  `MorganEscott_ContentStrategist_AbnormalAI_*` resume **and** cover letter
  (built 2026-08-05 14:23).

Those artifacts came from **`resume sample`**, not `run_pipeline` —
`fixtures/sample_jd.txt` is the Abnormal AI Content Strategist JD
(`source_job_id: 6a06fec9152f493123c4bc6c`, matching the checkpoint filename),
and CLAUDE.md documents that `build_sample.py` calls
`ResumeEngine.build_tailored_resume()` directly and **deliberately skips the
move-to-`completed/` and tracker-logging side effects**. That is correct
behavior for a re-runnable fixture. So: every resume this profile has ever
produced was produced by the one path designed not to count.

`run_pipeline`'s move (`orchestrator.py:3070-3072`) and
`get_completed_jds()` (`jd_manager.py:629-645`) are both correct as written.

### The defect that remains

`_stats_line_text()` (`cli_art.py:135-141`) derives "Resumes Customized
All-Time" from `len(get_completed_jds())` — a **mutable directory count**, not a
tally:

- `archive_jd()` (`jd_manager.py:648-660`) moves a file **out of
  `COMPLETED_DIR`** into `archived/`. Archiving one old application silently
  decrements an "All-Time" number.
- Deleting or re-importing a completed JD does the same.
- Two real resumes and a real cover letter sit on disk while the banner says
  zero, and there is no path by which that number can ever recover them.

`jd_tracker_log.csv` — append-only, one row per `mark_completed()` — is the
honest source and already exists for exactly this purpose.

### Relationship to B17 — **two bugs, not one**

`P4F2`/**B17** is the *opposite* failure in the same block: `orchestrator.py:3068`
gates on `if result:` and never checks `output_paths.get("pdf")`, so a JD moves
to `completed/` on a build that produced no PDF. Trace 2 is that the counter
reads a directory instead of a ledger. Fixing B17 does not make the banner
correct, and fixing the banner does not stop a PDF-less JD from being filed as
done. → **B61** (keep B17 as-is).

---

## Trace 3 — pre-profile paths are still live, and test runs leave residue

**H6 (never picked up). Two causes, both confirmed, both landing outside
`profile_paths.sync_roots()` and therefore invisible to Syncthing.**

### (a) Live pre-profile writers — Phase 6's `ingest.py` finding is *not* the only one

Three modules resolve an `output/` path without going through `profile_paths`:

| Site | Writes | Status |
| --- | --- | --- |
| `ingest.py:13-14,76,89` | `output/json/parsed_resume.json`, `output/txt/` | dead code — the one Phase 6 found, already recorded in **B44** (`P6 #11`) |
| `detect_blank_scores.py:34,206-207` | `output/json/unscored_bullets.json` | **live** — `mkdir(parents=True)` on a shared, non-profile path |
| `liveness.py:22,92-93` | `output/liveness_input_tmp.json` | **live** — root-level temp file, `makedirs` on `output/` itself; removed in a `finally`, so it leaves no trace *unless* the process is killed mid-check |

So the answer to the phase's question is: `ingest.py` was the *visible*
offender, not the only one. `detect_blank_scores.py` is the one that actually
still writes real profile-derived data (bullet-bank rows) to a shared path
where a second profile would overwrite it.

The four empty top-level directories (`output/checkpoints/`, `output/html/`,
`output/json/`, `output/pdf/`) are all dated **Jul 18 17:42**, four days before
the profile migration's other artifacts — they are pre-migration residue, not
evidence of a current writer. `output/txt/` does not exist at all, confirming
`ingest.py` has not run since. Only `output/json/` has a live writer that would
recreate it.

### (b) Test residue — the teardown covers one of four directories

`tests/test_menu_bootstrap.py:53-57` creates the profile
`test_guest_trigger_profile_xyz` for real (deliberately, and correctly — its
own comment explains why mocking `os.makedirs` would be dishonest). But
`create_new_profile()` seeds **all four** `sync_roots()` directories, each with
a `.stignore`, while `tearDown()` removes only:

```python
shutil.rmtree(os.path.join(profile_paths.PROFILES_DIR, self.test_profile_name), ...)
```

Left behind, since 2026-07-22: `jds/test_guest_trigger_profile_xyz/.stignore`,
`output/test_guest_trigger_profile_xyz/.stignore`,
`data/test_guest_trigger_profile_xyz/.stignore` — three orphan directories with
no matching `profiles/` entry, which is exactly the state
`bootstrap_bullet_bank.create_new_profile()` is designed never to leave.

This is the same class of bug CLAUDE.md legislates against: the teardown
hand-rolled one path instead of iterating `profile_paths.sync_roots(name)`. It
also means the test does not currently verify that the other three roots were
created — a genuine coverage gap sitting right next to the leak. → **B62**.

---

## Handoffs

- **None outward.** All three traces resolved to root cause inside their own
  boundaries; no finding was filed outside them.
- **B25 can be closed** once B60/B61/B62 are ranked — its three orphans now have
  owners.
- Note for the fix pass: **B60 and B2 touch the same artifact from opposite
  ends.** B2 makes the banner fast; B61 makes it true. Do them together.
