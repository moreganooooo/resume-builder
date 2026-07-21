# Three-Repo Merge Punchlist — career-ops + job_automater → resume-builder

## Status

Direction brainstormed and agreed 2026-07-04 (see `IDEAS.md`'s "Long-term:
merge with career-ops and job_automater" section for the full narrative,
rationale, and incident history). This file turns that narrative into an
ordered, actionable list — it doesn't re-argue anything already decided;
go to IDEAS.md for the "why" behind any item here.

**Updated 2026-07-20: section 2 (prerequisite engineering) is done** —
both items closed 2026-07-17, one day after this file was written. Every
other section below (3 through 7) is still exactly as unstarted as when
this was first drafted. Confirmed directly against the repo, not just the
narrative below: `scripts/profile_paths.py` exists and is live, no board
scraper for any of career-ops's ~26 providers exists in `scripts/`, and no
`.plist`/launchd artifact exists anywhere in the repo.

Nothing below has a target date. Pull an item into its own design spec +
implementation plan (the `docs/superpowers/specs/`+`plans/` pattern used
everywhere else in this repo) when it's actually time to build it.

## Already decided — don't re-litigate

- **Surviving codebase: resume-builder (Python).** career-ops's `.mjs`
  pipeline logic gets ported; its markdown/YAML tracker *format* carries
  over as data, not as a second live system.
- **Evidence bank ("the brain") is the highest-priority piece** — an
  extension of what already exists (`bullet_feedback.py`,
  `triage_needs_review.py`, the verified-bullet CSV schema), not a rebuild.
- **Cut entirely:** job_automater's ATS auto-apply/auto-submit engine
  (`automator_main.py`/`ats_fillers/`) and all three LaTeX/reportlab
  rendering backends (`document_generator/`). Playwright/HTML stays the one
  renderer; a human always has the final call before any submit, full stop.
- **Deferred, not decided against:** a career-ops-style dashboard/TUI.

## Punchlist, roughly in dependency order

### 0. Loose ends to close, independent of any merge work starting

