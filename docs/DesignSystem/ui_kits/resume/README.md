# UI kit — Resume (PDF output)

The second half of the product: the artifact the engine actually produces.
Python builds a JSON resume, `render_html.py` fills an HTML template, and
Playwright 1.61.1 headless Chromium prints it to PDF under a strict page budget.

**Screens**

| File | Source |
| --- | --- |
| `Resume.jsx` | `resume-engine/templates/cv-template.html` |
| `CoverLetter.jsx` | `resume-engine/templates/coverletter-template.html` |

`index.html` switches between them (1 / 2) and prints cleanly — the toggle and
footnote are hidden in print.

**Rules this kit exists to demonstrate**

- Absolute monochrome: `#000` on `#fff`, `#9aa3af` for rules. No colour enters
  the PDF, ever.
- One body size — 9.75pt at 1.15 — for bullets, job titles, meta, skills,
  education and certifications alike. Hierarchy is weight (400 vs 800) and rules.
- Section order: Summary → Skills (highest ATS signal) → Experience → Patents →
  Certifications → Education → Why. Empty sections are dropped entirely, not
  left as headers.
- `break-inside: avoid` on every job, education and certification block.
- Ligatures off. Never remove: pypdf and pdfminer extract "ﬁ" verbatim and the
  keyword stops matching.
- No bolding inside bullets.
- The cover letter runs a looser scale of its own: 10.5pt at 1.6, a 32pt name,
  a 14pt tagline, and a rule under the header block.

The signature image is a real feature (`profile_paths.signature_path()`), left
as a labelled placeholder here — no signature asset exists in the repository.
