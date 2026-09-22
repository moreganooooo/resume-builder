import React from "react";

// Vim-style search line, identical on Jobs and Pipeline: a SEARCH prompt
// pill while typing, a bare "/" once committed, then "N/M matching".
export function SearchBar({ query = "", active = false, matched = 0, total = 0 }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8.4, padding: "0 var(--pad-h)",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
      color: "var(--tui-text)", whiteSpace: "nowrap", overflow: "hidden",
    }}>
      {active
        ? <span style={{ background: "var(--tui-blue)", color: "var(--tui-surface)", fontWeight: 700, padding: "0 8.4px" }}>SEARCH</span>
        : <span style={{ color: "var(--tui-blue)", fontWeight: 700 }}>/</span>}
      <span>{query}{active ? <span style={{ color: "var(--tui-blue)" }}>█</span> : null}</span>
      <span style={{ color: "var(--tui-subtext)" }}>{matched}/{total} matching</span>
      <span style={{ color: "var(--tui-subtext)" }}>
        {active ? "Enter: keep   Esc: cancel   Ctrl+U: clear" : "Esc: clear   /: edit"}
      </span>
    </div>
  );
}
