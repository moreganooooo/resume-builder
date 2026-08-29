// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Ashby provider — hits the public posting-api endpoint.
// Auto-detects from careers_url pattern `https://jobs.ashbyhq.com/<slug>`.
// Falls back to entry.api if careers_url uses a custom domain (e.g. Zapier, Miro).
//
// Ashby location shape: { locationName: string, locationSublocationName: string|null }
// We surface locationName as the canonical location string.

function resolveApiUrl(entry) {
  // Prefer explicit api field — handles custom-domain careers pages
  if (entry.api) return entry.api;
  const url = entry.careers_url || '';
  const match = url.match(/jobs\.ashbyhq\.com\/([^/?#]+)/);
  if (!match) return null;
  return `https://api.ashbyhq.com/posting-api/job-board/${match[1]}?includeCompensation=true`;
}

function resolveLocation(loc) {
  if (!loc) return '';
  if (typeof loc === 'string') return loc;
  // Ashby returns { locationName, locationSublocationName }
  return loc.locationName || '';
}

// A remote-eligible posting often lists a dozen countries under
// `secondaryLocations`, each carrying a structured `address.postalAddress.
// addressCountry` -- the ONLY place that shows a "Remote" posting is
// actually restricted to specific non-US countries. Dropping this (as the
// old single-string `resolveLocation` did) let an international-only role
// report location: "Warsaw" -- a bare city name the location filter's
// international-country check can't recognize -- instead of naming any of
// the 13 other countries it was equally open to. Folding country names in
// gives the same filter something concrete to reject on.
function resolveLocationWithCountries(job) {
  const primary = resolveLocation(job.location);
  const countries = [];
  const primaryCountry = job.address?.postalAddress?.addressCountry;
  if (primaryCountry) countries.push(primaryCountry);
  for (const secondary of job.secondaryLocations || []) {
    const country = secondary?.address?.postalAddress?.addressCountry;
    if (country && !countries.includes(country)) countries.push(country);
  }
  const parts = [primary, ...countries].filter(Boolean);
  return [...new Set(parts)].join('; ');
}

/** @type {Provider} */
export default {
  id: 'ashby',

  detect(entry) {
    const apiUrl = resolveApiUrl(entry);
    return apiUrl ? { url: apiUrl } : null;
  },

  async fetch(entry, ctx) {
    const apiUrl = resolveApiUrl(entry);
    if (!apiUrl) throw new Error(`cannot derive API URL for ${entry.name}`);
    const json = await ctx.fetchJson(apiUrl);
    const jobs = Array.isArray(json?.jobs) ? json.jobs : [];
    // url is the cross-provider dedup key -- a posting with no jobUrl would
    // otherwise emit url: '', colliding with every other jobUrl-less posting.
    return jobs.filter(j => j.jobUrl).map(j => ({
      title: j.title || '',
      url: j.jobUrl || '',
      company: entry.name,
      location: resolveLocationWithCountries(j),
      posted_at: j.publishedDate || '',
      description: j.descriptionPlain || j.descriptionHtml || '',
    }));
  },
};
