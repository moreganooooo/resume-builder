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
  async fetch(entry, _ctx) {
    const baseUrl = resolveBaseUrl(entry);
    if (!baseUrl) throw new Error(`workday: cannot derive board URL for ${entry.name}`);

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
        // Build the canonical job URL from the board base + externalPath
        const jobUrl = j.externalPath
          ? new URL(j.externalPath, baseUrl).href
          : '';

        jobs.push({
          title: j.title || '',
          url: jobUrl,
          company: entry.name,
          location: j.locationsText || '',
        });
      }

      // Handle pagination — Workday returns total count and offset
      const total = data?.total ?? postings.length;
      const limit = data?.limit ?? 20;

      if (total > limit) {
        // Fire subsequent page requests directly via fetch — no browser needed
        // once we have the intercepted endpoint URL pattern
        const { origin, pathname } = new URL(baseUrl);
        const tenant = origin.match(/https?:\/\/([^.]+)\./)?.[1] ?? '';
        const board = pathname.replace(/^\/en-[A-Z]{2}\//, '/').replace(/^\//, '');
        const apiBase = `${origin}/wday/cxs/${tenant}/${board}/jobs`;

        for (let offset = limit; offset < total; offset += limit) {
          const res = await fetch(apiBase, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limit, offset, searchText: '', appliedFacets: {} }),
          });
          const page2 = await res.json();
          const more = Array.isArray(page2?.jobPostings) ? page2.jobPostings : [];
          for (const j of more) {
            const jobUrl = j.externalPath ? new URL(j.externalPath, baseUrl).href : '';
            jobs.push({
              title: j.title || '',
              url: jobUrl,
              company: entry.name,
              location: j.locationsText || '',
            });
          }
        }
      }
    } finally {
      await browser.close();
    }

    return jobs;
  },
};
