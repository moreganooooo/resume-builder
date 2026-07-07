# Polish Chat — Design

## Problem

The pipeline ends the moment a resume or cover letter PDF is generated.
Every finished document meets its JD-tailoring requirements, but Morgan
sometimes wants a small personal-preference change afterward (reword a
line, drop a bullet, tighten a paragraph) that has nothing to do with
JD-fit. Today the only path is hand-editing the rendered HTML file
directly, with no clear way to regenerate the PDF from that edit
afterward, and no path back through the JSON source of truth at all.

## Goals

1. `resume polish` opens an interactive terminal chat against an
   already-generated resume or cover letter's JSON.
2. Each turn is a free-form instruction ("make the tagline punchier",
   "drop the second Treering bullet") answered by a single Gemini call
   that returns the complete updated document, not a fragment.
3. Every turn's result is shown as a diff and requires explicit
   accept/reject before anything touches disk.
4. Accepting a turn saves the JSON, re-renders HTML, and regenerates the
   PDF immediately — polish output is always a complete, fresh,
   ready-to-send document, never a partial edit the user has to finish
   wiring up by hand.
5. Works on both resumes and cover letters through the same flow.

## Non-Goals

- No real multi-turn conversation/chat-history API usage. The on-disk
  JSON already encodes every previously-accepted edit, so each turn only
  ever needs (current JSON, new instruction) → new JSON. See Architecture.
- No re-tailoring against the JD, no company research, no knowledge-base
  context loading — polish edits content that already exists; it doesn't
  regenerate it from scratch. Keeps each turn fast and cheap.
- No batch/`--pick` mode — polish is a one-document-at-a-time
  conversation by nature.
- No undo-after-accept — rejecting before accepting is the safety net;
  once saved, reverting is a normal `git checkout`/manual-edit job like
  any other file in `output/`.

## Architecture

```
resume polish [FILE]
  → FILE given: load it directly.
    FILE omitted: questionary picker over output/json/*.json (newest
    first, labeled with type + company/title parsed from filename)
  → detect doc_type from filename suffix: "_Resume.json" -> resume,
    "_CoverLetter.json" -> coverletter
  → load current JSON as `doc` (the loop's working state)
  → loop:
      instruction = prompt user ("polish> ")
      instruction in {"", "done", "exit"} or Ctrl-D/Ctrl-C -> break
      candidate = generate_candidate(doc, instruction, doc_type)
      if candidate is None: print error, continue (no state change)
      diff = diff_documents(doc, candidate)
      if diff is empty: tell user nothing changed, continue
      print diff
      choice = ask accept / reject / quit
      quit -> break
      reject -> continue (doc unchanged, re-prompt)
      accept ->
        doc = candidate
        save_and_render(doc, doc_type, json_path)
        print output paths
  → on loop exit: print final summary (saved changes this session, if
    any) and return
```

`generate_candidate(doc, instruction, doc_type)`:
- resume: strip `_recommendation_actions` (non-schema tracking key) from
  `doc` before sending; call `GeminiClient.generate(model=BUILDER_MODEL,
  system_instruction=<polish_resume.md>, contents=<doc JSON +
  instruction>, response_schema=TemplateSchema, temperature=0.0)`; parse
  result; run `normalize_resume.normalize()` on it (idempotent — reapplies
  fixed contact/cert/education fields and formatting rules, e.g. TAGLINE
  uppercasing — confirmed safe to re-run on already-normalized data); if
  the original `doc` had `_recommendation_actions`, reattach it unchanged;
  run `validate_resume.validate()` and print any warnings (non-blocking —
  the diff+confirm step is the actual gate, same posture as the existing
  recommendation-apply loop in `orchestrator.py`).
- coverletter: call the same way with `response_schema=CoverLetterSchema`
  and `<polish_coverletter.md>`; `CoverLetterSchema`'s shape is already
  the full on-disk shape (no fixed-field merge step needed, no
  normalize equivalent); run `validate_coverletter.validate()` similarly.

This mirrors `build_tailored_resume`'s recommendation-apply step
(`orchestrator.py` ~line 2009-2037) almost exactly — polish is
functionally "one more recommendation, except it comes from Morgan
instead of a critique pass," so it reuses the same schema, same
normalize/validate calls, same JSON-in/JSON-out shape.

`diff_documents(old, new)`:
- Compares field-by-field. Scalar fields: print `field: "old" -> "new"`
  when different. `EXPERIENCE` and `body_paragraphs` (list fields):
  compare element-by-element by index, printing only the entries that
  differ (e.g. "EXPERIENCE[2].achievements[1] changed") rather than
  dumping entire lists. Fields not present in `TemplateSchema`/
  `CoverLetterSchema` (contact info, certifications, education,
  `_recommendation_actions`) are excluded from the diff entirely — they
  can't change from a polish turn, so surfacing them would just be noise.

