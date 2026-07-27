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

**Updated 2026-07-22: every item in section 1 reaffirmed (IDEAS.md's own
copy of these decisions had gone stale and was fixed to match); dashboard
went from deferred to promoted to actually built and vendored, all the
same day (see section 5b, new -- now the only section besides 0 and 2
that's fully done).** Nothing else below has moved.

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
- **career-ops-style dashboard/TUI — vendored and built, 2026-07-22**
  (previously deferred; promoted into near-term scope and shipped the
  same day). See section 5b.

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

All three items below were reaffirmed 2026-07-22 (IDEAS.md's own copy of
these decisions had drifted stale and was corrected to match this file --
nothing here changed, only IDEAS.md did).

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
- [x] **Writing-samples curation — decoupled from the merge entirely,
      2026-07-21.** Previously scoped as "curate career-ops's
      `writing-samples/` (291 files)." Morgan's call: this was never
      actually career-ops-dependent -- she has this source material in
      other places too and can pull it back up whenever she wants to dig
      into interview stories/negotiation talking points/etc., independent
      of whether or when the merge itself happens. Nothing here blocks or
      is blocked by anything else in this punchlist. See IDEAS.md's Medium
      tier for the one piece she did greenlight (strengthening
      `evidence-guide.csv` for cover letters) and the Very-Hard/Long-term
      tier for everything else (now tracked as its own standalone,
      non-essential item, not a merge subtask).

### 4. Evidence bank (item #5)

- [x] Phase 1 done 2026-07-07 (voice-anchors.md, trimmed
      detective-findings, evidence-guide.csv for cover letters, style-guide
      distillation).
- [x] **Tier 2 and full multi-type generalization — decoupled from the
      merge, 2026-07-21 (see item 3 above).** No longer tracked here at
      all; not a merge prerequisite or dependency. Whatever happens next
      with `evidence-guide.csv` or new evidence types (interview stories,
      negotiation talking points) happens on its own timeline in
      IDEAS.md, independent of career-ops/job_automater entirely.

### 5. Pipeline porting

- [x] **`scan`:** port **all** of career-ops's ~26 `providers/*.mjs` board
      scrapers (decided 2026-07-16, item 1) as parallel source plugins
      alongside job_automater's already-ported LinkedIn/JobRight scrapers
      (done 2026-07-04) -- shell out to each `.mjs` as a subprocess, parse
      its JSON output, no rewriting. Two real sub-categories, worth keeping
      distinct when sequencing this:
      - [x] **Aggregator/search-driven — done 2026-07-26.** 15 zero-config
        providers (RemoteOK, Remotive, Himalayas, Jobicy, WeWorkRemotely,
        WorkingNomads, FourDayWeek, NoDesk, AuthenticJobs, CrunchBoard,
        Jobspresso, RealWorkFromAnywhere, PowerToFly, TheMuse, HackerNews)
        vendored into `board-scanners/providers/` + a `run_provider.mjs`
        CLI shim; `scripts/scan_boards.py` shells out to each and wires
        into `scan.py`'s `SOURCE_FETCHERS` as a new `"boards"` source
        (`resume scan --source boards`, also in the interactive menu).
        Also ported career-ops's `title_filter`/`location_filter`
        keyword lists from `portals.yml` into `board-scanners/scan_filters.yml`
        (a Python port of `scan.mjs`'s `buildTitleFilter`/
        `buildLocationFilter`, applied before a listing becomes a JD file)
        -- **found and fixed while porting: career-ops's own
        `location_filter` config shape doesn't match what `buildLocationFilter()`
        reads (`location_filter:` is a flat list, `block:` is a separate
        top-level key, not nested `location_filter.block`), so location
        filtering is silently a no-op in career-ops today. Not ported
        broken -- fixed in the vendored copy; worth a fix upstream in
        career-ops too, separately.**
        Board-provider listings carry no description body (career-ops's
        own scan.mjs never fetches one either -- its pipeline is a
        human/Claude reading the URL, not a Gemini batch call), so
        `scan_boards.py` also does a best-effort full-page-text fetch per
        surviving posting (whole-page text via BeautifulSoup, not a
        per-ATS content selector -- good enough to tailor against, not
        guaranteed clean; a real follow-up would need per-site
        extraction or Playwright rendering). Also fixed a real
        pre-existing dedup gap in `scan.py` found while wiring this up:
        `job_key_known()` was only ever called when a source provided a
        numeric `source_job_id`, so any URL-only source (all board
        providers) would silently skip dedup entirely and re-write the
        same posting every scan -- now falls back to `source_url` as the
        dedup key. 15 new tests (`tests/test_scan_boards.py`,
        `tests/test_scan.py`), full suite green (955 tests).
        **Two more real bugs found on Morgan's actual first live run
        (2026-07-26), fixed same day:** the hardcoded placeholder passed
        as `entry.name` ("resume-builder-scan") was leaking into
        `company_name` on any listing whose raw source had no company
        field, since providers like remoteok.mjs fall back to
        `entry.name` themselves (`j.company || entry.name`) -- now uses
        the provider id instead, so a missing company reads as "we don't
        know, here's the source" rather than a fake company name; and
        HTML entities (`&amp;` etc.) weren't decoded on non-RSS
        providers' title/company text (RSS providers get this via
        `_rss.mjs`'s `decodeEntities`, JSON-API providers didn't) --
        fixed with `html.unescape()` at the Python normalization layer,
        one fix point covering every provider regardless of source
        format. Also added a guard dropping listings whose title is
        literally a URL (a handful of feed entries had this). 5 more
        regression tests (20 total in `test_scan_boards.py`). The 30
        already-written JD files with the bug baked in from that first
        run were deleted (with Morgan's confirmation) so a re-scan pulls
        clean versions instead of those URLs being silently skipped
        forever as "already known."
        **Further improvement, same day:** career-ops's providers only
        ever returned title/company/url/location -- 13 of the 15 vendored
        providers' own APIs already carry a full description in the same
        response (career-ops just never mapped it through, since its
        pipeline never needed one). Each vendored `providers/*.mjs` now
        maps that field through, and `scan_boards.py` prefers it over a
        second per-posting-page fetch (faster, and the only way to get a
        body at all for Himalayas, whose posting pages sit behind a
        Cloudflare managed challenge no plain HTTP request can pass --
        that was producing a 403 warning on every run). `_fetch_posting_text()`
        is now only a fallback for FourDayWeek, the one provider with no
        native description. Also switched `_html_to_text()`'s tag-join
        strategy from newline-per-tag (fragmented inline HTML like `<b>`/
        `<a>` across lines) to space-join with `<br>` preserved as real
        newlines. 6 more tests (23 total). Also replaced `scan.py`'s
        plain-print output with a themed Rich report
        (`cli_art.render_scan_report()`): a per-source Fetched/New/Skipped
        table plus a divider-separated list of only the newly-written
        postings -- the old version printed an "already known" line per
        skipped posting, which was tens/hundreds of noise lines on every
        run after the first. Menu label changed from vague "Board scan
        only" to "Public job boards only (RemoteOK, TheMuse, etc.)".
      - [x] **Direct-to-ATS + API-key providers + search sweep — done
        2026-07-26.** Ashby, Greenhouse, Lever, Recruitee, SmartRecruiters,
        Workable, Workday vendored into `board-scanners/providers/`;
        Adzuna/USAJobs added to `scan_boards.BOARD_PROVIDERS` (same
        mechanism as the aggregator batch, just gated on API keys).
        New `scripts/scan_ats.py` (`"ats"` source) resolves each
        `tracked_companies.yml` entry to a provider (explicit `provider:`
        field, else hostname pattern match) and runs the 68
        `search_queries.yml` sweep queries through the vendored
        `websearch.mjs`. **Both config files are career-ops's real
        curated data, ported wholesale from `portals.yml`, not empty
        templates** -- 400 tracked companies (292 resolve to Greenhouse
        alone; 0 of the 400 enabled entries are unresolved) and 68 Brave-
        search ATS sweep queries. Confirmed live end-to-end against real
        companies (Duolingo/Greenhouse: 60 postings, ClassDojo/Ashby: 12,
        ASPCA/Workday: 48). Adzuna/USAJobs need API keys, and the sweep
        queries need `BRAVE_API_KEY`, before they return anything --
        Morgan's to add when ready. **Two more real bugs found and fixed
        while porting:** `workday.mjs` had a stray debug
        `page.screenshot({ path: 'workday-debug.png' })` call writing a
        screenshot file on every single fetch, and `websearch.mjs` called
        `recognizeProvider(r.url)` without ever importing it -- a
        `ReferenceError` on every search result in career-ops today,
        silently breaking its "promote a sweep-discovered company to a
        direct provider" feature. Both fixed in the vendored copies. 10
        new tests (`tests/test_scan_ats.py`).
      - [x] **Liveness verification pass — done 2026-07-26.** career-ops's
        `scan.mjs --verify` (a Playwright liveness pass over only
        new/deduped postings, right after the API scan, before anything
        is presented as a hit) didn't need a new port -- resume-builder
        already had its own liveness checker (`liveness.py`/
        `check-liveness.mjs`, built 2026-07-05 for the standalone
        `resume liveness` command). Refactored `liveness.py` to split out
        `_verify_candidates()` (the actual check-and-move-expired core)
        from `run_liveness_check()`'s pending-queue-plus-recency-split
        concern, and added `verify_jd_paths(paths)` -- no recency skip,
        since scan-fresh postings are always worth a real check rather
        than trusting `_write_jd_file()`'s optimistic "confirmed to exist
        by scan" seed (a feed can list a posting that's already gone --
        seen live the same day: TheMuse serving a 404 for a listed
        posting). `scan.run_scan()` now runs this by default on every
        newly-written path across all sources in one pass (one browser
        launch, not one per source) and drops any confirmed-expired
        posting into `jds/expired/` before the report ever shows it as a
        hit -- `cli_art.render_scan_report()` gained an "Expired" column
        for this. `--no-verify` (CLI only, mirrors career-ops's own flag)
        skips it. Confirmed live end-to-end both ways: 3 new CIA
        postings via `--source boards` all verified active through a
        real headless-browser pass; 11 new JobRight postings via
        `--no-verify` written instantly with no browser launch at all.
        11 new tests (4 in `test_liveness.py`, 3 in `test_scan.py`), full
        suite green (978 tests).
- [x] **`evaluate`:** career-ops's fit-scoring — ported (done 2026-07-04,
      IDEAS.md item 1.3). The scam/ghost-posting legitimacy gap found
      2026-07-21 is also closed: `posting_legitimacy`/
      `posting_legitimacy_notes` are live in `FitEvaluationSchema`,
      `evaluate_fit.md`'s prompt, `jd_manager.py` persistence, and surfaced
      in both the single-JD and batch views. See `IDEAS_ARCHIVE.md`.
