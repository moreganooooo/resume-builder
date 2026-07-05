# Liveness Checker — Design

## Problem

IDEAS.md's item #10 originally bundled "Mongo migration + liveness check"
together, assuming both were needed for either to work. Investigation
(2026-07-05) found this isn't true: career-ops's actual liveness checker
(`liveness-core.mjs`, `liveness-browser.mjs`, `check-liveness.mjs`, ~230
lines total) needs **zero MongoDB** -- it's pure Playwright (already a
resume-builder dependency, via `generate-pdf.mjs`) plus deterministic
HTTP-status/regex/DOM classification, no LLM calls either. It just takes a
list of URLs and classifies each as `active`, `likely_active`, `expired`,
or `uncertain`.

Right now, `resume run`/`resume tailor` will happily spend real Gemini
calls tailoring a resume for a job posting that's already closed. Every
scanned JD already carries a `source_url` field (from both the JobRight
and LinkedIn scanners), so the pieces needed to check are already sitting
in `jds/`.

## Goals

1. `resume liveness` checks every pending JD's `source_url` (JDs without
   one are skipped, not flagged) and classifies each.
2. `expired` JDs move automatically to a new `jds/expired/` folder (same
   move pattern as `jds/completed/`), so `resume run` never wastes effort
   on them.
3. `uncertain` (and `likely_active`) results stay in the pending queue --
   only a confident `expired` signal triggers a move. Flagged in the
   printed summary for Morgan to eyeball herself.
4. Standalone, explicit command -- not auto-wired into `scan`/`run`, since
   a browser-driven check per JD is slow.
5. Port career-ops's classification logic (`liveness-core.mjs`,
   `liveness-browser.mjs`) verbatim -- proven, working, zero reason to
   touch it.

## Non-Goals

- No MongoDB, no persistence-layer changes of any kind.
- No checking of already-completed/tracked JDs this pass -- pending JDs
  only. Re-checking applied-to postings for the tracker is a separate,
  larger piece (own write-path into `applications.md`) left for later.
- No auto-wiring into `scan`/`run`/`tailor` -- always an explicit,
  separately-triggered command.
- No new JS test framework -- this project has none today (`package.json`'s
  `test` script is a stub), and `generate-pdf.mjs` already sets the
  precedent of verifying Node scripts live rather than with dedicated
  unit tests.

## Architecture

```
resume liveness
  → jd_manager.get_pending_jds() -- existing pending-JD discovery, reused as-is
  → gather {job_key, source_file, url} for every pending JD that has a
    source_url (JDs without one are skipped, counted separately, not
    flagged as anything)
  → write the candidates list to output/liveness_input_tmp.json (output/ is
    already gitignored and used for transient build artifacts), one
    subprocess call:
    node scripts/check-liveness.mjs --json-file output/liveness_input_tmp.json
    (batches all URLs into ONE Playwright browser session -- matches the
    "never run Playwright in parallel" rule already inherited from
    career-ops)
  → Node classifies each URL (liveness-core.mjs's classifyLiveness(),
    ported verbatim) and writes a JSON array of results to stdout;
    human-readable progress goes to stderr so stdout stays clean JSON
  → Python parses the JSON array:
      result == "expired"  -> move that JD file to jds/expired/
      anything else         -> leave in place
  → print summary: N active, N expired (moved), N uncertain/likely_active
    (flagged, not moved), N skipped (no source_url)
  → temp input file always deleted (try/finally), success or failure
```

## Components

- **`scripts/liveness-core.mjs`** (new, ported verbatim from
  `/Users/morganescott/career-ops/liveness-core.mjs`) -- pure
  pattern-matching classifier, `classifyLiveness({status, finalUrl,
  bodyText, applyControls}) -> {result, code, reason}`. No changes.
- **`scripts/liveness-browser.mjs`** (new, ported verbatim from
  career-ops) -- Playwright page-fetch wrapper,
  `checkUrlLiveness(page, url) -> {result, reason}`. No changes.
- **`scripts/check-liveness.mjs`** (new, adapted from career-ops's
  version) -- adds a `--json-file <path>` mode: reads a JSON array of
  `{job_key, source_file, url}` objects, checks each sequentially in one
  shared browser session (reusing career-ops's existing sequential-only
  rule), writes a JSON array of `{job_key, source_file, url, result,
  code, reason}` to stdout. Career-ops's original CLI usage (bare URL
  args, human-readable stdout) stays intact as the default mode --
  `--json-file` is additive, not a replacement.
- **`scripts/liveness.py`** (new, mirrors `scan.py`'s orchestration-module
  pattern) -- `run_liveness_check() -> dict`: gathers pending JDs with
  URLs via `jd_manager`, writes the temp input file, shells out to
  `check-liveness.mjs --json-file` (same `subprocess.run` pattern already
  used for `generate-pdf.mjs`), parses the JSON result, moves expired
  JDs, returns summary counts. Cleans up the temp file in `finally`.
- **`jd_manager.py`** (modify) -- add `EXPIRED_DIR = os.path.join(JDS_DIR,
  "expired")`, mirroring the existing `COMPLETED_DIR` constant.
- **`cli.py`** / **`resume-cli.sh`** (modify) -- new `resume liveness`
  command, same wiring pattern as `evaluate`/`scan`.

## Data Flow

```
resume liveness
  → run_liveness_check()
      pending = jd_manager.get_pending_jds()
      candidates = [(job_key, source_file, url) for each pending JD with
                    a real source_url field]
      if no candidates: print "Nothing to check" summary, return early
      write candidates to a temp JSON file
      subprocess.run(["node", "scripts/check-liveness.mjs",
                      "--json-file", tmp_path], capture_output=True)
      non-zero exit -> print stderr, move nothing, return failure summary
      parse stdout as JSON array; malformed -> print error, move nothing
      for each result:
        "expired" -> move source_file's JD from jds/ to jds/expired/
        else       -> leave in place
      delete temp file (always, via finally)
      print summary counts
      return summary dict
```

## Error Handling

- No pending JDs, or none with a `source_url` -- print a clear "nothing to
  check" message, return early, no subprocess call made.
- Node subprocess non-zero exit (e.g. Chromium missing/crashed) -- print
  stderr, move no files, return a failure summary.
- Malformed/unparseable JSON on stdout -- treat as total failure for the
  run, move no files (never partially trust a broken result set).
- A single URL's navigation error (timeout, DNS failure, etc.) is already
  handled inside `liveness-browser.mjs` (returns `uncertain` with a
  reason) -- doesn't abort the batch, doesn't need Python-side handling.
- Temp input file is always removed in `finally`, regardless of outcome.

## Testing

- `liveness-core.mjs`/`liveness-browser.mjs`: no new tests (verbatim port
  of already-proven code, zero changes).
- `check-liveness.mjs`'s new `--json-file` mode: live-verified with a
  couple of real URLs (one genuinely active posting, one deliberately
  broken/404 URL) confirming correctly-shaped, parseable JSON output --
  consistent with how `generate-pdf.mjs` is already verified in this
  project (no dedicated JS tests).
- `scripts/liveness.py`: real unit tests, `subprocess.run` mocked to
  return canned JSON (same convention as `company_research.py`'s mocked
  `requests.get`) -- confirms expired JDs get moved to `jds/expired/`,
  active/uncertain ones don't, JDs without a `source_url` are skipped and
  counted separately, summary counts are correct across a mixed batch.
- Live verification: run `resume liveness` against the real pending JDs
  already sitting in `jds/` (209+ from earlier scans) and spot-check a
  handful of results by eye.
