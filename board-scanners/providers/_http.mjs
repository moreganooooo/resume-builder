// HTTP transport helpers shared across providers.
// Files prefixed with _ are never loaded as providers by scan.mjs.

const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_MIN_GAP_MS = 0;
// Identifies real, contactable traffic -- names this repo (not career-ops,
// which this was vendored from and which this repo has since diverged from)
// at a version this repo actually has, and doesn't lead with a
// browser-impersonation prefix. See B26, docs/review/phase-9-backlog.md.
const DEFAULT_USER_AGENT = 'resume-builder/1.0 (+https://github.com/moreganooooo/resume-builder)';

const DEFAULT_MAX_RETRIES = 2; // up to 3 attempts total
const RETRY_BASE_MS = 500;
const RETRY_MAX_MS = 8_000;

// Per-provider defaults for requests that fire many of them in one
// provider.fetch() call and have no pacing of their own -- see B26/B36.
// `run_provider.mjs` looks a provider id up here and bakes the result into
// the ctx it hands that provider, so individual provider files don't each
// have to remember to pass options on every call. Providers not listed here
// get DEFAULT_TIMEOUT_MS / no forced gap (single-request providers, or ones
// like workday.mjs that already pace their own pagination loop internally).
export const PROVIDER_HTTP_CONFIG = {
  // Fires up to 60 near-simultaneous per-item fetches (Promise.all) --
  // minGapMs serializes them through the shared queue below instead of
  // hammering HN's API all at once.
  hackernews: { minGapMs: 150 },
  // Paginates the listing (previously unpaced) and, as of B36, does one
  // extra detail fetch per posting for a real description.
  smartrecruiters: { minGapMs: 200 },
  // Own pagination loop already paces itself (WORKDAY_PAGE_DELAY_MS); this
  // gap only governs the new per-job description detail fetches (B36),
  // which share the same ctx.
  workday: { minGapMs: 250 },
  // New per-posting .md detail fetch (B36) -- one extra request per listed job.
  workable: { minGapMs: 150 },
};

function parseRetryAfterMs(header) {
  if (!header) return null;
  const seconds = Number(header);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const dateMs = Date.parse(header);
  if (!Number.isNaN(dateMs)) return Math.max(0, dateMs - Date.now());
  return null;
}

function isRetryableStatus(status) {
  return status === 429 || (status >= 500 && status <= 599);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchOnce(url, { timeoutMs, headers, method, body, redirect }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method,
      headers: { 'user-agent': DEFAULT_USER_AGENT, ...headers },
      body,
      redirect,
      signal: controller.signal,
    });
    if (!res.ok) {
      const responseText = await res.text().catch(() => '');
      const snippet = responseText.replace(/\s+/g, ' ').trim().slice(0, 300);
      const err = new Error(snippet ? `HTTP ${res.status}: ${snippet}` : `HTTP ${res.status}`);
      err.status = res.status;
      err.body = responseText;
      err.retryAfterMs = parseRetryAfterMs(res.headers.get('retry-after'));
      throw err;
    }
    return res;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fetches `url`, retrying transient failures (429, 5xx, or a network-level
 * error other than our own timeout) with exponential backoff -- honoring
 * `Retry-After` when the response sends one instead of guessing. A request
 * that times out (AbortError) is NOT retried: it already spent `timeoutMs`
 * once, and every provider call here runs inside run_provider.mjs's own
 * subprocess timeout (scan_boards.NODE_TIMEOUT_SECONDS = 30s), so doubling
 * a slow request's wait is more likely to blow that budget than to help.
 */
export async function fetchWithTimeout(url, {
  timeoutMs = DEFAULT_TIMEOUT_MS, headers = {}, method = 'GET', body = null, redirect = 'follow',
  maxRetries = DEFAULT_MAX_RETRIES,
} = {}) {
  let targetUrl = url;
  const scrapeDoKey = process.env.SCRAPEDO_API_KEY;

  for (let attempt = 0; ; attempt++) {
    try {
      return await fetchOnce(targetUrl, { timeoutMs, headers, method, body, redirect });
    } catch (err) {
      // Anti-Bot Proxy Fallback Tier: If 403 / Bot Blocked and Scrape.do key is available, fallback to proxy
      if (err.status === 403 && scrapeDoKey && !targetUrl.includes('api.scrape.do')) {
        targetUrl = `https://api.scrape.do?token=${scrapeDoKey}&url=${encodeURIComponent(url)}`;
        continue;
      }

      const retryable = err.name !== 'AbortError' && (err.status === undefined || isRetryableStatus(err.status));
      if (!retryable || attempt >= maxRetries) throw err;
      const jitter = process.env.NODE_ENV === 'test' ? 0 : Math.floor(Math.random() * 100);
      const backoffMs = Math.min(RETRY_BASE_MS * 2 ** attempt, RETRY_MAX_MS) + jitter;
      await sleep(err.retryAfterMs ?? backoffMs);
    }
  }
}

export async function fetchJson(url, opts = {}) {
  const res = await fetchWithTimeout(url, opts);
  return await res.json();
}

export async function fetchText(url, opts = {}) {
  const res = await fetchWithTimeout(url, opts);
  return await res.text();
}

/**
 * Builds the context object handed to every provider.fetch(). Optionally
 * takes a provider id to apply that provider's PROVIDER_HTTP_CONFIG
 * defaults (timeoutMs / minGapMs) to every fetchJson/fetchText call made
 * through the returned ctx -- still overridable per-call via explicit opts.
 * When minGapMs is set, calls through this ctx are fully serialized (one in
 * flight at a time, at least minGapMs apart) via a closure-local queue, the
 * same pattern websearch.mjs used to keep as dead, per-process-only state --
 * this is the one shared place it actually works, since a single ctx is
 * exactly one provider.fetch() call's lifetime.
 * @param {string} [providerId]
 * @returns {import('./_types.js').Context}
 */
export function makeHttpCtx(providerId) {
  const config = (providerId && PROVIDER_HTTP_CONFIG[providerId]) || {};
  const defaultTimeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const minGapMs = config.minGapMs ?? DEFAULT_MIN_GAP_MS;

  let queue = Promise.resolve();
  function paced(fn) {
    if (!minGapMs) return fn;
    return (...args) => {
      const jitter = process.env.NODE_ENV === 'test' ? 0 : Math.floor(Math.random() * 30);
      const gap = minGapMs + jitter;
      const run = queue.then(() => fn(...args));
      queue = run.then(() => sleep(gap), () => sleep(gap));
      return run;
    };
  }

  return {
    transport: 'http',
    fetchJson: paced((url, opts = {}) => fetchJson(url, { timeoutMs: defaultTimeoutMs, ...opts })),
    fetchText: paced((url, opts = {}) => fetchText(url, { timeoutMs: defaultTimeoutMs, ...opts })),
  };
}

