/**
 * liveness-browser.mjs — Playwright browser layer for liveness checking
 *
 * Wraps liveness-core.mjs classification logic with actual page fetching.
 * Called by check-liveness.mjs. Never call directly.
 *
 * Project rule: never run Playwright in parallel — callers must sequence.
 */

import { classifyLiveness, MIN_CONTENT_CHARS } from './liveness-core.mjs';

const NAV_TIMEOUT_MS = 15_000;
const RENDER_WAIT_MS = 1_200;
// Client-rendered pages routinely have not painted their body by the time
// the fixed wait above elapses, and the classifier then sees nav/footer
// only. That was the single largest failure mode in the corpus: 208 of
// 364 "uncertain" verdicts were `insufficient_content`, concentrated on
// JS-rendered aggregators (jooble, jobicy, himalayas, weworkremotely) and
// Workday SPAs -- a checker limitation reported as an ambiguous posting.
// Instead of raising the fixed wait for every URL (which would add ~4s
// x 400 URLs to a sweep that already runs 15 minutes), only pages that
// come up short get polled, and only until they have enough to classify.
const CONTENT_POLL_BUDGET_MS = 5_000;
const CONTENT_POLL_INTERVAL_MS = 500;

const readBodyText = (page) => page.evaluate(() => document.body?.innerText ?? '');

/**
 * Read the page body, re-reading while it is too short to classify.
 *
 * Returns as soon as there is enough content, so a fast page pays
 * nothing and only a slow one spends the budget.
 */
async function readRenderedBodyText(page) {
  let bodyText = await readBodyText(page);
  let waited = 0;
  while (bodyText.trim().length < MIN_CONTENT_CHARS && waited < CONTENT_POLL_BUDGET_MS) {
    await page.waitForTimeout(CONTENT_POLL_INTERVAL_MS);
    waited += CONTENT_POLL_INTERVAL_MS;
    bodyText = await readBodyText(page);
  }
  return bodyText;
}

/**
 * Check whether a single URL points to an active job posting.
 *
 * @param {import('playwright').Page} page - A shared Playwright Page instance
 * @param {string} url - The job posting URL to check
 * @returns {Promise<{ result: 'active'|'likely_active'|'expired'|'blocked'|'uncertain', reason: string }>}
 */
export async function checkUrlLiveness(page, url) {
  let status = 0;
  let finalUrl = url;

  try {
    const response = await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout: NAV_TIMEOUT_MS,
    });

    status = response?.status() ?? 0;
    finalUrl = page.url();

    // Allow dynamic content a moment to render
    await page.waitForTimeout(RENDER_WAIT_MS);

    const bodyText = await readRenderedBodyText(page);

    // Collect visible button / link text for apply-control detection
    const applyControls = await page.evaluate(() =>
      Array.from(
        document.querySelectorAll('button, a[href], input[type="submit"]')
      ).map((el) => el.innerText?.trim() ?? el.value ?? '')
    );

    return classifyLiveness({ status, finalUrl, bodyText, applyControls });
  } catch (err) {
    // Navigation timeout or hard crash — treat as uncertain. code
    // matches classifyLiveness()'s vocabulary (liveness-core.mjs) so a
    // navigation failure is distinguishable from a genuine
    // classification instead of writing `code: undefined` (B42).
    return {
      result: 'uncertain',
      code: 'navigation_error',
      reason: `navigation error: ${err.message.split('\n')[0]}`,
    };
  }
}
