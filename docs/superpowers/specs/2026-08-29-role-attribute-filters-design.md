# Role Attribute Filters: Employment Type, Compensation, and IC vs. Manager

Date: 2026-08-29
Status: Design — not yet implemented

## Problem

`scan_filters.yml` can express **where** a role is (`location:` block,
radius, `workplace_mode`) but not three attributes that are just as
disqualifying:

1. **Employment type** — full-time vs. part-time vs. contract /
   contract-to-hire / temp / internship. Today a part-time contract
   lands in the pipeline indistinguishable from a salaried role.
2. **Compensation** — pay rate or salary band, and its period (annual /
   hourly). `scripts/prefilter.py` already has a `salary_floor`
   deal-breaker, but it runs on **JD body prose at batch-sweep time**,
   which is the wrong stage: the posting has already been written to
   disk, evaluated, and counted in the backlog. Nothing reads the
   structured salary fields providers actually publish.
3. **Role track** — individual contributor vs. managerial /
   people-facing. `title_filter.negative` is the current blunt
   instrument (`Director of`, `Vice President`, `Chief `), which is a
   string blocklist, not a classification: it cannot express "Senior
   Manager, Content" is a people-manager while "Content Marketing
   Manager" is an IC, and it silently pushes the decision into a
   per-profile YAML list nobody maintains.

## Design principles (carried over from the location work)

These are not new inventions — they are the rules the location gate
already earned, and every one of them applies here unchanged:

- **One chokepoint.** The location gate lives in exactly one place
  (`scan_boards._passes_location_filter()`) and `scan_ats.py` routes
  through it, so anything added covers both scanners. The new filters
  go in the same function, not in `prefilter.py`.
- **Unknown is kept, never rejected.** An unresolvable location is kept
  for review. Likewise: a posting with no stated salary is **not**
  dropped by a salary floor, and a title that classifies as neither IC
  nor manager is **not** dropped on track alone. Surfacing an unknown
  is cheap to eyeball; silently dropping a good role is not. Providers
  routinely omit these fields — Indeed/JobSpy publishes compensation on
  a minority of postings.
- **Unknown is `None`, never `0`.** `distance_miles` is `None` when
  unknown and decodes into a Go `*float64` so unknowns cannot float to
  the top of a nearest-first sort. `salary_min`/`salary_max` follow the
  same rule and the same pointer treatment.
- **Inert until configured.** The whole location system does nothing
  until a `location:` block exists. Each new block is likewise opt-in:
  absent block = no filtering, exactly today's behavior.
- **A verdict says why, not just whether.** `LocationVerdict` carries
  `passes`, the classification, the measurement, and a `reason`. Each
  new filter returns the same shape.
- **Single or list.** `workplace_mode` accepts `remote` or
  `[remote, onsite]`. `employment_type` and `role_track` do too.

## 1. Employment type

### Config (`scan_filters.yml`)

```yaml
employment:
  employment_type: [full_time, contract]   # or a single value
  # Absent -> no filtering. Values:
  #   full_time | part_time | contract | contract_to_hire
  #   temporary | internship | volunteer
```

### New module: `scripts/employment_filter.py`

Mirrors `location_filter.py` exactly:

```python
FULL_TIME, PART_TIME, CONTRACT, CONTRACT_TO_HIRE, TEMPORARY, INTERNSHIP, UNKNOWN

class EmploymentVerdict:  # passes, employment_type, reason

def classify_employment(
    title: str, description: str = "", job_type: str = "", **posting
) -> str
def wanted_employment_types(config: dict) -> set
def evaluate_employment(config: dict, **posting) -> EmploymentVerdict
```

`classify_employment` follows `classify_workplace`'s precedence:
**structured provider field first, prose second.** Providers that
publish a type today:

| Provider | Field |
| --- | --- |
| greenhouse | `metadata` / `employment_type` |
| lever | `categories.commitment` ("Full-time") |
| ashby | `employmentType` |
| workable | listing column `type` |
| ycombinator | already hardcodes `job_type:full_time` in the Algolia facet |
| indeed (JobSpy) | `job_type` |

