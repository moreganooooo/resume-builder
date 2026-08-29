# Role Attribute Filters: Employment Type, Compensation, and IC vs. Manager

Date: 2026-08-29
Status: Design — not yet implemented
Revision: 4 (v1 was written before the corpus was measured; §"What the
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

### Stage 3 — Rescore: turn criteria into a preference gradient

Filtering alone only prevents wrong roles from appearing. It does
nothing to make a *right* role rank first — and ranking is what the user
actually experiences.

Today the only attribute lever is binary: `hard_blockers` forces
`composite_score = 0.00`, and otherwise attributes are invisible to
scoring. There is no way to express "this is exactly what I want."

**The precedent already exists.** `rescore_evaluation_with_location()`
(orchestrator.py:1758) takes the model's guessed `remote_quality` and
**replaces it with a deterministic calibration from the measured
distance** via `calibrate_commute_quality()` — 5.0 at walking distance,
grading to 3.0 at the radius edge. A measured fact overrides a guess,
and the result is graded rather than binary. That is precisely the
pattern these attributes need, and it is already written.

`compensation_viability` carries weight **0.15** and its schema
description is "vs. stated target/floor, or likely range if unstated" —
the model guessing against a floor it was never given. Once a real range
is parsed and a real floor is configured, that guess is replaceable with
arithmetic.

Add `rescore_evaluation_with_attributes()`, a sibling of the location
rescore, and calibrate **existing** subscores:

| Subscore | Deterministic input |
| --- | --- |
| `compensation_viability` | parsed range vs. configured floor — well above → 5.0, at floor → ~3.0, below → blocker |
| `time_to_offer` | contract/temp typically resolve faster than FTE |
| `remote_quality` | *(already calibrated from distance)* |

**Calibrate existing subscores; do not add new ones.**
`PRACTICAL_PURSUE_WEIGHTS` sums to exactly 1.00. A new subscore forces
redistributing all seven weights, which silently re-ranks all 2,130
existing evaluations for a reason unrelated to any of them.
Recalibrating an existing subscore leaves the weights — and therefore
comparability — intact.

Compare against the range **max**, consistent with the filter rule and
with `prefilter.py`'s existing `max_val` comparison.

#### Score drift is a real cost, and it is currently unmanaged

Any recalibration makes recalibrated and legacy evaluations
non-comparable while they sit in one ranked list. **The location rescore
already has this problem silently** — there is no `scoring_version`
anywhere in `scripts/`.

Introduce `_evaluation["scoring_version"]`, bump it when weights or
calibrations change, and make the UI able to say a row was scored under
an older version. Then either backfill or display the mixture honestly.
Do not ship a second drift source on top of an unlabeled first one.

### Stage 4 — UI: filter and sort on the stored attributes

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
receives. **Measured live 2026-08-29**, not assumed — the adzuna lesson
is that an unparsed field defeats a filter *quietly*:

| Provider | Employment type | Salary | Sample |
| --- | --- | --- | --- |
| **ashby** | `employmentType` **100%** | `compensation` **49%** | 410 postings, 4 boards |
| **lever** | `categories.commitment` **96%** | `salaryRange` **61%** | 70 postings |
| **greenhouse** | **NONE** | **NONE structured** | 909 postings, 3 boards |
| jobright | `employment_type` 100% | — | already captured, 433 rows |
| workable | listing `type`, `salary` | — | not yet measured |
| indeed (JobSpy) | `job_type` | `min_amount`/`max_amount`/`interval` | not yet measured |

**Correction to v2 of this spec:** it claimed greenhouse exposes
`metadata` and `pay_input_ranges`. It does not. The public boards-api
returns **no** `pay_input_ranges` field on any of 909 postings, and
`metadata` is employer-defined free-form (Airbnb's is "Is this job part
of ACC?"). Greenhouse is the **largest ATS source in the corpus (453
rows)** and has zero structured coverage for both attributes. It depends
entirely on Stage 2.

Ashby's URL **already contains `includeCompensation=true`** and the
response is discarded at normalization — free data already paid for over
the wire.

### Provider value nuances

- **Normalization differs per provider.** Ashby is PascalCase with no
  separator (`FullTime`, `Intern`, `Contract`, `Temporary`); lever is
  hyphenated title case (`Full-time`, `Contract`, **`Fixed Term`** — a
  type this spec did not enumerate); jobright is comma-joined multi-value
  (`"Full-time, Contract"`). Normalize at the provider boundary, never
  downstream, so one vocabulary reaches the filter.
- **`shouldDisplayCompensationOnJobPostings`** (ashby) is a boolean the
  employer sets. Compensation data can be present while the employer has
  chosen not to display it. Honoring it or not is a deliberate call to
  make once and write down — not something to decide by accident.
- **10% of ashby postings carry multiple `compensationTiers`** — the
  range varies by geographic tier. "The salary" is not one number; it is
  a function of location, which interacts directly with the location
  filter. Pick the tier matching the user's resolved location where one
  matches, else the widest range, and record which.
- `salary_is_estimated`: Indeed publishes *estimated* ranges beside
  employer-stated ones. An estimate must never hard-reject — mark it,
  show it, let the user judge. Only employer-stated compensation gates.

## Coverage is uneven BY EMPLOYER, and that biases enforcement

The most consequential limitation, and it is not fixable by better
parsing.

Greenhouse salary-in-prose coverage, measured per board:

| Board | Postings with a $ range |
| --- | --- |
| Stripe | 16 / 575 (**2.8%**) |
| Figma | 96 / 163 (**58.9%**) |
| Airbnb | 115 / 171 (**67.3%**) |

Coverage is determined by **employer pay-transparency practice**, not by
provider or by parser quality. A twenty-fold spread inside one provider.

The consequence is systemic. With `require_stated: false` — the safe
default, required by the unknown-is-kept rule — an unstated salary always
passes. So enforcing a floor does not filter neutrally: it judges only
the postings that **disclose**. Ashby and lever roles get evaluated;
greenhouse and Stripe roles pass unexamined. Turning on a $65K floor does
not yield "roles above $65K." It yields *"roles above $65K, plus every
role from employers who do not disclose."* The visible corpus quietly
re-weights toward non-disclosing employers, and nothing in the UI says so.

**The reframe: unknown is not a coverage gap to be closed. It is a
routing decision.** Treating it as a gap leads to over-trusting weak
parsers to shrink it. Treating it as routing means:

- Unknown-attribute roles are a **named bucket**, not silent passers.
- The UI reports the split — "38 of 170 roles state no pay" — so the
  user knows what the filter did and did not see.
- A filter's status line shows coverage alongside the filter:
  `$65K+ · 112 judged · 38 unstated`. A filter that cannot say how much
  it examined is asserting more than it knows.
- Sorting keeps them separate rather than interleaving unknowns into a
  ranked list as though they had passed a test they were never given.

This also gives the shadow-mode review something concrete to check: if
the rejected set skews to one provider, that is provider bias, not
selectivity.

## Provider survey: all 34, measured

`scripts/probe_provider_fields.py` measures this and is committed
alongside the spec — it is re-runnable, seeded for reproducibility, and
samples ATS boards using REAL slugs from `tracked_companies.yml` (a
guessed slug 404s, or on SmartRecruiters returns 200 with an empty list,
and reads identically to "provider publishes nothing").

### The central finding: employment type is a provider property, salary is an employer property

Measured across 24 boards per provider (575 greenhouse / 390 ashby /
79 lever postings), reported as min / median / max **across boards**:

| Provider | Employment type | Salary |
| --- | --- | --- |
| greenhouse | **0 / 0 / 0%** | 0 / 80 / 100% (pooled 63%) |
| lever | **94 / 100 / 100%** | 0 / 0 / 100% (pooled 29%) |
| ashby | **100 / 100 / 100%** | 0 / 68 / 100% (pooled 41%) |

Employment type has **near-zero variance across boards**. It is a
property of the provider's schema, a provider-level number means
something, and Stage 1 can gate on it with confidence.

Salary spans **the full 0–100% range on every single provider**.
It is a property of the *employer's* disclosure practice. Therefore:

> **No provider-level salary coverage number is meaningful.** Any such
> figure is sampling noise presented as a fact.

This retroactively invalidates the salary column in v2/v3/v4's provider
tables ("ashby 49%", "lever 61%"). Those came from four randomly drawn
boards; consecutive runs of the same probe produced greenhouse 37% then
70%, ashby 68% then 100%, lever 53% then 18%. Nothing changed but the
sample.

**The design consequence is concrete:** Stage 1 may gate on employment
type per provider. Stage 1 must **never** gate on salary using a
provider-level expectation, and the UI must report salary coverage from
what a given scan actually observed — the `112 judged · 38 unstated`
line — rather than from any predicted rate.

### Full results

**Structured, reliable (Stage 1 can gate on employment type):**

| Provider | Employment field | Coverage | Salary field |
| --- | --- | --- | --- |
| ashby | `employmentType` | 100% | `compensation` |
| lever | `categories.commitment` | 98% | `salaryRange` |
| jobicy | `jobType` | 100% | `annualSalaryMin` |
| himalayas | `employmentType` | 100% | `minSalary`/`maxSalary` |
| remotive | `job_type` | 100% | `salary` (free text) |
| smartrecruiters | `typeOfEmployment.label` | 84% | none observed |
| workable | markdown `Type` column | 69% | `Salary` column |
| jobright | `employment_type` | 100% | none |

**No structured employment field — depends entirely on Stage 2:**
greenhouse (**0% on every board**, the largest ATS source at 453 rows),
remoteok, workingnomads, fourdayweek, themuse.

**RSS-backed** (`_rss.mjs`) — no structured fields are possible by
construction; only prose mentions: weworkremotely (100% prose mention),
authenticjobs (100%), jobspresso (30%), realworkfromanywhere (12%),
nodesk (0%).

**Needs attention — returned zero items:** `crunchboard` and
`powertofly` both parsed **0 postings**. Either the feed format changed
or the boards are dead. Worth checking independently of this feature;
a provider silently contributing nothing is the quiet failure mode this
whole spec is about.

**Not measurable by this script** (recorded explicitly so "unmeasured"
never reads as "measured and empty"): adzuna, jooble, usajobs
(API keys); otta, wellfound (authenticated sessions); levelsfyi (blocks
non-browser clients); ycombinator (Algolia endpoint needs POST, probe
uses GET); workday (per-tenant POST API — probe separately); hackernews
and remote_curated (free text and a link list, no fields by
construction); linkedin and indeed (Python sources).

### Vocabulary: not an enum, and unbounded

Observed values across providers:

| Provider | Observed |
| --- | --- |
| ashby | `FullTime`, `Intern`, `Contract`, `Temporary` |
| lever | `Full-time`, `Full-Time`, `Full Time / On Site`, `Full Time - Union`, `Full Time - Non-Union`, `Internship`, `Fixed Term` |
| jobright | `Full-time, Contract` (comma-joined multi-value) |
| jobicy | `['Full-Time']` (list-wrapped) |
| himalayas | `Full Time` |
| remotive | `full_time`, `freelance` |
| workable | `Full-time`, `Contract` |

**Lever's `commitment` is employer-authored free text, not an enum** —
`Full Time - Union`, `Full Time - Non-Union`, and `Full Time / On Site`
are things employers typed. Two consequences:

1. The value set is **unbounded**; no fixed mapping can be complete.
   `normalize_employment_type()` must match on substrings against a
   normalized form, not on equality, and must **log the provider and the
   unmapped value** so a new variant announces itself rather than
   silently becoming `unknown` and passing the filter.
2. `Full Time / On Site` **carries workplace mode inside the employment
   field**. Parsing it as employment type alone discards a location
   signal; worse, feeding the whole string to a workplace classifier
   could mis-set it. Split on separators and route each token to the
   right classifier.

### Two bugs the probe found in existing code

- **`workable.mjs` indexes its markdown table from the left.** A real
  posting on `panorama-education` has a pipe inside the title
  (`AI Solutions Consultant, Special Education | 1099 Consultant`),
  which shifts every column: `Type` reads the location, `Salary` reads
  the type. The probe hit this and now parses **from the right**
  (`Details` is always last). The provider should do the same.
- **`themuse`'s `type` field is not an employment type.** It reports
  `"external"` — the posting kind. An unvalidated probe recorded it as
  100% employment coverage. A field that is present and irrelevant is
  more dangerous than a missing one, because coverage metrics look
  healthy while the filter reads garbage.

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

### Settings menu: group, do not append

Settings & Upkeep already holds **eight** entries. Appending three more
("Employment Type", "Pay Floor", "Role Track") turns a menu into a list
and buries Location, which belongs with them.

Instead, **replace** the existing `manage_location` entry with one
grouped submenu — one entry out, one entry in, no net growth:

```
⚙ Settings & Upkeep
  ⌂ ↳ Role Criteria & Filters (14068 · 5mi · hybrid+remote · FT · $65K+)
      ⌂ ↳ Location & Commute Radius   (14068 -- 5 mi, hybrid+remote)
      ▤ ↳ Employment Type              (full-time, contract)
      ▤ ↳ Pay Floor                    ($65K/yr · reporting only)
      ▤ ↳ Role Track (IC vs. Manager)  (IC preferred · sort only)
```

These four answer one question — *what kind of role do I want?* — and
grouping them makes the whole criteria set legible at a glance, which
three flat siblings never would.

### Live-state labels are the existing pattern — keep it

`_location_filter_label()` (menu.py:230) calls
`location_settings.describe()` and renders the current config **inline in
the menu label**: `Location & Commute Radius (14068 -- 5 mi,
hybrid+remote)`. That is why the user can see their configuration
without opening anything.

Every new settings module must export `describe()` with the same
contract: one line, current state, and an explicit
`"not configured (keyword filtering only)"` when unset. The parent
"Role Criteria & Filters" label composes the children's summaries.

**Show enforcement state in the label.** During shadow mode the label
must say `reporting only` (as sketched above). A filter the user
believes is active but is not is a worse failure than no filter, and the
menu label is the cheapest possible place to prevent it.

### Dashboard key bindings — `[t]` is already taken

Measured against `screens/jobs.go`: bound keys are
`/ ? G J K L b d f g l m q s t u v w`. **`[t]` collides** (v2 proposed it
for role track).

Proposed, all verified free: **`[e]`** employment type, **`[c]`** career
track, **`[$]`** pay floor. Each follows the `[w]` workplace pattern
exactly — a `xFilter` string field, a `nextXFilter()` cycle, an
`xFilterLabel()` status chip — so the fourth filter reads like the three
before it and `?` help needs no new concepts.

New sort "Salary (high→low)", unstated **last**, which the `*float64`
makes enforceable rather than merely intended.

### Visual and theme constraints (each of these has bitten before)

- **New icons go in BOTH maps.** `scripts/theme.py` carries a Nerd Font
  set *and* a Unicode fallback (`RESUME_BUILDER_ICONS=unicode`). An icon
  added to one renders as a missing glyph for anyone on the other.
  Prefer reusing existing names — `location`, `evaluate`, `discovery`,
  `utility` — which sidesteps the problem entirely.
- **Mirror into Go.** `dashboard/internal/theme/icons.go` mirrors
  theme.py by name (`Location string // nf-fa-map_marker (theme.py's
  "location")`). Both sides or the dashboard diverges from the CLI.
- **Colors from `theme.go`'s own `c()` helper**, never
  `github.com/charmbracelet/lipgloss` v1. Both satisfy the interface at
  compile time; huh v2 silently renders a v1 color as `rgb(0,0,0)`.
  `resumebuilder.go` is **generated** by
  `scripts/sync_dashboard_theme.py` — fix the generator or `resume
  doctor` regenerates the bug. Extend `theme_test.go`'s
  `TestHuhThemeTitleIsNotBlack` list for any new theme variant.
- **Every prompt through `cli_art.confirm/select/checkbox/text()`** —
  never raw `questionary`, which renders nothing under
  `menu._run_with_chain()`'s DECSTBM scroll region and produces the
  "menu just hangs" bug.
- **Honor `RESUME_BUILDER_MOTION=reduced`** for any new chip transition
  or filter animation, and verify chips in both `dark` and `light`
  theme modes.
- **Chips must degrade to text.** A salary or track chip has to stay
  legible with Unicode fallback icons, no color, and a narrow terminal.
  Verify with `visual-tui` / `audit-tui` (see `dashboard/CLAUDE.md`)
  rather than by eye at one width.

### Rendering rules

- Render **nothing** for an unknown attribute — never a placeholder that
  reads as a measurement. This is the display half of the
  unknown-is-`None`-never-`0` rule.
- A **low-confidence** role track renders dimmed or parenthesized, never
  as fact. `role_track_confidence` exists precisely so the UI can be
  honest about how much it knows.
- The **coverage line** ships with the filter, not after:
  `$65K+ · 112 judged · 38 unstated`. Per the routing reframe above, a
  filter that cannot say how much it examined is asserting more than it
  knows.

**Pipeline** — `data.JobRowsToApplications` carries the fields through;
Pipeline and Jobs share one source and `reloadPipelineDataCmd` must read
that same source or a mid-session refresh silently reverts the screen.

**Elsewhere** — `picker.py`'s interactive picker shows the same chips in
its choice labels, so a role reads identically wherever it appears. The
CLI banner stays on `picker.count_active_roles()`: these are
display/selection concerns and must not introduce a fifth definition of
"how many roles do I have."

**Settings modules** — `scripts/role_filter_settings.py`, same shape as
`location_settings.py` (`read_settings`, `render_block`,
`write_settings`, `clear_settings`, `describe`, `run_*`), writing the
same `scan_filters.yml`.

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

1. **Provider field recovery (ashby + lever only)** — free, no new
   concepts. Ashby already fetches compensation and discards it.
   Greenhouse is measured to have nothing to recover; do not spend time
   there.
2. **`scoring_version` on evaluations** — before any rescoring lands.
   Cheap now, and it retroactively labels the location rescore's
   existing unmanaged drift.
3. **Schema + evaluation fields** — the unlock. Near-total coverage at
   zero marginal API cost, and the only path for greenhouse's 453 rows.
4. **jobright metadata backfill** — 433 rows, no API calls.
5. **Employment type**: config, scan gate, shadow mode, UI. Highest
   structured coverage, lowest ambiguity.
6. **Coverage reporting in the UI** — the "112 judged · 38 unstated"
   status line. Ships **before** any enforcement, because it is what
   makes enforcement's blind spot visible.
7. **Compensation** filter, folding `prefilter.py`'s salary branch into
   one parser so the two cannot drift. Keep prefilter as the downstream
   prose safety net, the same relation it has to the location gate.
8. **Compensation rescore** — `compensation_viability` calibration. The
   preference gradient, and the first point at which an on-target role
   actually ranks higher rather than merely surviving.
9. **Holdout labeling and the accuracy gate.** Before any `enforce:
   true`.
10. **Role track** — display and sort only. Promote to a hard filter
    only if it clears the bar, and accept that it may not.

Note the ordering principle: **every observability step precedes the
enforcement step it makes safe.** `scoring_version` before rescoring,
coverage reporting before filtering, shadow mode before enforcement,
holdout before hard exclusion.

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

### v2 → v3

- **v2's greenhouse provider row was wrong**, and it was wrong about the
  largest ATS source in the corpus. Live testing showed no
  `pay_input_ranges` on 909 postings and free-form employer `metadata`.
  Corrected with measured per-provider coverage.
- v2 had **no scoring story at all** — it filtered without ever making an
  on-target role rank higher. Added Stage 3, built on the existing
  `rescore_evaluation_with_location()` precedent, calibrating existing
  subscores rather than adding one (the weights sum to 1.00; adding one
  silently re-ranks the whole corpus).
- Surfaced that **score drift is already unmanaged** — the location
  rescore has no `scoring_version`. Fixing that is now a prerequisite
  rather than a consequence.
- Added the **per-employer coverage bias** finding (2.8% → 67% within
  greenhouse alone) and reframed unknown from a coverage gap to a
  routing decision, with coverage reporting as a shipped UI element
  rather than an implementation detail.
- Added provider value-normalization nuances (PascalCase vs. hyphenated
  vs. comma-joined; lever's unenumerated `Fixed Term`; ashby's
  multi-tier geographic compensation and its
  `shouldDisplayCompensationOnJobPostings` flag).

### v3 → v4

- Surveyed the remaining providers: **6 of 34 measured**, the other 28
  named with an expected-value ordering instead of silently assumed.
  himalayas and remotive measured as high-signal; `usajobs`,
  `levelsfyi`, and `fourdayweek` flagged as plausibly high-signal for
  this feature specifically.
- Found a **fifth** employment-type vocabulary and two unenumerated
  types (`Fixed Term`, `freelance`), which settles normalization as a
  provider-boundary concern with a logged warning on unmapped values.
- **`[t]` was already bound** in `screens/jobs.go`; v3 proposed it for
  role track. Rebound to `[e]`/`[c]`/`[$]`, all verified free.
- Reworked the menu from three appended siblings into one grouped
  "Role Criteria & Filters" submenu replacing the existing Location
  entry — net zero growth on an already-eight-item menu.
- Made enforcement state visible **in the menu label** (`reporting
  only`), since a filter the user believes is active but is not is
  worse than no filter.
- Collected the theme/icon constraints that have caused real bugs
  (dual icon maps, Go mirror, lipgloss v1 vs. v2, DECSTBM, reduced
  motion).

### v4 → v5

Everything here comes from running `scripts/probe_provider_fields.py`
against live providers, not from reading their docs.

- **Split the two fields.** Employment type is a provider property
  (near-zero cross-board variance); salary is an employer property
  (0–100% on every provider). Stage 1 may gate on the first and must
  never carry a provider-level expectation for the second. The
  per-provider salary column from v2–v4 was sampling noise — consecutive
  runs of the same probe moved greenhouse from 37% to 70%.
- **greenhouse publishes no employment type at all**, on every board
  measured, and it is the largest ATS source (453 corpus rows). The
  feature's value therefore rests on Stage 2, not Stage 1. v2 claimed
  the opposite from reasoning; that was wrong for three revisions.
- **The vocabulary is unbounded, not an enum.** Lever's `commitment` is
  employer-authored free text; `Full Time / On Site` puts workplace mode
  inside the employment field. Normalization must be substring-based and
  must log unmapped values with their provider.
- **Two defects found in existing code**: `workable.mjs` indexes its
  markdown table from the left and breaks on a pipe in a title;
  `themuse`'s `type` is a posting kind, not an employment type.
- **Named the unmeasurable.** Thirteen providers cannot be probed
  without keys, sessions, or a different transport, and are listed as
  such so a future reader does not mistake "unmeasured" for "empty".
  Open: ycombinator needs POST, workday is per-tenant POST,
  crunchboard/powertofly returned zero items and may be dead.
