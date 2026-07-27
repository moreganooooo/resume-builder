// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// NOTE: this endpoint's URL ends in `/rss` but returns JSON, not XML —
// confirmed against ever-jobs's PowertoflyApiResponse type ({ items, status }).
const POWERTOFLY_API_URL = 'https://powertofly.com/jobs/rss';
const POWERTOFLY_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(item, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const categories = Array.isArray(item.categories) ? item.categories.join(' ') : '';
  const haystack = `${item.title || ''} ${categories}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'powertofly',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const json = await ctx.fetchJson(POWERTOFLY_API_URL, { headers: POWERTOFLY_HEADERS });
    const items = Array.isArray(json?.items) ? json.items : [];
    return items
      .filter((item) => (item.link || item.guid) && item.title)
      .filter((item) => matchesSearchTerm(item, entry.search_term))
      .map((item) => ({
        title: item.title || '',
        url: item.link || item.guid,
        company: entry.name, // PowerToFly items don't expose a company field
        location: item.job_location || '',
        posted_at: item.published_on || '',
        description: item.description || '',
      }));
  },
};
