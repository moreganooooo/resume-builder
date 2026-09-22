import React from "react";

const SEP = <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>;

// Name in DM Serif Display 36pt, uppercase tagline at 15pt, then a
// pipe-separated contact row. Black only — no colour ever enters the PDF.
export function PrintHeader({ name, tagline, contacts = [], links = [] }) {
  return (
    <div style={{ marginBottom: 12, breakInside: "avoid" }}>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: "36pt", fontWeight: 400, lineHeight: "0.5625in", marginBottom: 1 }}>{name}</h1>
      {tagline ? <div style={{ fontSize: "15pt", lineHeight: "0.268in", marginBottom: 3 }}>{tagline}</div> : null}
      <div style={{ fontSize: "9.75pt", lineHeight: 1 }}>
        {contacts.map((c, i) => <React.Fragment key={i}>{i ? SEP : null}<span>{c}</span></React.Fragment>)}
      </div>
      {links.length ? (
        <div style={{ fontSize: "9.75pt", lineHeight: 1, marginTop: 3 }}>
          {links.map((c, i) => <React.Fragment key={i}>{i ? SEP : null}<span>{c}</span></React.Fragment>)}
        </div>
      ) : null}
    </div>
  );
}
