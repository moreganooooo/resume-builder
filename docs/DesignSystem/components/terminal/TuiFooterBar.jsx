import React from "react";

// RenderHierarchicalFooter: three tiers of keybinding, plus the wordmark
// pushed to the right edge. Primary keys are bracketed and Mauve.
export function TuiFooterBar({ primary = [], actions = [], system = [], brand = "resume-builder dashboard" }) {
  const tier = (list, keyColor, bracket) =>
    list.map((b, i) => (
      <span key={keyColor + i} style={{ whiteSpace: "nowrap" }}>
        <b style={{ color: keyColor, fontWeight: 700 }}>{bracket ? "[" + b.key + "]" : b.key}</b>
        <span style={{ color: "var(--tui-subtext)" }}> {b.desc}</span>
      </span>
    ));
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      background: "var(--tui-surface)", padding: "0 8.4px",
      minHeight: "var(--tui-line-height)", fontFamily: "var(--font-mono)",
      fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
      overflow: "hidden", whiteSpace: "nowrap",
    }}>
      <span style={{ display: "flex", gap: 16, minWidth: 0, overflow: "hidden" }}>
        {tier(primary, "var(--tui-mauve)", true)}
        {tier(actions, "var(--tui-blue)", false)}
        {tier(system, "var(--tui-overlay)", false)}
      </span>
      <span style={{ color: "var(--tui-subtext)" }}>{brand}</span>
    </div>
  );
}
