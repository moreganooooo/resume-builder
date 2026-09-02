# Stress / Challenge Scoring: Scoping Doc

Date: 2026-09-01
Status: Built. Both signals now feed `orchestrator.fit_composite_score()`
directly (see "Where either landed" below) -- the "sort/display only
until proven" recommendation further down was overridden by an explicit
user request to wire both into scoring, with low-stress weighted as a
reward rather than merely the absence of a penalty. That is a deliberate
preference choice, not a corpus-validated precision number the way
`work_hours.py`/`compensation.py`'s thresholds are -- see the caveat at
the bottom.

## The ask

Two distinct questions were floated together, and they are not the same
signal:

1. "How stressful/challenging will this role be, **given my current
   skills and background**?" — a stretch signal. Depends on the
   candidate, not just the posting.
2. "How low-stress is this role **intrinsically** — no high-volume
   calls, no quota pressure, no fire-fighting?" — a role-characteristic
   signal. Depends on the posting, not the candidate.

Conflating them would produce one number that means two different
things depending on which posting you're looking at, which is exactly
the mistake `role_track`'s "manager" vs. "unknown" collapse and
`compensation_viability`'s "low" vs. "not stated" collapse were both
built to avoid. They need two fields, not one.

## Signal 1: stretch, given the candidate

This is **not a new evaluation**. It is already partially computed and
partially thrown away:

- `FitSubscores.work_style_sustainability` (`scripts/schemas.py`) already
  asks "1-5: realistically sustainable/energizing vs.
  brute-force/burnout-prone" — but it is one ingredient folded into a
  composite `fit_score`, never surfaced on its own.
- `FitSubscores.level_plausibility` ("screen risk... overqualified vs.
  underqualified") is adjacent: under-leveled is a stretch, over-leveled
  is boredom, and today only the screen-risk framing is captured.
- `capability_gaps` (added for the earlier IC/manager work) already
  lists specific experience the JD asks for that the resume doesn't yet
  evidence — that list length and severity IS a stretch measurement that
  already exists on disk for every evaluated JD going forward.

The grounded move is the same one `compensation_viability` needed:
**don't add a new LLM call that re-derives a judgment from scratch — add
a field that reads the evidence the model already produced.** Concretely:

- Add `stretch_evidence: str` to `CapabilityEvaluationSchema` — "the
  single biggest gap between what this role asks and what the resume
  shows" (empty when there isn't one). This is `capability_gaps`
  reduced to its sharpest entry, not a new judgment.
- Surface `capability_gaps` count/severity plus `level_plausibility`
  together in the Jobs detail pane as "Stretch" — derived from fields
  that already exist, no new prompt call. (Built as display; the count
  also now feeds `fit_composite_score` as `STRETCH_GAP_PENALTY_PER_ITEM`
  — see "Where either landed".)

This is cheap and low-risk specifically because it adds no new LLM call
and reuses fields already validated by
`test_every_schema_field_has_a_place_to_land`. It is NOT a full "stress
score" — it answers "is this a reach" not "will this job burn me out",
which is signal 2.

## Signal 2: intrinsic role stress

This is a real gap, and it is a body-text detection problem before it is
a scoring problem — the same shape `work_hours.py` and `compensation.py`
were. Both of those started from **measuring the corpus for a
false-positive rate before shipping any threshold**, and both found the
naive approach was wrong (24-hour SLA language read as a work-hours
statement; a $50 internet stipend read as salary). A stress detector has
at least as much surface for the same failure:

- "Fast-paced environment" appears in a huge fraction of postings as
  pure boilerplate, unrelated to actual pace.
- "High call volume" / "high volume of calls" is a real signal but rare
  outside sales/support roles this profile's `title_filter` already
  screens out — so it may fire on almost nothing in this corpus
  specifically, which is worth knowing before investing in it.
- "Wears many hats" is sometimes a genuine understaffing red flag and
  sometimes founder-culture flavor text on a well-resourced team.
- Negative framing is common and easy to mis-read: "no on-call rotation"
  should read as LOW stress, not trip a same-word match on "on-call".

**Proposed phase 1 (cheap, no schema/LLM change):** a `stress_signals.py`
module in the shape of `work_hours.py` — a fixed list of phrase
patterns, each with a required "near-negation" exclusion window (same
technique `compensation.py`'s `_BENEFIT_NEAR` uses to keep a stipend from
reading as salary). Candidates to test against the real corpus, not
ship blind:

- volume/pace: "high call volume", "high-volume queue", "fast-paced
  environment" (measure its true hit-rate first — likely too common to
  be useful)