- [ ] **`track`:** adopt career-ops's markdown/YAML tracker fully —
      partially done (`applications.md` exists; Score/Report wired to the
      real evaluate stage 2026-07-16). Career-ops's dedup/merge logic
      (`merge-tracker.mjs`/`dedup-tracker.mjs`) not ported — resume-builder
      is still the only writer today, so not yet needed.
- [ ] **`interview-prep`:** deliberately deferred (Morgan's call, not
      essential right now).

### 5b. Dashboard integration — promoted AND done, 2026-07-22 (previously deferred)

career-ops's Go dashboard (`career-ops/dashboard/`, Bubble Tea TUI) went
from hypothetical port to actually-proven-out today:

- **Themed to match resume-builder** (`internal/theme/resumebuilder.go`,
  new -- ports `scripts/theme.py`'s exact hex palette; verified byte-exact
  in real rendered ANSI output) and made the default (`-theme` flag,
  `resume-builder` value).
- **Two real pre-existing bugs found and fixed**, independent of theming:
  a tracker-column-count mismatch (the Go parser was still written against
  career-ops's original 9-column format and was silently misreading
  resume-builder's 10-column one -- Link/Report/Notes were getting
  misattributed, dropping real location/pay/last-contact data derived from
  Notes) and a crash (`strings.Repeat` with an unclamped negative count) on
  narrow terminal widths.
