# Dashboard Brainstorm: Data, Stats & Visualization

A running idea list for the Go/Bubble Tea dashboard (`dashboard/`). Nothing here
is scheduled -- pull an item into a real plan (`docs/superpowers/plans/`) when
it's time to build it. Sibling of `IDEAS.md`, scoped specifically to what the
dashboard could *show* and how it could feel.

Organized by **what data it needs**, because that turned out to be the real
constraint: several obvious ideas are blocked not by rendering difficulty but by
the underlying table being empty.

---

## Data reality check (2026-08-20)

Worth reading before picking something, so nothing gets designed against data
that does not exist yet.

| Source | State | Powers |
| --- | --- | --- |
| `jobs` table | 1,457 pending, 2,977 scored | scores, companies, sources, ages |
| Evaluated export | 812 roles, all scored | everything the dashboard shows today |
| `bullet_bank` (CSV) | 1,431 bullets, tagged + audited | bullet analytics, coverage |
| Knowledge base | 57 tools / 506 metrics / 64 projects | skills radar, gap analysis |
| `jd_tracker_log.csv` | reset to 0 on 2026-08-20 | resumes built over time |
| `application_log` table | **empty** | funnel, conversion, response times |
| `contacts` table | **empty** | recruiter relationships |
| Email sync | classifies, matches, does not write yet | everything funnel-shaped |

**The single highest-leverage unlock is the email write-back.** Roughly half the
ideas below are gated on `application_log` having rows in it, and that table
fills the moment status write-back is trusted enough to run.

---

## Tier 1 -- Buildable today, data already exists

### Score distribution histogram
2,977 scored roles rendered as a horizontal histogram across score bands.
Immediately answers "is my pipeline top-heavy or am I hoarding 2.5s?". Colour by
band using the existing Catppuccin accents. Cheap, high daily value.

### Pipeline age / staleness curve
Days since discovery per role, as a distribution. Roles aging past the point
where an application is realistic are worth surfacing before they expire.
`stale_sweep.py` already computes ages; this is the visual half.

### Source-platform breakdown
Which boards actually produce high-scoring roles. A stacked bar of
`source_platform` x score band would answer "is LinkedIn worth scanning at all"
with real numbers. Data is already on every row.

### Company frequency / concentration
Top companies by saved-role count, with the fact that one staffing agency can
account for dozens of roles made visible rather than surprising.

### Score-vs-coverage scatter
`_coverage` (how much of the JD the bullet bank can support) against
`composite_score`. The interesting quadrant is high-score/low-coverage: roles
worth pursuing that the bullet bank cannot yet back. That is a concrete "write
these bullets next" signal.

### Skills radar
57 tools and 506 metrics against the skills named in JDs. Which requirements
recur that the knowledge base has no evidence for. `skill_radar.py` exists;
it needs a dashboard surface.

### Bullet-bank coverage heatmap
Bullets per role-archetype per employer, so gaps are visible as literal holes.
`bullet_analytics.py` has most of the computation.

---

## Tier 2 -- Needs the email write-back to land first

### The funnel
The centrepiece. Saved -> applied -> acknowledged -> responded -> interview ->
offer, as an animated Bubble Tea flow with counts and drop-off percentages at
each stage. This is the view that answers "how am I actually doing".

### Response-rate by score band
Do 4.5+ roles reply more often than 3.5s? If the evaluation rubric is any good,
this chart proves it -- and if it is not, this chart proves that instead, which
is arguably more valuable. Directly actionable for where to spend effort.

### Response-rate by company size / ATS / source
Same question sliced differently. "Greenhouse postings reply 3x more often than
Workday ones" would change where applications go.

### Time-to-response distribution
How long each stage actually takes, from real timestamps. Turns "should I have
heard back by now?" into a percentile.

### Silence detector / chase list
`inbox_sync.applications_without_replies()` already finds applications with no
reply. Age those into a ranked "chase these" list with a follow-up-drafting
action attached.

### Rejection reason clustering
Where rejection emails carry a reason, cluster them. Recurring themes across
rejections are the most direct feedback signal available.

### Application velocity over time
Applications per week against responses per week, so effort and outcome can be
compared on one axis.

---

## Tier 3 -- Bigger builds

### "Restore Roles" screen
Terminal roles (expired/archived) currently vanish. A dedicated screen to browse
and un-archive them, keeping them out of the working pipeline while still
reachable. Needs terminal roles to be retained rather than purged, so it pairs
with a retention policy decision.

### Interactive funnel drill-down
Click a funnel stage, get the roles in it, act on one without leaving the view.
Turns the funnel from a report into a control surface.

### Timeline / Gantt of a single application
One role's whole history on a line: discovered, evaluated, tailored, applied,
acknowledged, interviewed, decided. Reads like a story and makes gaps obvious.

### Company relationship view
Every role, email, and application for one company in one place. The Aquent
thread (5 roles, 20+ emails over 11 months) is the case that motivates it.

### Live scan monitor
Watch a scan run in real time -- boards polled, roles found, dedup hits, scores
as they land. `ScanActivity` already exists for the CLI; this is its dashboard
form.

### Comparison mode
Two roles side by side: scores, subscores, coverage, which bullets each would
use. For deciding where to spend a tailoring run.

---

## Presentation ideas (cross-cutting)

- **Sparklines in list rows** -- a tiny score or activity trend per row, no extra screen.
- **Animated transitions between stages** using the existing Harmonica springs, so the funnel *moves* when data changes.
- **Score-band colour language shared everywhere**, so a colour means the same thing on every screen.
- **Progressive disclosure** -- summary numbers by default, full distribution on keypress.
- **`RESUME_BUILDER_MOTION=reduced` respected everywhere**, per `tui_standards.md`.
- **Empty states that say what to do** ("no funnel data yet -- run `inbox_sync --apply` to populate it") rather than a blank panel. Several screens have already been confusing precisely because they rendered empty without explaining why.
- **Consistency of counts** -- every screen showing "how many roles" must use `picker.count_active_roles()`. Two true numbers measuring different things reads as a bug (see `CLAUDE.md`).

---

## Explicitly rejected (and why)

- **Sankey diagram of the funnel** -- looks impressive, but terminal cell resolution makes the ribbons unreadable below ~120 columns, and mobile/Termux runs at 35-55. A staged funnel carries the same information legibly.
- **Real-time auto-refresh polling** -- burns battery in Termux for data that changes a few times a day. Refresh on action instead.
- **Per-role score sparkline over time** -- scores are computed once and do not move; there is no series to draw.
