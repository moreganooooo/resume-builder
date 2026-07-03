# Morgan Escott – Complete Resume Design System

## Overview

This report consolidates all known rules, preferences, and processes that govern how to evaluate roles, generate, format, and tailor Morgan Escott’s resumes and related materials. It merges guidance from Claude and Gemini sessions into a single, canonical specification for Morgan’s resume system.[^1][^2][^3][^4]

***

## Core Resume Philosophy (15 Standing Rules)

1. **Decide professional identity before writing.** Fill in the sentence: “I am a [X] who helps organizations through [Y]” before touching the resume, and only keep content that supports that identity.[^3][^4]
2. **Build around the future role, not the past career.** Lead with evidence that proves Morgan can do what this employer needs; everything else is supporting context.[^4]
3. **Every bullet must pass the “Who cares?” test.** If a hiring manager’s reason to care is not obvious, rewrite the bullet; “Managed Salesforce data” fails, “Recovered 3M in dormant pipeline through CRM audits and reactivation workflows” passes.[^3][^4]
4. **Show systems, not tasks.** Use systems language (frameworks, infrastructure, programs) rather than task language (“ran campaigns,” “wrote emails”), especially for senior roles.[^4]
5. **Metrics are king; adjectives are noise.** Replace “excellent/successful/outstanding” with specific, credible numbers like open rates, reply rates, and revenue impact.[^3][^4]
6. **Put the strongest material first within each role.** Order bullets as (1) most relevant to this job, (2) most impressive, (3) most unique; never bury the headline.[^4]
7. **Mirror the employer’s language for ATS.** Use the JD’s exact phrasing for core terms (e.g., “lifecycle marketing,” not “customer communications”) across Summary, Skills, and bullets.[^4]
8. **Don’t waste space on assumed qualities.** Do not list generic soft skills (communication, teamwork, adaptability); use space to show scale, technical depth, and strategic ownership.[^4]
9. **Repeat differentiators deliberately.** Reuse real differentiators—K‑12 audience expertise, Salesforce administration, Outreach.io implementation, lifecycle systems thinking, training/enablement infrastructure, CRM operations—across Summary, Skills, and bullets where truly relevant.[^3][^4]
10. **Summary is positioning, not biography.** It must answer who she is, what she specializes in, and what value she creates, with no filler like “results‑oriented” or “seeking opportunities.”[^4]
11. **Skills sections reinforce identity.** Skills are evidence for the stated identity, not a tool dumping ground; lead with Lifecycle/CRM for lifecycle roles, not design tools.[^4]
12. **Think like the hiring manager.** Evaluate whether the resume dissolves their core anxieties (e.g., “Can she run CRM? Does she think strategically or just execute?”) and adjust content to remove those doubts.[^3][^4]
13. **Treat the bullet bank as LEGO, not prose inspiration.** Always start from existing curated bullets and variants rather than writing net‑new text when a suitable, verified version exists.[^3][^4]
14. **Relevance beats impressiveness.** When space forces cuts, remove the most impressive but irrelevant item before removing a relevant but modest one.[^4]
15. **Optimize for one reaction.** The target response is “She’s exactly the kind of person we need,” not “she’s done a lot” or “she’s smart.” Edits should serve that reaction alone.[^4]

***

## Role Evaluation and When to Generate a Resume

### Archetype Detection and Evidence Priorities

Morgan’s pipeline uses `modes/profile.md` and `config/profile.yml` to detect the role archetype and decide what evidence to foreground.[^3]

- **Email lifecycle:** prioritize campaign metrics, segmentation logic, Outreach.io depth, testing mindset.[^3]
- **Sales enablement:** prioritize Content Committee, library scale, training systems, playbooks, governance.[^3]
- **B2B content:** prioritize agency training, journalism foundation, voice/brand work, campaign strategy.[^3]
- **Marketing operations:** prioritize Salesforce hygiene, reporting, QA, territory analytics, pipeline cleanup, process docs.[^3]
- **Generalist:** prioritize cross‑functional range, adaptability, and practical execution.[^3]

During evaluation, the system explicitly distinguishes:

- **Title mismatch vs capability mismatch.** Lack of a perfect marketing title doesn’t reduce fit if the work itself matches the role.[^3]
- **Channel vs skill mis‑alignment.** Sales experience doesn’t imply a cold‑calling persona when the strength is written strategy and systems.[^3]
- **Adjacency rules.** Outbound sequences can count as lifecycle campaigns when mechanics align; HTML familiarity doesn’t imply email developer fit.[^3]

### Evaluation Pipeline and Scoring

A full evaluation (Batch mode) runs Blocks A–G (role summary, CV match, level, compensation, customization plan, interview plan, posting legitimacy) and then computes a weighted score.[^3]

- Weighted dimensions include CV match, North Star alignment, remote quality, level fit, estimated compensation, growth trajectory, speed, tool fit, company reputation, and cultural signals.[^3]
- Final labels: **Apply, Consider, Research first, Skip** must reflect the full context, not only the numeric score.[^3]

### When to Generate a Tailored Resume

- Tailored ATS‑ready resume generation is reserved for roles with an evaluation score **≥ 4.0**, or 3.5–3.9 when there is a clear strategic reason to stretch.[^5]
- The system must not claim a resume exists when PDF generation fails; tracker entries and file paths must match reality.[^2][^5]

***

## Mandatory Research and Truth‑Testing Before Writing

Before generating any resume, the system must perform a structured research pass:[^4][^3]

### Source Files That Must Be Read

