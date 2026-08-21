// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const ADZUNA_API_BASE_URL = 'https://api.adzuna.com/v1/api/jobs';
const ADZUNA_HEADERS = { Accept: 'application/json' };
const ADZUNA_COUNTRY_CODE = 'us';
const ADZUNA_RESULTS_PER_PAGE = 25;

/** @type {Provider} */
export default {
  id: 'adzuna',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const appId = process.env.ADZUNA_APP_ID;
    const appKey = process.env.ADZUNA_APP_KEY;
    if (!appId || !appKey) {
      throw new Error('missing ADZUNA_APP_ID / ADZUNA_APP_KEY environment variables');
    }
    const params = new URLSearchParams({
      app_id: appId,
      app_key: appKey,
      results_per_page: String(ADZUNA_RESULTS_PER_PAGE),
    });
    if (entry.search_term) params.set('what', entry.search_term);
    // Location comes from scan_filters.yml's `location:` block via
    // scan_boards.py. Adzuna's `distance` is KILOMETRES, so the
    // configured mile radius is converted -- sending miles verbatim
    // would quietly search a radius 1.6x too small.
    if (entry.location) {
      params.set('where', entry.location);
      if (entry.radius_miles) {
        params.set('distance', String(Math.max(1, Math.round(Number(entry.radius_miles) * 1.60934))));
      }
    }
    const url = `${ADZUNA_API_BASE_URL}/${ADZUNA_COUNTRY_CODE}/search/1?${params.toString()}`;
    const json = await ctx.fetchJson(url, { headers: ADZUNA_HEADERS });
    const jobs = Array.isArray(json?.results) ? json.results : [];
    return jobs
      .filter((j) => j.redirect_url && j.title)
      .map((j) => ({
        title: j.title || '',
        url: j.redirect_url,
        company: j.company?.display_name || entry.name,
        location: j.location?.display_name || '',
        posted_at: j.created || '',
        // The search API already returns a full description -- Adzuna's
        // own redirect_url (a click-tracking landing page, not the raw
        // posting) blocks plain HTTP requests with a 403, so this is the
        // only reliable source of body text for this provider (2026-07-26).
        description: j.description || '',
      }));
  },
};
