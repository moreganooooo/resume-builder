# IC vs. Manager (`role_track`): how it works today

Status as of 2026-09-01: a **display/sort facet, not a gate or filter**.
No posting is ever hidden, excluded, or scored differently based on
`role_track` today. It exists so the Jobs detail pane can flag "this is
a people-manager role" for your own read, and so a future filter has a
measured accuracy bar to clear before it's allowed to hide anything.

## Why title keywords aren't used to classify

The original approach — flag any posting with "Manager"/"Director"/"Lead"
etc. in the title — was tested and rejected. Measured over this profile's
corpus: 49% of titles contain a manager-signal word, but a hand-checked
sample of 49 postings whose *only* signal was the title contained **zero**
actual people managers. In marketing and operations roles, "Manager"
usually denotes scope of ownership ("Marketing Manager"), not headcount.
Title carries no usable signal on its own.

## How a posting actually gets classified

Classification is an LLM judgment call, made once per evaluation, inside
`evaluate_capability.md` (the same prompt that produces `capability_gaps`
and `stretch_evidence`). The instruction given to the model:

> Judge ONLY by stated responsibilities and direct reports, **never** by
> the word "Manager" in the title... Return `unknown` whenever the
> posting never says who reports to whom — that is the correct, expected
> answer for roughly two of every five postings, not a failure to
> classify. A role that says direct reports will come *later* ("no
> reports initially," "you will build the team over time") is `manager`,
> not `ic` — a management role that hasn't started is still a management
> role.

There is deliberately no fixed phrase list driving the actual verdict —
the model reads the full posting body and decides based on evidence, the
same way `capability_gaps` and `stretch_evidence` work.

### Schema (`scripts/schemas.py` / `CapabilityEvaluationSchema`)

| Field | Values | Meaning |
|---|---|---|
| `role_track` | `"ic"`, `"manager"`, `"player_coach"`, `"unknown"` | The verdict |
| `role_track_confidence` | `"high"`, `"medium"`, `"low"` | How directly the text supports the verdict |
| `role_track_evidence` | free text, or `""` | The deciding quoted phrase from the posting; empty when there's no signal at all |

`unknown` is expected for ~40% of postings and is treated as a correct
answer, not a gap to fill with a title-derived guess — that guessing bias
is exactly what this design avoids.

## Where the verdict goes after evaluation

1. **`orchestrator.evaluate_fit()`** reads `role_track`/`_confidence`/`_evidence`
   off the model's response (defaulting to `"unknown"`/`"low"`/`""` if
   absent) and assembles them into the evaluation dict.
2. **`jd_manager.save_evaluation()`** — the project's allowlist writer for
   persisted evaluation metadata — copies all three fields onto the JD's
   `_evaluation` block on disk. A field not listed here is silently
   dropped, so this is the one place a future field addition must also
   touch.
3. **`dashboard/internal/model/job.go`**'s `Evaluation` struct carries
   `RoleTrack`, `RoleTrackConfidence`, `RoleTrackEvidence` (`json:"role_track"`
   etc.), fed by the same JSON export every dashboard screen reads.
4. **`dashboard/internal/ui/screens/jobs.go`**'s Jobs detail pane shows a
   "Role track" block **only** when `RoleTrack` is `"manager"` or
   `"player_coach"` — `"ic"` and `"unknown"` render nothing, since
   flagging the expected ~40%-unknown case on every row would read as a
   data problem it isn't. When shown, it displays a label ("Manager
   role" / "Player-coach role (manages and does the work)") plus the
   quoted `role_track_evidence`, if any.

Nothing here feeds `composite_score`, `fit_score`, `interview_odds_score`,
or any filter/exclusion logic. It is read-only information for you.

## The holdout: measuring whether it's even worth trusting

`scripts/build_role_track_holdout.py` draws a blind, stratified,
hand-labeled sample so the model's future accuracy can be measured
against real human judgment — an LLM field with no labeled holdout is a
filter that hides jobs for reasons nobody can audit, and the design's
own bar is **≥90% precision on the excluded class** before `role_track`
could ever gate anything.

### Sampling: two phrase lists, sampling-only, never used to score

These regexes decide which *stratum* a posting is sampled into — they
are not the classifier and never touch a real evaluation:

