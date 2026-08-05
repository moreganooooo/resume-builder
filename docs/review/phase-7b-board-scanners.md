# Phase 7b — Board-scanner provider layer

Reviewed 2026-08-05. Scope: all of `board-scanners/` — `run_provider.mjs`,
`providers/_http.mjs`, `_rss.mjs`, `_recognition.mjs`, `_types.js`, and the 24
provider implementations. No files were found unowned; the plan's ownership list
already covers this directory.

**Method:** full source read of all 28 modules, plus live runs of 21 of the 24
providers through `run_provider.mjs` (the three key-gated ones were exercised on
their missing-key and bad-key paths). Timings below are measured, not estimated.

**Short answer to the phase question:** they diverge badly. There is no rate
limiting, no backoff, and no retry anywhere in this layer — `_http.mjs` is a
fetch wrapper with a single 10s timeout, not a policy layer, and the two
providers that matter most (`workday`, `websearch`) bypass it entirely with raw
`fetch()`. One provider (`workday`) currently returns zero jobs on every real
board while firing ~30 unthrottled POSTs at the target first.

---

## Finding 1 — `workday` fires ~100 unthrottled POSTs, blows the parent timeout, and returns nothing. Every run. (blocker, goals 1)

`board-scanners/providers/workday.mjs:121-147`

The pagination loop is unbounded (`for (let offset = limit; offset < total; offset += limit)`),
has no delay between requests, and no page cap — unlike `smartrecruiters.mjs:13`,
which caps at `SR_MAX_PAGES = 50`.

Measured, live, against a real board:

```
$ time node run_provider.mjs workday '{"name":"NVIDIA","careers_url":"https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"}'
1:34.19 total — 2000 jobs
```

94 seconds and ~100 back-to-back POSTs to `nvidia.wd5.myworkdayjobs.com`. The
Python caller kills this at `NODE_TIMEOUT_SECONDS = 30` (`scan_boards.py:77`),
and `run_provider.mjs:62` only writes to stdout *after* the full array is built —
so the subprocess is killed mid-pagination and **100% of the collected jobs are
discarded**. The user sees "no jobs"; NVIDIA saw ~30 seconds of unthrottled API
traffic for nothing. This repeats on every scan, for every Workday company.

This is simultaneously the "which ones hammer" answer and a correctness blocker:
Workday is one of the seven ATS providers in `scan_ats.py`'s recognition table,
so every tracked Workday company is silently contributing zero.

Secondary risk in the same loop: `const limit = data?.limit ?? 20` (line 119)
uses `??`, not `||`. A board that returns `limit: 0` with a non-zero `total`
gives `offset += 0` — an infinite POST loop bounded only by the 30s kill.

**Concrete fix:** cap pages the way `smartrecruiters` does, add a delay between
pages, route the requests through `_http.mjs` (see Finding 2), and either raise
the parent budget for this provider or emit what was collected before the cutoff.

---

## Finding 2 — `workday` and `websearch` bypass `_http.mjs` with raw `fetch()`: no timeout, no status check, no UA (major, goal 1)

`board-scanners/providers/workday.mjs:130-135`, `board-scanners/providers/websearch.mjs:221-227`

`workday`'s pagination `fetch()` never checks `res.ok`. A 429, a 503, or a
Cloudflare interstitial returns HTML with a 200-adjacent status, `res.json()`
throws, the exception propagates out of `fetch()`, and **the page-1 jobs already
in the array are thrown away too** — the `finally` only closes the browser. A
partial rate-limit becomes total data loss rather than a short result.

`websearch`'s `fetch()` has no `AbortController` and no timeout. If Brave hangs,
the only thing that stops it is the parent's 30s SIGKILL — with no error message,
since nothing was written to stderr.

Both also skip `_http.mjs`'s `user-agent` default, so these requests go out with
Node's default UA (`workday`'s browser page sets its own; the pagination fetches
do not — the same provider identifies itself two different ways within one run).

**Concrete fix:** both should call `ctx.fetchJson` / `fetchWithTimeout`.
`workday.fetch()` already receives `_ctx` and ignores it.

---

## Finding 3 — `_http.mjs` is a fetch wrapper, not a shared policy layer (major, goals 1, 5)

`board-scanners/providers/_http.mjs:1-48`

