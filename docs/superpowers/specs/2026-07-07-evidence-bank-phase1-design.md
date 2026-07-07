# Evidence Bank Extension — Phase 1: Voice Signals & Cover-Letter Context

## Problem

IDEAS.md's item 5 ("evidence bank extension") turned out to be much bigger
than one spec — reconciling two diverged knowledge-base directories across
resume-builder and career-ops, plus generalizing bullets into typed
multi-renderer evidence, is genuinely "Very Hard/Long-term" scope (see
IDEAS.md's 2026-07-07 research notes). But the research pass that scoped
that down surfaced several small, concrete, high-value gaps that are
tractable right now:

1. Career-ops has `MorganWritingStyleGuide.txt` -- Morgan's own pre-existing
   voice rubric, opening with "Morgan Escott writes with what can only be
   described as **strategic sparkle**" -- currently wired into nothing.
2. Career-ops has a small, already-curated `Application_Answers_Index.csv`
   (14 rows) with themes and "Quote Worth Pulling" lines -- also unwired.
3. resume-builder's own `detective-findings.csv` is referenced by its own
   already-wired `treering-archive-readme.md` as a "companion file"
   (alongside `verified-claims.csv`/`evidence-guide.csv`, which *are*
   wired) but isn't actually in `KB_ALLOWLIST`.
4. Cover letters currently get a much thinner context than resumes --
   `build_audit_static_prefix()` (profile.yml + 3 verified_*.json files)
   only, none of the 14 extra files resume building gets via
   `KB_ALLOWLIST` (`evidence-guide.csv` in particular is arguably *more*
   relevant to cover-letter narrative than to resume bullets).

Every one of these needs to respect a hard constraint Morgan has already
learned the expensive way: this codebase has real, previously-hit context/
rate-limit ceilings (see `orchestrator.py`'s comment on why
`bullet-bank-keepers-audited.csv` is deliberately excluded from
`KB_ALLOWLIST` -- including it once blew a real run past the free tier's
250k-input-tokens-per-minute cap). Nothing here should be a raw wholesale
file dump; everything follows the pattern already established elsewhere in
this codebase (bullet mining via embeddings-based top-K retrieval, the slim
Tier-1 audit prefix, `forbidden_phrases` as compact rules instead of raw
examples): **curated or trimmed, measured before it's wired in, never
dumped wholesale.**

## Goals

1. Distill `MorganWritingStyleGuide.txt` directly into existing rule/prompt
   files -- zero runtime token cost, a one-time content migration.
2. Copy `Application_Answers_Index.csv` into resume-builder's own
   `knowledge_base/` (no runtime cross-repo dependency) and generate a
   small curated `voice-anchors.md` from it (measured: ~1,011 tokens --
   trivially safe to wire in everywhere).
3. Generate a trimmed `detective-findings-trimmed.csv` (5 of its 14
   columns -- the ones that carry the "authorship framing and use caveats"
   value the README calls out) and wire *that* into `KB_ALLOWLIST`, not the
   raw file (measured: ~57,850 -> ~29,983 tokens, a 48.2% reduction).
4. Parameterize `build_audit_static_prefix(include_evidence_guide: bool =
   False)` so cover letters can get `evidence-guide.csv` (~17,329 tokens)
   without that cost multiplying across Step 3's per-bullet audit loop,
   which reuses the same function today.

## Non-Goals

- No wiring of `coverage-tracker.csv`, `screenshot-review-log.csv`, or the
  `.csv` twin of `treering-archive-readme.csv` -- confirmed audit-process
  tracking/duplicates, not evidence content, not model-facing.
- No ingestion of the raw "Treering Sequences" archive (140+ files, mixed
  authorship, heavy duplication) -- genuine future value, but needs its own
  curation pass first, filed as a follow-up in IDEAS.md, not built here.
- No live/runtime dependency on career-ops's filesystem path -- the two
  small source files this spec uses (`MorganWritingStyleGuide.txt`,
  `Application_Answers_Index.csv`) are read once, during implementation,
  and their derived content is committed into resume-builder's own
  `knowledge_base/`. Nothing in `scripts/` reads from `/Users/morganescott/
  career-ops/...` at runtime.
- No changes to any `KB_ALLOWLIST` entry's existing content, and no removal
  of anything currently wired.

## Architecture

### 1. Style guide distillation (one-time, zero runtime cost)

`resume-engine/rules/style_rules.yaml` -- add two entries to
`forbidden_phrases` (from the guide's "Anti-Voice Red Flags," not already
covered by the existing list):

```yaml
  - wear many hats
  - to whom it may concern
```

`resume-engine/prompts/tailor_coverletter.md` -- the guide's own
platform-specific rule for cover letters is more specific than what's
there today. Replace:

```
- Keep each paragraph to 3-5 sentences -- a cover letter, not an essay.
```

with:

```
- Keep each paragraph to 4-6 lines, 400-450 words total across the whole
  letter -- warmly strategic, not an essay (per Morgan's own established
  platform-specific style rule).
```

`resume-engine/prompts/critique_resume.md` -- add a new reference section
(usable standalone, not dependent on the separate Sparkle critique-signals
spec's Step 9.5), inserted right before "## Constraints":

```
## Voice Calibration Reference

From Morgan's own established writing-style rubric -- use these as
calibration examples when judging whether a section reads as
distinctive/flat, and how much personality is appropriate per section:

**Contrast examples (same underlying idea, different execution):**
- Generic/Professional: "I'm writing to express my interest in the role."
  (too stiff, no personality)
- Try-Hard/Creative: "I'm a unicorn who eats KPIs for breakfast."
  (performative, lacks depth)
- Morgan's actual voice: "It felt like more than an opportunity -- it felt
  like alignment." (human, reflective, quietly compelling)

**Sparkle calibration by section (dial personality up or down, don't
apply one flat level everywhere):**
- Resume Summary: keep sparkle low, structure high -- one standout phrase
  is the ceiling, not a target to exceed.
- Cover letter: warmer and more room for story-driven phrasing than a
  resume summary.
- Corporate/formal-toned JDs: subtle sparkle only -- one voice-y line is
  enough; match the JD's own register first.
```

### 2. `voice-anchors.md` (new, curated, measured at ~1,011 tokens)

- Copy `Application_Answers_Index.csv` (14 rows) from career-ops into
  `resume-engine/knowledge_base/application-answers-index.csv` -- a
  one-time file copy, committed to resume-builder's own repo.
- New script `scripts/build_voice_anchors.py`: reads that CSV, writes
  `resume-engine/knowledge_base/voice-anchors.md`, one section per row:

  ```markdown
  ### {Prompt / Topic}

  {Themes & Highlights}

  > {Quote Worth Pulling}
  ```

  (the `> quote` line omitted when that column is empty for a row -- 9 of
  14 rows have it populated, per the source data).
- Add `"voice-anchors.md"` to `KB_ALLOWLIST` in `orchestrator.py` (reaches
  Step 4 resume building).
- Load it unconditionally inside `build_audit_static_prefix()` (reaches
  Step 3's per-bullet audit loop *and* cover letters) -- safe to include
  unconditionally given its small, measured size, unlike `evidence-guide.csv`
  below.

### 3. `detective-findings-trimmed.csv` (new, measured at ~29,983 tokens,
   a 48.2% reduction from the raw file's ~57,850)

- New script `scripts/trim_detective_findings.py`: reads
  `detective-findings.csv`, projects to exactly these 5 columns (the ones
  carrying the README's called-out "authorship framing and use caveats"
  value -- drops `Finding ID`, `URL`, `Persona / Context`, `Portfolio
  Potential`, `Resume Potential`, `Reviewed`, `Next Follow-Up`, `Notes`,
  none of which are useful to a builder/critique LLM call):
  `Source File`, `Finding Type`, `Best Details`, `Confidence`,
  `Use Caveat`. Writes
  `resume-engine/knowledge_base/detective-findings-trimmed.csv`.
- Add `"detective-findings-trimmed.csv"` to `KB_ALLOWLIST` (Step 4 only --
  matching its siblings `evidence-guide.csv`/`verified-claims.csv`, which
  are also Step-4-only). The raw `detective-findings.csv` stays on disk,
  unwired, as the source of truth the trim script reads from.
- Re-runnable: if `detective-findings.csv` ever gets new rows (the Treering
  audit is described as ongoing), re-running the script regenerates the
  trimmed companion file.

### 4. `build_audit_static_prefix()` parameterization

```python
def build_audit_static_prefix(self, include_evidence_guide: bool = False) -> str:
    ...
    # existing profile.yml / verified_facts / verified_tools / verified_projects sections unchanged
    ...
    # voice-anchors.md loaded unconditionally here (see Architecture #2)
    if include_evidence_guide:
        fpath = os.path.join(self.kb_dir, "evidence-guide.csv")
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                data = f.read()
            sections.append(f"=== EVIDENCE GUIDE (thematic career-proof clusters) ===\n{data}")
    return "\n\n".join(sections)
```

`build_tailored_coverletter()`'s call site (`orchestrator.py:1573`)
changes from `self.build_audit_static_prefix()` to
`self.build_audit_static_prefix(include_evidence_guide=True)`. Step 3's
audit-loop call site (`orchestrator.py:1715`) is left unchanged (default
`False`) -- its cost stays exactly as it is today, since it's reused across
every bullet in a resume build, not called once like the cover-letter path.

## Data Flow

```
Implementation-time (one-time, not part of any live run):
  MorganWritingStyleGuide.txt (career-ops, RTF)
    -> read via textutil, distilled by hand into
       style_rules.yaml / tailor_coverletter.md / critique_resume.md

  Application_Answers_Index.csv (career-ops)
    -> copied to knowledge_base/application-answers-index.csv
    -> scripts/build_voice_anchors.py -> knowledge_base/voice-anchors.md

  detective-findings.csv (already in knowledge_base/, unwired)
    -> scripts/trim_detective_findings.py -> knowledge_base/detective-findings-trimmed.csv

Live, per resume/cover-letter build (orchestrator.py):
  Step 3 (audit) / cover letters -> build_audit_static_prefix(include_evidence_guide=?)
    -> profile.yml (trimmed) + verified_facts/tools/projects.json + voice-anchors.md
       + (cover letters only) evidence-guide.csv

  Step 4 (fresh resume builds) -> load_knowledge_base() -> KB_ALLOWLIST
    -> existing 17 files + voice-anchors.md + detective-findings-trimmed.csv
```

## Error Handling

- Missing `voice-anchors.md`/`detective-findings-trimmed.csv` at runtime --
  `load_knowledge_base()` already warns-and-skips missing allowlist entries
  (existing behavior, unchanged); `build_audit_static_prefix()`'s existing
  per-file `try/except` + `os.path.exists()` guards cover the new
  evidence-guide.csv load the same way the three verified_*.json loads are
  already guarded.
- `application-answers-index.csv` missing when `build_voice_anchors.py`
  runs -- print a clear error and exit non-zero rather than writing an
  empty/partial `voice-anchors.md`.
- `detective-findings.csv` missing when `trim_detective_findings.py` runs
  -- same: clear error, non-zero exit, no partial output file.
- A row missing one of the 5 kept columns (shouldn't happen, but
  defensively) -- `trim_detective_findings.py` writes an empty string for
  that cell rather than raising, matching `csv.DictWriter`'s default
  behavior with `restval=""`.

## Testing

- `scripts/build_voice_anchors.py`: unit tests with a small fixture CSV
  (2-3 rows, one with a populated `Quote Worth Pulling`, one without) --
  confirms the `> quote` line appears only when present, confirms section
  headers use the `Prompt / Topic` column, confirms output file is written
  to the expected path.
- `scripts/trim_detective_findings.py`: unit tests with a small fixture
  CSV -- confirms exactly the 5 target columns appear in the output header
  (in order), confirms dropped columns' data doesn't leak into any output
  cell, confirms row count is preserved (no rows silently dropped).
- `orchestrator.build_audit_static_prefix()`: unit tests (mirroring
  existing `ResumeEngine` test conventions) -- confirms
  `include_evidence_guide=False` (the default) produces output identical
  to today's behavior plus the new voice-anchors.md section; confirms
  `include_evidence_guide=True` additionally includes evidence-guide.csv's
  content; confirms a missing `voice-anchors.md`/`evidence-guide.csv` is
  skipped without raising (matching existing per-file guard behavior).
- `KB_ALLOWLIST` unit test: confirms `voice-anchors.md` and
  `detective-findings-trimmed.csv` are present in the sorted list, and
  confirms the raw `detective-findings.csv` is deliberately *not* present
  (guards against someone later adding the raw file by mistake instead of
  the trimmed one).
- Live verification: run `resume tailor <file>` and `resume coverletter
  <file>` against real pending JDs; confirm no token/rate-limit errors
  (the exact failure mode this spec is designed to avoid re-triggering),
  and eyeball whether the new voice-anchors/evidence-guide context
  produces any noticeably different tone in the output.
