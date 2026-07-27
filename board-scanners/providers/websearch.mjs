// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// NOTE (resume-builder, 2026-07-26): career-ops's original called
// recognizeProvider(r.url) below without ever importing it -- a real bug
// (ReferenceError on every single search result, silently breaking the
// 'promote a sweep-discovered company to a direct-API provider' path).
// Added the missing import here rather than carrying the crash forward.
import { recognizeProvider } from './_recognition.mjs';

// Brave Search provider — handles entries with `scan_method: websearch`.
// Fires the entry's `scan_query` at the Brave Web Search API and extracts
// job listings from the results.
//
// Required env var: BRAVE_API_KEY
// Free tier: https://api.search.brave.com (2,000 queries/month, 1 req/sec)
//
// Each result is returned in the standard provider format:
//   { title, url, company, location }
//
// Location is not reliably available from search snippets, so it defaults
// to empty string — the location filter in scan.mjs will pass empty locations
// through (by design), and the title filter handles the rest.

const BRAVE_API_URL = 'https://api.search.brave.com/res/v1/web/search';
const BRAVE_API_KEY = process.env.BRAVE_API_KEY;

// Sequential queue with a 100ms gap — ~10 req/sec, well under the paid plan's
// 50 req/sec limit. Keeps a small buffer in case of clock jitter.
const RATE_LIMIT_MS = 100;
let queue = Promise.resolve();

function enqueue(fn) {
  const next = queue.then(() => fn()).then(
    result => new Promise(resolve => setTimeout(() => resolve(result), RATE_LIMIT_MS)),
    err    => new Promise((_, reject) => setTimeout(() => reject(err),  RATE_LIMIT_MS)),
  );
  queue = next.then(() => {}, () => {}); // keep queue moving even on error
  return next;
}

// Domains that never contain direct job postings — aggregators, content sites,
// listicles, review sites, social networks, freelance platforms, etc.
// When a new aggregator slips through, add it here.
const BLOCKED_DOMAINS = new Set([
  // Social / professional networks
  'linkedin.com', 'twitter.com', 'x.com', 'facebook.com',
  'instagram.com', 'youtube.com', 'tiktok.com', 'reddit.com', 'quora.com',

  // Major job boards / aggregators
  'indeed.com', 'glassdoor.com', 'ziprecruiter.com', 'monster.com',
  'careerbuilder.com', 'simplyhired.com', 'dice.com', 'theladders.com',
  'snagajob.com', 'usajobs.gov', 'clearancejobs.com',

  // Salary / review sites
  'salary.com', 'payscale.com', 'levels.fyi',

  // Remote-specific aggregators
  'flexjobs.com', 'remote.co', 'weworkremotely.com', 'remoteok.com',
  'remoterocketship.com', 'dailyremote.com', 'virtualvocations.com',
  'justremote.co', 'workingnomads.com', 'nodesk.co', 'remotefront.com',
  'jobspresso.co', 'remotive.com', 'remotehub.com', 'remoteleaf.com',
  'remoteco.io', 'workremotely.io',

  // Tech / startup job boards
  'himalayas.app', 'wellfound.com', 'angel.co', 'builtin.com',
  'builtinnyc.com', 'builtinboston.com', 'builtinchicago.com',
  'builtinla.com', 'builtinsf.com', 'builtinaustin.com',
  'builtinseattle.com', 'builtincolorado.com',
  'startup.jobs', 'workatastartup.com',

  // AI / smart aggregators
  'lensa.com', 'lensa.ai', 'jobright.ai', 'jobright.io',
  'tarta.ai', 'talentify.io', 'jobgether.com',

  // General aggregators
  'jobleads.com', 'jobleads.de', 'jooble.org', 'jobsora.com',
  'neuvoo.com', 'trovit.com', 'adzuna.com', 'jobrapido.com',
  'joblist.com', 'getwork.com', 'careerjet.com', 'jobserve.com',
  'jobspider.com', 'jobvertise.com', 'jobs2careers.com',
  'brightcrowd.com', 'jobcase.com', 'recruit.net',
  'jobberman.com', 'jobillico.com', 'workopolis.com',
  'kickstartremote.com', 'jobomas.com', 'jobatus.com',

  // Freelance platforms
  'upwork.com', 'freelancer.com', 'fiverr.com', 'toptal.com', 'guru.com',

  // Sector-specific boards that surface other companies\' listings
  'edtechjobs.io', 'edtech.com', 'edjoin.org',

  // Content / media sites
  'crunchbase.com', 'pitchbook.com', 'techcrunch.com', 'forbes.com',
  'businessinsider.com', 'fastcompany.com', 'inc.com', 'wired.com',
  'medium.com', 'substack.com', 'wikipedia.org', 'wikihow.com',

  // Software / review sites sometimes indexed for job content
  'g2.com', 'capterra.com', 'trustpilot.com', 'yelp.com',
  'hubspot.com', 'salesforce.com',

  // Specific false-positive domains caught in earlier runs
  'neighborhoods.com',
]);

