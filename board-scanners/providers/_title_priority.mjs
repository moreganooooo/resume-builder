// Detail-fetch ordering shared by providers whose listing carries no
// description, so each posting costs one extra request (workday, icims).
// Files prefixed with _ are never loaded as providers by scan.mjs.
//
// Those providers can describe only as many postings as their time budget
// allows, and a large board lists far more than that (M&T 240, Moog 400,
// measured 2026-09-15). Fetched in listing order, the budget went to
// whatever came first -- mostly titles scan_ats.py's title filter then
// discards -- while the relevant postings came back empty, were never
// written, and were skipped the same way on every later scan.
//
// scan_ats.py passes the profile's title_filter in as entry._title_filter.
// This only REORDERS: Python still applies the real filter to every
// posting, so a mismatch between the two copies costs a description, never
// a posting.

/**
 * Rank 0: contains a positive keyword and no negative one (what Python
 * keeps). Rank 1: no negative keyword -- includes every title when the
 * profile has no positive list. Rank 2: hits a negative keyword.
 * @param {string} title
 * @param {{positive?: string[], negative?: string[]} | undefined} filter
 */
export function titleRank(title, filter) {
  const lower = String(title || '').toLowerCase();
  const positive = (filter?.positive || []).map(k => String(k).toLowerCase());
  const negative = (filter?.negative || []).map(k => String(k).toLowerCase());
  if (negative.some(k => lower.includes(k))) return 2;
  if (positive.length && positive.some(k => lower.includes(k))) return 0;
  return 1;
}

/**
 * Returns a new array, stable-sorted by titleRank. Without a filter the
 * order is unchanged.
 * @template {{title: string}} T
 * @param {T[]} jobs
 * @param {{positive?: string[], negative?: string[]} | undefined} filter
 * @returns {T[]}
 */
export function prioritizeByTitle(jobs, filter) {
  if (!filter) return jobs.slice();
  return jobs
    .map((job, index) => ({ job, index, rank: titleRank(job.title, filter) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ job }) => job);
}