Prose fallback patterns, checked in this order (most specific wins, as
hybrid is checked before remote today):

1. `contract-to-hire`, `contract to hire`, `C2H`, `temp-to-perm`
2. `part-time`, `part time`, `\d+ hours?/week` where N < 32
3. `contract`, `contractor`, `1099`, `W2 contract`, `SOW`
4. `intern`, `internship`, `co-op`
5. `temporary`, `seasonal`
6. `full-time`, `full time`, `permanent`, `salaried`, `FTE`

Ambiguity trap worth stating: **"contract" appears in ordinary prose**
("contract negotiation", "under contract with", "contract lifecycle
management" — a real skill in this profile's own corpus). Require
either a structured field or an employment-context anchor
(`contract position|role|opportunity|assignment`, `on a contract
basis`, `\d+-month contract`) before classifying from prose. Classify
`UNKNOWN` otherwise; do not guess.

## 2. Compensation

### Config

```yaml
compensation:
  annual_floor: 65000        # optional
  hourly_floor: 32           # optional; used when the posting quotes hourly
  # When only one is given, the other is DERIVED at 2080 hrs/yr for
  # comparison purposes only -- the stored value is always what the
  # posting actually said.
  require_stated: false      # default false. true drops unstated pay.
```

`require_stated: false` is the default and must stay that way — it is
the "unknown is kept" rule. `true` is offered because in states with
pay-transparency laws an unstated range is itself a signal, but it is
the user's explicit choice, never a default.

### New module: `scripts/compensation_filter.py`

```python
class CompensationVerdict:
    passes: bool
    salary_min: float | None      # None when unstated -- never 0
    salary_max: float | None
    period: str                   # "annual" | "hourly" | "unknown"
    currency: str                 # "USD" default
    is_estimated: bool            # provider estimate vs. employer-stated
    reason: str

def parse_compensation(text: str, **posting) -> CompensationVerdict
def evaluate_compensation(config: dict, **posting) -> CompensationVerdict
```

Structured fields first (greenhouse `pay_input_ranges`, ashby
`compensation`, lever `salaryRange`, JobSpy `min_amount`/`max_amount`/
`interval`/`currency`), then prose parsing of the forms that actually
occur:

- `$85,000 - $110,000`, `$85K-$110K`, `85,000 — 110,000 USD`
- `$45/hr`, `$45 - $60 per hour`, `$45.00 hourly`
- single values (`Salary: $95,000`) → min == max
- `up to $110,000` → max only, min `None`
- ranges spanning an order of magnitude apart (`$40 - $150,000`) are
  rejected as a mis-parse rather than trusted

**Filter semantics:** compare the posting's **max** against the floor,
not its min. A `$60K–$95K` range with a `$70K` floor is worth seeing —
the top of the band clears it. Rejecting on min would drop every wide
range. Reject only when a stated *maximum* falls below the floor. This
matches what `prefilter.py` already does (it compares `max_val`), and
that behavior should be preserved when the salary check moves upstream.

`is_estimated` matters: Indeed publishes *estimated* ranges alongside
employer-stated ones. An estimate must never hard-reject a posting —
mark it and let the user see it. Only employer-stated compensation
gates.

**Migration note:** `prefilter.evaluate_preflight_gate()`'s
`salary_floor` branch becomes a thin wrapper over
`compensation_filter.parse_compensation()` so there is one parser, not
two that drift. Keep prefilter's gate as the downstream safety net for
JD body prose (same relationship it has with the location gate today).

## 3. IC vs. managerial / people-facing

The subtlest of the three, because title alone is unreliable in both
directions: "Marketing Manager" is usually an IC; "Staff Engineer" and
"Principal Designer" are senior ICs; "Head of Content" at a startup may
manage nobody.

### Config

```yaml
role_track:
  track: [ic]              # ic | manager | either
  allow_player_coach: true # roles that are both; default true
```

### New module: `scripts/role_track_filter.py`

```python
IC, MANAGER, PLAYER_COACH, UNKNOWN

class RoleTrackVerdict:  # passes, track, confidence, evidence, reason

def classify_role_track(title: str, description: str = "") -> RoleTrackVerdict
def evaluate_role_track(config: dict, **posting) -> RoleTrackVerdict
```

Classification is **evidence-based and layered**, not a title
blocklist:

**Strong manager evidence (body text, highest weight)** — this is the
signal that actually generalizes:
- `manage a team of`, `\d+ direct reports`, `lead a team of`
- `hire, coach, and develop`, `performance reviews`, `mentor and manage`
- `people management`, `team leadership`, `manage and grow the team`

**Strong IC evidence:**
- `individual contributor` (stated outright — common and decisive)
- `no direct reports`, `hands-on`, `this is an IC role`
- `you will personally` / `you will write / design / build`

**Title signals (weaker, tie-breakers only):**
- Manager-leaning: `Director`, `Head of`, `VP`, `Chief`, `Manager of
  <function>`, `Senior Manager`
- IC-leaning: `Staff`, `Principal`, `Senior <craft>`, `Specialist`,
  `Individual Contributor`, `Lead <craft>` (ambiguous — weak)

**Resolution:** body evidence beats title. Both present →
`PLAYER_COACH` (a real and common shape: manages two people, still does
the work). No evidence either way → `UNKNOWN`, which passes. Emit
`confidence` and `evidence` (the matched phrases) so the dashboard can
show *why* a role was called managerial — the user will disagree
sometimes, and an unexplained classification is not correctable.

`title_filter.negative`'s existing `Director of` / `VP ` / `Chief `
entries stay put — they are a user's blocklist and are not this
system's business to relitigate. But once `role_track` is configured,
document that the two overlap so a user isn't confused about which one
dropped a role. The verdict `reason` names which gate rejected it.

## Wiring: one gate, one exporter, one model

### Gate

`scan_boards._passes_location_filter()` is renamed
`_passes_posting_filters()` (keeping a thin
`_passes_location_filter` alias, since tests and `scan_ats.py` import
it by name) and calls all four evaluators, short-circuiting on the
first rejection. `scan_ats.py` needs no change — it already routes
through this function, which is the whole point of the chokepoint.

Provider `.mjs` files must pass through the structured fields they
already receive (`employmentType`, `commitment`, `pay_input_ranges`,
`job_type`, `min_amount`) rather than dropping them at normalization.
Verify each provider individually against a live response — the adzuna
lesson (reporting `"Buffalo, Erie County"` and silently landing in the
permissive bucket) is that an unparsed field defeats a filter *quietly*.

### Persistence

Following the JD-JSON metadata convention: a new `_attributes` key on
the JD's own JSON, with matching `jd_manager.save_attributes()` /
`read_attributes()`. Underscore-prefixed, so `read_jd_text()` already
strips it before any prompt — no prompt-leak risk, no new mechanism.

```json
"_attributes": {
  "employment_type": "full_time",
  "compensation": {"min": 85000, "max": 110000, "period": "annual",
                   "currency": "USD", "is_estimated": false},
  "role_track": {"track": "ic", "confidence": "high",
                 "evidence": ["no direct reports"]}
}
```

### Export

`picker._location_fields()` gets a sibling `_attribute_fields()`, both
called from the same two places in `list_all_evaluated_jds()` and
`_database_only_rows()`. Emitted keys: `employment_type`,
`salary_min`, `salary_max`, `salary_period`, `salary_estimated`,
`role_track`.

**Hard requirement:** every new key needs a matching `model.JobRow`
field in the same change. A field in the export with no Go counterpart
fails `encoding/json` for the *whole document* and `LoadJobs` returns
zero rows — this silently emptied the Jobs screen once already (the
`skills` bug). Add both sides together or neither.

```go
EmploymentType  string   `json:"employment_type"`
SalaryMin       *float64 `json:"salary_min"`   // pointer: unstated != $0
SalaryMax       *float64 `json:"salary_max"`
SalaryPeriod    string   `json:"salary_period"`
SalaryEstimated bool     `json:"salary_estimated"`
RoleTrack       string   `json:"role_track"`
```

Plus constants mirroring the Python values (as `WorkplaceRemote` etc.
already do) and `HasSalary()` / `Salary()` accessors matching
`HasDistance()` / `Miles()`.

### Dashboard UI

**Browse & Manage Jobs** (`screens/jobs.go`) — follow the `[w]`
workplace filter exactly (`workplaceFilter` field, `nextWorkplaceFilter`
cycle, `workplaceFilterLabel` status-bar chip):
- `[e]` cycles employment type: All → Full-time → Part-time → Contract
- `[t]` cycles role track: All → IC → Manager
- `[$]` cycles a salary floor: All → configured floor → any stated pay
- Sort options gain "Salary (high→low)". Unstated pay sorts **last**,
  never first — the `*float64` makes that enforceable.
- Row rendering: a compact chip per attribute, and nothing rendered for
  an unknown rather than a misleading placeholder.

**Pipeline** (`screens/pipeline.go`) — `data.JobRowsToApplications`
carries the new fields through so Pipeline and Jobs agree; they share
one source and a mid-session `reloadPipelineDataCmd` must read that
same source or the screen silently reverts to an older data set.

**Non-dashboard surfaces:** `picker.py`'s interactive role picker shows
the chips in its choice labels; `cli_art` listing helpers show them
where a role is summarized. The CLI banner counts stay on
`picker.count_active_roles()` — these filters are display/selection
concerns and must not introduce a fifth definition of "how many roles
do I have."

### Settings

`scripts/location_settings.py` is location-specific; the new blocks get
`scripts/role_filter_settings.py` with the same shape (`read_settings`,
`render_block`, `write_settings`, `clear_settings`, `describe`,
`run_*_settings`) writing to the same `scan_filters.yml`. Settings &
Upkeep gains "Employment type & pay" and "Role track (IC vs. manager)"
entries beside the existing location entry.

All prompts go through `cli_art.confirm/select/checkbox/text()` — never
raw `questionary`, which renders nothing under `menu._run_with_chain()`'s
DECSTBM scroll region.

## Testing

`profile_paths.isolate_for_tests(tmpdir)` for anything touching a
profile — all four roots, never just `PROFILES_DIR`. `tests/persona.py`
for any identity. No network: the `gemini_client._get_auth_headers()`
guard and `websearch_ddg`'s `_TEST_NETWORK_ENV` both fail closed, and
these filters need no LLM call at all — classification is deterministic
by design, which also makes it cheap and testable.

New test files: `test_employment_filter.py`,
`test_compensation_filter.py`, `test_role_track_filter.py`,
`test_role_filter_settings.py`, plus cases in `test_scan_boards.py`
proving the chokepoint covers `scan_ats.py` too, and Go tests in
`jobs_test.go` / `jobs_to_apps_test.go` for the filter cycles and the
unstated-sorts-last rule.

Calibrate the prose parsers against this profile's real corpus, the way
`MIN_DESCRIPTION_CHARS` was set from measured data (thinnest real
posting 632 chars, teasers clustered at 275) rather than guessed. Before
implementing, measure over existing JDs: what fraction state
compensation at all, how many carry a structured employment type, and
how often body text contains strong manager/IC evidence. If strong IC/
manager evidence appears in well under half of postings, the honest
answer is that `role_track` is mostly `UNKNOWN` — which is fine (unknown
passes), but it should be known going in rather than discovered as
disappointment.

## Suggested sequencing

1. Measurement pass over the existing corpus (above) — cheap, and it
   sets the parser targets.
2. `employment_filter.py` + config + gate + tests. Smallest surface,
   best structured-field coverage.
3. `compensation_filter.py`, folding `prefilter.py`'s salary branch
   into it.
4. `role_track_filter.py` — last, because it is the one whose accuracy
   depends on the measurement.
5. Export + `model.JobRow` in a single change (both sides or neither).
6. Dashboard filters/sort, then non-dashboard surfaces.
7. Settings screens.
