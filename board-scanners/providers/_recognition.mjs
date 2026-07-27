/**
 * _recognition.mjs — Shared utility to identify an ATS provider from a URL.
 */

const RECOGNITION_RULES = [
  { id: 'greenhouse', pattern: /greenhouse\.io/i },
  { id: 'lever', pattern: /lever\.co/i },
  { id: 'ashby', pattern: /ashbyhq\.com/i },
  { id: 'workable', pattern: /workable\.com/i },
  { id: 'workday', pattern: /myworkdayjobs\.com/i },
  { id: 'smartrecruiters', pattern: /smartrecruiters\.com/i },
  { id: 'bamboohr', pattern: /bamboohr\.com/i },
  { id: 'jobvite', pattern: /jobvite\.com/i },
  { id: 'icims', pattern: /icims\.com/i },
  { id: 'jazzhr', pattern: /applytojob\.com/i },
];

/**
 * Identifies the provider ID from a URL string.
 * @param {string} url 
 * @returns {string|null}
 */
export function recognizeProvider(url) {
  if (!url) return null;
  for (const rule of RECOGNITION_RULES) {
    if (rule.pattern.test(url)) return rule.id;
  }
  return null;
}

/**
 * Normalizes a company name into a domain-friendly slug.
 */
export function slugify(name) {
  return name.toLowerCase()
    .replace(/[^a-z0-9]/g, '')
    .replace(/\s+/g, '');
}
