// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Lever provider — hits the public postings endpoint.
// Auto-detects from careers_url pattern `https://jobs.lever.co/<slug>`.

// Postings older than this are silently dropped — likely filled or forgotten.
const MAX_AGE_DAYS = 45;
const MAX_AGE_MS = MAX_AGE_DAYS * 24 * 60 * 60 * 1000;

function resolveApiUrl(entry) {
  if (entry.api) {
    const match = entry.api.match(/api\.lever\.co\/v0\/postings\/([^/?#]+)/);
    if (match) return entry.api;
  }
  const url = entry.careers_url || '';
  const match = url.match(/jobs\.lever\.co\/([^/?#]+)/);
  if (!match) return null;
  return `https://api.lever.co/v0/postings/${match[1]}`;
}

// `categories.allLocations` carries every eligible location for a
// multi-country remote posting; `categories.location` alone is often just
// "Remote" (same gap found and fixed in ashby.mjs/greenhouse.mjs,
// 2026-08-27).
function resolveLocation(categories) {
  const primary = categories?.location || '';
  const all = Array.isArray(categories?.allLocations) ? categories.allLocations : [];
  const parts = [primary, ...all].filter(Boolean);
  return [...new Set(parts)].join('; ');
}

function isTooOld(createdAt) {
  if (!createdAt) return false; // missing field — let it through, Playwright will catch it
  // Lever returns Unix ms timestamps
  const ts = typeof createdAt === 'number' ? createdAt : Number(createdAt);
  if (isNaN(ts)) return false;
  return Date.now() - ts > MAX_AGE_MS;
}

/** @type {Provider} */
export default {
  id: 'lever',

  detect(entry) {
    const apiUrl = resolveApiUrl(entry);
    return apiUrl ? { url: apiUrl } : null;
  },

  async fetch(entry, ctx) {
    const apiUrl = resolveApiUrl(entry);
    if (!apiUrl) throw new Error(`cannot derive API URL for ${entry.name}`);
    const json = await ctx.fetchJson(apiUrl);
    if (!Array.isArray(json)) return [];
    return json
      .filter(j => !isTooOld(j.createdAt))
      .map(j => ({
        title: j.text || '',
        url: j.hostedUrl || '',
        company: entry.name,
        location: resolveLocation(j.categories),
        posted_at: j.createdAt ? new Date(j.createdAt).toISOString().slice(0, 10) : '',
        // descriptionPlain already includes openingPlain as its prefix;
        // additionalPlain (closing/EEO section) is genuinely separate
        // content, not included in descriptionPlain -- confirmed live
        // against a real posting (2026-07-26).
        description: [j.descriptionPlain, j.additionalPlain].filter(Boolean).join('\n\n'),
        // Employer-authored free text, not an enum: real values include
        // "Full Time - Union" and "Full Time / On Site". Passed through
        // verbatim for the same reason.
        employment_type: j.categories?.commitment || '',
      }));
  },
};
