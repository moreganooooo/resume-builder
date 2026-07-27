// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const HIMALAYAS_API_URL = 'https://himalayas.app/jobs/api';
const HIMALAYAS_HEADERS = { Accept: 'application/json' };
const PAGE_SIZE = 20;

function matchesSearchTerm(job, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const haystack = `${job.title || ''} ${(job.categories || []).join(' ')}`.toLowerCase();
  return haystack.includes(needle);
}

function formatPostedAt(pubDate) {
  if (!pubDate) return '';
  // Seconds-resolution epochs top out around 1e10 until year 2286; treat
  // anything past 1e12 as already-milliseconds rather than misreading it.
  const ms = pubDate > 1e12 ? pubDate : pubDate * 1000;
  const d = new Date(ms);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString();
}

/** @type {Provider} */
export default {
  id: 'himalayas',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const url = `${HIMALAYAS_API_URL}?limit=${PAGE_SIZE}&offset=0`;
    const json = await ctx.fetchJson(url, { headers: HIMALAYAS_HEADERS });
    const jobs = Array.isArray(json?.jobs) ? json.jobs : [];
    return jobs
      .filter((j) => j.applicationLink && j.title)
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.title || '',
        url: j.applicationLink,
        company: j.companyName || entry.name,
        location: Array.isArray(j.locationRestrictions) ? j.locationRestrictions.join(', ') : '',
        posted_at: formatPostedAt(j.pubDate),
        // The listing API already returns a full description -- himalayas.app's
        // own posting pages sit behind a Cloudflare managed challenge that
        // blocks a plain HTTP fetch, so this is the only reliable source of
        // body text for this provider (2026-07-26).
        description: j.description || j.excerpt || '',
      }));
  },
};