`grep -rn "retry\|backoff\|Retry-After\|429" board-scanners/` returns nothing.
The entire layer has:

- **no retry** on any provider, for any status;
- **no backoff**, and no handling of `Retry-After` on a 429;
- **one global 10s timeout** (`DEFAULT_TIMEOUT_MS`), which no provider overrides —
  `himalayas` (20 items) and `smartrecruiters` (up to 50 sequential pages) get the
  same budget per request;
- **no inter-request delay** on any of the three multi-request providers
  (`workday`, `smartrecruiters`, `hackernews`).

`hackernews.mjs:34-36` is the one place with real concurrency: it fires **60
simultaneous** requests via `Promise.all` with no chunking. Firebase tolerates it,
but it is the only unthrottled burst in the layer and it's there by accident, not
by policy.

Everything else is polite by luck: 18 of 24 providers make exactly one request
per run, which is why nothing has been blocked yet.

**Concrete fix:** put retry-with-backoff, 429/`Retry-After` handling, and an
optional per-provider `timeoutMs`/`minGapMs` into `_http.mjs`, and make
`makeHttpCtx()` the only way out to the network.

---

## Finding 4 — `websearch`'s rate limiter is dead code across the subprocess boundary (major, goal 1)

`board-scanners/providers/websearch.mjs:28-40`

The `queue` promise chain and its `RATE_LIMIT_MS = 100` gap are **module-level
state in a process that handles exactly one query and then exits**.
`run_provider.mjs` is spawned per provider call, so `enqueue()` never has a
second call to serialize against. The limiter does nothing; the real pacing is
whatever the Python side's spawn loop happens to do.

It also contradicts its own documentation. Line 16 states the free tier is
**1 req/sec**, and lines 28-29 justify 100ms against "the paid plan's 50 req/sec
limit" — so the code is tuned 10× above the limit of the plan its own docstring
tells the user to sign up for.

**Concrete fix:** delete the queue (it cannot work here) and enforce the gap on
the Python side where the loop actually lives, sized for the free tier.

---

## Finding 5 — `isJobUrl()` returns `true` on both branches; the job-path allowlist is inert (major, goals 1, 2)

`board-scanners/providers/websearch.mjs:181-184`

```js
if (CONTENT_PATH_SIGNALS.some(s => path.includes(s))) return false;
if (JOB_PATH_SIGNALS.some(s => path.includes(s))) return true;
return true;
```

The last two lines are the same answer. `JOB_PATH_SIGNALS` (lines 105-110, 20
entries) has no effect on any decision — the function is really "not a blocked
domain and not a blog post". `https://acme.com/team/leadership` or
`https://acme.com/2026-q3-roadmap` pass as job postings.

Impact lands downstream: a false positive here becomes a JD file, which becomes a
Gemini tailoring call against a page that isn't a job.

Related, smaller: two `BLOCKED_DOMAINS` entries have the wrong TLD and so block
nothing — `workingnomads.com` (the site is `workingnomads.co`, and this repo's own
provider fetches `workingnomads.co`) and `remoteok.com` alongside the also-live
`remoteok.io`.

---

## Finding 6 — 6 of 24 providers never emit a `description` at all; `_types.js` doesn't know the field exists (major, goal 2)

`board-scanners/providers/_types.js:15-21`

`Job` is documented as `{title, url, company, location}`. Eighteen providers
return `description` and `posted_at` anyway; six do not emit `description` in any
code path:

| Provider | emits `description`? | evidence |
|---|---|---|
| `workday.mjs:109-114` | no | live: 2000/2000 jobs with no description |
| `smartrecruiters.mjs:123` | no | live (Visa): 2/2 with no description |
| `recruitee.mjs:97-102` | no | source — object literal has no key |
| `workable.mjs:116` | no | source |
| `fourdayweek.mjs:56-62` | no | live: 2/2 with no description |
| `websearch.mjs:248-254` | no | source |

This is the upstream source of Phase 7's null-description JD files: the four ATS
providers plus `websearch` are exactly the paths that produce company-direct
postings, so the highest-value listings are the ones arriving with no body text.
Nothing here is "wrong" per the contract — the contract is stale, which is why the
divergence went unnoticed.

`websearch` also adds an undeclared `_promotedPortal` field (line 253).