// URL path segments that strongly indicate a real job posting page.
const JOB_PATH_SIGNALS = [
  '/job', '/jobs', '/career', '/careers', '/opening', '/openings',
  '/position', '/positions', '/apply', '/application', '/listing',
  '/vacancy', '/vacancies', '/hire', '/hiring', '/work-with-us',
  '/work_with_us', '/join', '/join-us', '/join_us', '/opportunities',
];

// URL path segments that strongly indicate non-job content.
const CONTENT_PATH_SIGNALS = [
  '/blog', '/news', '/article', '/articles', '/post', '/posts',
  '/guide', '/guides', '/resource', '/resources', '/learn',
  '/tutorial', '/tutorials', '/review', '/reviews', '/report',
  '/reports', '/podcast', '/webinar', '/ebook', '/whitepaper',
  '/press', '/media', '/about', '/pricing', '/product', '/features',
  '/solutions', '/customers', '/case-study', '/case_study',
  '/best-', '/top-', '/how-to', '/what-is',
];

// Title patterns that indicate an aggregator surfacing another company's job.
const AGGREGATOR_TITLE_PATTERNS = [
  /\bjob at\b/i,
  /\bjobs at\b/i,
  /\bposition at\b/i,
  /\bopening at\b/i,
  /\bvia\s+lensa\b/i,
  /\|\s*lensa\s*$/i,
  /\blensa\b/i,
  /\bJobright\b/i,
  /\bTalentify\b/i,
  /\bJooble\b/i,
  /\bAdzuna\b/i,
  /\bNeuvoo\b/i,
  /\bJobgether\b/i,
  /\bRemote Rocketship\b/i,
  /\bDailyRemote\b/i,
  /\bVirtual Vocations\b/i,
  // "[Remote Job]" bracket tag used by aggregators
  /\[Remote Job\]/i,
  /\[Remote\]/i,
  // "@CompanyName" at-mention format used by aggregators
  /@[A-Z][a-zA-Z\s]+$/,
  // Category/listing pages masquerading as job postings
  /^Remote \w[\w\s]* Jobs?$/i,     // "Remote Email Marketing Jobs"
  /^\d+\s+\w+ Jobs?$/i,            // "297 Marketing Jobs"
  /\ud83d\udde8|\ud83e\udde8|\u{1F9E8}/u, // emoji flags common in spam titles
];

/**
 * Returns true if the title looks like a direct company job (not aggregator noise).
 * @param {string} title
 * @returns {boolean}
 */
function isDirectJobTitle(title) {
  return !AGGREGATOR_TITLE_PATTERNS.some(pattern => pattern.test(title));
}

/**
 * Returns true if the URL looks like a real job posting.
 * @param {string} rawUrl
 * @returns {boolean}
 */
function isJobUrl(rawUrl) {
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return false;
  }

  const domain = parsed.hostname.replace(/^www\./, '');

  if (BLOCKED_DOMAINS.has(domain)) return false;
  for (const blocked of BLOCKED_DOMAINS) {
    if (domain.endsWith('.' + blocked)) return false;
  }

  const path = parsed.pathname.toLowerCase();
  if (CONTENT_PATH_SIGNALS.some(s => path.includes(s))) return false;
  if (JOB_PATH_SIGNALS.some(s => path.includes(s))) return true;
  return true;
}

