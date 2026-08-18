// Executive Resume Typst Template
// Designed for Senior, Staff, Director, and VP-level roles.
#let executive_resume(
  name: "Candidate Name",
  tagline: "",
  contact: "",
  summary: "",
  skills: (),
  experience: (),
  education: (),
) = {
  set page(paper: "us-letter", margin: (x: 0.6in, y: 0.6in))
  set text(font: "Libertinus Serif", size: 10pt, fill: rgb("#111827"))
  set par(justify: true, leading: 0.55em)

  align(center)[
    #text(size: 20pt, weight: "bold", tracking: 0.05em)[#upper(name)]
    #if tagline != "" [
      \ #v(2pt) #text(size: 11pt, style: "italic", fill: rgb("#374151"))[#tagline]
    ]
    #if contact != "" [
      \ #v(2pt) #text(size: 8.5pt, fill: rgb("#4b5563"))[#contact]
    ]
  ]

  v(6pt)
  line(length: 100%, stroke: 1pt + rgb("#111827"))
  v(4pt)

  if summary != "" [
    #text(size: 11pt, weight: "bold")[EXECUTIVE PROFILE]
    #v(2pt)
    #summary
    #v(6pt)
  ]

  if skills.len() > 0 [
    #text(size: 11pt, weight: "bold")[CORE LEADERSHIP & TECHNICAL COMPETENCIES]
    #v(2pt)
    #skills.join(" • ")
    #v(6pt)
  ]

  if experience.len() > 0 [
    #text(size: 11pt, weight: "bold")[PROFESSIONAL EXPERIENCE]
    #v(2pt)
    #for job in experience [
      #grid(
        columns: (1fr, auto),
        [*#job.title* — #job.company],
        [#job.period]
      )
      #if job.location != "" [
        #text(size: 8.5pt, style: "italic", fill: rgb("#4b5563"))[#job.location] \
      ]
      #for b in job.achievements [
        - #b
      ]
      #v(4pt)
    ]
  ]

  if education.len() > 0 [
    #text(size: 11pt, weight: "bold")[EDUCATION & CREDENTIALS]
    #v(2pt)
    #for edu in education [
      - *#edu.degree* — #edu.institution #if edu.year != "" [(#edu.year)]
    ]
  ]
}
