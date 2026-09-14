# Hard blockers (`years_experience`/`degree`/`field_domain`): measured, and not yet cleared

Status as of 2026-09-12: **display/filter-only, same as `role_track` before
its holdout measurement**. `experience_blockers` (the `years_experience`/
`degree` carve-out) and `field_domain` are surfaced as opt-in view filters
on Jobs (`[c]`) and Pipeline (`[x]`) but do not gate `composite_score` or
`recommendation` — every other `hard_blockers` category still does,
unconditionally, with no measurement at all. See [[role_track]] for why
that unconditional-zero design is itself the thing being fixed here, one
category at a time, and for the ≥90% precision bar this file measures
against.

## Why this is candidate-specific, unlike `role_track`

`role_track` asks "does this posting describe a people-manager role" --
answerable from the posting alone. This asks "does this posting's stated
years/degree or field/domain requirement actually disqualify THIS
candidate" -- not answerable from the posting alone. A "5+ years in
finance" requirement blocks a candidate with 2 years and doesn't block one
with 8. `scripts/build_hard_blocker_holdout.py` only automates finding and
presenting the right rows to look at; the labeler brings their own
background to each row.

## The holdout

`profiles/<profile>/hard_blocker_holdout.csv` (gitignored, one per
profile), built by `scripts/build_hard_blocker_holdout.py` -- blind (no
model prediction shown) and stratified on a cheap regex signal for
years/degree language (`degree-only`, `years-only`, `years+degree`,
`neither`; 30-40 rows each). Two label columns share one sample rather
than requiring a second holdout draw:

- `label` -- years/degree judgment (`blocks` / `does_not_block` / `unclear` / `n/a`)
- `field_domain_label` -- field/domain judgment, same value set

`field_domain` (required industry/functional background, e.g. "requires
healthcare experience") was added as its own category after the first
labeling pass surfaced it as the single largest blocker bucket in this
profile's corpus -- far bigger than years/degree combined -- previously
falling inconsistently into the catch-all `other` category, which already
force-zeroes the score with no measurement at all.

Full source text for each holdout row is preserved separately in
`hard_blocker_holdout_source.json`, so `eval_hard_blocker.py` measures
against the exact text that was labeled rather than a live re-scrape.

### Current state: 150/150 labeled on both dimensions

```
== years/degree (label) ==
labeled 150/150
  blocks          36
  does_not_block  114

== field/domain (field_domain_label) ==
labeled 150/150
  blocks          107
  does_not_block  43
```

## Measured result (2026-09-12): neither dimension clears the ≥90% bar

`scripts/eval_hard_blocker.py --profile morgan` re-runs the real
`evaluate_recruiter.md` call against each holdout row's preserved text and
scores both dimensions independently against the same 150 rows.

### years_experience / degree

```
predicted \ label           blocks  does_not_block         unclear             n/a
flagged                         16              12               0               0
not_flagged                     20             102               0               0

Blocker-class precision: 57.1% (16/28 flagged)
Blocker-class recall:    44.4% (16/36 actual)

Per stratum (scoreable rows only):
  degree-only    precision= 66.7%  recall= 16.7%  n=30
  neither        precision= 25.0%  recall=100.0%  n=40
  years+degree   precision= 85.7%  recall= 57.1%  n=40
  years-only     precision= 14.3%  recall= 50.0%  n=40
```

57.1% precision is well short of the 90% bar `role_track` cleared before
graduating. The `years-only` stratum is the weak point (14.3% precision)
-- the model flags a years-of-experience mention as blocking far more
often than a human labeler agrees it actually disqualifies the candidate,
while the `neither` stratum's 100% recall on only 4 actual blocks (25%
precision) suggests the model is also over-flagging borderline language in
postings a human read as clearly not blocking.

### field_domain

```
predicted \ label           blocks  does_not_block         unclear             n/a
flagged                         36               7               0               0
not_flagged                     71              36               0               0

Blocker-class precision: 83.7% (36/43 flagged)
Blocker-class recall:    33.6% (36/107 actual)

Per stratum (scoreable rows only):
  degree-only    precision= 83.3%  recall= 43.5%  n=30
  neither        precision= 75.0%  recall= 11.1%  n=40
  years+degree   precision= 90.5%  recall= 65.5%  n=40
  years-only     precision= 66.7%  recall= 14.3%  n=40
```

