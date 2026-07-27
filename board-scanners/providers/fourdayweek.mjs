// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const FOURDAYWEEK_API_URL = 'https://4dayweek.io/api/jobs';
const FOURDAYWEEK_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(job, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const haystack = `${job.title || ''} ${job.category || ''} ${(job.tags || []).join(' ')}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'fourdayweek',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const json = await ctx.fetchJson(FOURDAYWEEK_API_URL, { headers: FOURDAYWEEK_HEADERS });
    const jobs = Array.isArray(json) ? json : Array.isArray(json?.jobs) ? json.jobs : [];
    return jobs
      .filter((j) => j.url && j.title)
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.title || '',
        url: j.url,
        company: j.company || entry.name,
        location: j.location || '',
        posted_at: j.published_at || '',
      }));
  },
};