**Concrete fix:** add `description` and `posted_at` to the `Job` typedef as
optional-but-expected, and give the six a description source (Greenhouse's
`?content=true` trick at `greenhouse.mjs:66-67` is the model — it already solved
this for its own provider).

---

## Finding 7 — the layer identifies itself as a browser, and as the wrong project (major, goals 1, 5)

`board-scanners/providers/_http.mjs:5`, `board-scanners/providers/workday.mjs:65-67`

Default UA for 22 providers:

```js
const DEFAULT_USER_AGENT = 'Mozilla/5.0 (compatible; career-ops/1.3)';
```

Two problems. It leads with `Mozilla/5.0` — the browser-impersonation prefix
that gets an IP blocked when a site decides to enforce — and it names
`career-ops/1.3`, a different project at a version this repo doesn't have. A
site operator who wants to contact the owner of this traffic, or allowlist it,
cannot.

`workday.mjs:66` goes further and sends a full Chrome 124 fingerprint. That's the
same split Phase 7 found on the Python side (`scan_boards.py:239` honest vs.
`scan_jobright.py:19-27` fake Chrome) — this layer inherits both conventions and
picks neither.

`usajobs.mjs:28` sending the user's email as UA is correct — that's USAJOBS's
documented auth requirement, not impersonation.

**Concrete better version:** `resume-builder/1.0 (+<repo url>)` as the shared
default, and drop the Chrome string in `workday` unless a live check proves the
board rejects an honest UA.

---

## Finding 8 — every failure mode exits 1 with an empty stdout, so "misconfigured" and "no jobs today" are indistinguishable to the caller (major, goal 1)

`board-scanners/run_provider.mjs:36-66`

Measured on the three key-gated providers:

| Case | stderr | exit |
|---|---|---|
| `adzuna`, no key | `adzuna: adzuna: missing ADZUNA_APP_ID / ADZUNA_APP_KEY…` | 1 |
| `adzuna`, bad key | `adzuna: HTTP 401: {"exception":"AUTH_FAIL"…}` | 1 |
| `usajobs`, no key | `usajobs: missing USAJOBS_API_KEY / USAJOBS_EMAIL…` | 1 |
| `websearch`, no key | `websearch: BRAVE_API_KEY is not set…` | 1 |
| unknown provider | `bogus: failed to load provider — Cannot find module…` | 1 |
| unresolvable entry | `greenhouse: cannot derive API URL for X` | 1 |

Good news: none of these fail *silently* — a missing key throws rather than
returning `[]`, so the Phase 7 Finding 1 shape does not reproduce here on the
key-based providers. The text is genuinely informative.

Bad news: it's all one exit code and stdout is empty in every case, and the
caller collapses non-zero exit, timeout, and invalid JSON into `return []`. A
quota exhaustion is byte-for-byte the same signal as a quiet Tuesday.

There is one residual silent path worth naming: the twelve providers using
`Array.isArray(json?.jobs) ? json.jobs : []` (e.g. `remotive.mjs:18`,
`jobicy.mjs:22`, `himalayas.mjs:33`) return `[]` on a **200 response carrying an
error object** — the one shape that doesn't trip `_http.mjs`'s `res.ok` check.

**Concrete better version:** write a JSON envelope to stdout even on failure —
`{"error":{"kind":"auth"|"quota"|"network"|"config","message":"…"}}` — and let
the Python side distinguish "this source is broken, tell the user" from "this
source is empty".

---

## Finding 9 — `_recognition.mjs` has drifted from its Python mirror in both directions (minor, goal 1)

`board-scanners/providers/_recognition.mjs:5-16` vs. `scripts/scan_ats.py:57-65`

The `.mjs` list is missing `recruitee`, which the Python mirror has and which
exists as a full provider module here. Consequence: `websearch.mjs:242`'s
`recognizeProvider()` returns `null` for any `*.recruitee.com` hit, so a
sweep-discovered Recruitee company can never be promoted to its direct-API
provider — the exact path the missing-import fix at `websearch.mjs:9` was meant
to restore.

In the other direction, `_recognition.mjs` still lists `bamboohr`, `jobvite`,
`icims`, and `jazzhr`, none of which have a provider module. A promotion on one
of those resolves to a `providers/<id>.mjs` that doesn't exist —
`run_provider.mjs:37` then reports `failed to load provider` and exits 1.

