import React from "react";

const STATUS = {
  offer: "var(--status-offer)", interview: "var(--status-interview)",
  responded: "var(--status-responded)", applied: "var(--status-applied)",
  evaluated: "var(--status-evaluated)", skip: "var(--status-skip)",
  rejected: "var(--status-rejected)", discarded: "var(--status-discarded)",
};

// Base-coloured text on the status colour, uppercased, one cell of padding
// each side. Closed-out statuses share Subtext so a rejection never reads
// like a response.
export function StatusPill({ status }) {
  const key = String(status || "").toLowerCase();
  return (
    <span style={{
      background: STATUS[key] || "var(--tui-subtext)", color: "var(--tui-base)",
      fontWeight: 700, padding: "var(--pad-pill)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap",
    }}>{key.toUpperCase()}</span>
  );
}
