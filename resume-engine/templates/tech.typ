// Modern Technical Resume Typst Template
// Designed for Software Engineers, Systems Architects, and Data Scientists.
#let tech_resume(
  name: "Candidate Name",
  tagline: "",
  contact: "",
  summary: "",
  skills: (),
  experience: (),
  education: (),
) = {
  set page(paper: "us-letter", margin: (x: 0.5in, y: 0.5in))
  set text(font: "DM Sans", size: 9.5pt, fill: rgb("#0f172a"))
  set par(justify: true, leading: 0.5em)

  text(size: 18pt, weight: "bold", fill: rgb("#0f172a"))[#name]
  if tagline != "" [
    #h(8pt) #text(size: 10pt, weight: "medium", fill: rgb("#0284c7"))[// #tagline]
  ]
  \
  if contact != "" [
    #text(size: 8.5pt, fill: rgb("#64748b"))[#contact]
  ]

  v(4pt)
  line(length: 100%, stroke: 1pt + rgb("#0284c7"))
  v(4pt)

  if summary != "" [
    #text(size: 10.5pt, weight: "bold", fill: rgb("#0284c7"))[01 // TECHNICAL SUMMARY]
    #v(2pt)
    #summary
    #v(6pt)
  ]

  if skills.len() > 0 [
    #text(size: 10.5pt, weight: "bold", fill: rgb("#0284c7"))[02 // CORE TECHNOLOGIES]
    #v(2pt)
    #for s in skills [
      #box(fill: rgb("#f1f5f9"), inset: (x: 4pt, y: 2pt), radius: 2pt)[#text(size: 8.5pt, font: "Fira Code", fill: rgb("#0f172a"))[#s]] #h(3pt)
    ]
    #v(6pt)
  ]

  if experience.len() > 0 [
    #text(size: 10.5pt, weight: "bold", fill: rgb("#0284c7"))[03 // SYSTEMS & ENGINEERING EXPERIENCE]
    #v(2pt)
    #for job in experience [
      #grid(
        columns: (1fr, auto),
        [*#job.title* @ *#job.company*],
        [#text(size: 8.5pt, fill: rgb("#64748b"))[#job.period]]
      )
      #if job.location != "" [
        #text(size: 8pt, fill: rgb("#94a3b8"))[#job.location] \
      ]
      #for b in job.achievements [
        - #b
      ]
      #v(4pt)
    ]
  ]

  if education.len() > 0 [
    #text(size: 10.5pt, weight: "bold", fill: rgb("#0284c7"))[04 // EDUCATION & RESEARCH]
    #v(2pt)
    #for edu in education [
      - *#edu.degree* — #edu.institution #if edu.year != "" [(#edu.year)]
    ]
  ]
}
