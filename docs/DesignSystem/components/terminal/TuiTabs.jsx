import React from "react";

// Pipeline's filter tabs: label + live count, with a heavy ━ underline on
// the active tab and a light ─ under the rest.
export function TuiTabs({ tabs, active = 0, onChange }) {
  const label = (t) => t.label + (typeof t.count === "number" ? " (" + t.count + ")" : "");
  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", padding: "var(--pad-v) 0", overflow: "hidden" }}>
      <div style={{ display: "flex", whiteSpace: "nowrap" }}>
        {tabs.map((t, i) => (
          <button key={t.label} onClick={() => onChange && onChange(i)}
            style={{
              all: "unset", cursor: onChange ? "pointer" : "default", padding: "0 8.4px",
              fontFamily: "inherit", fontSize: "inherit", lineHeight: "inherit",
              fontWeight: i === active ? 700 : 400,
              color: i === active ? "var(--tui-blue)" : "var(--tui-subtext)",
            }}>{label(t)}</button>
        ))}
      </div>
      <div style={{ display: "flex", whiteSpace: "pre", marginTop: "var(--tui-line-height)" }}>
        {tabs.map((t, i) => (
          <span key={t.label} style={{ color: i === active ? "var(--tui-blue)" : "var(--tui-overlay)" }}>
            {(i === active ? "━" : "─").repeat(label(t).length + 2)}
          </span>
        ))}
      </div>
    </div>
  );
}
