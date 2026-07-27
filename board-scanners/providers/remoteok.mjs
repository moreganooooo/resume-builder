// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const REMOTEOK_API_URL = 'https://remoteok.com/api';
const REMOTEOK_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(job, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const haystack = `${job.position || ''} ${(job.tags || []).join(' ')}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'remoteok',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const json = await ctx.fetchJson(REMOTEOK_API_URL, { headers: REMOTEOK_HEADERS });
    const jobs = Array.isArray(json) ? json.slice(1) : []; // first element is API metadata, not a job
    return jobs
      .filter((j) => j && j.position && (j.apply_url || j.url))
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.position || '',
        url: j.apply_url || j.url,
        company: j.company || entry.name,
        location: j.location || '',
        posted_at: j.date || '',
        description: j.description || '',
      }));
  },
};
