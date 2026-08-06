// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Workday provider — uses Playwright to intercept the internal XHR call
// that Workday SPAs fire on page load, returning clean JSON.
//
// Requires: `npm install playwright && npx playwright install chromium`
//
// Auto-detects from careers_url patterns like:
//   https://<tenant>.wd1.myworkdayjobs.com/en-US/<board>
//   https://<tenant>.myworkdayjobs.com/<board>

const WORKDAY_HOST_RE = /\.myworkdayjobs\.com/;

// Workday's internal search endpoint path (consistent across tenants)
const SEARCH_PATH_RE = /\/wday\/cxs\/[^/]+\/[^/]+\/jobs$/;

// Pagination safety net — see B19 (docs/review/phase-9-backlog.md). Measured
// live against NVIDIA: ~100 back-to-back unthrottled POSTs, 94 seconds total,
// against `scripts/scan_boards.py`'s NODE_TIMEOUT_SECONDS = 30 subprocess
// kill. All four bounds below exist so a large board degrades to a partial
// result instead of the whole run being discarded:
const WORKDAY_MAX_PAGES = 50;          // mirrors smartrecruiters.mjs:13
const WORKDAY_PAGE_DELAY_MS = 300;     // politeness delay between paginated POSTs
const WORKDAY_TIME_BUDGET_MS = 20_000; // stay well under the 30s parent timeout
const WORKDAY_DEFAULT_LIMIT = 20;      // fallback when the board reports limit: 0

// B36 (docs/review/phase-9-backlog.md): the search/listing response never
// carries a description -- only the per-job detail endpoint does, and
// Workday's public posting *page* is a JS SPA (the whole reason this
// provider drives Playwright in the first place), so
// scan_boards.py's plain-GET page-fetch fallback can't scrape one either.
// Bounded by count; shares the same wall-clock deadline as pagination
// below rather than a second budget.
const WORKDAY_DETAIL_FETCH_CAP = 40;

/**
 * Resolves the effective page size from a Workday search response. Exported
 * for unit tests. `data.limit` can come back as `0` on some boards; `||`
 * (not `??`) treats any falsy limit -- 0 included -- as invalid and falls
 * back to WORKDAY_DEFAULT_LIMIT, closing the `offset += 0` infinite-loop bug
 * from B19.
 * @param {any} data
 * @returns {number}
 */
export function resolveWorkdayLimit(data) {
  return data?.limit || WORKDAY_DEFAULT_LIMIT;
}

/**
 * Paginates through Workday's search endpoint via `ctx.fetchJson`, picking
 * up after the already-collected first page. Exported for unit tests -- see
 * workday.test.mjs. Bounded by a page cap, a wall-clock time budget, and an
 * inter-page delay (all overridable so tests don't have to wait on the real
 * ones); a request failure (429, network error, or any non-ok response --
 * `ctx.fetchJson` throws on those) stops the loop and returns what has been
 * collected so far instead of discarding it.
 * @param {import('./_types.js').Context} ctx
 * @param {string} apiBase
 * @param {string} baseUrl
 * @param {string} companyName
 * @param {number} limit
 * @param {number} total
 * @param {{maxPages?: number, delayMs?: number, deadline?: number}} [opts]
 * @returns {Promise<Array<{title: string, url: string, company: string, location: string, _externalPath: string}>>}
 */
export async function paginateWorkdayJobs(ctx, apiBase, baseUrl, companyName, limit, total, opts = {}) {
  const maxPages = opts.maxPages ?? WORKDAY_MAX_PAGES;
  const delayMs = opts.delayMs ?? WORKDAY_PAGE_DELAY_MS;
  const deadline = opts.deadline ?? (Date.now() + WORKDAY_TIME_BUDGET_MS);
  const jobs = [];

  for (
    let offset = limit, pageNum = 0;
    offset < total && pageNum < maxPages;
    offset += limit, pageNum++
  ) {
    if (Date.now() >= deadline) break; // out of time budget -- return what we have

    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));

    let page2;
    try {
      page2 = await ctx.fetchJson(apiBase, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit, offset, searchText: '', appliedFacets: {} }),
      });
    } catch {
      // Rate limited (429) or other transient failure mid-pagination -- return
      // the jobs already collected instead of discarding them.
      break;
    }

    const more = Array.isArray(page2?.jobPostings) ? page2.jobPostings : [];
    for (const j of more) {
      const jobUrl = j.externalPath ? `${baseUrl}${j.externalPath}` : '';  // same fix as above
      jobs.push({
        title: j.title || '',
        url: jobUrl,
        company: companyName,
        location: j.locationsText || '',
        // Not part of the Job contract (see _types.js) -- carries the raw
        // path through to fetch()'s detail-fetch loop, which deletes it.
        _externalPath: j.externalPath || '',
      });
    }
  }

  return jobs;
}

