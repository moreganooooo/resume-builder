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

// A redirect loop is unambiguous, not merely a failed check: Chromium gave
// up bouncing between the same handful of URLs, which is exactly what a
// removed Greenhouse posting does (job URL -> ?error=true -> the bare
// board page -> back and forth) rather than serving a clean 404. Manually
// confirmed against a real posting (2026-08-27): the same loop that made
// Chromium raise this also made the user's own browser report "too many
// redirects" trying the same URL. Every other navigation failure (DNS,
// timeout waiting for a slow page, a transient connection reset) stays
// `uncertain` -- those really are ambiguous and can just as easily be a
// live posting having a bad moment.
const REDIRECT_LOOP_PATTERN = /ERR_TOO_MANY_REDIRECTS/;

export function classifyNavigationError(err) {
  const message = err.message.split('\n')[0];
  if (REDIRECT_LOOP_PATTERN.test(message)) {
    return {
      result: 'expired',
      code: 'redirect_loop',
      reason: `redirect loop -- browser gave up: ${message}`,
    };
  }
  return {
    result: 'uncertain',
    code: 'navigation_error',
    reason: `navigation error: ${message}`,
  };
}

/**
 * Read the page body, re-reading while it is too short to classify.
 *
 * Returns as soon as there is enough content, so a fast page pays
 * nothing and only a slow one spends the budget. `readText`/`wait` are
 * injected so this is unit-testable without a real Page.
 */
export async function pollForStableContent(readText, wait) {
  let bodyText = await readText();
  const neededPolling = bodyText.trim().length < MIN_CONTENT_CHARS;
  let waited = 0;

  while (bodyText.trim().length < MIN_CONTENT_CHARS && waited < CONTENT_POLL_BUDGET_MS) {
    await wait(CONTENT_POLL_INTERVAL_MS);
    waited += CONTENT_POLL_INTERVAL_MS;
    bodyText = await readText();
  }

  // A page that only cleared MIN_CONTENT_CHARS via polling (i.e. it was
  // still client-rendering) gets one more read to confirm the content
  // has actually settled. Measured live (2026-08-27) on a Workday
  // posting: at the first poll past the threshold, the body held only a
  // cookie-consent banner (848 chars) -- long enough to clear the bar --
  // and the real content (in this case, an expired-posting notice) did
  // not land until the very next render tick, 200ms later. A page that
  // was already long enough on the FIRST read (the overwhelming
  // majority of a sweep) skips this entirely, so it costs nothing there.
  if (neededPolling && waited < CONTENT_POLL_BUDGET_MS) {
    await wait(CONTENT_POLL_INTERVAL_MS);
    bodyText = await readText();
  }

  return bodyText;
}

const readRenderedBodyText = (page) =>
  pollForStableContent(() => readBodyText(page), (ms) => page.waitForTimeout(ms));

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
    // code matches classifyLiveness()'s vocabulary (liveness-core.mjs) so
    // a navigation failure is distinguishable from a genuine
    // classification instead of writing `code: undefined` (B42).
    const classified = classifyNavigationError(err);

    // A failed navigation (e.g. the redirect loop above) can leave the
    // shared page mid-transition to Chromium's own error page. The batch
    // sweep reuses one `page` sequentially, so calling goto() again for
    // the very next URL before that settles races against it -- observed
    // live (2026-08-27): the check immediately following a redirect-loop
    // failure came back "interrupted by another navigation", a spurious
    // verdict about the WRONG URL. Waiting for the page to settle here,
    // not at the top of the next call, is what lets this be attributed
    // to the URL that actually caused it. A fixed wait, not
    // waitForLoadState() -- that can resolve immediately if it also
    // observes the same in-flight navigation, giving no real delay.
    await page.waitForTimeout(1_000);

    return classified;
  }
}
