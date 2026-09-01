// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Workable provider — hits the public markdown feed at /<slug>/jobs.md.
// Workable's documented JSON API requires an auth token; the markdown feed
// is the only no-auth public surface. Auto-detects from careers_url pattern
// `https://apply.workable.com/<slug>` OR the equivalent `<slug>.workable.com`
// custom-subdomain form (added 2026-07-26 -- found live: a real tracked
// company, Doist, uses the subdomain form and career-ops's original never
// handled it, so it never resolved to any provider at all). Both forms
// resolve to the same apply.workable.com/<slug>/jobs.md feed URL. A
// tracked_companies entry can also set `provider: workable` explicitly to
// bypass detection.

const ALLOWED_WORKABLE_HOSTS = new Set(['apply.workable.com']);
const RESERVED_WORKABLE_SUBDOMAINS = new Set(['apply', 'www', 'api']);

// B36 (docs/review/phase-9-backlog.md): the jobs.md table above has no
// description column, but each row's own [View] link (before this parser
// strips it down to the human-facing URL below) already points at a
// `<id>.md` detail page -- a plain markdown document, no second API or
// per-ATS selector needed. Bounded by count since a large board can list
// hundreds of postings and each one is an extra request.
const WORKABLE_DETAIL_FETCH_CAP = 40;
const WORKABLE_DETAIL_TIME_BUDGET_MS = 15_000;

function assertWorkableUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`invalid URL: ${url}`);
  }
  if (parsed.protocol !== 'https:') throw new Error(`URL must use HTTPS: ${url}`);
  if (!ALLOWED_WORKABLE_HOSTS.has(parsed.hostname)) {
    throw new Error(`untrusted hostname "${parsed.hostname}" — must be one of: ${[...ALLOWED_WORKABLE_HOSTS].join(', ')}`);
  }
  return url;
}

function resolveFeedUrl(entry) {
  const raw = typeof entry.careers_url === 'string' ? entry.careers_url : '';
  if (!raw) return null;
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:') return null;

  if (parsed.hostname === 'apply.workable.com') {
    const slug = parsed.pathname.split('/').filter(Boolean)[0];
    return slug ? `https://apply.workable.com/${slug}/jobs.md` : null;
  }

  if (parsed.hostname.endsWith('.workable.com')) {
    const subdomain = parsed.hostname.slice(0, -'.workable.com'.length);
    if (subdomain && !subdomain.includes('.') && !RESERVED_WORKABLE_SUBDOMAINS.has(subdomain)) {
      return `https://apply.workable.com/${subdomain}/jobs.md`;
    }
  }

  return null;
}

/** @type {Provider} */
export default {
  id: 'workable',

  detect(entry) {
    const feedUrl = resolveFeedUrl(entry);
    return feedUrl ? { url: feedUrl } : null;
  },

  async fetch(entry, ctx) {
    const feedUrl = resolveFeedUrl(entry);
    if (!feedUrl) throw new Error(`cannot derive feed URL for ${entry.name}`);
    assertWorkableUrl(feedUrl);
    // redirect:'error' prevents SSRF via server-side redirects; combined with
    // assertWorkableUrl above it guarantees the final hostname stays in the allowlist.
    const text = await ctx.fetchText(feedUrl, { redirect: 'error' });
    const jobs = parseWorkableMarkdown(text, entry.name);

    const deadline = Date.now() + WORKABLE_DETAIL_TIME_BUDGET_MS;
    for (const job of jobs.slice(0, WORKABLE_DETAIL_FETCH_CAP)) {
      if (Date.now() >= deadline) break;
      if (!job._detailUrl) continue;
      job.description = await fetchPostingDescription(ctx, job._detailUrl);
      delete job._detailUrl;
    }

    return jobs;
  },
};

/**
 * Fetches one posting's own `.md` detail page and returns it as-is -- it's
 * already plain markdown, not HTML, so no extraction step is needed before
 * scan_boards.py's _html_to_text() (which passes plain text through
 * unchanged). Best-effort: any failure returns "" so one bad posting
 * doesn't drop the whole board's results.
 * @param {import('./_types.js').Context} ctx
 * @param {string} detailUrl
 * @returns {Promise<string>}
 */
async function fetchPostingDescription(ctx, detailUrl) {
  try {
    return await ctx.fetchText(detailUrl, { redirect: 'error' });
  } catch {
    return '';
  }
}

