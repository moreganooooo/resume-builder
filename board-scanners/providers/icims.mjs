// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// iCIMS provider — the hosted career portal's own iframe pages.
// Auto-detects from careers_url patterns like:
//   https://careers-<company>.icims.com/
//   https://<anything>.icims.com/jobs/search
//
// iCIMS has no public JSON API, but its portal serves plain server-rendered
// HTML when asked for the iframe variant (?in_iframe=1): the search page
// lists 20 postings per page (?pr=N, zero-based), and each posting page
// embeds a schema.org JobPosting JSON-LD block carrying the full HTML
// description, datePosted, employmentType and a structured address.
// Verified live 2026-09-15 against Calspan (31 postings over 2 pages, each
// posting page ~0.2s). No browser, cookie or login needed.

import { prioritizeByTitle } from './_title_priority.mjs';

const ICIMS_HOST_RE = /^[a-z0-9-]+\.icims\.com$/i;
const ICIMS_MAX_PAGES = 25;           // 500 postings -- well past any tracked board
const ICIMS_TIME_BUDGET_MS = 35_000;  // under scan_boards.PROVIDER_TIMEOUT_SECONDS["icims"]

/**
 * The portal origin for an iCIMS careers_url, or null when it isn't one.
 * The hostname is validated because it is interpolated into every request.
 * Exported for unit tests.
 * @param {any} entry
 * @returns {string | null}
 */
export function resolveOrigin(entry) {
  const raw = typeof entry?.careers_url === 'string' ? entry.careers_url : '';
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:' || !ICIMS_HOST_RE.test(parsed.hostname)) return null;
  return parsed.origin;
}

function decodeEntities(text) {
  return String(text)
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

/**
 * Posting links on one search page, in page order, deduped by id. The
 * anchor's title attribute reads "<id> - <Job Title>". Exported for unit
 * tests.
 * @param {string} html
 * @param {string} origin
 * @returns {Array<{id: string, url: string, title: string}>}
 */
export function parseSearchPage(html, origin) {
  const host = new URL(origin).host;
  const escapedHost = host.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const anchorRe = new RegExp(
    `<a\\b[^>]*href="https://${escapedHost}(/jobs/(\\d+)/[^"?]*/job)[^"]*"[^>]*>`,
    'gi',
  );
  const seen = new Set();
  const postings = [];
  for (const m of html.matchAll(anchorRe)) {
    const [tag, path, id] = m;
    if (seen.has(id)) continue;
    seen.add(id);
    const titleAttr = tag.match(/\btitle="([^"]*)"/i)?.[1] || '';
    const title = decodeEntities(titleAttr.replace(/^\s*\d+\s*-\s*/, '')).trim();
    postings.push({ id, url: `${origin}${path}`, title });
  }
  return postings;
}

/**
 * The JobPosting JSON-LD object on a posting page, or null. Exported for
 * unit tests.
 * @param {string} html
 */
export function extractJobPosting(html) {
  const blockRe = /<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi;
  for (const m of html.matchAll(blockRe)) {
    let data;
    try {
      data = JSON.parse(m[1]);
    } catch {
      continue;
    }
    for (const node of Array.isArray(data) ? data : [data]) {
      if (node?.['@type'] === 'JobPosting') return node;
    }
  }
  return null;
}

/**
 * "City, ST" per jobLocation, joined with " OR " -- the compound form
 * location_filter scores by NEAREST. Exported for unit tests.
 * @param {any} posting
 */
export function formatLocation(posting) {
  const places = Array.isArray(posting?.jobLocation) ? posting.jobLocation : [posting?.jobLocation];
  const names = places
    .map(p => p?.address)
    .filter(Boolean)
    .map(a => [a.addressLocality, a.addressRegion].filter(Boolean).join(', '))
    .filter(Boolean);
  return [...new Set(names)].join(' OR ');
}

/** @type {Provider} */
export default {
  id: 'icims',

  detect(entry) {
    const origin = resolveOrigin(entry);
    return origin ? { url: `${origin}/jobs/search` } : null;
  },

  async fetch(entry, ctx, opts = {}) {
    const origin = resolveOrigin(entry);
    if (!origin) throw new Error(`cannot derive iCIMS portal for ${entry.name}`);
    const deadline = Date.now() + (opts.timeBudgetMs ?? ICIMS_TIME_BUDGET_MS);

    // Paginate until a page adds nothing new: iCIMS answers a page past
    // the end with an empty list rather than an error.
    const listed = [];
    const seen = new Set();
    for (let pr = 0; pr < ICIMS_MAX_PAGES && Date.now() < deadline; pr++) {
      const html = await ctx.fetchText(`${origin}/jobs/search?ss=1&in_iframe=1&pr=${pr}`);
      const fresh = parseSearchPage(html, origin).filter(p => !seen.has(p.id));
      if (!fresh.length) break;
      for (const p of fresh) seen.add(p.id);
      listed.push(...fresh);
    }

    const jobs = listed.map(p => ({ title: p.title, url: p.url, company: entry.name, location: '' }));

    // A posting left undescribed when the budget runs out still carries
    // its title and URL; scan_ats falls back to a plain page fetch for it.
    for (const job of prioritizeByTitle(jobs, entry._title_filter)) {
      if (Date.now() >= deadline) break;
      let posting;
      try {
        posting = extractJobPosting(await ctx.fetchText(`${job.url}?in_iframe=1`));
      } catch {
        continue;
      }
      if (!posting) continue;
      /** @type {any} */ (job).description = posting.description || '';
      job.title = decodeEntities(posting.title || job.title).trim();
      job.location = formatLocation(posting);
      if (posting.datePosted) /** @type {any} */ (job).posted_at = posting.datePosted;
      if (posting.employmentType) {
        /** @type {any} */ (job).employment_type = Array.isArray(posting.employmentType)
          ? posting.employmentType.join(', ')
          : String(posting.employmentType);
      }
      if (posting.jobLocationType === 'TELECOMMUTE') /** @type {any} */ (job).is_remote = true;
    }
    return jobs;
  },
};
