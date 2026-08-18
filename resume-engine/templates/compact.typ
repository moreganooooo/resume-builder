// Compact 1-Page Resume Typst Template
// Designed for high-density space efficiency and strict 1-page limits.
#let compact_resume(
  name: "Candidate Name",
  tagline: "",
  contact: "",
  summary: "",
  skills: (),
  experience: (),
  education: (),
) = {
  set page(paper: "us-letter", margin: (x: 0.4in, y: 0.4in))
  set text(font: "DM Sans", size: 9pt, fill: rgb("#0f172a"))
  set par(justify: true, leading: 0.45em)

  grid(
    columns: (1fr, auto),
    [
      #text(size: 16pt, weight: "bold")[#name] \
      #if tagline != "" [#text(size: 9.5pt, weight: "medium", fill: rgb("#2563eb"))[#tagline]]
    ],
    [
      #align(right)[#text(size: 8pt, fill: rgb("#475569"))[#contact]]
    ]
  )

  v(2pt)
  line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
  v(2pt)

  if summary != "" [
    #text(size: 9.5pt, weight: "bold", fill: rgb("#1e293b"))[SUMMARY]
    #v(1pt)
    #summary
    #v(3pt)
  ]

  if skills.len() > 0 [
    #text(size: 9.5pt, weight: "bold", fill: rgb("#1e293b"))[SKILLS]
    #v(1pt)
    #skills.join(" | ")
    #v(3pt)
  ]

  if experience.len() > 0 [
    #text(size: 9.5pt, weight: "bold", fill: rgb("#1e293b"))[EXPERIENCE]
    #v(1pt)
    #for job in experience [
      #grid(
        columns: (1fr, auto),
        [*#job.title*, #job.company],
        [#job.period]
      )
      #for b in job.achievements [
        - #b
      ]
      #v(2pt)
    ]
  ]

  if education.len() > 0 [
    #text(size: 9.5pt, weight: "bold", fill: rgb("#1e293b"))[EDUCATION]
    #v(1pt)
    #for edu in education [
      - *#edu.degree*, #edu.institution #if edu.year != "" [(#edu.year)]
    ]
  ]
}