- [x] **Security — the hardcoded LinkedIn cookie is gone (done 2026-07-16).**
      job_automater's local-only `scrapers/recommended_scraper.py` had a
      `li_at` session cookie hardcoded in plaintext. Confirmed **not** part
      of the real upstream project — an ad-hoc local script. Morgan judged
      the cookie itself already stale (LinkedIn's anti-automation detection
      rotates `li_at` the moment it senses automation, sometimes on a new
      session, sometimes with no obvious trigger — so a hardcoded copy from
      an earlier session was almost certainly dead already) and opted to
      skip a separate rotation step. The file was deleted and its removal
      committed in job_automater (`a8c55e3`, "Remove stray
      scrapers/recommended_scraper.py"). Note: since the file was tracked
      in git, the plaintext value still exists in job_automater's git
      history prior to this commit — moot given the cookie's presumed-dead
      status, but worth knowing if that history is ever shared externally.
      **Not the same thing as** resume-builder's own `scan_linkedin.py`
      (built 2026-07-04, already live-tested and working) — that one reads
      the live cookie correctly via `browser_cookie3` straight from an
      already-logged-in Chrome session, never touching disk. Nothing to fix
      there; it carries forward as-is, and **no hardcoded-cookie mechanism
      of any kind gets pulled into resume-builder** — there was never
      anything to port here, not even as a fallback.

### 1. Decisions needed before their dependent work can start

- [x] **Persistence layer — decided 2026-07-16: stay with CSV/markdown,
      adopt nothing new yet.** Today there's a single writer
      (resume-builder itself), so the concurrency problem Mongo/SQLite
      would solve doesn't exist yet. Mongo also means a permanently-running
      Docker daemon for a single-user personal tool -- real ongoing
      operational cost for zero current benefit, and it breaks the
      "everything's readable in a text editor" pattern used everywhere
      else in this project. **Trigger to revisit:** the day the scheduler
      (item 6) actually fires multiple launchd jobs that could write to the
      tracker concurrently -- at that point, adopt SQLite specifically (real
      transactional safety via WAL mode, no daemon required, stdlib-only),
      not Mongo. Not before.
- [x] **Scheduler job layout — decided 2026-07-16: one dispatcher job, not
      one per saved search.** The scheduler design already agreed
      (item 6) is "every run ends with **one** macOS notification and
      **one** email digest" -- that only makes sense with a single job
      gathering all searches before notifying once; N separate per-search
      jobs would mean N separate notifications, fighting the "one scored
      list" design. Bonus: one plist to maintain instead of N. If a search
      ever needs its own cadence, add that inside the dispatcher (a
      per-search "last run" timestamp, checked each tick) rather than
      spinning up separate OS-level jobs.
- [x] **Which of career-ops's ~26 `providers/*.mjs` board scrapers to
      port — decided 2026-07-16: port all of them.** Investigated real
      usage first via career-ops's `data/scan-history.tsv` (2,324 real
      historical rows, `portal` column): Greenhouse 73%, Ashby 10%, Workday
      5%, everything else long-tail. But digging into *why* revealed the
      code-porting cost is uniform across all 26 (each is already a
      working, self-contained `.mjs` script; resume-builder's approach is
      to shell out to them as subprocesses and parse JSON, not rewrite) --
      so there's no real savings in leaving any of them un-ported. The
      volume skew is a **curation artifact, not a scraper-quality
      difference**: `portals.yml`'s `tracked_companies` list has 18
      hand-curated Greenhouse company board URLs and 5 Ashby ones (e.g.
      Duolingo, Khan Academy, Coursera) and *zero* for any other
      direct-to-ATS provider — Workday's real hits come from a
      no-curation-needed `site:myworkdayjobs.com` search query instead.
      **Decision: port all providers now; curate/adjust company lists
      afterward as a separate, ongoing content task** (see item 5 below),
      not a blocker to porting itself.

### 2. Prerequisite engineering (blocks multi-user AND the merge's shared-engine goal) — DONE 2026-07-20

