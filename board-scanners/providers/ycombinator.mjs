// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const YC_ALGOLIA_URL =
  'https://45bwydsgqq-dsn.algolia.net/1/indexes/waas_jobs/query';
const YC_ALGOLIA_HEADERS = {
  'X-Algolia-Application-Id': '45BWYDSGQQ',
  'X-Algolia-API-Key': '182f2324f2a74c20f1883c0762cfef64',
  'Content-Type': 'application/json',
};

/** @type {Provider} */
export default {
  id: 'ycombinator',
  detect(url) {
    if (/ycombinator\.com\/companies|workatastartup\.com/i.test(url)) {
      return { provider: 'ycombinator', board: 'waas' };
    }
    return null;
  },
  async fetch(entry, ctx) {
    const query = entry.search_term || 'software engineer';
    const payload = {
      query: query,
      hitsPerPage: 25,
      facetFilters: [['job_type:full_time']],
    };

    try {
      const resp = await ctx.fetchJson(YC_ALGOLIA_URL, {
        method: 'POST',
        headers: YC_ALGOLIA_HEADERS,
        body: JSON.stringify(payload),
      });

      const hits = Array.isArray(resp?.hits) ? resp.hits : [];
      return hits.map((h) => ({
        title: h.title || 'Software Engineer',
        company: h.company_name || 'YC Startup',
        url:
          h.apply_url ||
          `https://www.workatastartup.com/jobs/${h.objectID || ''}`,
        location: h.location || (h.remote ? 'Remote' : 'San Francisco, CA'),
        posted_at: h.created_at
          ? new Date(h.created_at * 1000).toISOString()
          : new Date().toISOString(),
        description: h.description || '',
      }));
    } catch {
      return [];
    }
  },
};