1. `cv.md` – canonical career history, titles, dates, and baseline content.[^4]
2. `config/profile.yml` – archetypes, proof points, compensation targets, superpowers, and narrative preferences.[^4]
3. `data/bullet-bank.md` – curated bullets with tags and preference notes; the primary source for Experience bullets.[^4][^3]
4. `data/bullet-bank-clean.csv` – full archive of ~1,500 bullet variants; use for grep‑based exploration of stronger phrasings.[^4]
5. `data/morgan-background-guide.md` – corrected career timeline and tailoring notes per role type.[^4]
6. `data/treering-archive-readme.md` – key Treering metrics reference; used to verify yearbook‑related numbers.[^4][^3]
7. `data/verified-claims.csv` – fact‑checked claims with confidence ratings; primary source of truth for metrics.[^4]
8. `data/evidence-guide.csv` – thematic proof clusters for enablement, ops, Why‑section content, etc.[^4][^3]
9. `data/summaries-and-skills-clean.csv` – archive of previous successful Summaries and Skills; used to avoid reinventing good phrasings.[^4]
10. `data/extracted-screenshot-metrics.csv` – campaign metrics verified via screenshots; authoritative for open/reply rates.[^3][^4]
11. `data/TreeringAccomplishmentsComplete.pdf` – narrative braindump of Treering tenure; used especially for ops/enablement/management‑focused roles.[^4]

### Metrics Sourcing Rules

- **No unsourced metrics.** Every number (open rate, reply rate, revenue, pipeline value, account count, etc.) must be traceable to `verified-claims.csv` or `extracted-screenshot-metrics.csv`, or another explicitly marked verified source.[^4]
- If a number cannot be verified, it is not used; the system describes impact qualitatively instead.[^4]
- When citing marginally noisy metrics (e.g., niche sequences that others over‑used), the resume uses cautious language like “among our highest‑performing sequences” rather than absolute claims.[^3]

***

## ATS and PDF Design Standards

### ATS Parsing Rules

- Single column only; no sidebars or multi‑column layout.[^1]
- Standard section headers only: **Professional Summary, Skills, Work Experience, Training & Certifications, Education, Why [Company]?**[^1]
- No text inside images or SVGs; all information must be selectable text.[^1]
- No critical content in PDF headers or footers; ATS may ignore those regions.[^1]
- No nested tables in the resume content.[^1]
- UTF‑8 text only, with ATS‑safe punctuation; no exotic symbols that might break parsing.[^3]

### PDF Typography and Layout

- Page size: **Letter (8.5 × 11 in)** for US/Canada roles; A4 only for explicitly international roles.[^1][^3]
- Margins: **0.5 in** on all sides; content width ~7.5 in.[^1]
- Fonts:
  - **DM Serif Display 400** – used for the name (32pt) and section headers (16pt).[^1]
  - **Space Grotesk 400/600** – for all body text, tagline, contact row, job metadata, skills, bullets.[^1]
  - Inter is prohibited, because Chromium/Playwright sometimes renders reversed text when copying from PDFs using Inter.[^4]
- Color palette:
  - All text in pure black `#000000`.[^1]
  - Horizontal rules and separators in `#9aa3af` only; no gradients or accent colors.[^1]
  - Background pure white.[^1]

### Header Block

- Name: DM Serif Display, 32pt, normal weight, black.[^1]
- Tagline: Space Grotesk, 14pt, all caps, *hard‑coded* uppercase in HTML (not via CSS `text-transform`) to avoid reversed text bugs.[^1]
- Contact row: Space Grotesk, 10pt, using separators (`·` or `|`) between phone, email, LinkedIn, location.[^4]
- Updated: no portfolio link (removed resume-wide); LinkedIn is plain text (spelled-out URL, no hyperlink) rather than a clickable link, since hyperlinks in a resume can read as a red flag to some ATS parsers.
- Updated: all contact info (name, phone, email, LinkedIn, location) is fixed content -- it doesn't vary by JD, so the builder no longer generates it.
- Ampersand usage in tagline and labels uses “&” (e.g., “Content & Lifecycle Systems”).[^4]

### Page Layout and Section Order

**Global rule:** every resume is exactly **2 pages**, never more.[^1]

- Page 1:
  - Header
  - Professional Summary
  - Skills
  - Work Experience: Mercor (if present), Treering, Inside Sales Team (IST). IST must fit entirely on page 1.[^1][^4]
- Page 2:
  - Work Experience (continuation): Element 8 / Strategy LLC, VML, Callahan Creek
  - Training & Certifications
  - Education
  - Why [Company]? (if present)[^1]

### Trimming Priority to Keep 2 Pages

When content overflows to 3 pages, apply these in order (updated: Why is now the *first* thing trimmed, not the last resort — it only belongs on the resume if it fits):

1. Remove the Why section entirely.
2. Trim Summary to its 5‑line limit.
3. Tighten bullets by trimming adjectives, front‑loading keywords, and collapsing redundant clauses.
4. Remove the least relevant bullets, starting with Treering (after protecting core proof points such as Outreach implementation and CRM hygiene).[^1]

***

## Summary Rules

### Global Summary Pattern

- Maximum **5 lines** of text.[^1]
- First sentence always **bold**, wrapped in `<strong>` tags.[^1]
- First sentence must state: who she is, years of experience, and core expertise, using the JD’s vocabulary.[^1][^4]
- Remaining sentences provide:
  - Narrative bridge and exit story (why she’s moving/returning), and
  - 1–2 proof points most relevant to this specific role (metrics or scope, not adjectives).[^1]
- Tone mirrors the company’s public voice (formal vs conversational, jargon level, keywords like “human,” “bold,” “impact”), but facts, titles, dates, bullets, and skills remain literal and honest.[^1]
- Explicitly ban words like “passionate,” “driven,” “results‑oriented,” “dynamic,” “synergy,” “best‑in‑class.”[^1]

### Tone Mirroring from Company Research

- Use company About/Mission/Values and Careers pages to detect:
  - Formal vs conversational register
  - “We” (community‑centric) vs “you/the customer” framing
  - Short punchy sentences vs longer flowing prose
  - Jargon density and recurring key words
  - Overall tone (playful, earnest, warm, rigorous, etc.)[^1]
- Apply this mirroring only to Summary tone and to Why section word choice, not to factual content or structure.[^1]

