# Phase 3 — Output quality & voice

Model: Opus 5. Date: 2026-08-05. Goal served: 2 (highest achievable output
quality). Artifacts judged: the `resume sample` run of 2026-08-05 14:23
(`output/morgan/{json,html,pdf}/MorganEscott_ContentStrategist_AbnormalAI_*`),
against `fixtures/sample_jd.txt`.

No code changed. Every claim below was reproduced by running code against the
real artifact, not inferred from reading.

## Two deviations from the plan's setup instructions

1. **I did not re-run `resume sample`.** Phase 0 ran it at 14:23 today against
   this same commit; those artifacts are what I judged. A re-run costs real
   API spend to re-roll the same pipeline nondeterministically, and would not
   have made the findings more current.
2. **"Diff the impression against the committed PDFs in `output/morgan/pdf/`"
   is unexecutable.** `output/` is gitignored (`.gitignore:32`) and
   `git ls-files output/morgan/pdf/` returns nothing. There is no committed
   baseline in this repo to diff against. If before/after comparison is
   wanted for future phases, a small set of reference PDFs has to be
   deliberately committed somewhere outside `output/`.

## Ownership gap in PLAN.md

`scripts/validate_pdf_text.py` is assigned to **no phase**. Phase 0 routed its
§2d finding to Phase 3, and that finding lives entirely in this file, so I
read it (61 lines). Two of the highest-severity findings below are in it. It
needs an owner.

---

## BLOCKER 1 — Typographic ligatures in the PDF text layer defeat ATS keyword matching

