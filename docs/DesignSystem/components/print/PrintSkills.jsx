import React from "react";

// One category per line, never pipe-joined (a joined flow left stray "|"
// characters at line wraps). Category label is an 800-weight strong.
export function PrintSkills({ groups = [] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1, fontSize: "9.75pt", lineHeight: 1.15 }}>
      {groups.map((g, i) => (
        <span key={i} style={{ fontWeight: 400 }}>
          <strong style={{ fontWeight: 800 }}>{g.label}: </strong>{g.items.join(" · ")}
        </span>
      ))}
    </div>
  );
}
