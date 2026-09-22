import React from "react";

// The compact header the CLI shows once you are inside a script: product
// mark, the active screen, and the execution-mode note, pipe-separated in a
// Sky-bordered bar.
export function CliModeBar({ product = "RESUME BUILDER", screen, mode = "Active Script Execution Mode" }) {
  const pipe = <span style={{ color: "var(--tui-overlay)", padding: "0 8.4px" }}>|</span>;
  return (
    <div style={{
      border: "1px solid var(--tui-sky)", borderRadius: "var(--radius-panel)",
      padding: "2px 21px", fontFamily: "var(--font-mono)",
      fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
      whiteSpace: "nowrap", overflow: "hidden",
    }}>
      <span style={{ color: "var(--tui-mauve)" }}>✦ ◆ </span>
      <span style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>{product}</span>
      {pipe}
      <span style={{ color: "var(--tui-blue)", fontWeight: 700 }}>{screen}</span>
      {pipe}
      <span style={{ color: "var(--tui-subtext)" }}>{mode}</span>
      <span style={{ color: "var(--tui-mauve)" }}> ✦</span>
    </div>
  );
}