### Archetype Taglines

The tagline is generated automatically from the JD and archetype.[^1]

- **Primary:** the role title from the JD, cleaned (remove “Sr.”/“Junior,” “Remote,” parentheses) but keeping the essence.[^1]
- **Secondary:** archetype‑specific descriptor in Title Case:
  - Email Lifecycle → “Campaign CRM Strategist”
  - Sales Enablement → “Content Systems & Training Designer”
  - B2B Content → “Brand Voice & Campaign Copywriter”
  - Marketing Ops → “CRM Campaign Systems Specialist”
  - Generalist Coordinator → “Campaign Strategy & Lifecycle Marketing”[^1]
- Tagline must fit on one printed line; if too long, shorten the secondary descriptor (never the role title). Target 70–80 characters at 14pt.[^1]

### Copywriter/Communications Variants

- For senior copywriter or communications roles, Summary may be slightly more narrative, but still obeys all rules above and uses systems‑informed framing (content systems, editorial programs) instead of only craft adjectives.[^4]

***

## Skills Section Rules

- Skills always appears **immediately after Summary**.[^1]
- It is treated as the most important ATS signal and should be curated with the same care as Summary.[^1]

### Content Selection

- Include every tool, platform, methodology, framework, and skill explicitly named in the JD that Morgan genuinely knows.[^1]
- Also include logically implied skills (e.g., JD mentions HubSpot but not “CRM”; you include “CRM” if true).[^1]
- Do **not** pad with soft skills unless the JD explicitly lists them as requirements.[^1]

### Line Length and Widow Prevention

- Skills lines must not exceed **110 characters**, including category labels and commas, to avoid a single trailing word on the next line.[^1]
- Category labels are bold and take up extra width, so 110 characters is the safety threshold.
- If a line wraps with a one‑word widow, trim or move items to another category until the line fits cleanly.[^1]

### Category Structure and Ordering

- Items are comma‑separated, with a space after each comma; no bullets, pipes, or line breaks inside a category.[^1]
- Category labels are bold via `.skill-category`; items are plain body font.[^1]
- Categories are archetype‑dependent but follow these principles:
  - Lifecycle roles lead with Lifecycle/Retention Marketing, then CRM/Revenue Operations, then Content/Enablement/Training, then Creative/Design last.[^4]
  - Copywriter/communications variants may lead with Content & Communications Strategy and Writing & Editing, with Nonprofit/CRM/Creative/Analytics following.[^4]
- Category names include meaningful language upgrades, for example:
  - “Salesforce Administration” instead of “Salesforce” (signalling admin‑level depth).[^4]
  - “Revenue Operations” instead of “Marketing Operations” where appropriate.[^4]
  - “Lifecycle Strategy” instead of “Lifecycle Campaign Design.”[^4]

***

## Bullet Writing and Metrics Rules

### Verb and Structure Constraints

- Every bullet opens with a **strong, specific action verb** in past tense (present tense only for actively held roles).[^1]
- Opening verbs must be **unique across the entire CV**; no verb can be reused as the first word in more than one bullet.[^1]
- Banned openers: “responsible for,” “helped with,” “worked on,” “assisted with,” “participated in,” generic “managed/handled/ran” when a sharper verb exists.[^1]
- Recommended verbs include: Architected, Authored, Launched, Recovered, Systematized, Audited, Spearheaded, Negotiated, Synthesized, Produced, Streamlined, Championed, Deployed, Developed, Expanded, Coordinated, Mentored, Built, Implemented, etc.[^1]
- Each bullet follows the pattern: **Action verb → task/responsibility → result/outcome**, with a metric if one exists.[^1]

### Metrics Uniqueness and Placement

- Every numeric metric (percentages, counts, dollar amounts) appears at most **once in the entire CV**.[^4][^1]
- If a metric appears in the Summary, it must not appear inside any bullet; pick whichever location produces the most impact.[^1]
- If two bullets naturally share a metric, rewrite one to avoid repetition.

### Length, Layout, and Widows

- Target length: 110–120 characters for one‑line bullets; up to 180–220 characters for intentionally two‑line bullets.[^4]
- Majority of bullets (~70%) should be clean one‑liners; minority (~30%) may be two lines for high‑impact achievements.[^4]
- No bullet may exceed two printed lines.
- Avoid bullets that wrap to a second line with fewer than ~5 words; either shorten to one line or expand meaningfully.

### Punctuation and Character Rules

- Bullets never end with periods or any trailing punctuation; they are list fragments, not full sentences.[^1]
- No parentheses in bullets or Summary; replace with commas or semicolons.[^1]
- No dashes (`-`, `--`, `—`) in prose; dashes are allowed only in date ranges, page width measurements, or hyphenated modifiers (e.g., “six‑email campaign”).[^1]
- No bold text inside `>` elements; bullets remain plain; action verbs and metrics carry the emphasis without formatting.[^1]

### Tool and Method Mentions

- Mention tools (Salesforce, Outreach.io, HubSpot, Mailchimp, etc.) inside bullets only when they add necessary specificity.[^1]
- One tool mention per bullet is ideal; two are acceptable if both are central to the story; three or more reads as a list, not a narrative.

### Outbound vs Lifecycle Framing

- Outbound email sequence work is framed as lifecycle‑equivalent when the mechanics align: segmentation, multi‑touch journeys, AB testing, and lifecycle‑style copy decisions.[^3]

***

## Special Protected Bullets and Stories

### Outreach.io and Salesforce Implementation

- There must be a bullet that clearly shows **full platform ownership**, including:
  - Vendor evaluation and selection
  - Salesforce integration and data migration
  - Team‑wide adoption and training
  - Ongoing platform stewardship/expertise[^4][^1]
- This bullet may not be aggressively shortened; if space is tight, other bullets are trimmed first.[^4]

### CRM Data Hygiene and 3M Stale Pipeline

