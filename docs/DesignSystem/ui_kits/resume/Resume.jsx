const { PrintPage, PrintHeader, PrintSection, PrintEntry, PrintSkills } = window.ResumeBuilderDesignSystem_2d03b1;

const CONTACTS = ["(785) 555-0134", "morgan@example.com", "linkedin.com/in/morganavery", "Lawrence, KS"];

function Resume() {
  return (
    <PrintPage>
      <PrintHeader name="Morgan Avery" tagline="SENIOR BRAND STRATEGIST | CONTENT LEAD" contacts={CONTACTS} />

      <PrintSection title="PROFESSIONAL SUMMARY" avoidBreak>
        Brand strategist with eleven years across CPG, retail and agency work. Builds campaign systems that
        survive handoff — seasonal planning frameworks, voice guidelines and review processes that let nine-person
        teams ship without a bottleneck. Owned <strong style={{ fontWeight: 800 }}>$4.1M</strong> in annual media
        and production budget and reduced concept-to-air from eleven weeks to six.
      </PrintSection>

      <PrintSection title="SKILLS" avoidBreak>
        <PrintSkills groups={[
          { label: "Brand", items: ["Positioning", "Naming", "Voice & tone", "Brand architecture"] },
          { label: "Campaign", items: ["Seasonal planning", "Concept development", "Retail media", "Production oversight"] },
          { label: "Leadership", items: ["Team building", "Budget ownership", "Agency management", "Cross-functional review"] },
        ]} />
      </PrintSection>

      <PrintSection title="WORK EXPERIENCE">
        <PrintEntry
          title="Creative Director, Consumer Packaged Goods"
          meta={["Callahan Creek", "450 staff", "Lawrence, KS", "2019 – 2024"]}
          note="Role absorbed two adjacent teams after the 2021 merger."
          bullets={[
            "Rebuilt the seasonal campaign process, cutting concept-to-air from 11 weeks to 6 across four product lines.",
            "Led a team of nine — three copy, four art direction, two production — through a merger and two leadership changes.",
            "Owned $4.1M in annual media and production budget, coming in under plan in three of five years.",
            "Established the voice guidelines still used across the agency's CPG roster.",
          ]} />
        <PrintEntry
          title="Associate Creative Director, Retail & Grocery"
          meta={["VML", "2,000+ staff", "Kansas City, MO", "2015 – 2019"]}
          clients="Hy-Vee, Sprint, Dairy Farmers of America"
          bullets={[
            "Ran the grocery vertical's weekly circular creative, a 52-week cadence with zero missed drops.",
            "Introduced concept testing ahead of production, which cut late-stage revisions by roughly a third.",
          ]} />
        <PrintEntry
          title="Senior Copywriter"
          meta={["Bluestem Cooperative", "180 staff", "Lawrence, KS", "2013 – 2015"]}
          bullets={[
            "Wrote member-facing campaigns, annual reports and internal comms for a 40,000-member cooperative.",
          ]} />
      </PrintSection>

      <PrintSection title="TRAINING & CERTIFICATIONS" avoidBreak>
        <div style={{ marginBottom: 1 }}>
          <span style={{ fontWeight: 800 }}>Brand Strategy Intensive</span>
          <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
          <span>Berlin School of Creative Leadership</span>
          <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
          <span>2021</span>
        </div>
        <div>
          <span style={{ fontWeight: 800 }}>Google Analytics 4 Certification</span>
          <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
          <span>Google</span>
          <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
          <span>2023</span>
        </div>
      </PrintSection>

      <PrintSection title="EDUCATION" avoidBreak>
        <div style={{ breakInside: "avoid", marginBottom: 6 }}>
          <div style={{ marginBottom: 3, borderBottom: "0.018cm solid var(--print-divider)" }}>
            <span style={{ fontWeight: 800 }}>BA, Journalism &amp; Mass Communications</span>
            <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
            <span style={{ fontWeight: 800 }}>University of Kansas</span>
            <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
            <span style={{ fontWeight: 800 }}>Lawrence, KS</span>
            <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>
            <span style={{ fontWeight: 800 }}>2013</span>
          </div>
        </div>
      </PrintSection>

      <PrintSection title="WHY HARLOW &amp; FINCH?" avoidBreak>
        <p style={{ marginBottom: 8 }}>
          The brief describes a brand that outgrew its founding voice — the same problem the 2021 merger handed me,
          where two creative teams and two vocabularies had to become one without either side feeling overwritten.
        </p>
        <p>
          A sixty-person, founder-led company is the size where a brand system either gets built properly or gets
          improvised for another three years. That is the work I want to be doing.
        </p>
      </PrintSection>
    </PrintPage>
  );
}

Object.assign(window, { Resume });