function resolveBaseUrl(entry) {
  const url = entry.careers_url || '';
  if (!WORKDAY_HOST_RE.test(url)) return null;
  try {
    const { origin, pathname } = new URL(url);
    // Strip locale segment (/en-US/ etc.) to get the board root
    const board = pathname.replace(/^\/en-[A-Z]{2}\//, '/').replace(/\/$/, '');
    return `${origin}${board}`;
  } catch {
    return null;
  }
}

/** @type {Provider} */
export default {
  id: 'workday',

  detect(entry) {
    const base = resolveBaseUrl(entry);
    return base ? { url: base } : null;
  },

// NOTE (resume-builder, 2026-07-26): career-ops's original had a stray
// debug `page.screenshot({ path: 'workday-debug.png' })` call here that
// wrote a screenshot file to whatever the current working directory
// happened to be on every single fetch -- removed as a real bug found
// while vendoring, not a deliberate feature.
  async fetch(entry, ctx) {
    const baseUrl = resolveBaseUrl(entry);
    if (!baseUrl) throw new Error(`cannot derive board URL for ${entry.name}`);

    const deadline = Date.now() + WORKDAY_TIME_BUDGET_MS;

    let chromium;
    try {
      ({ chromium } = await import('playwright'));
    } catch {
      throw new Error(
        `workday provider requires Playwright.\n` +
        `Run: npm install playwright && npx playwright install chromium`
      );
    }

    const browser = await chromium.launch({ headless: true });
    const jobs = [];
    let apiBase = '';

    try {

      const page = await browser.newPage();
      await page.setExtraHTTPHeaders({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
      });
      // Intercept the internal Workday searchJobs XHR response
      const intercepted = new Promise((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error(`workday: XHR intercept timed out for ${entry.name}`)),
          20_000
        );

        page.on('response', async (response) => {
          const url = response.url();
          if (SEARCH_PATH_RE.test(url) && response.request().method() === 'POST') {
            clearTimeout(timer);
            try {
              const json = await response.json();
              resolve(json);
            } catch (e) {
              reject(e);
            }
          }
        });
      });

      // Navigate to the board — this triggers the XHR call automatically
      await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30_000 });

      const data = await intercepted;

      // Workday JSON shape: { jobPostings: [{ title, locationsText, externalPath, ... }] }
      const postings = Array.isArray(data?.jobPostings) ? data.jobPostings : [];

      for (const j of postings) {
        // Build the canonical job URL from the board base + externalPath.
        // NOTE (resume-builder, 2026-07-26): career-ops's original used
        // `new URL(j.externalPath, baseUrl).href` here -- externalPath
        // always starts with a leading slash (e.g. "/job/..."), and per
        // the WHatWG URL spec a leading-slash path resolves against the
        // *origin*, discarding baseUrl's own tenant-board path segment
        // (e.g. "/ASPCAWebsite"). Confirmed live: every single Workday
        // posting across every tracked company 404'd because of this --
        // plain string concatenation is what was actually intended here.
        const jobUrl = j.externalPath ? `${baseUrl}${j.externalPath}` : '';

        jobs.push({
          title: j.title || '',
          url: jobUrl,
          company: entry.name,
          location: j.locationsText || '',
          // Not part of the Job contract (see _types.js) -- carries the raw
          // path through to the detail-fetch loop below, which deletes it.
          _externalPath: j.externalPath || '',
        });
      }

      // Handle pagination — Workday returns total count and offset.
      const total = data?.total ?? postings.length;
      const limit = resolveWorkdayLimit(data);

      // Computed unconditionally (not just when paginating) -- the
      // detail-fetch loop below needs it regardless of whether this board
      // fit on a single page.
      const { origin, pathname } = new URL(baseUrl);
      const tenant = origin.match(/https?:\/\/([^.]+)\./)?.[1] ?? '';
      const board = pathname.replace(/^\/en-[A-Z]{2}\//, '/').replace(/^\//, '');
      apiBase = `${origin}/wday/cxs/${tenant}/${board}/jobs`;

      if (total > limit) {
        // Fire subsequent page requests directly through the shared HTTP
        // helper — no browser needed once we have the intercepted endpoint
        // URL pattern. paginateWorkdayJobs bounds this by a page cap, a
        // wall-clock time budget (so a large board yields a partial result
        // instead of blowing the parent's subprocess timeout and losing
        // everything), and an inter-page delay for politeness toward the
        // target site.
        const morePages = await paginateWorkdayJobs(ctx, apiBase, baseUrl, entry.name, limit, total, { deadline });
        jobs.push(...morePages);
      }
    } finally {
      await browser.close();
    }

    // B36: description detail-fetches are plain JSON requests through ctx
    // -- no Playwright needed, so these run after the browser has already
    // closed. Shares `deadline` with the pagination above rather than a
    // second budget, so the two together can't exceed
    // WORKDAY_TIME_BUDGET_MS.
    for (const job of jobs.slice(0, WORKDAY_DETAIL_FETCH_CAP)) {
      if (Date.now() >= deadline) break;
      if (!job._externalPath || !apiBase) continue;
      job.description = await fetchJobDescription(ctx, apiBase, job._externalPath);
      delete job._externalPath;
    }

    return jobs;
  },
};

/**
 * Fetches one posting's JSON detail via the same `/wday/cxs/.../jobs`
 * endpoint family (swap the trailing `/jobs` for the posting's own
 * `externalPath`, which already starts with `/job/...`) and extracts its
 * description. Best-effort: any failure returns "" rather than throwing, so
 * one bad posting doesn't drop the whole board's results.
 * @param {import('./_types.js').Context} ctx
 * @param {string} apiBase
 * @param {string} externalPath
 * @returns {Promise<string>}
 */
export async function fetchJobDescription(ctx, apiBase, externalPath) {
  try {
    const detailUrl = apiBase.replace(/\/jobs$/, '') + externalPath;
    const detail = await ctx.fetchJson(detailUrl);
    return detail?.jobPostingInfo?.jobDescription || '';
  } catch {
    return '';
  }
}
