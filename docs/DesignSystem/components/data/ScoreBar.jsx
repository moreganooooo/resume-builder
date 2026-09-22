import React from "react";

// renderSpringBar: 15 cells of the LOWER THREE-QUARTERS block. Filled and
// empty use the same glyph so the bar reads as one shape; the quarter-cell
// gap at the top is what stops stacked bars fusing into a slab.
export function ScoreBar({ value, max = 5, width = 15, label, valueText }) {
  const ratio = Math.max(0, Math.min(1, (value || 0) / max));
  const fill = Math.round(ratio * width);
  const color = ratio >= 0.8 ? "var(--tui-green)" : ratio >= 0.6 ? "var(--tui-blue)" : ratio >= 0.4 ? "var(--tui-yellow)" : "var(--tui-subtext)";
  return (
    <div style={{ display: "flex", gap: 8.4, fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", whiteSpace: "pre" }}>
      {label != null ? <span style={{ color: "var(--tui-subtext)", minWidth: 160, flex: "0 0 auto" }}>{label}</span> : null}
      <span style={{ flex: "0 0 auto" }}><span style={{ color }}>{"\u2586".repeat(fill)}</span><span style={{ color: "var(--tui-overlay)" }}>{"\u2586".repeat(width - fill)}</span></span>
      <span style={{ color: "var(--tui-text)", flex: "0 0 auto" }}>{valueText != null ? valueText : (max === 100 ? Math.round(value) + "%" : Number(value).toFixed(1))}</span>
    </div>
  );
}
