// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const HN_API_BASE = 'https://hacker-news.firebaseio.com/v0';
const HN_JOB_STORIES_URL = `${HN_API_BASE}/jobstories.json`;
const HN_ITEM_URL = (id) => `${HN_API_BASE}/item/${id}.json`;
const MAX_STORIES_TO_SCAN = 60;

function matchesSearchTerm(item, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const haystack = `${item.title || ''} ${item.text || ''}`.toLowerCase();
  return haystack.includes(needle);
}

function extractCompanyName(title) {
  if (!title) return '';
  const hiringMatch = title.match(/^(.+?)\s+is\s+hiring/i);
  if (hiringMatch) return hiringMatch[1].trim();
  const separatorMatch = title.match(/^(.+?)\s*[-|]\s+/);
  if (separatorMatch) return separatorMatch[1].trim();
  return '';
}

/** @type {Provider} */
export default {
  id: 'hackernews',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const ids = await ctx.fetchJson(HN_JOB_STORIES_URL);
    const candidateIds = Array.isArray(ids) ? ids.slice(0, MAX_STORIES_TO_SCAN) : [];
    const items = await Promise.all(
      candidateIds.map((id) => ctx.fetchJson(HN_ITEM_URL(id)).catch(() => null)),
    );
    return items
      .filter((item) => item && item.title && item.url)
      .filter((item) => matchesSearchTerm(item, entry.search_term))
      .map((item) => ({
        title: item.title || '',
        url: item.url,
        company: extractCompanyName(item.title) || entry.name,
        location: '',
        posted_at: item.time ? new Date(item.time * 1000).toISOString() : '',
        // Usually empty -- HN "hiring" stories with an external `url` rarely
        // also carry HN's own self-text `text` field, but free when present.
        description: item.text || '',
      }));
  },
};