- pressure/targets: "aggressive targets", "quota", "meet or exceed
  quota", "KPIs are strictly enforced"
- availability: "24/7", "on-call rotation", "after-hours", "weekend
  coverage" (each needs a negation check: "no on-call", "no weekend
  work")
- churn/crisis: "fire-fighting", "wear many hats", "fast-changing
  priorities", "ambiguity" (double-edged — some candidates want this)

Run this read-only against the existing corpus (like `work_hours.py`'s
2.3%-of-postings measurement) and report hit rates and a sample of
matches for hand review, **before** wiring it into any filter or score.
That measurement either produces a useful signal or kills the idea
early and cheaply — which is the right order, given how often a
plausible-sounding phrase list has turned out to fire on the wrong
thing in this codebase (hours, compensation, unpaid-work keyword scans
all failed this exact test on first attempt).

**Not phase 1:** an LLM-judged "stress score." A model asked to rate
1-5 how stressful a posting sounds, with no anchor, is exactly the
"invented, not estimated" failure mode `compensation_viability` already
hit once — no floor was ever given to the prompt, so the model
free-associated a number. If this signal is worth a scored subscore at
all, it should be anchored the same way compensation was ultimately
fixed: hand the model the DETECTED phrases from phase 1's deterministic
scan, not "does this sound stressful."

## Where either landed

Both signals enter `orchestrator.fit_composite_score()` directly, in
Python, alongside the existing proximity bonus and stale-posting penalty
-- not as an LLM-judged subscore, since both are deterministic counts
(`stress_signals.categories()`'s category count and
`len(capability_gaps)`), consistent with "all composite math stays in
Python (never trusted from the model)."

- **Stress**: `STRESS_SIGNAL_PENALTY_PER_CATEGORY` (0.25/category, capped
  at `STRESS_SIGNAL_MAX_PENALTY` = 0.75) vs. `LOW_STRESS_BONUS` (0.40) for
  zero detected categories. The bonus is deliberately larger than the
  cost of any single category, per the explicit ask: finding a
  comfortable, sustainable role is the goal, not merely avoiding red
  flags, so "clean" should be rewarded, not just spared a penalty.
- **Stretch**: `STRETCH_GAP_PENALTY_PER_ITEM` (0.20/gap, capped at
  `STRETCH_GAP_MAX_PENALTY` = 0.80) on `len(capability_gaps)` -- a
  deterministic count, distinct from `fit_subscores.level_plausibility`
  (the model's own subjective screen-risk judgment), which already
  carries its own weight in `FIT_SUBSCORE_WEIGHTS` and is untouched here.

This is a **preference weighting, not a validated precision threshold**.
Unlike `work_hours.py`/`compensation.py`, whose thresholds were tuned
against a measured false-positive rate on the real corpus, these numbers
were chosen to satisfy the stated goal (reward low-stress heavily,
penalize a stretch role) without a corpus-measured "correct" weight to
aim for -- there is no ground truth for "how many points should a
fast-paced posting lose." If these turn out to over- or under-weight in
practice, adjust the constants directly in `orchestrator.py`; there is
no Settings & Upkeep control for them, unlike `compensation.annual_floor`
or `location.radius_miles`, because these are composite-scoring tuning
constants in the same category as `FIT_SUBSCORE_WEIGHTS` and
`STALE_POSTING_PENALTY_PER_DAY` (developer-tuned application constants),
not a literal personal cutoff a user sets once (see
[[feedback_user_configurable_not_hardcoded]] for that distinction).

`role_track` shipped narrower -- sort/display only until a labeled
holdout proved titles carry zero manager signal, before it became even
a narrow opt-in gate. Stress/stretch skipped that same validation step
by explicit user request; the corpus measurement that exists
(`measure_stress_signals.py`'s 7.8%-of-postings hit rate) establishes
that the signal fires rarely, not that it's precise when it does.

## Recommended next step

If you want to move on this, the lowest-risk, most useful next action
is phase 1 of signal 2 in isolation: write `stress_signals.py`'s
phrase/negation detector, run it read-only against the real corpus, and
report hit rates — no schema change, no prompt change, nothing shipped
to the dashboard yet. That tells us in one pass whether any of these
phrases are common enough and precise enough to be worth a badge, let
alone a score, before touching `CapabilityEvaluationSchema` or
`RecruiterEvaluationSchema` at all.

Signal 1 (stretch, given the candidate) is separately cheap enough to
ship on its own whenever wanted — it's one new `str` field plus a
display change, no new LLM call, no new corpus measurement needed.
