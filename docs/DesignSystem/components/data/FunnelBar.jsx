import React from "react";

// Analytics bars: solid █ blocks, label column left, count and percentage
// in Subtext on the right. Stage colours run cool to warm.
export const FUNNEL_COLORS = ["var(--tui-blue)", "var(--tui-sky)", "var(--tui-green)", "var(--tui-yellow)", "var(--tui-peach)"];

export function FunnelBar({ label, count, max = 1, pct, color = "var(--tui-blue)", width = 40, glyph = "\u2588", labelWidth = 84 }) {
  const cells = max > 0 ? Math.max(count > 0 ? 1 : 0, Math.round((count * width) / max)) : 0;
  return (
    <div style={{ display: "flex", gap: 8.4, fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", whiteSpace: "pre" }}>
      <span style={{ color: "var(--tui-text)", width: labelWidth, flex: "0 0 auto" }}>{label}</span>
      <span style={{ color }}>{glyph.repeat(cells)}</span>
      <span style={{ color: "var(--tui-subtext)" }}>{count}{pct != null ? " (" + Math.round(pct) + "%)" : ""}</span>
    </div>
  );
}