- CRM scrub and pipeline recovery bullets must show:
  - Scale (e.g., thousands of accounts processed)
  - Systematic audit and cleanup process
  - Verified `3M` pipeline recovery metric, sourced from `verified-claims` and scrub documents (e.g., DF‑0124).[^3]

### Content Committee and Enablement Systems

- At least one Treering bullet should capture the Content Committee’s role as a cross‑department content governance body:
  - Founded and chaired by Morgan
  - Created library of 100+ email assets and 129 sequences
  - Established QA process, voice/tone guidelines, and content awards program.[^3]

### SDR Process Map and Training Program

- Enablement bullets should highlight:
  - The 8‑step SDR Process Map website used as official onboarding asset years after creation
  - Live and async training for ~20 SDRs, with agenda‑driven sessions and durable documentation.[^3]

### Agency, CACU, and Regulated Industries

- Copywriting bullets for agency roles should foreground:
  - Client selection for rollout
  - Regulated financial product copy (CACU: mortgages, insurance, PPC) with accuracy and compliance
  - Multi‑channel work (PPC, DM, TV, radio, web, long‑form educational content).[^3]

***

## Section‑Specific Rules

### Work Experience Formatting

- Each job uses:
  - `.job-title` – role title plus industry/type descriptor (e.g., “Senior Sales Development Lead B2B SaaS / EdTech”).[^1]
  - `.job-meta` – company name, size, revenue, location or work type, then dates in `MMYYYY – MMYYYY` format, separated by pipes.
- Dates are always numeric (e.g., `08/2016 – 08/2024` sans slashes in HTML) with an en‑dash; never “August 2016.”[^1]
- Company details appear in the same line as job meta; location can be replaced by “Short‑Term Contract” when appropriate.[^1]

#### Job Title Reframing

- Honest, role‑specific reframing of the title itself is allowed to better match responsibilities and target archetypes.[^1]
- Two formats for the title itself:
  - Additive: `Title A + Title B`, e.g. `ABM Specialist + Business Development Representative` (Inside Sales Team) or `Creative Strategy Lead + Senior Sales Development Lead`/`Manager` (Treering, or other reasonable `X + Senior Sales Development Lead/Manager` variants per archetype).[^1]
  - Single title: used when one title already captures the role well (e.g. `Lead Graphic Designer`, `Copywriting Intern`).
- Company, dates, and seniority level may not be altered.
- Updated: a fixed industry/role-type descriptor is appended automatically after whatever title is
  produced, per company (independent of which title format above is used):
  - Mercor: `(AI Training)`
  - Treering Yearbooks: `(SaaS/EdTech)`
  - Inside Sales Team: `(Outbound/Agency)`
  - Element 8 / Strategy LLC: `(Design/Agency/Startup)`
  - VML: `(Agency/Digital/Brand)`
  - Callahan Creek: `(Agency/Creative/Brand)`

#### Career Note at Treering

- Updated: always included, Treering‑only (previously optional), and hard-coded (not LLM-generated)
  given the sensitivity of the content.
- Updated: positioned after the Treering entry's bullets (previously before them), formatted as
  bold `Career Note:` followed by the note in italics.
- Updated: pronouns and standard sentence punctuation are allowed here, unlike the rest of the
  Experience section.
- Current text: “Career Note: After a fulfilling run at Treering, I took intentional time in 2024–25
  to support a loved one's health and invest in professional growth while searching for a role
  aligned with my skills and values. I'm excited to return to work with renewed focus.”[^3][^1]

### Training & Certifications

- Section title: **Training & Certifications**.[^1]
- Exactly three entries in this order:
  1. Email Marketing Software Certification — HubSpot (2026)
  2. Video for Sales Certification — Vidyard (2021)
  3. Camp Portfolio — Bernstein Rein, Kansas City (2008)[^4][^1]
- Only the certification name is bold; the institution and year remain regular weight.[^1]

### Education

- Section title: **Education**.[^1]
- Institutions in fixed order:
  1. University of Kansas – Bachelor of Science, Journalism (Strategic Communication)
  2. Kansas City Kansas Community College – Associate of Arts, Journalism
  3. Johnson County Community College – Relevant Coursework, Graphic Design[^1]

- Bullet counts:
  - KU: exactly 2 bullets (GPA + scholarship; one action‑verb achievement bullet).[^6]
  - KCKCC: exactly 2 bullets (GPA + scholarship/honors; one action‑verb achievement bullet).[^6]
  - JCCC: exactly 1 bullet (GPA + coursework summary line).[^6]

- GPA line format:
  - “3.56 GPA, Phi Theta Kappa Scholarship recipient” (single slash or comma pattern per `pdf.md` templates).[^6]
  - JCCC bullet: “3.86 GPA, studied color theory, typography, illustration, 3D concepts, desktop publishing, and film photography.”[^6]

### Why [Company]? Section

- Section header always uses the real company name: “Why Acme Co.?”; if unavailable, use “Additional Relevant Experience.”[^1]
- Present only when:
  - The company explicitly values mission/culture fit, or
  - The application requests a “why this company” response, or
  - Space allows a 2‑page resume with this section included.[^1]
- If adding Why pushes the PDF to 3 pages, remove it and regenerate.[^1]

#### Formatting and Tone

- Format: two short paragraphs.[^1]
- Style: only the first and last sentences of the entire section are italicized for emphasis; the middle remains plain.[^1]
- Voice: first‑person; personal pronouns (“I, my, me”) are required here and forbidden elsewhere in the resume.[^1]
- Length: maximum 8 lines total.[^1]
- Content:
  - Must reference specific details from company research (mission language, products, audiences, operating model).
  - Must connect each reference to concrete, verified facts from Morgan’s history (e.g., K‑12 audience depth, Title 1 campaigns).[^3][^1]

***

## Numbers, Style, and Language Consistency

### Number Formatting

