# PLAN.md Gap Review

Findings from a review of `docs/review/PLAN.md` itself (not the codebase),
looking for coverage gaps in the 6-phase review plan. Confirmed against the
live `scripts/` inventory and `menu.py`/`cli.py` wiring, not source-read in
depth.

## 1. ~25 scripts owned by no phase

Roughly half of `scripts/` never appears in any phase's ownership list.
Confirmed live via `grep` against `scripts/menu.py` and `scripts/cli.py` —
not dead code.

**Bullet-bank curation subsystem** (feeds goal 2's voice/personalization
directly — Phase 3 reviews the *prompts* that consume `voice-anchors.md`,
but not the pipeline that *builds* it):
- `audit_bullet_bank.py`
- `cluster_bullet_bank.py`
- `tag_bullet_bank.py`
- `score_keeper_gems.py`
- `detect_hidden_gems.py`
- `detect_blank_scores.py`
- `embed_bullet_bank.py`
- `build_voice_anchors.py`
- `retire_rewrite_queue.py`
- `trim_detective_findings.py`
- `triage_needs_review.py`
- `bullet_feedback.py`

If this pipeline is broken, Phase 3's central question ("does the pipeline
verifiably use `voice-anchors.md`?") gets judged against a bad artifact
with no phase positioned to notice.

**Job-discovery subsystem** — absent from the plan's frame entirely, despite
goal 1 being scoped as "the entire process":
- `scan.py`
- `scan_ats.py`
- `scan_boards.py`
- `scan_jobright.py`
- `scan_linkedin.py`
- `company_research.py`
- `followup.py`
- `situational_roles.py`

**Misc utilities**, unclaimed:
- `git_update.py`
- `maintenance.py`
- `ingest.py`
- `normalize_resume.py`
- `batch_evaluate.py`
- `bootstrap_timeline.py`
- `build_sample.py`
- `dashboard.py` (the Python shim — distinct from `dashboard/`, the Go
  module Phase 2 owns)
- `validate_coverletter.py` (its sibling `validate_resume.py` is owned by
  Phase 3; this one is nowhere)

The plan's own "Unowned files" rule requires claiming or explicitly
recording unowned files rather than silently skipping them — this is a
larger, unaddressed instance of exactly that.

## 2. No synthesis/reconciliation phase

Six phases each produce independent findings docs with fixes explicitly
deferred to a separate pass. Phase 4 is instructed to "pick a side" on the
ligature-normalization fix layer even though Phase 2 already made a
recommendation — nothing merges the six docs into one de-duplicated,
prioritized backlog, or formally resolves contradictions the plan itself
flags. Without a closing phase, the docs just accumulate.

## 3. No prompt-injection / secrets check

CLAUDE.md already flags that underscore-prefixed JD metadata must not leak
into prompts via `read_jd_text()`. No phase asks the adjacent question:
JD text itself is attacker-controlled/untrusted input — can embedded
instructions in a job posting manipulate the Gemini call (e.g., an
"ignore prior instructions, score this 100" payload)? Nor does any phase
check whether API keys / `.env` contents could leak via crash logs, error
messages, or the Syncthing-synced profile folders.

## 4. No data-integrity / backup question for the knowledge base

Per project memory, the sibling `career-ops` repo has a precedent of its
auto-update silently clobbering personalized files despite a data contract
meant to prevent it. No phase in this plan asks whether a crashed write
mid-run can corrupt `bullet-bank.md` or other KB files, or whether any
recovery path exists if it does.

---

**Smallest fix:** explicitly scope the job-discovery and bullet-bank-
curation subsystems into an existing phase (3, and/or a new lightweight
3b), and add one short closing phase for synthesis plus the two
cross-cutting security/data-integrity questions above.
