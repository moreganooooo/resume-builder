// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Dayforce provider — the candidate portal's own JSON search API.
// Auto-detects from careers_url patterns like:
//   https://jobs.dayforcehcm.com/en-US/<clientNamespace>/<jobBoardCode>
//   https://jobs.dayforcehcm.com/en-US/<clientNamespace>   (board defaults to CANDIDATEPORTAL)
//
// The portal is a Next.js SPA (a plain GET renders "Loading" and nothing
// else), but its search endpoint returns every posting WITH its full
// description, 25 per page. The endpoint 403s any POST lacking a next-auth
// CSRF pair -- the X-CSRF-TOKEN header plus the __Host-next-auth.csrf-token
// cookie -- which the public, unauthenticated /api/auth/csrf hands out.
// Verified live 2026-09-15 against ACV Auctions (194 postings): no page
// load, browser User-Agent, or login needed; without the header it's 403.
// That cookie is why this provider calls fetchWithTimeout directly instead
// of ctx.fetchJson, which returns only the body.

import { fetchWithTimeout } from './_http.mjs';

const DAYFORCE_HOST = 'jobs.dayforcehcm.com';
const DEFAULT_BOARD = 'CANDIDATEPORTAL';
const CULTURE_RE = /^[a-z]{2}-[a-z]{2}$/i;
const SLUG_RE = /^[a-z0-9_-]+$/i;

// Same shape as workday.mjs's bounds: a large board degrades to a partial
// result instead of being killed. Each page is ~2s server-side (ACV's 8
// pages took 18s), so the budget sits under scan_boards.py's
// PROVIDER_TIMEOUT_SECONDS["dayforce"] with room for one in-flight request.
const DAYFORCE_MAX_PAGES = 40;
const DAYFORCE_PAGE_DELAY_MS = 300;
const DAYFORCE_TIME_BUDGET_MS = 35_000;

/**
 * Parses a Dayforce careers_url into its portal coordinates, or null when it
 * isn't one. Every segment is validated because two of them are
 * interpolated into the API path. Exported for unit tests.
 * @param {any} entry
 * @returns {{culture: string, namespace: string, board: string} | null}
 */
export function resolvePortal(entry) {
  const raw = typeof entry?.careers_url === 'string' ? entry.careers_url : '';
  if (!raw) return null;
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:' || parsed.hostname !== DAYFORCE_HOST) return null;
  const [culture, namespace, board] = parsed.pathname.split('/').filter(Boolean);
  if (!culture || !CULTURE_RE.test(culture) || !namespace || !SLUG_RE.test(namespace)) return null;
  if (board && !SLUG_RE.test(board)) return null;
  return { culture, namespace, board: board || DEFAULT_BOARD };
}

/** Exported for unit tests. */
export function buildSearchBody(portal, offset) {
  return {
    clientNamespace: portal.namespace,
    jobBoardCode: portal.board,
    cultureCode: portal.culture,
    distanceUnit: 0,
    paginationStart: offset,
  };
}

/**
 * Reduces Set-Cookie headers to a Cookie request header (name=value only).
 * Exported for unit tests.
 * @param {string[]} setCookies
 */
export function cookieHeader(setCookies) {
  return (setCookies || [])
    .map(c => String(c).split(';')[0].trim())
    .filter(pair => pair.includes('='))
    .join('; ');
}

/**
 * Parse one page of a Dayforce jobposting/search response. Exported for
 * unit tests.
 *
 * Dayforce returns:
 *   { jobPostings: [{ jobPostingId, jobTitle, jobDescription (HTML),
 *     postingLocations: [{ formattedAddress }], hasVirtualLocation,
 *     postingStartTimestampUTC }], offset, count, maxCount }
 *
 * - url: rebuilt from the portal coordinates and a numeric jobPostingId --
 *   the response carries no URL of its own.
 * - location: several locations are joined with " OR ", the compound form
 *   location_filter scores by NEAREST, so a multi-site posting is judged by
 *   its closest site rather than dropped as unresolvable.
 * - is_remote: set only when hasVirtualLocation is true; false does not
 *   mean onsite, and an absent flag is kept by the workplace gate.
 * @param {any} json
 * @param {string} companyName
 * @param {{culture: string, namespace: string, board: string}} portal
 */
export function parseDayforceResponse(json, companyName, portal) {
  const postings = json?.jobPostings;
  if (!Array.isArray(postings)) return [];
  return postings.map(p => {
    const id = p?.jobPostingId;
    const url = Number.isInteger(id)
      ? `https://${DAYFORCE_HOST}/${portal.culture}/${portal.namespace}/${portal.board}/jobs/${id}`
      : '';
    const locations = Array.isArray(p?.postingLocations)
      ? p.postingLocations.map(l => l?.formattedAddress).filter(Boolean)
      : [];
    /** @type {any} */
    const job = {
      title: (p?.jobTitle || '').trim(),
      url,
      company: companyName,
      location: locations.join(' OR '),
      description: p?.jobDescription || '',
    };
    if (p?.postingStartTimestampUTC) job.posted_at = p.postingStartTimestampUTC;
    if (p?.hasVirtualLocation === true) job.is_remote = true;
    return job;
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/** @type {Provider} */
export default {
  id: 'dayforce',

  detect(entry) {
    const portal = resolvePortal(entry);
    return portal ? { url: `https://${DAYFORCE_HOST}/api/geo/${portal.namespace}/jobposting/search` } : null;
  },

  async fetch(entry, _ctx, opts = {}) {
    const portal = resolvePortal(entry);
    if (!portal) throw new Error(`cannot derive Dayforce portal for ${entry.name}`);
    const delayMs = opts.delayMs ?? DAYFORCE_PAGE_DELAY_MS;
    const deadline = Date.now() + (opts.timeBudgetMs ?? DAYFORCE_TIME_BUDGET_MS);

    const csrfRes = await fetchWithTimeout(`https://${DAYFORCE_HOST}/api/auth/csrf`, { redirect: 'error' });
    const cookie = cookieHeader(csrfRes.headers.getSetCookie());
    const { csrfToken } = /** @type {any} */ (await csrfRes.json());
    if (!csrfToken) throw new Error('Dayforce /api/auth/csrf returned no csrfToken');

    const searchUrl = `https://${DAYFORCE_HOST}/api/geo/${portal.namespace}/jobposting/search`;
    const jobs = [];
    let offset = 0;
    for (let page = 0; page < DAYFORCE_MAX_PAGES; page++) {
      if (page > 0) {
        if (Date.now() + delayMs >= deadline) break;
        await sleep(delayMs);
      }
      const res = await fetchWithTimeout(searchUrl, {
        method: 'POST',
        redirect: 'error',
        headers: {
          'content-type': 'application/json',
          accept: 'application/json',
          'x-csrf-token': csrfToken,
          cookie,
        },
        body: JSON.stringify(buildSearchBody(portal, offset)),
      });
      const json = /** @type {any} */ (await res.json());
      const batch = parseDayforceResponse(json, entry.name, portal);
      jobs.push(...batch);
      const count = Number(json?.count) || batch.length;
      offset += count;
      if (!count || offset >= (Number(json?.maxCount) || 0)) break;
    }
    return jobs;
  },
};