/** @type {Provider} */
export default {
  id: 'websearch',

  detect(entry) {
    const scan_method = /** @type {any} */ (entry).scan_method;
    const scan_query  = /** @type {any} */ (entry).scan_query;
    if (scan_method === 'websearch' && scan_query) {
      return { url: BRAVE_API_URL };
    }
    return null;
  },

  async fetch(entry, _ctx) {
    if (!BRAVE_API_KEY) {
      throw new Error(
        'websearch: BRAVE_API_KEY is not set. Add it to your .env file.\n' +
        '  Get a free key at: https://api.search.brave.com'
      );
    }

    const query = /** @type {any} */ (entry).scan_query;
    if (!query) throw new Error(`websearch: no scan_query defined for ${entry.name}`);

    const params = new URLSearchParams({
      q: query,
      count: '20',
      search_lang: 'en',
      country: 'us',
      safesearch: 'moderate',
      freshness: 'pm',  // past month — keeps results recent
    });

    const json = await enqueue(async () => {
      const response = await fetch(`${BRAVE_API_URL}?${params}`, {
        headers: {
          'Accept': 'application/json',
          'Accept-Encoding': 'gzip',
          'X-Subscription-Token': BRAVE_API_KEY,
        },
      });
      if (!response.ok) {
        throw new Error(
          `websearch: Brave API error ${response.status} for "${entry.name}" — ${await response.text()}`
        );
      }
      return response.json();
    });

    const results = /** @type {any[]} */ (json?.web?.results || []);

    return results
      .filter(r => r.url && r.title && isJobUrl(r.url) && isDirectJobTitle(r.title))
      .map(r => {
        const urlCompany = extractCompanyFromUrl(r.url);
        const recognizedProvider = recognizeProvider(r.url);

        // For sweeps, prefer the URL-extracted company name.
        // For tracked companies, use entry.name as the source of truth.
        const companyName = (/** @type {any} */(entry)._isSweep && urlCompany) ? urlCompany : entry.name;
        
        return {
          title: cleanTitle(r.title, companyName),
          url: r.url,
          company: companyName,
          location: extractLocation(r.description || r.extra_snippets?.[0] || ''),
          _promotedPortal: recognizedProvider ? { provider: recognizedProvider, url: r.url } : null
        };
      });
  },
};

/**
 * @param {string} rawUrl
 * @returns {string|null}
 */
function extractCompanyFromUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    const host = url.hostname.replace(/^www\./, '');
    const path = url.pathname.split('/').filter(Boolean);

    // Greenhouse: boards.greenhouse.io/company or job-boards.greenhouse.io/company
    if ((host === 'greenhouse.io' || host.endsWith('.greenhouse.io')) && path.length >= 1) {
      return capitalize(path[0]);
    }
    // Lever: jobs.lever.co/company
    if (host === 'jobs.lever.co' && path.length >= 1) {
      return capitalize(path[0]);
    }
    // Ashby: jobs.ashbyhq.com/company
    if (host === 'jobs.ashbyhq.com' && path.length >= 1) {
      return capitalize(path[0]);
    }
    // Workable: apply.workable.com/company
    if (host === 'apply.workable.com' && path.length >= 1) {
      return capitalize(path[0]);
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * @param {string} str
 * @returns {string}
 */
function capitalize(str) {
  if (!str) return str;
  return str.split(/[-_]/).map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

/**
 * @param {string} raw
 * @param {string} companyName
 * @returns {string}
 */
function cleanTitle(raw, companyName) {
  let cleaned = raw;
  if (companyName) {
    cleaned = cleaned.replace(new RegExp(`\\s*[-|]\\s*${escapeRegex(companyName)}.*$`, 'i'), '');
  }
  return cleaned
    .replace(/\s*[-|]\s*(Jobs|Careers|Job Board|Greenhouse|Lever|Ashby|LinkedIn|Indeed|Glassdoor|ZipRecruiter|Workable).*$/i, '')
    .trim();
}

/**
 * @param {string} snippet
 * @returns {string}
 */
function extractLocation(snippet) {
  const remoteMatch = snippet.match(/\b(remote|fully remote|work from anywhere)\b/i);
  if (remoteMatch) return 'Remote';
  // NOTE (resume-builder, 2026-07-26): this used to also try a generic
  // capitalized-word regex as a location guess when "remote" wasn't
  // found -- confirmed live it was matching arbitrary capitalized words
  // in the snippet ("Partnering", "You", "Explore", "Give"), never real
  // locations, contradicting this function's own stated intent ("Location
  // is not reliably available from search snippets, so it defaults to
  // empty string" -- see the module header comment). Removed rather than
  // ported broken; empty string lets the location filter treat it the
  // same permissive way as any other missing-location listing.
  return '';
}

/**
 * @param {string} str
 * @returns {string}
 */
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
