// The cover letter is its own template (resume-engine/templates/coverletter-template.html)
// with a slightly larger, looser scale than the resume: 10.5pt at 1.6,
// a 32pt name, and a rule under the header block.
const SEP = <span style={{ color: "var(--print-divider)", padding: "0 3px" }}>|</span>;

function CoverLetter() {
  const body = {
    fontFamily: "var(--font-body)", fontSize: "10.5pt", fontWeight: 400,
    lineHeight: 1.6, color: "var(--print-text)", background: "var(--print-bg)",
    width: "100%", maxWidth: "8.5in", margin: "0 auto",
    fontVariantLigatures: "none", fontFeatureSettings: '"liga" 0, "clig" 0',
  };
  return (
    <div style={body}>
      <div>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: "32pt", fontWeight: 400, lineHeight: "0.5in" }}>Morgan Avery</h1>
        <div style={{ fontSize: "14pt", lineHeight: "0.25in", marginBottom: 4 }}>SENIOR BRAND STRATEGIST | CONTENT LEAD</div>
        <div style={{ fontSize: "9.75pt", lineHeight: 1 }}>
          <span>(785) 555-0134</span>{SEP}<span>morgan@example.com</span>{SEP}
          <span>linkedin.com/in/morganavery</span>{SEP}<span>Lawrence, KS</span>
        </div>
        <hr style={{ border: "none", borderTop: "0.018cm solid var(--print-divider)", marginTop: 6 }} />
      </div>

      <div style={{ marginTop: 28, lineHeight: 1.4 }}>19 September 2026</div>

      <div style={{ marginTop: 30, lineHeight: 1.3 }}>
        Priya Raghavan<br />Founder &amp; CEO<br />Harlow &amp; Finch<br />Kansas City, MO
      </div>

      <div style={{ marginTop: 30 }}>Dear Priya,</div>

      <div style={{ marginTop: 8, lineHeight: 1.5 }}>
        <p style={{ marginBottom: 10 }}>
          Your posting says Harlow &amp; Finch has outgrown the voice it launched with. I spent 2021 and 2022 doing
          exactly that work at Callahan Creek: two creative teams merged, two vocabularies, and a client roster that
          noticed every seam. The guidelines we wrote then are still the ones that agency uses for its CPG accounts.
        </p>
        <p style={{ marginBottom: 10 }}>
          What I would bring first is process, not taste. The seasonal campaign system I built took concept-to-air
          from eleven weeks to six across four product lines — not by working faster, but by deciding earlier which
          approvals actually mattered. At sixty people, that is the difference between a brand system that holds and
          one that gets improvised for another three years.
        </p>
        <p>
          I would welcome the chance to talk through what the first ninety days should look like.
        </p>
      </div>

      <div style={{ marginTop: 18 }}>Sincerely,</div>
      <div style={{ marginTop: 10 }}>
        <div style={{ height: 80, maxWidth: 240, display: "flex", alignItems: "center", color: "var(--print-divider)", fontStyle: "italic", fontSize: "9pt", marginBottom: 10 }}>
          [signature image — profile_paths.signature_path(), optional]
        </div>
        <div style={{ lineHeight: 1.5 }}>Morgan Avery<br />(785) 555-0134 · morgan@example.com</div>
      </div>
    </div>
  );
}

Object.assign(window, { CoverLetter });