- Spell out whole numbers under 10 unless tied to a unit/metric (e.g., “six‑email campaign,” but “6% reply rate”).[^1]
- Always use numerals for:
  - Percentages (e.g., 74% open rate)
  - Dollar figures (3M, 1.1M)
  - Decimals (3.56 GPA, 8.7% reply rate)
  - Quantities over 10 (20 employees, 129 sequences)
  - Date ranges (2006–2008)[^3][^1]

### Ampersand vs “and”

- Use “&” in headings, labels, tagline, and category names (e.g., “Content & Enablement”).[^4]
- Use “and” spelled out in body prose and bullets.[^4]

### Pronoun Rules

- No “I, my, me, we, our” in Summary, Skills, Work Experience, Training, or Education.
- Pronouns are allowed and encouraged only in the Why section.[^4]

### Banned Words and Phrases

- No “responsible for,” “helped with,” “worked on,” “assisted with,” “participated in” in any bullet.[^1]
- Avoid corporate‑speak and empty buzzwords across all sections.

***

## Global Process and Integrity Rules

### Ethical Constraints

- Never invent experience, metrics, titles, or skills.[^3][^4]
- Never modify the underlying source‑of‑truth files (`cv.md`, `config/profile.yml`, bullet bank archives) based on one resume session.[^3]
- Never submit applications on Morgan’s behalf.
- Never recommend roles below her configured minimum compensation without explicitly flagging the issue.[^3]

### Application Tracker Integration

- Each evaluated role gets a new TSV line with numeric score, decision label, and links to the evaluation report and generated PDF, but only after successful PDF generation.[^3]

***

## Summary of Archetype‑Specific Tailoring

- **Email Lifecycle:** Summary and top Treering bullets emphasize campaign numbers, segmentation, Personalized Outreach infrastructure, and revival/retention logic; Skills lead with Lifecycle/Retention, then CRM.[^3]
- **Sales Enablement:** Lead with Content Committee, SDR Process Map, training programs, and content governance; emphasize sequences as enablement assets, not just outbound volume.[^3]
- **B2B Content/Copywriter:** Lead with agency training, CACU and regulated industries, journalism method, and brand voice work; Skills prioritize content strategy and writing, with CRM as a supporting strength.[^3]
- **Marketing Ops/CRM Specialist:** Lead with Salesforce territory as a product, national Hot Zone analysis, CRM scrub and imports, competitive intelligence training; Skills center on CRM, data hygiene, reporting, and automation.[^3]
- **Generalist Marketing/Coordinator:** Lead with range: campaigns, CRM, content, design, and internal enablement; show ability to carry multi‑hat IC roles without implying director‑level management.[^3]

This consolidated system is designed to be stable: future updates should be additive and documented as explicit rule changes, not ad‑hoc exceptions.

---

## References

1. [gemini-session-2026-05-30T23-56-8abfbc97.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_70d92eb4-67ee-4ec6-ac4f-4f8c114ae23e/73be85ce-aab2-42bf-8827-471e165ee6a3/gemini-session-2026-05-30T23-56-8abfbc97.md?AWSAccessKeyId=ASIA2F3EMEYE4SDUA64V&Signature=4JVWC0BzTWNtU1jNPyOKVB4UvQI%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQC0kUlGxr3SYK5DXFaRqAZYEWCxbwIuGuxspe9RwZplJgIhAJ6pX08o%2BByNHsJmu4ZDaGwmJJhdggYeiW00cPQUKg1jKvwECLL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMNjk5NzUzMzA5NzA1IgzJmZYTAP26WOjlETYq0ATbKoCHIlyo5N4mcmaBH5%2BkJMSbT1QCg%2FNyBAyTpAojkt878HTNRuuwnmPDvy%2BddNv8czR9bpHUBB8pA4fSop%2B%2F9a7ks1IPYEJyy6n2sWDd7%2BQJs6d8wG0sAozUu6yW5mU1XiPv160HpxVzveoWz5kGQBeyglhfRoG9tOhGLZS1YkMnBy5LC11tyYhTXVbET%2FEQfzPUPIpL%2FTxTtFUK8OZi574lXKkUJ%2Fx4FBjIQAaDlkZbXMlunJh69BI4yBimnA1QmifcUva3woFYPt5JSkXtfVCZ8gQkV1C%2BDFNPEiU%2BbSk9trLJSEgd%2F644zsVB1WD%2FFkVTy72cFzagcttqte8jOXL5%2B%2F2lMCognmGTVCzhjvmXYDDJ551QXEChYCvtZckRICRBE%2FNVvonjlAdwgBAtZd1od%2FBl0%2FOTz1fmQ13d0SJAzzUhT%2FUoospkgu9QK8K4%2BD82t%2BEuPmHmDXKXc6XOf4vcxc8PGS1J5Yj1t7nr2w6nEdHl%2BgJzN%2B6Z5uy7PW7%2FryxAwPBPyzuDISXHhq8z8DC2SFCcujKV%2FEBsPbLDw4FohBNeVx3u0X%2FDzn3XIaqxoLbR67J0DCDOMVSokW%2BjLpFxCM69mSYdfL9XnGET8mIgfWGjcQwhW7yFTQxnt0Z8QvVBmggUOBUkoAp8owfW0q8PLUJPUr02dMIR0ZqAGWT82fVZlw%2BPQhswylBtiHR47YpP8lc9q8UuW6DZrCqUF8zaayOXwjY39yhiwGJcEsbtoy93%2FKikJT3IjEmPo%2BEntWAkij1rqLe%2BqMKk%2Fkj3MN2l0tEGOpcBS2gyWK%2FM1AMZ9hLQqhNz0rDcwCpQwmyFMve%2BRFJ2IAch9zhEt1HPmDHqXbJ6FKBZuPPhG0%2BNCFqH728CLTFPoMHuyn%2BzANGou%2Bwunze%2Bw2MuzsvExvgbF1%2BoWd7VZbL5mqh4PTwSltyUdHzbDlqDz4dZDUKZKMyDMuoEFydRMYTEIeBsXoc7v3DEGZuMtvTZa6ZYOVLKSg%3D%3D&Expires=1781833904) - . Ive also refined the Why section rules to be one to two paragraphs, eliminating subheadings and bo...

