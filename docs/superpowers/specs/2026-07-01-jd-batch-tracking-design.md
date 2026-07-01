# JD Batch Tracking & Mid-Pipeline Resume — Design

## Problem

Today, `scripts/orchestrator.py` requires the JD file path on the command line
(`python scripts/orchestrator.py jds/some_jd.txt`), and there is no record of
which JDs have already had a resume generated. Every run is manual and
single-file.

Separately, the real JD source (a companion tool at
`/Users/morganescott/job_automater`) exports jobs as either:
- a single job posting (JSON object or plain text), or
- a batch export: a JSON array of ~20 job objects (see
  `jobright_jobs_backup.json`), each already carrying `status`, `job_title`,
  `company_name`, and a unique `source_job_id`.

## Goals

1. Running the orchestrator with no arguments processes every JD in `jds/`
   that hasn't already been completed, and skips ones that have.
2. Batch export files (JSON arrays) are auto-split into one file per job so
   the rest of the system can treat everything as "one file = one job."
3. Completed JDs move to their own folder; a CSV log tracks history.
4. Failures don't halt the batch and don't lose progress — the next run
   retries only what didn't finish, resuming mid-pipeline rather than from
   scratch.
5. Existing single-file invocation (`orchestrator.py jds/foo.json`) keeps
   working for ad hoc/manual runs.

## Non-Goals

- Changing how a single JD is scored, mined, or rendered (steps 1-7 of
  `build_tailored_resume` stay the same).
- Building any UI — this is CLI-only.
- Deduplicating jobs across different job boards (source_job_id uniqueness
  is trusted as-is).

## Architecture

**New module: `scripts/jd_manager.py`**
Handles JD intake, splitting, and completion tracking. Kept separate from
`orchestrator.py` (which owns resume-building) so each file has one clear
job.

**Modified: `scripts/orchestrator.py`**
- `main()`: no positional arg → batch mode (new default). A path arg still
  runs single-file mode, unchanged in spirit but now also checkpointed and
  logged like a batch run of size 1.
- `build_tailored_resume()`: gains checkpoint load/save at each step
  boundary (see "Mid-Pipeline Resume" below).

## Components (`jd_manager.py`)

- **`split_batch_jds(path) -> list[Path]`**
  Reads `path`. If its content parses as a JSON array, writes one file per
  array element into `jds/`, named `YYYY-MM-DD_Company_JobTitle.json`
  (date = today; company/title pulled from `company_name`/`job_title`,
  sanitized for filesystem safety). Deletes the original array file once all
  elements are written. Returns the list of new file paths. If the file is
  not a JSON array (single object or plain text), returns `[path]` unchanged.

- **`compute_job_key(jd_path) -> str`**
  Returns the tracking identity for a JD file. If the file is JSON and has a
  `source_job_id` field, returns that. Otherwise returns a SHA-256 hex digest
  of the file's raw bytes (covers plain-text drop-ins and any JSON without an
  id).

- **`JDTracker`**
  Thin CSV wrapper over `jds/jd_tracker_log.csv` (name matches the existing
  `*_log.csv` gitignore rule — JD payloads can contain names/LinkedIn URLs of
  social connections, so this file should not be committed).
  Columns: `job_key, job_title, company_name, source_file, status,
  date_processed, output_json, output_pdf, error_message`.
  - `is_completed(job_key) -> bool`
  - `mark_completed(job_key, **fields)`
  - `mark_failed(job_key, **fields)`

- **`get_pending_jds() -> list[Path]`**
  Scans `jds/` at the root (ignoring `jds/completed/`), runs any array files
  through `split_batch_jds` first, then returns the files whose
  `compute_job_key` isn't already marked completed in the tracker.

## Data Flow

```
run with no args
  → get_pending_jds() scans jds/, splits any batch arrays first
  → for each pending file:
      job_key = compute_job_key(file)
      result = build_tailored_resume(file, job_key=job_key, ...)
      success → move file to jds/completed/, tracker.mark_completed(...)
      failure → leave file in jds/, tracker.mark_failed(...) (checkpoint
                 file, if any, is left in place for the next run)
  → print summary: N completed, N failed, N skipped (already done)

run with a specific file path (unchanged use case)
  → same per-JD handling as above, scoped to that one file
```

## Mid-Pipeline Resume

Per-job checkpoint file at `output/checkpoints/<job_key>.json` (covered by
the existing `output/` gitignore rule). Contents:

```json
{
  "job_key": "...",
  "jd_keywords": {...} ,
  "bullet_tuples": [[bullet, company, tags], ...],
  "refined_bullets": ["...", "..."],
  "resume_data": {...},
  "critique_data": {...}
}
```

Each field is populated as its corresponding step finishes; fields not yet
computed stay absent/null.

`build_tailored_resume` behavior change:
1. At the start, load the checkpoint for `job_key` if one exists (empty dict
   if not).
2. Before each of the 5 major steps (extract keywords → mine bullets →
   audit/refine bullets → build resume → critique), check whether the
   checkpoint already has that step's output. If so, reuse it and skip
   straight to the next step. If not, run the step and save its output to
   the checkpoint immediately after.
3. Inside the audit/refine loop specifically (`audit_and_refine_bullets`,
   the step that makes one API call per bullet and is the slowest/most
   interruption-prone), save the checkpoint's `refined_bullets` list after
   *every individual bullet* completes, not just at the end of the loop. On
   resume, the loop starts from `len(refined_bullets)` instead of 0.
4. On full success (JSON saved, HTML rendered, PDF generated), delete the
   checkpoint file — there's nothing left to resume.
5. On any exception or external interruption, the checkpoint file is simply
   left as whatever was last saved. No special handling needed — the next
   run for that `job_key` picks it up automatically via step 1 above.

## Folder Layout

```
jds/
  <pending JD files, JSON or plain text>
  completed/
    <JD files that finished successfully>
  jd_tracker_log.csv          (gitignored via existing *_log.csv rule)
  dummy_jd.txt                (kept for now per user; manually deleted later)

output/
  checkpoints/
    <job_key>.json            (deleted on success; gitignored via output/)
```

## Error Handling

- A failure at any pipeline step marks that JD `failed` in the CSV and
  leaves both the JD file and its checkpoint in place. The batch loop moves
  on to the next JD rather than aborting.
- A crash, Ctrl+C, or machine sleep mid-batch behaves the same as an
  explicit failure for the JD that was in-flight: nothing is marked
  completed for it, so the next run resumes it from its checkpoint. Every
  JD that finished before the interruption is already marked completed and
  is not reprocessed.

## Testing

- Unit tests (fixtures in a temp dir, no real Gemini calls):
  - `compute_job_key`: JSON-with-`source_job_id` path vs. plain-text hash
    path; same content → same key; different content → different key.
  - `split_batch_jds`: array of N job objects → N files written with the
    expected naming, original file deleted; non-array input passed through
    unchanged.
  - Checkpoint resume: simulate a checkpoint with `jd_keywords` and
    `bullet_tuples` already present but no `refined_bullets`, confirm the
    audit loop starts fresh but keyword extraction and mining are skipped.
- Manual end-to-end check: drop a small fake 2-job array into `jds/`, run
  no-arg mode, confirm split → both processed → moved to `completed/` → CSV
  rows written. Run again with nothing new and confirm "0 pending." Kill the
  process mid-audit-loop on a 3rd fake job, rerun, confirm it resumes from
  the bullet it stopped on rather than restarting keyword extraction.
