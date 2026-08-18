// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const LEVELS_API_URL = 'https://www.levels.fyi/api/jobs/search';
const LEVELS_HEADERS = {
  Accept: 'application/json',
  'User-Agent':
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
};

/** @type {Provider} */
export default {
  id: 'levelsfyi',
  detect(url) {
    if (/levels\.fyi\/jobs/i.test(url)) {
      return { provider: 'levelsfyi', board: 'levels' };
    }
    return null;
  },
  async fetch(entry, ctx) {
    const query = entry.search_term || 'Software Engineer';
    const targetUrl = `${LEVELS_API_URL}?query=${encodeURIComponent(query)}`;

    try {
      const resp = await ctx.fetchJson(targetUrl, { headers: LEVELS_HEADERS });
      const listings = Array.isArray(resp?.jobs)
        ? resp.jobs
        : Array.isArray(resp)
        ? resp
        : [];

      return listings.map((j) => ({
        title: j.title || j.jobTitle || 'Software Engineer',
        company: j.company || j.companyName || entry.name || 'Tech Company',
        url:
          j.url ||
          j.applyUrl ||
          `https://www.levels.fyi/jobs?jobId=${j.id || ''}`,
        location: j.location || 'Remote',
        posted_at: j.postedDate || new Date().toISOString(),
        description: j.description || j.summary || '',
      }));
    } catch {
      return [];
    }
  },
};
