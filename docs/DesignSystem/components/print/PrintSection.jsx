import React from "react";

// Section title: DM Serif Display 16pt over a 0.018cm #9aa3af rule, 10px
// below the block. That rule weight is the only one in the document.
export function PrintSection({ title, avoidBreak = false, children }) {
  return (
    <div style={{ marginBottom: 10, breakInside: avoidBreak ? "avoid" : "auto", pageBreakInside: avoidBreak ? "avoid" : "auto" }}>
      <div style={{
        fontFamily: "var(--font-display)", fontSize: "16pt", fontWeight: 400, lineHeight: 1.15,
        borderBottom: "0.018cm solid var(--print-divider)", paddingBottom: 2, marginBottom: 3,
      }}>{title}</div>
      {children}
    </div>
  );
}