- **Verified end-to-end** against a realistic synthetic `applications.md`
  fixture via a real pty (build clean, `go vet` clean, existing Go test
  suite green, plus a manual pty-driven run confirming no panic and
  correct rendering/coloring).

- [x] **Integration approach decided and built, same day: (a), vendor it.**
      `dashboard/` now lives inside resume-builder itself (copied from
      career-ops, module path + internal imports rewritten to
      `github.com/moreganooooo/resume-builder/dashboard`, footer branding
      updated) -- 18/18 `.go` files, builds/vets/tests clean as its own
      module. `scripts/dashboard.py` shells out to it via `go run .`
      (never `go build` -- no compiled binary should ever land in the
      repo), defaulting `-path` to the active profile's `data/<profile>/`
      via `profile_paths.data_dir()`. New `resume dashboard`
      CLI command + "Career Dashboard" menu entry + `resume doctor` check
      (optional, never a hard failure) for the Go toolchain. **This
      repo's copy is now authoritative** -- career-ops's original is not
      where future dashboard changes should land, and will drift stale
      over time; nothing there was deleted, but it's effectively
      superseded. 9 new Python tests (mocked subprocess/menu wiring) plus
      the existing vendored Go test suite; full Python suite 912 green.

**Section 5b is fully closed** -- decided, built, and verified same day
(2026-07-22).

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

## References

- Full narrative, rationale, and incident history: `IDEAS.md`, "Long-term:
  merge with career-ops and job_automater" section.
- Related tracked items in IDEAS.md's main table: #4, #5, #7, #9.