```python
# Title tokens that merely SUGGEST people leadership (decides sampling
# bucket only — a false positive here just costs a row in the harder band)
MANAGER_SIGNAL = re.compile(
    r"\b(manager|director|head of|vp|vice president|chief|lead|supervisor|principal)\b",
    re.I,
)

# Body-text phrases that genuinely indicate reports
REPORTS_EVIDENCE = re.compile(
    r"\b(direct reports?|manage a team|managing a team|people manager|"
    r"lead a team|leading a team|hire,? (?:train|develop)|"
    r"coach(?:ing)? and develop|team of \d+|mentor(?:ing)? and manag)",
    re.I,
)
```

Four strata result, sized by `--per-stratum` (default 40 each):

| Stratum | Title signal | Body signal | Expectation |
|---|---|---|---|
| `title+body` | yes | yes | should be easy — a miss here is alarming |
| `title-only` | yes | no | **the ambiguous band — most classifier errors live here** |
| `body-only` | no | yes | IC-sounding title, real reports described |
| `neither` | no | no | should be easy IC |

The sample is drawn from `profiles/<profile>/data.db`'s `jobs` table
(`raw_text`'s embedded `description`, HTML-stripped), and rows are
shuffled across strata before writing so a labeler can't infer a row's
stratum from its position and start pattern-matching instead of reading.
A posting needs both a title and ≥200 characters of body to be sampled
at all — nothing else to judge otherwise.

### Labeling

The holdout CSV (`profiles/<profile>/role_track_holdout.csv`, gitignored,
outside git, one per profile) has columns `job_id, title, company,
stratum, label, note, excerpt`. It is **blind by design** — no model
prediction appears anywhere in it. A labeler shown a guess agrees with
it, and a holdout that agrees with the model by construction measures
nothing.

Allowed `label` values: `ic`, `manager`, `unclear`, `n/a` (plus common
aliases like `na`, `individual contributor`, `people manager`,
`unsure`/`unknown` → `unclear`). `n/a` is a real, correct verdict for
postings with no IC/manager axis at all (e.g. an in-person retail
associate) — forcing those into `ic` would poison the ground truth.

Excerpts show the whole body for anything ≤6,000 characters
(`MAX_FULL_EXCERPT_CHARS`); longer bodies get a 3,000-character window
centered on the first `REPORTS_EVIDENCE` match (word-boundary aligned),
rather than a naive `body[:900]`, which was mostly "About us..."
boilerplate and starved labelers of real signal.

### CLI

```
python scripts/build_role_track_holdout.py                 # write a fresh holdout CSV
python scripts/build_role_track_holdout.py --status         # labeling progress + stratum cross-tab
python scripts/build_role_track_holdout.py --refresh-excerpts  # rewrite excerpts in place, keep labels/notes
python scripts/build_role_track_holdout.py --force           # overwrite, discarding existing labels
```

`--status` prints how many rows are labeled, a count per label value, and
a **stratum × label cross-tab** — the actual point of the tool, since a
pooled accuracy number would hide the one thing that matters: whether a
cheap stratum (like `neither`) already separates the classes cleanly,
and which band (`title-only`) the classifier actually has to earn its
score on.

### Current state (as of 2026-09-02)

- **134/134 rows labeled** (completed 2026-09-01).
- The 134 labeled jobs' full source text was preserved separately in
  `profiles/<profile>/role_track_holdout_source.json` (job_id → title/
  company/raw_text) ahead of a 2026-09-01 pipeline wipe, specifically so
  the labeling work stays usable once fresh evaluations exist to compare
  against.
- **The comparison described below as "still unbuilt" has since been
  built and run**: `scripts/eval_role_track.py` re-runs the real
  `evaluate_capability.md` prompt against each holdout row's preserved
  text and reports a confusion matrix + per-stratum precision/recall on
  the excluded class (`manager`/`player_coach`). It makes real, billable
  Gemini calls, so it's a manual/on-demand script, not part of CI.
  Usage: `python scripts/eval_role_track.py --profile morgan [--limit N]`.

### Measured result: 90.3% precision / 90.3% recall (2026-09-02)

This clears the design's own ≥90% precision bar on the excluded class.
Getting here took one holdout correction and two prompt experiments,
both of which failed — recorded below so neither is re-attempted without
new evidence.

**Holdout audit.** The first eval run scored 90.3% precision but only
87.5% recall, with 3 genuine-looking misses in the two single-signal
strata (`title-only`, `body-only`) — the model predicted `ic` on rows
hand-labeled `manager`. Before assuming the model was wrong, the full
raw posting text and the labeler's own `note` field were pulled for all
3 rows (there are only 3 `manager`-labeled single-signal rows in the
whole 134-row holdout, so this was exhaustive, not a sample):

- **2 of 3 (`body-only`, both "Revenue Strategy & Operations" @
  Anthropic — a role posted twice) were correct labels.** The note
  correctly invokes the prompt's own stated rule: the posting says "no
  direct reports initially... you will build the team over time," which
  the prompt explicitly defines as `manager`, not `ic`. These are real
  model misses (see below).
- **1 of 3 (`title-only`, "Partner Sales Manager, Systems Integrators" @
  Anthropic) was a mislabel, now corrected.** Its only manager-shaped
  language is "hold that partner accountable for the outcomes they
  own" — but the partners being held accountable are external partner
  companies (boutiques/regional Systems Integrators), not direct
  reports. There's no headcount, hiring, or performance-review language
  anywhere in the posting, and the role itself reports INTO "GTM
  Partnerships EMEA." It doesn't meet the prompt's own manager criteria.
  Relabeled `manager` → `ic` in `role_track_holdout.csv`, with the
  rationale appended to that row's `note` field.

Fixing the mislabel moved recall from 87.5% → 90.3% with precision
unchanged (90.3%), and fully resolved the `title-only` stratum's
apparent 0% recall — it turned out to have zero genuine misses once the
bad label was fixed.

**The one remaining genuine miss** (the two Anthropic "Revenue Strategy
& Operations" `body-only` rows, which are the same posting seen twice)
is a real model failure to apply the prompt's own explicit
reports-come-later rule.

### What was tried and didn't work

The research question after the audit was whether this miss is
class-imbalance / low-confidence hedging (the model defaulting to the
majority class `ic` under uncertainty) or something else. It's not:

- **Repeatability test (temp=0.7, 8 calls) — the miss is deterministic,
  not noise.** All 8 calls returned `role_track: "ic"` at
  `role_track_confidence: "high"`, and all 8 correctly quoted "no direct
  reports initially" (or the equivalent surrounding phrase) as their
  `role_track_evidence` — i.e. the model isn't uncertain and isn't
  missing the trigger phrase. It reads the exact rule-triggering text,
  identifies it as the deciding evidence, and still concludes `ic`. This
  falsifies the majority-class-defaulting theory for this failure mode:
  it's a confident, repeatable misapplication of a known rule, not
  hedging under ambiguity.

- **Experiment 1 (rejected, not attempted): broad "Kamsa" four-dimension
  rubric.** Restructuring the whole `role_track` paragraph into a
  multi-dimension rubric was tried earlier in this project's history and
  made things worse — 87.5% precision / 87.5% recall, no recall gain,
  plus one new false positive. Not worth repeating without a
  fundamentally different structural idea.

- **Experiment 2 (tried 2026-09-02, null result): surgical hard-rule
  reinforcement.** Added one sentence to `evaluate_capability.md`'s
  `role_track` paragraph, immediately after the existing
  reports-come-later example: *"This is a hard rule, not a factor to
  weigh against other signals: if the phrase you are about to quote in
  `role_track_evidence` says or implies reports are coming later, your
  `role_track` MUST be `manager`. Quoting a 'no reports initially' style
  phrase as evidence for `ic` is always wrong — that phrase is manager
  evidence by definition, never ic evidence."* Repeatability-tested
  (temp=0.7, 8 calls) against the exact same miss both before and after:
  **8/8 → 8/8, zero change** — identical `ic` verdict, identical
  confidence, identical evidence quote. The prompt edit was reverted
  (`evaluate_capability.md` is back to its original wording; no net diff
  survives from this experiment). This is a stronger, more targeted
  version of the "make the rule more explicit" idea than the Kamsa
  rubric, and it still didn't move this specific case — the model isn't
  failing to find or understand the rule, it's failing to apply it
  consistently even when told to. A future fix attempt for this specific
  pattern likely needs new evidence (e.g. a larger sample of similar
  misses to look for a common structural cause) rather than another
  prompt-wording iteration.

Given the corpus now scores 90.3%/90.3% against a design bar of ≥90%,
with the one remaining known gap being a single, prompt-immune edge
case, `role_track` graduation to any kind of opt-in filter should treat
this as evidence the design bar is met, not as a reason to hold off
pending a fix for the one remaining miss.

### The high-confidence gate: all 3 false positives are already high-confidence

Before shipping any opt-in filter, the natural follow-up question is
whether gating on `role_track_confidence == "high"` (on top of the
verdict) improves precision further. `eval_role_track.py`'s
per-confidence breakdown already existed in the script (nothing new to
build) — it just hadn't been run and read. It has now:

```
Per confidence level (scoreable rows only):
  high     precision= 90.3%  recall= 90.3%  n=90
  medium   precision=  nan%  recall=  nan%  n=3
```

(`low` confidence never appears here — of the 2 `low`-confidence
predictions in the full 134-row run, both were `role_track: "unknown"`
on `unclear`-labeled rows, so neither is scoreable.)

**All 31 manager/player_coach predictions — the 28 true positives and
all 3 false positives — were made at `high` confidence.** None of the 3
false positives are `medium` or `low`. That means the high-confidence
gate is a no-op on this holdout: precision at the gate is 90.3%,
identical to the ungated number, because there was nothing at a lower
confidence to filter out. This lands on the "all high confidence" row
of the scenario table above — the floor of the range, not an
improvement, but still clearing the ≥90% bar with nothing left on the
table to gain from confidence-gating alone.

The 3 false positives, for the record:

| Posting | Predicted | Label |
|---|---|---|
| "Influencer Marketing Lead" @ Aftershoot | manager (high) | ic |
| "Marketing Automation SaaS + Services Line of Business Owner" @ New Law Business Model | manager (high) | ic |
| "Sr. Customer Success Executive" @ Lumahealth | manager (high) | ic |

None of these three were investigated further (unlike the one known
false negative above) — three isolated postings with no shared
structural pattern, versus the Anthropic case's clean 8/8 repeatability
signal, don't justify the same depth of investigation for a metric
that already clears its bar.

## Where this landed: opt-in Jobs-screen view filter (2026-09-02)

`role_track` graduated to an opt-in, default-OFF **view filter** on the
Jobs screen — deliberately not a scan-time or database gate. The
distinction matters given the one known false negative above: a
scan-time filter would permanently drop a posting like the Anthropic
"build the team over time" case from the corpus, with no way to recover
it once the classifier missed it. A view filter can't do that — every
posting is still scanned, evaluated, and saved to `data.db` exactly as
before, regardless of `role_track`. The filter only narrows what the
Jobs list *displays*, and toggling it off always shows everything
again, including postings the classifier missed or scored low-confidence.

- **Gate**: `model.JobRow.IsManagerTrack()` — `role_track` is `manager`
  OR `player_coach` (a player-coach still manages people, and is
  scored as part of the same excluded class by
  `eval_role_track.py`'s `MANAGER_VERDICTS`), AND
  `role_track_confidence == "high"`.
- **Control**: the `[r]` key on the Jobs screen (`JobsModel.roleTrackFilter`,
  `dashboard/internal/ui/screens/jobs.go`) — same shape as the existing
  `[w]`/`[e]`/`[$]` view filters on that screen, but a single boolean
  rather than a multi-value cycle, since the measured ≥90% precision bar
  only covers the combined manager/player_coach class at high confidence
  specifically — there's no other value worth exposing as a filter
  option.
- **Default**: off. Nothing changes for a user who never presses `[r]`.

## What's still unbuilt

Nothing structural — the precision/recall comparison against hand
labels, the confidence-level breakdown, and the opt-in filter itself are
all built and have been run/shipped. What's left is process, not code:
re-running `eval_role_track.py` periodically as the prompt or holdout
changes, and expanding the holdout past 134 rows if the filter's
observed real-world miss rate ever suggests the current confidence
interval is too wide to trust.
