/**
 * liveness-browser.mjs — Playwright browser layer for liveness checking
 *
 * Wraps liveness-core.mjs classification logic with actual page fetching.
 * Called by check-liveness.mjs. Never call directly.
 *
 * Project rule: never run Playwright in parallel — callers must sequence.
 */

import { classifyLiveness } from './liveness-core.mjs';

const NAV_TIMEOUT_MS = 15_000;
const RENDER_WAIT_MS = 1_200;

/**
 * Check whether a single URL points to an active job posting.
 *
 * @param {import('playwright').Page} page - A shared Playwright Page instance
 * @param {string} url - The job posting URL to check
 * @returns {Promise<{ result: 'active'|'expired'|'uncertain', reason: string }>}
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

    const bodyText = await page.evaluate(() => document.body?.innerText ?? '');

    // Collect visible button / link text for apply-control detection
    const applyControls = await page.evaluate(() =>
      Array.from(
        document.querySelectorAll('button, a[href], input[type="submit"]')
      ).map((el) => el.innerText?.trim() ?? el.value ?? '')
    );

    return classifyLiveness({ status, finalUrl, bodyText, applyControls });
  } catch (err) {
    // Navigation timeout or hard crash — treat as uncertain
    return {
      result: 'uncertain',
      reason: `navigation error: ${err.message.split('\n')[0]}`,
    };
  }
}