**Where:** the rendered PDF text layer. Root cause is in the template/font
layer (Phase 2's files — see Handoffs). **Goal: 2.**

**The failure.** Every PDF this tool produces encodes `fi`/`fl`/`ffi` as
single ligature codepoints (U+FB01/FB02/FB03). An ATS extracting text gets
character sequences that do not match the keywords it is searching for:

| ATS actually reads | Should read |
|---|---|
| `workﬂows` | `workflows` |
| `Certiﬁcation` | `Certification` |
| `revenue-ﬁrst` | `revenue-first` |
| `ofﬁcial` | `official` |
| `fulﬁlling` | `fulfilling` |
| `ﬁlm` | `film` |
| `uniﬁed`, `ﬂuency`, `efﬁciently`, `ﬂexible`, `human-ﬁrst` | (cover letter) |

8 corrupted tokens in the resume, 7 in the cover letter.

**Why this is a blocker and not a curiosity.** `AI-assisted workflows` is a
verbatim phrase from this JD's requirements (confirmed present in
`fixtures/sample_jd.txt`'s `description`). The pipeline correctly identified
it, mirrored it into both the Skills section and the cover letter for keyword
match — and then the renderer silently broke it. The single most valuable
thing this tool does is defeated at the last step. `Certification` is a
generic high-frequency ATS term and is corrupted in the certifications
heading.

This affects **every document this tool has ever produced**, not this sample.

**Fix direction (unverified — Phase 2 owns the file):** disable discretionary
ligatures in the resume/cover-letter CSS —
`font-variant-ligatures: none; font-feature-settings: "liga" 0, "clig" 0;`
then re-render and re-run the scan.

**Reproduce:**
```python
import re
from pdfminer.high_level import extract_text
raw = extract_text("output/morgan/pdf/MorganEscott_ContentStrategist_AbnormalAI_Resume.pdf")
print(re.findall(r"\S*[ﬀ-ﬆ]\S*", raw))
```

---

## MAJOR 2 — `validate_pdf_text.py` emits 3 guaranteed false positives every run, burying the one real signal

**Where:** `scripts/validate_pdf_text.py:25-31` (`_normalize`), `:57-59`.
**Goals: 1, 2.**

**The failure.** `_normalize` substitutes curly quotes, en/em dashes and
non-breaking spaces, collapses whitespace, and lowercases. It does **not**
strip markdown `**bold**` markers. Every SKILLS line is emitted as
`**Content Strategy & Operations:** …`, and the renderer converts `**…**` to
`<strong>`, so the asterisks are absent from the PDF text layer. The
comparison therefore fails on markup, not content.

Measured against the shipped resume — the check reported 5 warnings:

- 3 of the 4 skills-line warnings are **pure false positives**; stripping `**`
  makes them match exactly.
- The remaining 2 (1 skills line, 1 bullet) are **real**, and are Blocker 1:
  they break at `AI-Assisted | Workﬂows` and `plus an | ofﬁcial`.

**Consequence, and why this is the more expensive bug of the two.** Because 3
of 5 warnings are noise on every single run, the check reads as chronically
unreliable. Phase 0 saw all 5, concluded "content the validator approved could
not be found in the PDF… and the pipeline shipped the PDF anyway," and filed
it as an unexplained major. The cry-wolf rate is precisely what stopped the
one genuine ATS defect from being legible. The module's own docstring
(`:2-11`) names **ligatures** as a thing it exists to catch — and then its
normalizer doesn't handle them.

**The concrete better version.** Two changes, and the second matters more:

1. Strip markdown emphasis in `_normalize` so markup never reads as missing
   content.
2. Do **not** simply add ligatures to `_TYPOGRAPHIC_SUBSTITUTIONS` — that
   would silence Blocker 1 rather than report it. Normalize ligatures for the
   "is this content present?" test, but emit a **separate, differently-worded
   warning** that names ligature corruption and says an ATS will not match the
   affected keyword. "Not found intact" is the wrong sentence for this defect;
   it sent Phase 0 looking for missing text.

**Reproduce:**
```python
import json, sys; sys.path.insert(0, "scripts")
import validate_pdf_text as v
data = json.load(open("output/morgan/json/MorganEscott_ContentStrategist_AbnormalAI_Resume.json"))
print(v.validate_pdf_text("output/morgan/pdf/MorganEscott_ContentStrategist_AbnormalAI_Resume.pdf", data))
# 5 warnings; re-test with line.replace("**","") -> 3 of them vanish
```

---

## MAJOR 3 — Reflective questions meant for Morgan are applied as resume copy

**Where:** `resume-engine/prompts/critique_resume.md:129-135` +
`scripts/orchestrator.py:2796-2814` (Step 5.5 apply loop). **Goal: 2.**

**The failure.** `critique_resume.md:129-135` instructs that any
recommendation about voice, personality, or distinctiveness be *"phrased as a
reflective question aimed at the candidate rather than a directive."* That is
a good instinct — real voice has to come from Morgan, not from a model.

But Step 5.5 feeds recommendations straight into an LLM that edits the resume.
There is a guard (`orchestrator.py:2807-2812`, `needs_personal_input`), and it
is well designed — but it only triggers when a question "asks you to reveal
something **personal** (e.g. why a project mattered, what felt satisfying)."
Voice questions phrased in strategic rather than emotional language fall
straight through it.

**What actually happened, from the shipped artifact.** The output records this
under `_recommendation_actions.applied`
(`…AbnormalAI_Resume.json:110`) — note that it is a question:

> "Since you have a strong background in CRM and sales operations, how do you
> see your transition into a pure content strategy role allowing you to
> leverage your unique 'revenue-first' perspective on content?"

And the resulting `SUMMARY_TEXT` contains:

> "Leverages a revenue-first perspective to ensure every content asset
> directly supports pipeline growth and sales enablement."

A question containing no instruction was "applied" the only way a model can
apply a question: by paraphrasing its own noun phrases into the document.
`revenue-first perspective` is lifted verbatim from the question. The
mechanism designed to elicit Morgan's real voice instead manufactured the
flattest sentence in the resume — the design intent is exactly inverted.

**The concrete better version.** Recommendations phrased as questions must not
reach the auto-apply loop at all. Either (a) have `critique_resume.md` emit
voice questions into a *separate schema field* from actionable
recommendations, so Step 5.5 never sees them and they surface to Morgan as
prompts to answer; or (b) widen the `needs_personal_input` guard from
"personal/emotional" to "any recommendation ending in a question mark."
(a) is the real fix; (b) is the one-line stopgap.

---

## MAJOR 4 — The Summary is generic by explicit instruction, and its own quality rule is never enforced

**Where:** `resume-engine/prompts/tailor_resume.md:67`. **Goal: 2.**

**The failure.** Read the shipped summary as a hiring manager:

> "**Campaign & CRM Strategist with 10+ years of experience transforming
> complex technical inputs into high-performing campaign assets and
> activation-ready narratives.** Specializes in using AI-assisted workflows to
> accelerate content transformation… Leverages a revenue-first perspective to
> ensure every content asset directly supports pipeline growth… Maintains
> brand alignment at scale while driving engagement through data-informed
> storytelling. Translates research, threat reports, and customer stories
> into cohesive, multi-channel content…"

Four consecutive sentences of the identical shape: `[Verb]s [abstract noun
phrase] to [abstract outcome]`. It is interchangeable with any competent
candidate's summary.

This is not model laziness — it is what the prompt asks for.
`tailor_resume.md:67` supplies the exemplars:

> `keep the same pronoun-free, name-free voice throughout (e.g. "Specializes
> in..." / "Transforms..." …)`

The output's second sentence begins, literally, "Specializes in…".

**The unenforced rule.** That same line also requires *"1–2 most relevant
proof points (metrics or scope, not adjectives)."* Measured against the
shipped summary: **zero** metrics in sentences 2–5 (only "10+ years" in
sentence 1). The prompt states the rule and nothing checks it —
`validate_resume.py` has no summary-substance check at all.

**Stated fairly:** pronoun-free summaries are a legitimate résumé convention
and I am not recommending first-person here. The defect is that the prompt's
*only* positive guidance is a stock verb exemplar, with no requirement that
the summary carry a checkable specific. You can be pronoun-free and still
distinctive — "Built the outbound program that became Treering's company-wide
template" is pronoun-free, concrete, and unmistakably Morgan.

**The contrast that proves the point.** The bullets in the same document are
concrete and specific ("Recovered $3M+ in stale Salesforce pipeline through a
systematic CRM data hygiene audit"). Bullets go through the voice-anchor-fed
audit path; the Summary is generated by the builder and then rewritten by two
stages that never see voice-anchors (see Finding 8). The one field with the
most latitude is the flattest thing in the document.

**Fix belongs in:** `tailor_resume.md:67` (replace the generic exemplars with
a requirement for one concrete, checkable specific), plus a
`validate_resume.py` check that the summary contains ≥1 metric or named
scope beyond the years-of-experience figure.

---

## MAJOR 5 — `validate_resume.py` never inspects `career_note` or `EDUCATION` bullets

**Where:** `scripts/validate_resume.py:33-37` (`_all_bullets`), `:216-226`
(`_check_pronouns_outside_why`). **Goal: 2.**

**Measured:** the shipped resume returns **0 violations** from
`validate_resume.validate()`. It nonetheless contains:

- **Pronouns outside the Why section.** `career_note`
  (`…Resume.json:28`) reads *"After a fulfilling run at Treering, **I** took
  time in 2024–25 to support a loved one's health and invest in **my**
  professional growth. **I'm** excited to return to work…"* — three pronouns.
  `tailor_resume.md:213` states the Why section is *"the ONLY section where
  pronouns are allowed."* `_check_pronouns_outside_why` inspects
  `SUMMARY_TEXT`, `SKILLS`, and EXPERIENCE bullets — not `career_note`. The
  document ships with a third-person summary and a first-person career note:
  two voices on one page.
- **5 completely unvalidated EDUCATION bullets.** `_all_bullets()` iterates
  `EXPERIENCE` only. The 5 bullets under `EDUCATION` (including *"drove 800%
  social media follower growth…"*) receive no length check, no forbidden-phrase
  check, no opening-verb-uniqueness check, and no pronoun check. 9 bullets are
  validated; 14 exist.

**Separately worth stating plainly:** every check in this file is a
*formatting* check — lengths, title case, verb uniqueness, banned words. Not
one is an ATS check or a substance check. To the plan's question — *does
`validate_resume.py` catch what a real ATS and a real recruiter would reject?*
— the answer is **no**. It catches what a copyeditor would reject. The two
things an ATS actually rejects on (keyword coverage against the JD, and
text-layer parseability) are checked nowhere in this file, and the JD-keyword
coverage of the finished resume is verified by nothing in the pipeline at all.

---

## MINOR 6 — The same fact carries two different numbers across the two documents

**Goal: 2.**

Resume: *"building a scalable library of **129** Outreach sequences and 55 SDR
personas."*
Cover letter: *"I authored **over 120** sequences…"*

`129` appears throughout the knowledge base. The string `120 sequences`
appears **nowhere** in it. A recruiter reading both documents from one
application sees two figures for one accomplishment, and the weaker one is the
invented rounding. Nothing in the pipeline validates consistency *between* the
resume and the cover letter — they are generated by separate calls with no
cross-check.

---

## MINOR 7 — The cover letter opens with the most generic sentence available to it

**Where:** `resume-engine/prompts/tailor_coverletter.md`. **Goal: 2.**

> "I am writing to express my interest in the Content Strategist role at
> Abnormal AI."

Also: "I am eager to…", "I am comfortable…", "I am ready to…" — three `I am
[adjective] to` constructions in three paragraphs — and "I have long admired
how Abnormal AI models human behavior," which is unverifiable flattery of
exactly the kind recruiters discount.

**Credit where due:** the cover letter is markedly *better* than the resume
summary — genuinely concrete ("8-step SDR onboarding website", "2,263-account
portfolio valued at $15.1M", "14-category QA checklists"). That tracks: the
cover-letter call is the one that requests the fuller context bundle
(`orchestrator.py:2319-2320`, `include_evidence_guide=True`).

**The gap:** `tailor_resume.md` carries a BANNED-words list and a
forbidden-openers rule for bullets. `tailor_coverletter.md` has no equivalent
banned-opener list, so the single most clichéd opening in business
correspondence is not prohibited anywhere.

---

## Finding 8 — Does the pipeline verifiably use `voice-anchors.md`? Yes — but not where it matters most

**Goal: 2.** Traced by reading the call sites, not assumed.

| Stage | Gets voice-anchors? | Where |
|---|---|---|
| Step 3 bullet audit/rewrite | **Yes** | `orchestrator.py:1288` via `build_audit_static_prefix()` |
| Cover letter | **Yes** | `orchestrator.py:2319-2320` |
| Step 4 builder (`tailor_resume.md`) | **Yes, but diluted** | `KB_ALLOWLIST` (`orchestrator.py:216`) → `load_knowledge_base()` → `kb_context` (`:2533`) |
| Step 5 critique (`critique_resume.md`) | **No** | `critique_contents` (`:2704-2706`) is JD + resume JSON only |
| Step 5.5 recommendation apply | **No** | `:2793-2814` — current resume JSON + one recommendation |

Two real problems follow:

1. **The builder sees it as 1 of 19 undifferentiated KB files** inside a
   ~105k-token `=== SYSTEM KNOWLEDGE BASE ===` blob that also contains three
   large CSVs. `grep -i voice resume-engine/prompts/tailor_resume.md` returns
   no instruction to use it for voice — the word "voice" appears there only in
   archetype labels and in the pronoun rule. The file is *present* but nothing
   tells the model what it is for.
2. **The two stages that most directly rewrite the Summary are voice-blind.**
   The critique scores voice and flags `flat_sections` (`critique_resume.md:
   187-210`) using `profile.yml`'s `voice_calibration_example` — a different,
   much smaller source — while `voice-anchors.md` itself is absent from that
   call. Findings 3 and 4 are downstream of this.

### 8b — `voice-anchors.md` mostly *describes* the voice instead of *demonstrating* it

Roughly 70% of the file is third-person summary of Morgan's past answers:

> "Describes agency internship experience; emphasizes creativity, fast-paced
> environment, and teamwork."

That teaches a model nothing about how Morgan sounds. The actual voice signal
is confined to the `>` blockquotes, and it is excellent and unmistakable:

> "I've been in WYSIWYG editors since the Geocities and Angelfire days, back
> when your cursor sparkled and your background auto-played MIDI files."
> "Journalism taught me to respect the reader's time — marketing taught me to
> earn it."
> "I love building systems that work quietly in the background — so people
> don't have to."

None of that register survives into either generated document. Root cause is
upstream in `scripts/build_voice_anchors.py`, which projects
`application-answers-index.csv` into thematic summaries. A voice file should
be mostly verbatim specimens; this one is mostly abstract paraphrase of them.

---

## Finding 9 — Fabrication risk: no fabrication detected. This is the pipeline's strongest area.

**Goal: 2.** The plan calls fabrication "a blocker class of its own." I could
not produce one.

Every quantitative claim in both documents traces to a knowledge-base file:

| Claim | Found in |
|---|---|
| `$75M+`, `$17M+`, `~$21M` revenue | `bullet-bank.md`, `summaries-and-skills-clean.csv`, `active-inventory.csv` |
| `800%` follower growth | `user-background-guide.md`, `bullet-bank-audited.csv` |
| `$3M+` pipeline recovered | `user-background-guide.md`, `active-inventory.csv` |
| `181 pages` of survey responses | `verified_metrics.json`, `coverage-tracker.csv` |
| `95% open` / `54% reply` | `active-inventory.csv`, `bullet-bank-keepers.csv` |
| `2,263` accounts / `$15.1M` / `8-step` (cover letter) | `active-inventory.csv`, `coverage-tracker.csv`, `bullet-bank-cluster-map-updated.csv` |

The `needs_personal_input` channel (`orchestrator.py:1017-1021`, `:2807-2812`)
is genuinely good anti-fabrication architecture: it instructs the model to
refuse to invent a personal answer rather than produce one. It is the reason
Finding 3 produced *bland* copy instead of *invented* copy — the guard held on
fabrication even while the routing failed.

The one exception is Finding 6's `over 120` — a loosened rounding of a
verified `129`, which is a fidelity defect rather than an invention.

---

## Summary of findings

| # | Severity | Finding | Goal |
|---|---|---|---|
| 1 | **Blocker** | Ligatures in PDF text layer break ATS keyword matching (incl. a verbatim JD phrase) | 2 |
| 2 | **Major** | `validate_pdf_text.py` false-positives on markdown every run, burying finding 1 | 1, 2 |
| 3 | **Major** | Critique's reflective questions auto-applied as resume copy | 2 |
| 4 | **Major** | Summary generic by prompt instruction; its proof-point rule unenforced | 2 |
| 5 | **Major** | `validate_resume.py` skips `career_note` and all EDUCATION bullets; checks style, not ATS | 2 |
| 6 | Minor | Resume says 129 sequences, cover letter says "over 120" | 2 |
| 7 | Minor | Cover letter opens with a stock cliché; no banned-opener rule for it | 2 |
| 8 | Major | voice-anchors reaches bullets + cover letter, but not critique/apply; and is mostly paraphrase, not specimen | 2 |
| 9 | — | No fabrication found; anti-fabrication design is sound | 2 |

**If only one thing gets fixed:** Finding 1. It silently degrades every
document the tool has ever produced, against the exact keywords the tool works
hardest to place.

**Cheapest high-value fix:** Finding 3(b) — one condition in the Step 5.5
guard stops questions being applied as copy.

## Post-review patch (2026-08-05, approved separately)

`scripts/validate_pdf_text.py` was patched after this review — the *detection*
half of Findings 1 and 2 only. The render defect itself is untouched.

- `_normalize` now strips emphasis markup (`**`, HTML tags) and expands
  ligatures, so neither reads as dropped content.
- New `_check_ligatures()` reports ligature corruption as its own named
  warning, listed first, naming the affected words and the CSS fix.
- `tests/test_validate_pdf_text.py`: fixture corrected to carry the
  `**Label:**` markdown real output always has (its absence is why this
  shipped), plus 7 new tests. Suite: 1098 tests, OK.

Measured on the same artifacts: resume **5 warnings → 1**, and that one now
names the real defect. Cover letter reports its own 7 ligature-corrupted words.

**New finding from the patch — MAJOR, for Phase 4:** `validate_pdf_text` is
called at `orchestrator.py:2990` on the **resume only**. The cover letter PDF
is never text-layer checked at all, despite carrying 7 ligature-corrupted
words of its own (`workﬂows`, `ﬂexible`, `efﬁciently`, `human-ﬁrst`…). Half
the application package ships with no ATS verification whatsoever.

## Handoffs

- **Phase 2 (blocking, highest priority):** Finding 1's fix lives in the
  resume/cover-letter templates or `render_html.py` — disable discretionary
  ligatures (`font-variant-ligatures: none`, `font-feature-settings: "liga" 0,
  "clig" 0`) and re-run the ligature scan in Finding 1 to confirm zero hits.
  I did not read or test those files (disjoint ownership).
- **Phase 4:** `scripts/validate_pdf_text.py` has no phase owner in
  `PLAN.md`; Findings 1 and 2 both land in it. Also — Phase 0's §2c
  observation (validator silent about whether attempt 2 passed or gave up) is
  real: `validate()` returns a bare list of strings and the pipeline prints
  nothing on success, so "0 issues" and "budget exhausted" are
  indistinguishable in the log.
- **Phase 4:** nothing in the pipeline verifies JD-keyword coverage of the
  *finished* resume. Given that keyword placement is the tool's core value,
  the absence of any coverage check is an architecture gap, not a validator
  gap.
- **Phase 1:** `build_voice_anchors.py` produces a voice file that is mostly
  paraphrase (Finding 8b). If onboarding generates this file for new users,
  every new profile inherits the same weakness.
