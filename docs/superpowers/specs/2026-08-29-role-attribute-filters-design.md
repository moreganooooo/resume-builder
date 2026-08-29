# Role Attribute Filters: Employment Type, Compensation, and IC vs. Manager

Date: 2026-08-29
Status: Design — not yet implemented
Revision: 2 (v1 was written before the corpus was measured; §"What the
corpus says" invalidated its central design choice. See "What changed
and why" at the end.)

## Problem

`scan_filters.yml` can express **where** a role is (`location:` block,
radius, `workplace_mode`) but not three attributes that are just as
disqualifying:

1. **Employment type** — full-time vs. part-time vs. contract /
   contract-to-hire / temp / internship.
2. **Compensation** — pay rate or salary band and its period.
   `scripts/prefilter.py` has a `salary_floor` deal-breaker, but it runs
   on JD body prose at batch-sweep time, which is the wrong stage: the
   posting is already on disk, evaluated, and counted in the backlog.
   Nothing reads the structured salary fields providers publish.
3. **Role track** — individual contributor vs. managerial /
   people-facing. `title_filter.negative` is the current instrument
   (`Director of`, `VP `, `Chief `), which is a user-owned string
   blocklist, not a classification.

## What the corpus says

Measured 2026-08-29 over `profiles/morgan/data.db`: 2,510 job rows,
1,612 descriptions longer than 600 characters. **These numbers are the
reason this design looks the way it does** — every structural decision
below traces to one of them.

| Signal | Coverage | Note |
| --- | --- | --- |
| Structured `employment_type` in metadata | 433 / 2,510 (**17%**) | jobright ONLY |
| Structured `seniority_level` | 433 (17%) | jobright only |
| Salary `$` pattern in description prose | 554 / 1,612 (**34%**) | |
| Strong manager evidence in body | 56 (**3.5%**) | `N direct reports`, `manage a team` |
| Strong IC evidence in body | 100 (**6.2%**) | `individual contributor`, `no direct reports` |
| Either (both: 20) | 136 (**8.4%**) | |
| **Neither** | **1,476 (91.6%)** | |
| Manager-ish *title* token | 1,070 / 2,159 (49.6%) | high coverage, low precision |

Two findings drive everything:

**(a) A deterministic role-track classifier is not viable.** Body
evidence covers 8.4% of postings. The obvious fallback — title tokens —
has 88.5% coverage and **near-zero precision** on this profile's own
corpus. Real titles from the data, all of them IC roles:

```
Marketing Manager · Lifecycle Marketing Manager · Digital Marketing Manager
Marketing Automation Manager · Global Campaign Manager
Sr. Strategy & Operations Manager · Development Operations Manager
```

In marketing, "Manager" denotes scope, not reports. A title-based
classifier would not be low-coverage; it would be **confidently wrong**,
which is strictly worse than `UNKNOWN`. (`title_filter.negative` gets
away with the same tokens only because it is an explicit user blocklist
that never claims to classify.)

**(b) Employment type is multi-valued.** Observed values include
`"Full-time, Contract"`, `"Part-time, Contract"`, `"Full-time,
Part-time"`. It is a set, not a scalar.

Also confirmed by reading the providers: `greenhouse.mjs` and
`ashby.mjs` map API responses to a fixed six-field shape (`title`,
`url`, `description`, `location`, `posted_at`, `id`) and **discard**
`employmentType`, `compensation`, and `pay_input_ranges` — fields
already fetched over the wire. That is free coverage being thrown away.

## Architecture: two stages, not one gate

v1 of this spec put all three filters in
`scan_boards._passes_location_filter()`, reasoning from the location
system's one-chokepoint rule. That reasoning was wrong: location is
*knowable at scan time* from a provider field. These attributes largely
are not. Forcing them into the scan gate is what produced a design that
returns `UNKNOWN` for 92% of roles.

### Stage 1 — Scan gate: structured fields only, exclusion-only

Deterministic, free, no LLM. Reads **only** structured provider fields,
never prose. Rejects a posting only when a field is **present and
definitive** (`employmentType: "Intern"` against `employment_type:
[full_time]`). Absent field → passes, always. High precision, low
coverage, zero guessing.

This still lives in `scan_boards._passes_location_filter()` (renamed
`_passes_posting_filters()`, with the old name kept as an alias since
`scan_ats.py` and tests import it) — the chokepoint rule holds, the
scope of what it decides narrows.

### Stage 2 — Evaluation: LLM classification, zero marginal API cost

**This is the load-bearing change.** `evaluate_fit.md` →
`FitEvaluationSchema` already sends every JD's full text to Gemini and
parses structured output back. Adding attribute fields to that schema
costs **no additional API call** — the JD is already in the prompt, the
call already happens, only a few dozen output tokens are added.

A model reading the whole posting resolves "Marketing Manager — owns the
lifecycle email program, no direct reports" correctly. No regex will.
This is the difference between 8.4% and near-total coverage, and it is
already funded.

Extend `PracticalPursueSubscores`' sibling structures with:

```python
class RoleAttributes(BaseModel):
    employment_types: List[Literal[
        "full_time","part_time","contract","contract_to_hire",
        "temporary","internship","unknown"]] = Field(
        description="All employment types the posting offers; "
                    "['unknown'] when the posting does not say")
    role_track: Literal["ic","manager","player_coach","unknown"] = Field(
        description="IC vs. people-manager. 'player_coach' when the role "
                    "both manages people and does the work. Judge by stated "
                    "responsibilities and direct reports, NEVER by the word "
                    "'Manager' in the title -- in marketing and operations "
                    "that word denotes scope, not reports.")
    role_track_confidence: Literal["high","medium","low"]
    role_track_evidence: str = Field(
        description="The phrase from the posting that decided it; "
                    "empty when the posting gives no signal")
    salary_min: float | None
    salary_max: float | None
    salary_period: Literal["annual","hourly","unknown"]
    salary_is_estimated: bool
```

`role_track_evidence` is not decoration. The user will disagree with
this classifier sometimes, and an unexplained verdict is not
correctable. It is also how the holdout labeling below gets done
cheaply.

The negative instruction in `role_track`'s description is written
directly from finding (a) — the model has the same title bias the regex
did, and must be told.

### Stage 3 — UI: filter and sort on the stored attributes

Display and selection only. No new API calls, no reclassification.

## Validation before enforcement

The two practices that make this production-grade rather than plausible,
both absent from v1:

### A labeled holdout and a stated accuracy bar

Hand-label ~100 JDs sampled across platforms for role track and
employment type (`role_track_evidence` makes this fast — you are
confirming or rejecting a quoted phrase, not reading a full posting).
Store as `fixtures/role_attribute_holdout.jsonl`, and assert against it
in `tests/test_role_attribute_accuracy.py`, skipped by default and run
deliberately (it needs `RESUME_ALLOW_TEST_NETWORK=1`, so it cannot fire
during a normal suite run — same escape hatch as `test_gemini_client`).

**The bar, per attribute:** a filter may not **hard-exclude** on an
attribute until it clears **≥90% precision on the excluded class**. The
asymmetry is deliberate and is the whole point: a false exclude is
invisible and permanent — the role never appears and you never learn it
existed. A false include costs five seconds of scrolling. Below the bar,
an attribute may sort, display, and de-prioritize, but not drop.

Realistic expectation from the measurement: employment type will clear
this comfortably; role track may not, and **role track may correctly
remain a display/sort facet forever**. That is a successful outcome, not
a failed one. At 90% accuracy role track is genuinely useful as a
sortable column; as an auto-reject it would need ~98%, and nothing in
the data suggests it will get there.

### Shadow mode before enforcement

Every filter ships **report-only** first. `enforce: false` (the default
on introduction) logs what would have been rejected to
`data/<profile>/filter_shadow.jsonl` and rejects nothing. Review a
week's worth, then flip `enforce: true`.

You already learned this lesson expensively: adzuna silently defeated
the radius filter by reporting "Buffalo, Erie County" and landing in the
permissive bucket, and workday silently wrote 28 empty JDs that
`job_key_known()` then made permanent. **A filter's failures are
invisible by construction** — a rejected posting leaves no trace unless
one is deliberately written. Shadow mode is that trace.

## Config

```yaml
employment:
  enforce: false                        # shadow mode until reviewed
  employment_type: [full_time, contract]

compensation:
  enforce: false
  annual_floor: 65000
  hourly_floor: 32
  require_stated: false                 # MUST default false
  # Compare against the posting's MAX, never its min: a $60-95K band
  # clears a $70K floor and is worth seeing. Rejecting on min drops
  # every wide range. (prefilter.py already compares max_val -- preserve
  # that when the check moves upstream.)

role_track:
  enforce: false                        # expected to STAY false
  track: [ic]
  allow_player_coach: true
```

Absent block = no filtering, exactly today's behavior. Inert until
configured, like the `location:` block.

## Design principles (carried from the location work)

Unchanged and all still binding:

- **Unknown is kept, never rejected.** Unresolvable location is kept for
  review; likewise unstated pay, unknown employment type, unknown track.
  Given 91.6% unknown role track, this rule is not a nicety here — it is
  the only thing making the feature safe to ship.
- **Unknown is `None`, never `0`.** `salary_min`/`salary_max` follow
  `distance_miles` into Go `*float64`, so unstated pay cannot sort as $0.
- **A verdict says why, not just whether** — `passes`, the
  classification, the measurement, a `reason`.
- **Single or list** in config, as `workplace_mode` accepts both.
- **One chokepoint** for the scan-time half.

## Provider field recovery (do this first — it is free)

Widen each provider's normalized shape to carry through what it already
receives. Verify each against a live response; the adzuna lesson is that
an unparsed field defeats a filter *quietly*.

| Provider | Fields to stop discarding |
| --- | --- |
| ashby | `employmentType`, `compensation` |
| greenhouse | `metadata`, `pay_input_ranges` |
| lever | `categories.commitment` |
| workable | listing `type`, `salary` |
| indeed (JobSpy) | `job_type`, `min_amount`, `max_amount`, `interval`, `currency` |
| jobright | `employment_type`, `seniority_level` (**already captured** — 433 rows) |

`salary_is_estimated` matters: Indeed publishes *estimated* ranges
beside employer-stated ones. An estimate must never hard-reject — mark
it, show it, let the user judge. Only employer-stated compensation
gates.

## Persistence, export, model

Follows the JD-JSON metadata convention: a new `_attributes` key on the
JD's own JSON with `jd_manager.save_attributes()` / `read_attributes()`.
Underscore-prefixed, so `read_jd_text()` already strips it before any
prompt — no leak risk, no new mechanism.

```json
"_attributes": {
  "employment_types": ["full_time"],
  "compensation": {"min": 85000, "max": 110000, "period": "annual",
                   "currency": "USD", "is_estimated": false},
  "role_track": {"track": "ic", "confidence": "high",
                 "evidence": "no direct reports"},
  "_source": "evaluation"
}
```

`_source` (`"provider"` | `"evaluation"`) records which stage produced
the value, mirroring `_research_source` on company research. A provider's
structured field outranks the model's reading and must not be silently
overwritten by a later re-evaluation.

Export via `picker._attribute_fields()`, a sibling of
`_location_fields()`, called from the same two sites in
`list_all_evaluated_jds()` and `_database_only_rows()`.

**Hard requirement:** every new export key needs a matching
`model.JobRow` field **in the same change**. A key with no Go
counterpart fails `encoding/json` for the whole document and `LoadJobs`
returns zero rows — this silently emptied the Jobs screen once already
(the `skills` bug). Both sides or neither.

```go
EmploymentTypes []string `json:"employment_types"`
SalaryMin       *float64 `json:"salary_min"`   // pointer: unstated != $0
SalaryMax       *float64 `json:"salary_max"`
SalaryPeriod    string   `json:"salary_period"`
SalaryEstimated bool     `json:"salary_estimated"`
RoleTrack       string   `json:"role_track"`
RoleTrackConf   string   `json:"role_track_confidence"`
```

Plus value constants mirroring Python (as `WorkplaceRemote` does) and
`HasSalary()` / `Salary()` accessors matching `HasDistance()` / `Miles()`.

## UI

**Browse & Manage Jobs** (`screens/jobs.go`) — follow the `[w]`
workplace filter exactly (`workplaceFilter` field, `nextWorkplaceFilter`
cycle, `workplaceFilterLabel` status chip): `[e]` employment type, `[t]`
role track, `[$]` salary floor. New sort "Salary (high→low)" with
unstated **last**, which the `*float64` makes enforceable. Render
nothing for an unknown rather than a misleading placeholder; show a
low-confidence role track dimmed or parenthesized, never as fact.

**Pipeline** — `data.JobRowsToApplications` carries the fields through;
Pipeline and Jobs share one source and `reloadPipelineDataCmd` must read
that same source or a mid-session refresh silently reverts the screen.

**Elsewhere** — `picker.py`'s interactive picker shows chips in choice
labels. The CLI banner stays on `picker.count_active_roles()`: these are
display/selection concerns and must not introduce a fifth definition of
"how many roles do I have."

**Settings** — `scripts/role_filter_settings.py`, same shape as
`location_settings.py` (`read_settings`, `render_block`,
`write_settings`, `clear_settings`, `describe`, `run_*`), writing the
same `scan_filters.yml`. Every prompt through
`cli_art.confirm/select/checkbox/text()` — never raw `questionary`,
which renders nothing under `menu._run_with_chain()`'s DECSTBM scroll
region.

## Backfill

2,130 rows already carry an `_evaluation` produced without these fields.
Do **not** re-evaluate the corpus wholesale. New evaluations get the
fields free; backfill only what you would act on — pending and evaluated
non-terminal rows — and gate it behind an explicit
`--max-jobs N` cap, as `refresh_verified_ledger.py` caps chunks. jobright
rows (433) can be backfilled with **no API call at all** from their
existing `employment_type` / `seniority_level` metadata; do that pass
first and measure what remains.

## Testing

`profile_paths.isolate_for_tests(tmpdir)` for anything touching a
profile — all four roots, never just `PROFILES_DIR`. `tests/persona.py`
for identity. The `gemini_client._get_auth_headers()` guard fails closed,
so unit tests mock the model and assert on schema handling; the holdout
accuracy test is the one deliberate opt-in.

New: `test_employment_filter.py`, `test_compensation_filter.py`,
`test_role_attributes_schema.py`, `test_role_filter_settings.py`,
`test_role_attribute_accuracy.py` (opt-in), cases in
`test_scan_boards.py` proving the gate covers `scan_ats.py`, and Go
tests in `jobs_test.go` / `jobs_to_apps_test.go` for the filter cycles
and the unstated-sorts-last rule.

## Sequencing

Ordered by value per unit of risk, not by module:

1. **Provider field recovery** — free, no new concepts, immediately
   raises structured coverage above today's 17%.
2. **Schema + evaluation fields** — the unlock. Near-total coverage at
   zero marginal API cost.
3. **jobright metadata backfill** — 433 rows, no API calls.
4. **Employment type**: config, scan gate, shadow mode, UI.
5. **Compensation**, folding `prefilter.py`'s salary branch into one
   parser so the two cannot drift. Keep prefilter as the downstream
   prose safety net, the same relation it has to the location gate.
6. **Holdout labeling and the accuracy gate.** Before any `enforce:
   true`.
7. **Role track** — display and sort only. Promote to a hard filter only
   if it clears the bar, and accept that it may not.

## What changed and why (v1 → v2)

Recorded so the reasoning is not lost:

- v1 specced `role_track_filter.py` as a deterministic body-evidence
  classifier with title tie-breakers. **Measurement killed it**: 8.4%
  body coverage, and the title fallback is confidently wrong on this
  profile's own roles. Replaced by an LLM field on an existing call.
- v1 put all three filters in the scan gate on the strength of the
  one-chokepoint rule. That rule was generalized past its warrant —
  location is knowable at scan time, these largely are not. Split into
  scan-time (structured, exclusion-only) and evaluation-time (LLM).
- v1 treated `employment_type` as a scalar. The data has
  `"Full-time, Contract"`. It is a set.
- v1 had no validation story. Added a labeled holdout, an explicit
  asymmetric precision bar for hard exclusion, and shadow mode — because
  a filter's false negatives are invisible unless deliberately logged.
- v1 said "measure the corpus first" as step 1. That measurement is now
  done and is recorded above rather than deferred.
