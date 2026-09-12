# Tesla @ Buffalo — Implementation Spec for Dominick

*Written: 2026-09-11, as a follow-up to `tesla-job-integration-legal-&-free-solutions-for-resume-builder-codebase-verified.md`*

That research doc got the landscape mostly right, but I verified the specific claims that matter against this codebase and against Dominick's actual configured profile before recommending anything, and found two real, concrete blockers — one Tesla-specific, one much bigger.

## The most important finding isn't about Tesla at all

**Indeed has been silently searching for `"marketing"` on every scan, for every profile, this whole time.** `scan_indeed.py`'s `fetch_indeed_jobs()` only uses a real search term when one is explicitly passed in — but I checked every real call site (`cli.py`, `menu.py`, `dashboard_actions.py`, `dashboard_actions.py`) and **none of them ever pass one**. `scan.run_scan()` calls every source as `fetch(activity=activity)`, full stop. So the module's `DEFAULT_SEARCH_TERM = "marketing"` — a leftover, unrelated to any real profile — was quietly what Indeed actually searched for on Dominick's scans, not "Data Scientist" or anything from his configured target roles.

**Fixed.** `scan_indeed.py` now falls back to the profile's own `scan_filters.yml` → `title_filter.positive`'s first entry (already seeded from his target roles: "Data Scientist") instead of the hardcoded literal, only falling back to `"marketing"` if that file is genuinely missing or empty. Added 5 tests covering it. This alone is probably worth more to his job search than anything Tesla-specific below — it means his *entire* Indeed source may have been returning irrelevant results until now, not just missing Tesla.

## Tesla-specific findings

**1. His location radius doesn't reach Buffalo — blocking regardless of source.** I computed this with the codebase's own geocoding:

| From Getzville, NY (his configured location) | Distance |
|---|---|
| Buffalo, NY (downtown) | **11.4 mi** |
| Tesla Gigafactory 2 (South Buffalo, the actual Tesla facility) | **14.0 mi** |

His `scan_filters.yml` radius is currently **10 miles**. That's short of *Buffalo itself*, let alone the Gigafactory. Any Tesla Buffalo posting — from Indeed, from any future source — gets filtered out by `location_filter.py`'s radius gate before it's ever evaluated, independent of which job source finds it. This also contradicts his own stated preference from the research report ("Open to local (Buffalo, NY area)... "). **Recommend widening to ~20 miles** (Settings & Upkeep → Location & Commute Radius) before anything else here matters.

**2. Confirmed live: Tesla has no public ATS board.** I ran this codebase's own `discover_local_employers.find_ats_board("Tesla")` against the real Greenhouse/Ashby/Lever/SmartRecruiters/Workable/Workday endpoints — zero hits. This matches the research doc's own finding that Tesla runs a bespoke internal `cua-api`, not a standard ATS. The clean, already-built, ToS-respecting discovery path (`scan_ats.py`/tracked_companies.yml) is a dead end for Tesla specifically — not worth spending engineering time trying to make it work.

I also tried fetching `tesla.com/robots.txt` directly (the one thing every site is expected to let automated tools read) and got an Akamai "Access Denied" — their edge infrastructure blocks even that. Reinforces that anything scraping-adjacent against tesla.com directly is both against their Terms of Use (which the research doc already quoted) and likely to just get blocked outright.

**3. The research doc's "Tesla Email Alerts" proposal has a real legal gap in it, not just a technical one.** Receiving an email alert Dominick opted into is clearly fine. But the doc's own code template then has `_fetch_tesla_job_description(url)` — a `requests.get()` + BeautifulSoup scrape of the linked tesla.com job page to pull the full description. That's still automated scraping of tesla.com content; "the link came from an email Tesla sent me" doesn't create an exception to their ToS clause prohibiting scraping. **If this gets built, drop that function entirely** — parse title/location/date from the alert email's own body text (which Tesla controls and sends directly, no scraping involved), store the direct URL, and either leave the description for Dominick to read himself when he clicks through, or mark it `description_is_teaser: true` (same convention this codebase already uses for jooble/adzuna's teaser-only text) so the fit-scorer doesn't treat a title-only stub as a full JD.

**4. His friend at Tesla is the highest-leverage lever here, and it's not a code problem.** The research report already flagged this as his own action item ("Note: Has a friend at Tesla — seeking warm introduction"). A warm internal referral routes around ATS ranking entirely and is worth more than any scraper this session could build. Nothing to spec — just don't let the engineering rabbit hole distract from the actual highest-value move being a text message to a friend.

## Recommended order of operations

1. **Widen the location radius** (Settings & Upkeep, no code) — otherwise nothing else here can matter.
2. **Re-run a scan** — Indeed now searches "Data Scientist" instead of "marketing," and the wider radius means Buffalo-area postings (Tesla or otherwise) stop being silently dropped. Zero new code, already shippable.
3. **Have Dominick message his friend directly.** Not a pipeline problem.
4. *(Optional, only if he wants broader automated Tesla-specific coverage beyond what Indeed surfaces)*: build the email-alert path from the research doc, minus the description-scraping function as described above.
5. *(Not recommended)*: don't chase the RSS feed option — the doc itself notes it's likely a different company ("Tesla Search Group"), not Tesla Inc.
