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
    if (!apiUrl) throw new Error(`lever: cannot derive API URL for ${entry.name}`);
    const json = await ctx.fetchJson(apiUrl);
    if (!Array.isArray(json)) return [];
    return json
      .filter(j => !isTooOld(j.createdAt))
      .map(j => ({
        title: j.text || '',
        url: j.hostedUrl || '',
        company: entry.name,
        location: j.categories?.location || '',
        posted_at: j.createdAt ? new Date(j.createdAt).toISOString().slice(0, 10) : '',
      }));
  },
};