2. [gemini-session-2026-06-01T15-31-92b86e9a.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_70d92eb4-67ee-4ec6-ac4f-4f8c114ae23e/37c4c2bc-969f-4527-a2cf-2584bf9dc8bf/gemini-session-2026-06-01T15-31-92b86e9a.md?AWSAccessKeyId=ASIA2F3EMEYE4SDUA64V&Signature=ei%2FBkOFBJy%2B06QVmJpI80jZXqR8%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQC0kUlGxr3SYK5DXFaRqAZYEWCxbwIuGuxspe9RwZplJgIhAJ6pX08o%2BByNHsJmu4ZDaGwmJJhdggYeiW00cPQUKg1jKvwECLL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMNjk5NzUzMzA5NzA1IgzJmZYTAP26WOjlETYq0ATbKoCHIlyo5N4mcmaBH5%2BkJMSbT1QCg%2FNyBAyTpAojkt878HTNRuuwnmPDvy%2BddNv8czR9bpHUBB8pA4fSop%2B%2F9a7ks1IPYEJyy6n2sWDd7%2BQJs6d8wG0sAozUu6yW5mU1XiPv160HpxVzveoWz5kGQBeyglhfRoG9tOhGLZS1YkMnBy5LC11tyYhTXVbET%2FEQfzPUPIpL%2FTxTtFUK8OZi574lXKkUJ%2Fx4FBjIQAaDlkZbXMlunJh69BI4yBimnA1QmifcUva3woFYPt5JSkXtfVCZ8gQkV1C%2BDFNPEiU%2BbSk9trLJSEgd%2F644zsVB1WD%2FFkVTy72cFzagcttqte8jOXL5%2B%2F2lMCognmGTVCzhjvmXYDDJ551QXEChYCvtZckRICRBE%2FNVvonjlAdwgBAtZd1od%2FBl0%2FOTz1fmQ13d0SJAzzUhT%2FUoospkgu9QK8K4%2BD82t%2BEuPmHmDXKXc6XOf4vcxc8PGS1J5Yj1t7nr2w6nEdHl%2BgJzN%2B6Z5uy7PW7%2FryxAwPBPyzuDISXHhq8z8DC2SFCcujKV%2FEBsPbLDw4FohBNeVx3u0X%2FDzn3XIaqxoLbR67J0DCDOMVSokW%2BjLpFxCM69mSYdfL9XnGET8mIgfWGjcQwhW7yFTQxnt0Z8QvVBmggUOBUkoAp8owfW0q8PLUJPUr02dMIR0ZqAGWT82fVZlw%2BPQhswylBtiHR47YpP8lc9q8UuW6DZrCqUF8zaayOXwjY39yhiwGJcEsbtoy93%2FKikJT3IjEmPo%2BEntWAkij1rqLe%2BqMKk%2Fkj3MN2l0tEGOpcBS2gyWK%2FM1AMZ9hLQqhNz0rDcwCpQwmyFMve%2BRFJ2IAch9zhEt1HPmDHqXbJ6FKBZuPPhG0%2BNCFqH728CLTFPoMHuyn%2BzANGou%2Bwunze%2Bw2MuzsvExvgbF1%2BoWd7VZbL5mqh4PTwSltyUdHzbDlqDz4dZDUKZKMyDMuoEFydRMYTEIeBsXoc7v3DEGZuMtvTZa6ZYOVLKSg%3D%3D&Expires=1781833904) - id1c1a294b-db8d-4e8b-b5fe-ae5326ab2f44,timestamp2026-06-01T163133.034Z,typegemini,content,thoughtssu...

3. [gemini-session-2026-06-10T04-01-782a8e57.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_70d92eb4-67ee-4ec6-ac4f-4f8c114ae23e/097122e9-bea0-4540-8e6c-74a15338df6b/gemini-session-2026-06-10T04-01-782a8e57.md?AWSAccessKeyId=ASIA2F3EMEYE4SDUA64V&Signature=iuj%2BlSwDGSGq6I0B8oXJXjYK07g%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQC0kUlGxr3SYK5DXFaRqAZYEWCxbwIuGuxspe9RwZplJgIhAJ6pX08o%2BByNHsJmu4ZDaGwmJJhdggYeiW00cPQUKg1jKvwECLL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMNjk5NzUzMzA5NzA1IgzJmZYTAP26WOjlETYq0ATbKoCHIlyo5N4mcmaBH5%2BkJMSbT1QCg%2FNyBAyTpAojkt878HTNRuuwnmPDvy%2BddNv8czR9bpHUBB8pA4fSop%2B%2F9a7ks1IPYEJyy6n2sWDd7%2BQJs6d8wG0sAozUu6yW5mU1XiPv160HpxVzveoWz5kGQBeyglhfRoG9tOhGLZS1YkMnBy5LC11tyYhTXVbET%2FEQfzPUPIpL%2FTxTtFUK8OZi574lXKkUJ%2Fx4FBjIQAaDlkZbXMlunJh69BI4yBimnA1QmifcUva3woFYPt5JSkXtfVCZ8gQkV1C%2BDFNPEiU%2BbSk9trLJSEgd%2F644zsVB1WD%2FFkVTy72cFzagcttqte8jOXL5%2B%2F2lMCognmGTVCzhjvmXYDDJ551QXEChYCvtZckRICRBE%2FNVvonjlAdwgBAtZd1od%2FBl0%2FOTz1fmQ13d0SJAzzUhT%2FUoospkgu9QK8K4%2BD82t%2BEuPmHmDXKXc6XOf4vcxc8PGS1J5Yj1t7nr2w6nEdHl%2BgJzN%2B6Z5uy7PW7%2FryxAwPBPyzuDISXHhq8z8DC2SFCcujKV%2FEBsPbLDw4FohBNeVx3u0X%2FDzn3XIaqxoLbR67J0DCDOMVSokW%2BjLpFxCM69mSYdfL9XnGET8mIgfWGjcQwhW7yFTQxnt0Z8QvVBmggUOBUkoAp8owfW0q8PLUJPUr02dMIR0ZqAGWT82fVZlw%2BPQhswylBtiHR47YpP8lc9q8UuW6DZrCqUF8zaayOXwjY39yhiwGJcEsbtoy93%2FKikJT3IjEmPo%2BEntWAkij1rqLe%2BqMKk%2Fkj3MN2l0tEGOpcBS2gyWK%2FM1AMZ9hLQqhNz0rDcwCpQwmyFMve%2BRFJ2IAch9zhEt1HPmDHqXbJ6FKBZuPPhG0%2BNCFqH728CLTFPoMHuyn%2BzANGou%2Bwunze%2Bw2MuzsvExvgbF1%2BoWd7VZbL5mqh4PTwSltyUdHzbDlqDz4dZDUKZKMyDMuoEFydRMYTEIeBsXoc7v3DEGZuMtvTZa6ZYOVLKSg%3D%3D&Expires=1781833904) - . Thats the same logic that underlies drip campaigns, onboarding sequences, and re-engagement flows ...

