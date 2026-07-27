// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const FOURDAYWEEK_API_URL = 'https://4dayweek.io/api/jobs';
const FOURDAYWEEK_HEADERS = { Accept: 'application/json' };

// NOTE (resume-builder, 2026-07-26): career-ops's original read j.url,
// j.company (as a string), j.location (as a string), and j.published_at
// -- none of those fields exist in 4dayweek.io's current API response
// (confirmed live: it's j.slug + a link built from it, j.company as an
// object, j.locations as an array, j.posted as a unix timestamp). The
// provider was returning zero results unconditionally, every single
// company/tags filter checking fields that were always undefined.
// Rebuilt against the real current response shape rather than porting
// the broken field names forward. No description field in this response
// (listing-only API) -- still falls back to a page fetch, same as before.

function resolveUrl(job) {
  return job.slug ? `https://4dayweek.io/jobs/${job.slug}` : '';
}

function resolveCompany(job, fallbackName) {
  return job.company?.name || job.company_name || fallbackName;
}

function resolveLocation(job) {
  if (job.work_arrangement === 'remote') return 'Remote';
  const loc = Array.isArray(job.locations) ? job.locations[0] : null;
  if (!loc) return '';
  return [loc.city, loc.country].filter(Boolean).join(', ');
}

function resolvePostedAt(job) {
  return typeof job.posted === 'number' ? new Date(job.posted * 1000).toISOString() : '';
}

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
      .filter((j) => j.slug && j.title)
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.title || '',
        url: resolveUrl(j),
        company: resolveCompany(j, entry.name),
        location: resolveLocation(j),
        posted_at: resolvePostedAt(j),
      }));
  },
};