// Workable's current column layout, used when a feed carries no header
// row. Keys are the header labels, lowercased; values are the index into
// a row split on "|" (which yields a leading empty cell, so Title is 1).
const COLUMN_DEFAULTS = { title: 1, location: 3, type: 4, salary: 5 };

/**
 * Parse Workable's public markdown feed. Exported as a named export for unit
 * tests. The feed exposes a table:
 *   | Title | Department | Location | Type | Salary | Posted | Details |
 * where `Details` holds a markdown link
 *   [View](https://apply.workable.com/<slug>/jobs/view/<id>.md)
 * URLs are validated against `https://apply.workable.com/` — off-domain or
 * non-HTTPS [View] links are skipped (not emitted).
 *
 * B36 (docs/review/phase-9-backlog.md): the same [View] link, before the
 * `.md` suffix is stripped for the human-facing `url`, is itself a fetchable
 * per-posting markdown detail page -- kept as `_detailUrl` (not part of the
 * Job contract; fetch()'s detail-fetch loop consumes and deletes it) so the
 * description doesn't have to come from a second guess at the URL shape.
 *
 * @param {string} text — markdown body
 * @param {string} companyName — value to write into job.company
 * @returns {Array<{title: string, url: string, company: string, location: string, _detailUrl: string}>}
 */
export function parseWorkableMarkdown(text, companyName) {
  if (typeof text !== 'string') return [];
  const lines = text.split('\n');
  // Resolve columns BY NAME from the header row rather than by fixed
  // position. The positions below are Workable's current layout, but a
  // feed that drops "Department" or inserts a column shifts every index
  // after it -- and the failure is SILENT and plausible: Location reads
  // the Type column, so a posting lands with location "Full-time",
  // which the radius filter cannot resolve and therefore KEEPS. A
  // mismapped field is worse than a missing one, because nothing
  // downstream can tell it is wrong.
  // Copied, not aliased: this is mutated below, and COLUMN_DEFAULTS is
  // module-level -- one feed without a Department column would otherwise
  // reshape the defaults for every later company in the same run.
  const header = { ...COLUMN_DEFAULTS };
  const headerLine = lines.find(
    (l) => l.startsWith('|') && !l.includes('[View]') && /\|\s*Title\s*\|/i.test(l),
  );
  if (headerLine) {
    const names = headerLine.split('|').map((c) => c.trim().toLowerCase());
    for (const key of Object.keys(COLUMN_DEFAULTS)) {
      const at = names.indexOf(key);
      // -1 means this feed omits the column entirely; leaving the
      // default would read whatever now sits in that slot, so record
      // the absence instead and let the field come back empty.
      header[key] = at;
    }
  }

  const jobs = [];
  for (const line of lines) {
    if (!line.startsWith('|') || !line.includes('[View]')) continue;
    const cols = line.split('|').map(c => c.trim());
    const col = (name) => (header[name] >= 0 ? cols[header[name]] || '' : '');
    // No minimum column count: that guard was the same fixed-layout
    // assumption in another form, and it silently discarded every row of
    // any feed with fewer columns than Workable's current default. A row
    // is usable when it has a title and a resolvable [View] link;
    // everything else is optional by design.
    const title = col('title');
    if (!title || title === 'Title') continue;
    const location = col('location');
    const urlMatch = line.match(/\[View\]\(([^)]+)\)/);
    let detailUrl = urlMatch ? urlMatch[1] : '';
    if (!detailUrl) continue;  // skip rows with no resolvable URL (e.g., malformed [View] link)
    let url = detailUrl.endsWith('.md') ? detailUrl.slice(0, -3) : detailUrl;

    // Validate both URLs — must parse as https://apply.workable.com/...
    try {
      const parsedUrl = new URL(url);
      const parsedDetailUrl = new URL(detailUrl);
      if (parsedUrl.protocol !== 'https:' || parsedUrl.hostname !== 'apply.workable.com') continue;
      if (parsedDetailUrl.protocol !== 'https:' || parsedDetailUrl.hostname !== 'apply.workable.com') continue;
      url = parsedUrl.href;
      detailUrl = parsedDetailUrl.href;
    } catch {
      continue;
    }

    // Absent on shorter rows, which is fine -- the gate keeps an
    // unstated type.
    const employmentType = col('type');
    // Usually blank -- Workable renders the column whether or not the
    // employer filled it in -- and free text when present, which
    // compensation.py's prose parser handles.
    const salary = col('salary');

    jobs.push({ title, url, location, company: companyName, employment_type: employmentType, compensation: salary, _detailUrl: detailUrl });
  }
  return jobs;
}
