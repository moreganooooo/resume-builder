import React from "react";

const SEP = <span style={{ color: "var(--print-divider)", padding: "0 4px" }}>|</span>;

// One job / education entry: 800-weight title, a pipe-separated meta line
// under a hairline rule, then bullets. Bullets are never bolded.
export function PrintEntry({ title, meta = [], clients, note, bullets = [], groupLabel }) {
  return (
    <div style={{ marginBottom: 10, breakInside: "avoid", pageBreakInside: "avoid" }}>
      <div style={{ fontWeight: 800 }}>{title}</div>
      {meta.length ? (
        <div style={{ fontWeight: 800, marginBottom: 3, borderBottom: "0.018cm solid var(--print-divider)" }}>
          {meta.map((m, i) => <React.Fragment key={i}>{i ? SEP : null}<span>{m}</span></React.Fragment>)}
        </div>
      ) : null}
      {clients ? <div style={{ marginTop: 3 }}><strong style={{ fontWeight: 800 }}>Clients: </strong>{clients}</div> : null}
      {note ? <div style={{ fontStyle: "italic", marginTop: 4, marginBottom: 3 }}><strong style={{ fontWeight: 800, fontStyle: "normal" }}>Career Note: </strong>{note}</div> : null}
      {groupLabel ? <div style={{ fontStyle: "italic", fontWeight: 600, marginTop: 5, marginBottom: 1 }}>{groupLabel}</div> : null}
      {bullets.length ? (
        <ul style={{ paddingLeft: 16, marginTop: 3 }}>
          {bullets.map((b, i) => <li key={i} style={{ marginBottom: 1, fontWeight: 400 }}>{b}</li>)}
        </ul>
      ) : null}
    </div>
  );
}