- [x] **Engine/profile split** (item #4) — done 2026-07-17, across four
      same-day passes (`profile_paths.py`, per-profile `fixed_content.py`,
      every hardcoded Morgan constant in `orchestrator.py`/
      `rewrite_bullets.py`, the per-profile tag taxonomy). Full writeup:
      `IDEAS_ARCHIVE.md`'s "Engine/profile split" and "Multi-user support"
      entries.
- [x] **Per-user secrets** (item #7) — done 2026-07-17, same week. Every
      script now loads `profiles/<name>/.env`; Morgan's real `.env`
      migrated. See `IDEAS_ARCHIVE.md`.

### 3. Data reconciliation

- [x] **CSV authority — decided 2026-07-20: resume-builder's copies win,
      no merge needed.** Checked row counts on all 5 shared-name files
      directly: `evidence-guide.csv` (78/78), `detective-findings.csv`
      (174/174), and `verified-claims.csv` (132/132) are identical between
      the two repos -- nothing to reconcile. `bullet-bank-clean.csv`
      (1,432 rows here vs. 1,493 in career-ops) and
      `summaries-and-skills-clean.csv` (1,163 vs. 1,310) genuinely
      diverged after the original one-time copy, but Morgan's call:
      resume-builder's versions are the better-curated ones at this point
      (real pipeline logic -- clustering, auditing, hidden-gem scoring --
      ran on top of these copies since the split, career-ops's never got
      that treatment). Keep resume-builder's copies as authoritative for
      all 5 files; career-ops's originals aren't pulled forward into
      anything.
- [ ] Curate career-ops's `writing-samples/` (291 files, mostly untapped)
      for evidence-bank Tier 2 — `MorganWritingStyleGuide.txt` already
      ported (Phase 1, 2026-07-07); `BestCopySamples`/`Master Cover
      Letters`/the raw "Treering Sequences" archive still need their own
      curation pass (heavy duplication, some non-Morgan authorship to
      filter out first).

### 4. Evidence bank (item #5) — the priority piece

- [ ] Phase 1 done 2026-07-07 (voice-anchors.md, trimmed
      detective-findings, evidence-guide.csv for cover letters, style-guide
      distillation).
- [ ] Tier 2 (item 3's writing-samples curation) — unscheduled.
- [ ] Full multi-type generalization beyond resume bullets (interview
      stories, cover-letter proof points, negotiation talking points) —
      not started.

### 5. Pipeline porting

- [ ] **`scan`:** port **all** of career-ops's ~26 `providers/*.mjs` board
      scrapers (decided 2026-07-16, item 1) as parallel source plugins
      alongside job_automater's already-ported LinkedIn/JobRight scrapers
      (done 2026-07-04) -- shell out to each `.mjs` as a subprocess, parse
      its JSON output, no rewriting. Two real sub-categories, worth keeping
      distinct when sequencing this:
      - **Aggregator/search-driven** (RemoteOK, Adzuna, USAJobs, Himalayas,
        WeWorkRemotely, Jobicy, Remotive, etc.) -- one search query/API
        config each, no per-company list, produce results immediately once
        wired up. Straightforward to knock out as a batch.
      - **Direct-to-ATS** (Greenhouse, Ashby, Lever, SmartRecruiters,
        Recruitee, Workable) -- only surface results for companies present
        in a `tracked_companies`-style curated list (18 Greenhouse, 5 Ashby
        entries exist today in career-ops's `portals.yml`; zero for the
        other four). Porting the code is just as cheap, but **each will
        return nothing until someone spends real time hand-picking
        companies for it** -- that curation pass is a separate, ongoing
        follow-up task, not part of "porting," and can happen incrementally
        after the fact (start with what's already curated, expand as
        Morgan identifies more companies worth tracking on each ATS).
- [ ] **`evaluate`:** career-ops's fit-scoring — already ported (done
      2026-07-04, IDEAS.md item 1.3). Nothing further needed for the merge
      itself.
- [ ] **`track`:** adopt career-ops's markdown/YAML tracker fully —
      partially done (`applications.md` exists; Score/Report wired to the
      real evaluate stage 2026-07-16). Career-ops's dedup/merge logic
      (`merge-tracker.mjs`/`dedup-tracker.mjs`) not ported — resume-builder
      is still the only writer today, so not yet needed.
- [ ] **`interview-prep`:** deliberately deferred (Morgan's call, not
      essential right now).

### 6. Scheduler + notifications (item #9)

- [ ] Unblocked since 2026-07-04 (scan + evaluate both exist); item 1's
      persistence-layer (stay CSV/markdown) and launchd-layout (single
      dispatcher job) decisions are now locked in too, so nothing further
      blocks starting this. Not started. Shape already agreed: saved
      searches on a schedule, matches >=90 land on a review list, matches
      >=95 additionally auto-trigger tailor+render, every run ends with a
      macOS notification + email digest. Never applies or submits anything.

### 7. Sunset

- [ ] Once resume-builder's pipeline covers what Morgan actually uses from
      both siblings, decide when/whether to stop maintaining career-ops and
      job_automater as separate live repos. Not urgent; no target date.

## Out of scope / decided against

- ATS auto-apply/auto-submit — cut, human-in-the-loop only, full stop.
- LaTeX/reportlab rendering — cut, Playwright/HTML is the one renderer.
- career-ops-style dashboard/TUI — deferred, not decided against.

## References

- Full narrative, rationale, and incident history: `IDEAS.md`, "Long-term:
  merge with career-ops and job_automater" section.
- Related tracked items in IDEAS.md's main table: #4, #5, #7, #9.