**Fix:** make the `.mjs` list match `scan_ats.py`'s seven, or better, have the
Python side read the `.mjs` rules rather than mirroring them by hand.

---

## Finding 10 — `search_term` is filtered client-side against a single unpaginated page on two providers (minor, goals 1, 2)

`board-scanners/providers/themuse.mjs:22`, `board-scanners/providers/himalayas.mjs:31`

`themuse` requests `?page=0` (20 of several thousand postings) and `himalayas`
requests `limit=20&offset=0`, then filter locally. Live:

```
themuse   search_term="marketing" → 0 jobs;  no search_term → results present
himalayas search_term="marketing" → 0 jobs;  no search_term → results present
```

Both APIs accept server-side filters. `remotive.mjs:14-16` and `adzuna.mjs:26`
already pass the term to the server and return matches. As written, these two
providers are effectively dead whenever a search term is set — they aren't
broken, they're searching the wrong 20 rows.

---

## Finding 11 — `ashby` is the only provider with no output filter (minor, goal 1)

`board-scanners/providers/ashby.mjs:41-48`

Every sibling filters on a URL and title before mapping (`greenhouse.mjs:73`,
`lever` via `hostedUrl`, all twelve aggregators). `ashby` maps unconditionally,
so a posting missing `jobUrl` is emitted as `url: ''` — and `url` is the dedup
key per `_types.js:18`. `recruitee.mjs:99` and `smartrecruiters.mjs:123` can also
emit `url: ''` (deliberately, when validation rejects the URL), but at least
document it; nothing downstream in this layer drops those rows.

---

## Finding 12 — doubled provider prefix in every error message (minor, goal 3)

`board-scanners/run_provider.mjs:64` prepends `${providerId}: ` to a message that
several providers already prefix themselves, producing user-facing lines like:

```
adzuna: adzuna: missing ADZUNA_APP_ID / ADZUNA_APP_KEY environment variables
```

Affects `adzuna`, `usajobs`, `websearch`, `greenhouse`, `lever`, `ashby`,
`recruitee`, `workable`, `smartrecruiters`, `workday`.

---

## What's healthy (worth not breaking)

- **SSRF defence is real and consistent** across the four ATS providers that
  accept a user-supplied URL: `greenhouse.mjs:18-29`, `workable.mjs:18-30`,
  `smartrecruiters.mjs:15-27` use host allowlists, `recruitee.mjs:10-24` a
  tenant-slug regex, and all four pair it with `redirect: 'error'` so a
  server-side redirect can't escape the allowlist. `workday` is the exception —
  it takes any `*.myworkdayjobs.com` URL and drives a browser at it.
- **The vendoring notes are excellent.** `fourdayweek.mjs:7-16`,
  `workday.mjs:99-106`, `websearch.mjs:4-8`, and `extractLocation`'s note at
  `websearch.mjs:323-331` each document a real bug found and fixed while porting
  from career-ops, with the live evidence. That's why this review could tell
  "ported broken" from "deliberate".
- **21 of 24 providers are alive and fast.** Every aggregator returned parseable
  results in under 1s in live runs; none were silently dead.
- **`_rss.mjs`** is a reasonable regex parser for the narrow subset of RSS these
  feeds emit, and all six RSS providers use it identically — the most consistent
  group in the layer.

---

## Handoffs

- `scripts/scan_boards.py:77` — `NODE_TIMEOUT_SECONDS = 30` is the other half of
  Finding 1; the fix has to be agreed across the boundary. (Phase 7)
- `scripts/scan_ats.py` — its own comment (`scan_boards.py:95`) notes ~400
  sequential subprocess spawns; each is a full Node process launch, and for
  Workday each is also a Chromium launch. Cost/pacing question sits on the Python
  side. (Phase 7)
- `scripts/scan_boards.py` — Finding 8's proposed JSON error envelope needs a
  consumer; the parsing change lands there. (Phase 7)
- `board-scanners/providers/adzuna.mjs:21-27` puts `app_key` in the query string.
  It does not leak into this layer's error messages (`_http.mjs:21` reports status
  + body only), but any Python-side logging of the invocation or of a URL would.
  (Phase 8)