Closer to the bar (83.7% vs. 90%) but still short, and recall is the
dominant problem here, not precision: the model only flags 43 of 150 rows
at all against 107 human-labeled actual blocks, so most real field/domain
requirements pass through unflagged. `field_domain` is not yet its own
carve-out (unlike `years_experience`/`degree`) -- it still falls into the
catch-all `other` category, which unconditionally zeroes the score.

## First fix attempt (2026-09-12): modest gain, does not clear the bar

Re-running the mismatched holdout rows through the model directly (not
just reading the aggregate numbers) surfaced three concrete, fixable
patterns in `years_experience`/`degree` precision:

1. **Title-inference bug** -- the exact anti-pattern `role_track` already
   had to eliminate. "VP, Marketplace Growth" @ DonorsChoose was flagged
   `years_experience` with `text` set to the literal job title, not any
   stated requirement -- the model inferred a threshold from seniority
   implied by the title, with no number anywhere in the posting.
2. **No directional check on low floors.** Entry-level ranges ("0-2
   years," "1-3 years") were flagged as blocking, when a low floor
   essentially never disqualifies an experienced candidate -- flagging
   looked driven by the mere presence of a years-number, not a real
   comparison against the candidate's own tenure.
3. **Category conflation.** "5 years in the drilling industry" was
   tagged `years_experience` when the disqualifying element is the
   industry match, which belongs under `field_domain`.

`resume-engine/prompts/evaluate_recruiter.md`'s `hard_blockers`
instructions were edited to address all three: an explicit
never-infer-from-title-alone rule with a quote requirement, a directional
floor-comparison rule with a low-floor example, and a category-routing
rule for industry-qualified years language. `field_domain`'s guidance was
also broadened to cover implicit/systemic domain fit (a role built
entirely around an "Insurance Platform" or higher-ed partnerships,
without ever using the word "required"), not just literal quoted
requirement sentences -- the recall gap suggested the model was only
reaching for the literal-quote pattern.

### Measured result: real but insufficient movement

```
                        before -> after
years/degree precision:  57.1% -> 59.4%
years/degree recall:     44.4% -> 52.8%
field_domain precision:  83.7% -> 87.2%
field_domain recall:     33.6% -> 38.3%
```

field_domain precision moved meaningfully closer to the 90% bar; recall
improved on both dimensions. years/degree precision barely moved, and one
stratum got worse: `years-only` precision dropped from 14.3% to 9.1%.

### Root cause of the remaining years-only failure: overqualification, not underqualification

Directly re-running the Nasuni "Inside Sales Representative" case (the
same "1-3 years of experience" row that was a false positive before the
fix) confirmed the low-floor instruction did not change the model's
behavior on it at all -- it still flags the same requirement, quoting the
same text, after the fix. This is not a wording gap. The model appears to
be reasoning about a genuinely different, real recruiting concern:
**overqualification** -- "this posting reads as entry-level; an
experienced candidate is a mismatch for the role, and might get screened
out for being overqualified." That is a legitimate practical judgment a
human recruiter might make, but it is not what the `years_experience`
schema field is defined to mean (a stated minimum the candidate's history
falls *below*, not a role the candidate has outgrown). A wording fix
telling the model "don't flag low floors" collides with this instinct
rather than resolving it, because the model isn't failing to understand
the instruction -- it's answering a different, adjacent question. This is
recorded here, in the same spirit as `role_track.md`'s null-result
prompt experiments, so a future attempt doesn't re-try the same
directional-comparison wording expecting a different outcome.

A fix here likely needs a structural change, not another wording pass:
e.g., splitting `years_experience` into an explicit
under-qualified/over-qualified distinction the model states directly
(mirroring how `role_track_confidence` gives the model room to express a
distinction the raw verdict can't), with only the under-qualified case
counted as a real blocker -- rather than hoping prompt wording alone
resolves a genuine ambiguity in what "blocks" should mean for a threshold
requirement.

## Second fix attempt (2026-09-12, same day): the structural split, built

Implemented the structural fix proposed above rather than another wording
pass. `HardBlockerSchema` (`scripts/schemas.py`) gained a `direction`
field (`"under_qualified"` / `"over_qualified"` / `"n/a"`), meaningful
only for `years_experience`. `evaluate_recruiter.md` now tells the model
to keep flagging a low-floor requirement (it clearly wants to) but tag it
`over_qualified` rather than suppressing it -- the fix works WITH the
model's instinct instead of against it. `orchestrator.rescore_evaluation_with_location()`
then filters `direction == "over_qualified"` entries out of
`experience_blockers` before they ever reach the opt-in view filter or
`eval_hard_blocker.py`'s precision count, so the signal surfaces (still
visible in raw `hard_blockers`, still informative) without counting as a
disqualifier.

While testing this, the same title-inference bug from the first attempt
resurfaced: asking the model to also produce a `direction` value nudged
it back toward inferring a threshold from "VP, Marketplace Growth"'s
title alone (a near-empty, boilerplate-only posting with nothing else to
judge from) -- fixed with an explicit rule that needing a `direction`
value never excuses a quote-less blocker, plus a rule that a
boilerplate-only posting should produce an empty `hard_blockers` list
under any category rather than inventing one from the title.

Also audited one holdout label in passing: a BioIVT posting's
`field_domain_label` was `blocks`, but its only disqualifying text is a
state-hiring exclusion ("unable to hire in AK, HI, NM..."), which is a
location issue, not a domain one -- corrected to `n/a` in
`hard_blocker_holdout.csv` with a note explaining the correction (same
practice as `role_track.md`'s own holdout audit).

### Measured result: field_domain clears the bar; years/degree does not

Two of the three eval runs against this fix ran into severe, unrelated
Gemini rate-limiting (a wrong API key was active for long stretches of
both), which caused heavy model-fallback bouncing between
`gemini-3.1-flash-lite` and `gemma-4-31b-it` mid-run -- noisy, mixed-model
numbers that are not reported here. Once a working key was in place, a
clean 150/150 run with zero rate-limit retries and no fallback bouncing
gave:

```
### years_experience / degree ###
predicted \ label           blocks  does_not_block         unclear             n/a
flagged                         16              20               0               0
not_flagged                     20              94               0               0

Blocker-class precision: 44.4% (16/36 flagged)
Blocker-class recall:    44.4% (16/36 actual)

Per stratum (scoreable rows only):
  degree-only    precision= 66.7%  recall= 33.3%  n=30
  neither        precision=  0.0%  recall=  0.0%  n=40
  years+degree   precision= 78.6%  recall= 52.4%  n=40
  years-only     precision=  6.7%  recall= 50.0%  n=40

### field_domain ###
predicted \ label           blocks  does_not_block         unclear             n/a
flagged                         40               4               0               0
not_flagged                     66              39               0               1

Blocker-class precision: 90.9% (40/44 flagged)
Blocker-class recall:    37.7% (40/106 actual)

Per stratum (scoreable rows only):
  degree-only    precision=100.0%  recall= 43.5%  n=30
  neither        precision= 80.0%  recall= 14.8%  n=40
  years+degree   precision= 95.0%  recall= 67.9%  n=39
  years-only     precision= 77.8%  recall= 25.0%  n=40
```

**field_domain: 90.9% precision -- clears the ≥90% bar for the first
time**, with recall essentially unchanged (37.7%, vs. 33.6% at baseline).
This is the number to trust; it is a clean, single-model measurement,
unlike the earlier noisy runs.

**years_experience/degree: 44.4% precision -- reads WORSE than the noisy
runs suggested (59.4%), and this is the number to trust, not those.** The
`direction` filter provably works (verified by direct re-test: Nasuni's
"1-3 years" case is now correctly excluded from `experience_blockers`),
but it only helps precision on the specific low-floor false positives it
targets -- it does nothing for the model's broader, still-unexplained
tendency to both over- and under-flag `years_experience`/`degree` on this
clean single-model measurement. The `years-only` stratum (6.7% precision)
remains the dominant failure. This is now a harder, more central problem
than the overqualification pattern alone; a future investigation should
start from fresh false-positive/false-negative sampling against this
clean baseline, not by assuming the overqualification fix was the only
open issue.

## What this means today

`field_domain` has cleared the same ≥90% precision bar `role_track`
needed before it was allowed to graduate past display-only -- see
[[role_track]] for that graduation's own two-stage shape (opt-in view
filter, then a real `scan_filters.yml`-driven exclusion). Whether to
actually carve `field_domain` out of the unconditional zero-score/Skip
path the way `EXPERIENCE_BLOCKER_CATEGORIES` already does for
years_experience/degree is a real decision this file does not make
unilaterally -- recall is still only 37.7%, meaning most real field/domain
mismatches still pass through unflagged either way, so graduating it
changes what the ~27% it DOES catch does (informational -> filterable),
not the underlying coverage. `years_experience`/`degree` is further from
that bar than before this session's work started, not closer.

As of this measurement, neither category has actually been switched to a
different runtime behavior -- this is a documentation of what the numbers
support, not a changelog of a scoring change:

- `years_experience`/`degree` (`experience_blockers`) stays exactly where
  `orchestrator.EXPERIENCE_BLOCKER_CATEGORIES` already put it -- carved out
  of the unconditional zero-score/Skip path, surfaced only as an opt-in
  view filter (Jobs `[c]` / Pipeline `[x]`), never gating `composite_score`.
  Still correct: precision (44.4%) is nowhere near the bar.
- `field_domain` also still remains in `other`'s unconditional
  zero-out/Skip behavior for now, even though its precision has cleared
  the bar -- graduating it to `EXPERIENCE_BLOCKER_CATEGORIES`-style
  carve-out, or further to a real `scan_filters.yml`-driven exclusion
  (role_track's second-stage shape), is a decision for whoever owns this
  category to make deliberately, weighing the still-low 37.7% recall
  against the value of no longer force-zeroing a role over field_domain
  when it does have a signal.

## Where a fix would likely need to start next

Both items from the first attempt's list above are now done (the
structural `direction` split, and the one BioIVT holdout correction found
in passing) -- see the second fix attempt section. What's left, in rough
order of how likely it is to move a number without another null result:

1. **`years_experience`/`degree` needs fresh false-positive/false-negative
   sampling against the CLEAN single-model baseline above (44.4%/44.4%),
   not against the noisy rate-limited runs.** The `direction` split
   measurably fixed the specific low-floor pattern it targeted (verified
   by direct re-test), but the clean measurement shows a broader,
   still-uncharacterized problem -- precision and recall are now
   identical (44.4%/44.4%), which on a sample this size is consistent
   with the model's flag/no-flag decision carrying much less real signal
   on this category than field_domain's does. The next investigation
   should start from scratch on what's driving both directions of error,
   not assume the overqualification fix was the whole story.
2. **A full holdout label audit**, not just the one BioIVT correction
   found in passing -- `role_track`'s own numbers weren't trustworthy
   until it got a deliberate second labeling pass (see [[role_track]]'s
   "Second labeling pass" section). This holdout has had no equivalent
   pass, and the `field_domain` sample in particular was never
   stratified on a field_domain-specific signal (it rides on the
   years/degree regex strata), so a stratified re-sample specifically for
   field_domain would help distinguish real recall gaps from
   sampling-population effects.
3. **`field_domain` recall (37.7%)** is the number left on the table now
   that its precision has cleared the bar. Worth a second pass sampling
   more `field_domain`-signal-heavy rows specifically (not just
   years/degree strata) to see whether the remaining misses are genuinely
   implicit domain-fit judgments (hard to write a rule for) or still
   literal-quote misses (fixable with more worked examples).

## What's still unbuilt

- `field_domain` has no carve-out constant analogous to
  `EXPERIENCE_BLOCKER_CATEGORIES` -- **decided 2026-09-13 by the profile
  owner: it stays a hard blocker** (zero score, auto-archived as Skip),
  rather than becoming a penalty or a scan-time filter. The reasoning:
  precision cleared the bar, so a flag is usually right (roughly 1 in 10
  blocked roles may be a genuine fit, recoverable from the archive), and
  low recall only means most real mismatches go unflagged and are scored
  normally -- it does not cause wrong blocks. On that day it accounted for
  24 of one profile's 42 re-score Skips (12 with no other blocker); a
  review list of those went to the owner. Revisit if a relabeling pass
  (below) moves precision back under the bar.
- No fresh investigation has started on `years_experience`/`degree`'s
  clean-baseline failure mode (item 1 above) -- the `direction` split is
  real and verified, but does not explain the bulk of the remaining gap.
- No holdout relabeling pass has been done (item 2 above) -- only one
  mislabel was caught incidentally.
- Re-run `eval_hard_blocker.py` after any further prompt or schema
  change to `evaluate_recruiter.md`'s hard-blocker instructions, same
  discipline as `eval_role_track.py` -- and confirm `resume doctor`'s
  Python-packages/API-key checks pass first, since a bad key produces
  misleading mixed-model numbers that look like partial progress (see
  the second fix attempt's own measurement note).
