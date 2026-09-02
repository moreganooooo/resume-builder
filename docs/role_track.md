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

### Current state (as of this doc)

- **134/134 rows labeled** (completed 2026-09-01).
- `role_track` predictions are **not yet computed for any job** — the
  field postdates the last full evaluation pass, so 0 of the (then)
  2,510 jobs in `data.db` carried a `role_track` value at all. There is
  currently nothing to compare the hand labels against.
- The 134 labeled jobs' full source text was preserved separately in
  `profiles/<profile>/role_track_holdout_source.json` (job_id → title/
  company/raw_text) ahead of a 2026-09-01 pipeline wipe, specifically so
  the labeling work stays usable once fresh evaluations exist to compare
  against.

## What's still unbuilt

There is **no script that computes precision/accuracy of the model's
`role_track` predictions against the hand labels**. `status()` only
cross-tabs stratum vs. label — it has no column for what the model
actually predicted, by design (the holdout stays blind). Building that
comparison is the natural next step once a fresh batch of evaluations
exists (see `role_track_holdout_source.json` above): re-run those 134
preserved postings through `evaluate_capability`, join predictions
against the hand labels by `job_id`, and report precision per stratum —
especially on the excluded class, against the design's ≥90% bar. Only
past that measurement should `role_track` be considered for graduation
from display-only to any kind of opt-in filter.
