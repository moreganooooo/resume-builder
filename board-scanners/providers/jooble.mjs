// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */
/** @typedef {import('./_types.js').Job} Job */

/**
 * jooble.mjs -- Jooble's free aggregator API.
 *
 * The only board provider here with real LOCAL coverage: everything else
 * in BOARD_PROVIDERS is remote-first, which is exactly the gap the
 * radius filter exists to close. Jooble indexes regional aggregators
 * (Lensa and friends) and takes a location + radius server-side.
 *
 * Auth: JOOBLE_API_KEY in the active profile's .env. The key is part of
 * the PATH (POST /api/<key>), not a header -- their design, not ours.
 *
 * Two hard-won details about their API:
 *
 * 1. `location` wants a CITY NAME, not a ZIP. Posting "14068" returns
 *    totalCount 0 with a 200 status -- a silent empty result, not an
 *    error -- while "Getzville, NY" returns thousands. scan_boards.py
 *    therefore sends city/state from the configured origin, and this
 *    provider refuses to run on a ZIP-only origin rather than quietly
 *    returning nothing.
 *
 * 2. `snippet` is a TRUNCATED teaser (~275 chars, routinely cut
 *    mid-word), and it is all the text this API will ever give. The
 *    posting page behind `link` answers 403 to any fetch, browser
 *    User-Agent included, and does not redirect to the employer, so
 *    scan_boards.py's _fetch_posting_text fallback cannot recover the
 *    real description either.
 *
 *    ~275 chars clears MIN_DESCRIPTION_CHARS (200), so these postings
 *    would otherwise ship looking complete while being far too thin to
 *    tailor a resume against. That is why each job carries
 *    `description_is_teaser: true` -- scan_boards.py honors the flag and
 *    marks the posting thin regardless of length, so the scan report
 *    says so out loud instead of the shortfall being discovered later,
 *    in a bad tailored resume.
 */

const API_HOST = 'https://jooble.org/api';

/** Strips the HTML fragments Jooble embeds in `snippet`. */
function cleanSnippet(snippet) {
  return String(snippet || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

/** ISO-8601 with a fractional-second tail Jooble returns; keep the date. */
function normalizeUpdated(updated) {
  const text = String(updated || '');
  const match = text.match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : '';
}

/** @type {Provider} */
const provider = {
  id: 'jooble',

  async fetch(entry, ctx) {
    const key = process.env.JOOBLE_API_KEY;
    if (!key) {
      throw new Error('JOOBLE_API_KEY is not set in the active profile\'s .env');
    }

    // Supplied by scan_boards.py from the profile's `location:` block.
    const location = String(entry.location || '').trim();
    if (!location) {
      throw new Error(
        'jooble needs a city/state location -- set city and state under `location:` '
        + 'in scan_filters.yml (a ZIP alone returns no results from this API)'
      );
    }

    const payload = {
      keywords: String(entry.search_term || 'marketing').trim(),
      location,
    };
    if (entry.radius_miles) {
      payload.radius = String(entry.radius_miles);
    }

    const data = await ctx.fetchJson(`${API_HOST}/${key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const rawJobs = (data && data.jobs) || [];
    /** @type {Job[]} */
    const jobs = [];
    for (const raw of rawJobs) {
      const title = String(raw.title || '').trim();
      const url = String(raw.link || '').trim();
      if (!title || !url) continue;

      jobs.push({
        title,
        url,
        company: String(raw.company || '').trim(),
        location: String(raw.location || '').trim(),
        description: cleanSnippet(raw.snippet),
        // See the header note: this is a teaser, and saying so is the
        // whole point -- length alone would misreport it as sufficient.
        description_is_teaser: true,
        posted_at: normalizeUpdated(raw.updated),
      });
    }
    return jobs;
  },
};

export default provider;