4. [gemini-b008e9cf-11c5-4d6e-a314-cbfafdbfa9b2.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_70d92eb4-67ee-4ec6-ac4f-4f8c114ae23e/6f50d630-3802-4650-8a82-b711067007a2/gemini-b008e9cf-11c5-4d6e-a314-cbfafdbfa9b2.md?AWSAccessKeyId=ASIA2F3EMEYE4SDUA64V&Signature=EAnWObbZkMP9UeWKe9YOUsMQPzQ%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQC0kUlGxr3SYK5DXFaRqAZYEWCxbwIuGuxspe9RwZplJgIhAJ6pX08o%2BByNHsJmu4ZDaGwmJJhdggYeiW00cPQUKg1jKvwECLL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMNjk5NzUzMzA5NzA1IgzJmZYTAP26WOjlETYq0ATbKoCHIlyo5N4mcmaBH5%2BkJMSbT1QCg%2FNyBAyTpAojkt878HTNRuuwnmPDvy%2BddNv8czR9bpHUBB8pA4fSop%2B%2F9a7ks1IPYEJyy6n2sWDd7%2BQJs6d8wG0sAozUu6yW5mU1XiPv160HpxVzveoWz5kGQBeyglhfRoG9tOhGLZS1YkMnBy5LC11tyYhTXVbET%2FEQfzPUPIpL%2FTxTtFUK8OZi574lXKkUJ%2Fx4FBjIQAaDlkZbXMlunJh69BI4yBimnA1QmifcUva3woFYPt5JSkXtfVCZ8gQkV1C%2BDFNPEiU%2BbSk9trLJSEgd%2F644zsVB1WD%2FFkVTy72cFzagcttqte8jOXL5%2B%2F2lMCognmGTVCzhjvmXYDDJ551QXEChYCvtZckRICRBE%2FNVvonjlAdwgBAtZd1od%2FBl0%2FOTz1fmQ13d0SJAzzUhT%2FUoospkgu9QK8K4%2BD82t%2BEuPmHmDXKXc6XOf4vcxc8PGS1J5Yj1t7nr2w6nEdHl%2BgJzN%2B6Z5uy7PW7%2FryxAwPBPyzuDISXHhq8z8DC2SFCcujKV%2FEBsPbLDw4FohBNeVx3u0X%2FDzn3XIaqxoLbR67J0DCDOMVSokW%2BjLpFxCM69mSYdfL9XnGET8mIgfWGjcQwhW7yFTQxnt0Z8QvVBmggUOBUkoAp8owfW0q8PLUJPUr02dMIR0ZqAGWT82fVZlw%2BPQhswylBtiHR47YpP8lc9q8UuW6DZrCqUF8zaayOXwjY39yhiwGJcEsbtoy93%2FKikJT3IjEmPo%2BEntWAkij1rqLe%2BqMKk%2Fkj3MN2l0tEGOpcBS2gyWK%2FM1AMZ9hLQqhNz0rDcwCpQwmyFMve%2BRFJ2IAch9zhEt1HPmDHqXbJ6FKBZuPPhG0%2BNCFqH728CLTFPoMHuyn%2BzANGou%2Bwunze%2Bw2MuzsvExvgbF1%2BoWd7VZbL5mqh4PTwSltyUdHzbDlqDz4dZDUKZKMyDMuoEFydRMYTEIeBsXoc7v3DEGZuMtvTZa6ZYOVLKSg%3D%3D&Expires=1781833904) - . A resume built without this research will miss the best bullets, misframe the narrative, and risk ...

