// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const ADZUNA_API_BASE_URL = 'https://api.adzuna.com/v1/api/jobs';
const ADZUNA_HEADERS = { Accept: 'application/json' };
const ADZUNA_COUNTRY_CODE = 'us';
const ADZUNA_RESULTS_PER_PAGE = 25;

/**
 * Builds a "City, State" location from Adzuna's structured `area`.
 *
 * Adzuna's `display_name` is "City, County" ("Buffalo, Erie County"),
 * which no state-based resolver can parse -- scripts/geo_distance.py
 * reads the part after the comma as a state, finds "Erie County" is not
 * one, and gives up. Every Adzuna posting then landed in the permissive
 * "unresolvable, keep for review" bucket and bypassed the commute radius
 * entirely, which is how gig listings 35 miles out survived a 25-mile
 * filter.
 *
 * `area` is ordered [country, state, county, city], so the city is the
 * last element and the state the second. Falls back to display_name when
 * the array is too short to be trusted.
 */
function formatLocation(loc) {
  const area = Array.isArray(loc?.area) ? loc.area : [];
  if (area.length >= 3) {
    const city = area[area.length - 1];
    const state = area[1];
    if (city && state && city !== state) return `${city}, ${state}`;
  }
  return loc?.display_name || '';
}

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
        location: formatLocation(j.location),
        posted_at: j.created || '',
        // Adzuna HARD-TRUNCATES to exactly 500 characters with a
        // trailing ellipsis. Measured 2026-08-21: 75 of 75 postings
        // across three unrelated queries came back at exactly 500 chars,
        // every one ending in "…". An earlier comment here claimed this
        // was a full description; it never was.
        //
        // There is no recovery path, which is why the teaser flag is set
        // rather than the text being re-fetched: redirect_url is a
        // click-tracking landing page that answers 403 to plain HTTP
        // (2026-07-26), so scan_boards' _fetch_posting_text cannot reach
        // the real posting either. Same shape as jooble.mjs.
        description: j.description || '',
        description_is_teaser: true,
      }));
  },
};