`save_and_render(doc, doc_type, json_path)`:
- Writes `doc` to `json_path` (overwrite).
- Derives `stem` by stripping the known `_Resume.json`/`_CoverLetter.json`
  suffix from `json_path`'s filename (polish always starts from an
  existing output file, so this is simpler than `_build_output_stem`,
  which derives a stem from a *JD* path).
- Calls `render_html()`/`render_coverletter()` directly (already plain
  importable functions) to regenerate the HTML.
- Shells out to `generate-pdf.mjs` exactly like `build_tailored_resume`/
  `build_tailored_coverletter` already do (`subprocess.run(["node",
  pdf_script, html_out, pdf_out, "--format=letter"], ...)`).
- Prints the resulting json/html/pdf paths on success; prints stderr and
  leaves the just-saved JSON in place (but does not roll it back) on a
  PDF-generation failure — the JSON accept already happened, so the
  document reflects the accepted edit even if that particular render
  attempt failed; the next accepted turn (or a manual re-run) will retry
  the render.

## Components

- **`resume-engine/prompts/polish_resume.md`** (new) — system prompt:
  given the current resume JSON and one instruction, return the complete
  resume JSON in the same schema with ONLY the requested change applied;
  every other field must be preserved verbatim; do not rewrite
  unrelated bullets/wording, do not re-optimize for ATS/keywords, do not
  "fix" anything not mentioned; if the instruction is ambiguous, make the
  single most reasonable interpretation rather than asking a clarifying
  question back (there's no back-channel for that in one structured-output
  call).
- **`resume-engine/prompts/polish_coverletter.md`** (new) — same
  contract, scoped to `CoverLetterSchema`'s fields (`greeting`,
  `body_paragraphs`, `sign_off`); the prompt explicitly tells the model
  to leave `company_name` untouched even if the instruction seems to ask
  for it, since a company-name change is a data-correctness edit, not a
  wording/preference one, and belongs upstream in the JD/builder step.
- **`scripts/polish.py`** (new) — `run(file: str | None) -> None`:
  entry point wired from `cli.py`. Contains `pick_polish_target()`,
  the main loop, `generate_candidate()`, `diff_documents()`,
  `save_and_render()`.
- **`cli.py`** (modify) — new `resume polish [FILE]` command, same
  wiring pattern as `tailor`/`coverletter`.
- **`menu.py`** (modify) — new interactive-menu entry alongside the
  existing tailor/coverletter/evaluate items.
- **`scripts/orchestrator.py`** (no changes) — `TemplateSchema`,
  `CoverLetterSchema`, `BUILDER_MODEL`, `normalize_resume.normalize`,
  `validate_resume.validate`, `validate_coverletter.validate`,
  `render_html`, `render_coverletter` are all imported/reused as-is.

## Error Handling

- `FILE` given but doesn't exist, or picker finds zero files in
  `output/json/` — print a clear message, exit without entering the
  loop.
- Filename doesn't match either known suffix (`_Resume.json`/
  `_CoverLetter.json`) — print an error naming the expected suffixes,
  exit without entering the loop (polish can't guess which schema to
  target).
- Gemini call returns no parseable JSON for a turn — print a warning,
  discard that turn's attempt, `doc` stays unchanged, loop continues
  (same recoverable posture as a reject).
- Diff comes back empty (Gemini echoed the input unchanged) — tell the
  user nothing changed rather than presenting an empty diff as if it were
  a real turn to confirm.
- `generate-pdf.mjs` non-zero exit after an accept — print stderr; the
  JSON/HTML for that turn are already written, only the PDF regeneration
  itself failed; message says so explicitly so it isn't mistaken for the
  edit having been lost.
- Ctrl-D/Ctrl-C at the instruction prompt — treated as a clean "done",
  same as typing `done`/`exit`; no traceback.

## Testing

- `diff_documents()`: unit tests covering scalar-field changes,
  list-field (EXPERIENCE/body_paragraphs) element-level changes, no-op
  (identical documents) case, and confirming excluded/non-schema fields
  never appear in the diff output.
- `generate_candidate()`: unit tests with `GeminiClient.generate` mocked
  (same convention as existing orchestrator tests) covering: resume path
  re-attaches `_recommendation_actions` unchanged; resume path re-runs
  `normalize_resume.normalize()` (e.g. confirms TAGLINE gets
  re-uppercased if the model returned it lowercase); unparseable response
  returns `None` rather than raising.
- `pick_polish_target()`/filename-suffix detection: unit tests for
  correct doc_type classification, and for the "no match" error path on
  an unrecognized filename.
- `save_and_render()`: unit test with `subprocess.run` mocked (same
  convention as `liveness.py`'s tests) confirming the json/html/pdf paths
  used match the input file's stem, and that a non-zero mocked exit
  doesn't raise past the function.
- Live verification: run `resume polish` against a real existing output
  file, make one real edit request, confirm the diff shown matches what
  actually changed, accept it, and confirm the regenerated PDF opens and
  reflects the change.