5. [gemini-session-2026-06-06T18-02-148ac0a1.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_70d92eb4-67ee-4ec6-ac4f-4f8c114ae23e/b4c79546-40de-4889-8654-b1edda43d631/gemini-session-2026-06-06T18-02-148ac0a1.md?AWSAccessKeyId=ASIA2F3EMEYE4SDUA64V&Signature=3lz3Ys684MHEyqad5kC%2FJ5%2B7iRg%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQC0kUlGxr3SYK5DXFaRqAZYEWCxbwIuGuxspe9RwZplJgIhAJ6pX08o%2BByNHsJmu4ZDaGwmJJhdggYeiW00cPQUKg1jKvwECLL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMNjk5NzUzMzA5NzA1IgzJmZYTAP26WOjlETYq0ATbKoCHIlyo5N4mcmaBH5%2BkJMSbT1QCg%2FNyBAyTpAojkt878HTNRuuwnmPDvy%2BddNv8czR9bpHUBB8pA4fSop%2B%2F9a7ks1IPYEJyy6n2sWDd7%2BQJs6d8wG0sAozUu6yW5mU1XiPv160HpxVzveoWz5kGQBeyglhfRoG9tOhGLZS1YkMnBy5LC11tyYhTXVbET%2FEQfzPUPIpL%2FTxTtFUK8OZi574lXKkUJ%2Fx4FBjIQAaDlkZbXMlunJh69BI4yBimnA1QmifcUva3woFYPt5JSkXtfVCZ8gQkV1C%2BDFNPEiU%2BbSk9trLJSEgd%2F644zsVB1WD%2FFkVTy72cFzagcttqte8jOXL5%2B%2F2lMCognmGTVCzhjvmXYDDJ551QXEChYCvtZckRICRBE%2FNVvonjlAdwgBAtZd1od%2FBl0%2FOTz1fmQ13d0SJAzzUhT%2FUoospkgu9QK8K4%2BD82t%2BEuPmHmDXKXc6XOf4vcxc8PGS1J5Yj1t7nr2w6nEdHl%2BgJzN%2B6Z5uy7PW7%2FryxAwPBPyzuDISXHhq8z8DC2SFCcujKV%2FEBsPbLDw4FohBNeVx3u0X%2FDzn3XIaqxoLbR67J0DCDOMVSokW%2BjLpFxCM69mSYdfL9XnGET8mIgfWGjcQwhW7yFTQxnt0Z8QvVBmggUOBUkoAp8owfW0q8PLUJPUr02dMIR0ZqAGWT82fVZlw%2BPQhswylBtiHR47YpP8lc9q8UuW6DZrCqUF8zaayOXwjY39yhiwGJcEsbtoy93%2FKikJT3IjEmPo%2BEntWAkij1rqLe%2BqMKk%2Fkj3MN2l0tEGOpcBS2gyWK%2FM1AMZ9hLQqhNz0rDcwCpQwmyFMve%2BRFJ2IAch9zhEt1HPmDHqXbJ6FKBZuPPhG0%2BNCFqH728CLTFPoMHuyn%2BzANGou%2Bwunze%2Bw2MuzsvExvgbF1%2BoWd7VZbL5mqh4PTwSltyUdHzbDlqDz4dZDUKZKMyDMuoEFydRMYTEIeBsXoc7v3DEGZuMtvTZa6ZYOVLKSg%3D%3D&Expires=1781833904) - . My current focus is on incorporating the new seniorityboost and roleboost features, prioritizing I...

6. [gemini-session-2026-05-31T19-42-42097be6.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/collection_70d92eb4-67ee-4ec6-ac4f-4f8c114ae23e/3cdfeebc-4ff4-40ea-a2da-27eff24a7685/gemini-session-2026-05-31T19-42-42097be6.md?AWSAccessKeyId=ASIA2F3EMEYE4SDUA64V&Signature=CuP8ukAiJPT4TZs5NCKVtD%2BHNV0%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEOn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQC0kUlGxr3SYK5DXFaRqAZYEWCxbwIuGuxspe9RwZplJgIhAJ6pX08o%2BByNHsJmu4ZDaGwmJJhdggYeiW00cPQUKg1jKvwECLL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQARoMNjk5NzUzMzA5NzA1IgzJmZYTAP26WOjlETYq0ATbKoCHIlyo5N4mcmaBH5%2BkJMSbT1QCg%2FNyBAyTpAojkt878HTNRuuwnmPDvy%2BddNv8czR9bpHUBB8pA4fSop%2B%2F9a7ks1IPYEJyy6n2sWDd7%2BQJs6d8wG0sAozUu6yW5mU1XiPv160HpxVzveoWz5kGQBeyglhfRoG9tOhGLZS1YkMnBy5LC11tyYhTXVbET%2FEQfzPUPIpL%2FTxTtFUK8OZi574lXKkUJ%2Fx4FBjIQAaDlkZbXMlunJh69BI4yBimnA1QmifcUva3woFYPt5JSkXtfVCZ8gQkV1C%2BDFNPEiU%2BbSk9trLJSEgd%2F644zsVB1WD%2FFkVTy72cFzagcttqte8jOXL5%2B%2F2lMCognmGTVCzhjvmXYDDJ551QXEChYCvtZckRICRBE%2FNVvonjlAdwgBAtZd1od%2FBl0%2FOTz1fmQ13d0SJAzzUhT%2FUoospkgu9QK8K4%2BD82t%2BEuPmHmDXKXc6XOf4vcxc8PGS1J5Yj1t7nr2w6nEdHl%2BgJzN%2B6Z5uy7PW7%2FryxAwPBPyzuDISXHhq8z8DC2SFCcujKV%2FEBsPbLDw4FohBNeVx3u0X%2FDzn3XIaqxoLbR67J0DCDOMVSokW%2BjLpFxCM69mSYdfL9XnGET8mIgfWGjcQwhW7yFTQxnt0Z8QvVBmggUOBUkoAp8owfW0q8PLUJPUr02dMIR0ZqAGWT82fVZlw%2BPQhswylBtiHR47YpP8lc9q8UuW6DZrCqUF8zaayOXwjY39yhiwGJcEsbtoy93%2FKikJT3IjEmPo%2BEntWAkij1rqLe%2BqMKk%2Fkj3MN2l0tEGOpcBS2gyWK%2FM1AMZ9hLQqhNz0rDcwCpQwmyFMve%2BRFJ2IAch9zhEt1HPmDHqXbJ6FKBZuPPhG0%2BNCFqH728CLTFPoMHuyn%2BzANGou%2Bwunze%2Bw2MuzsvExvgbF1%2BoWd7VZbL5mqh4PTwSltyUdHzbDlqDz4dZDUKZKMyDMuoEFydRMYTEIeBsXoc7v3DEGZuMtvTZa6ZYOVLKSg%3D%3D&Expires=1781833904)

