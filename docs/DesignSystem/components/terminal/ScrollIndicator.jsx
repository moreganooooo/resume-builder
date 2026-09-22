import React from "react";

// The evidence that a viewport scrolls. Bubbles' viewport knows its
// position and never shows it; without this, "is there more below?" is a
// question the user answers by pressing keys.
//
// Two forms, used together:
//   rail     a right-edge thumb, height proportional to the visible
//            fraction, Overlay track and Mauve thumb. One cell wide.
//   readout  "12%" or "3 of 28" in the pane's top-right, in Subtext
//
// The rail hides itself when everything fits — a full-height thumb is
// noise. Percentages clamp to 0/100 at the ends so the user can trust
// "100%" to mean the actual bottom.
export function ScrollIndicator({ offset = 0, visible = 10, total = 10, height, style }) {
  const overflow = total > visible;
  const max = Math.max(1, total - visible);
  const pct = overflow ? Math.round(Math.min(1, Math.max(0, offset / max)) * 100) : 100;
  const frac = Math.min(1, visible / Math.max(1, total));
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", ...style }}>
      <div style={{ color: "var(--tui-subtext)", whiteSpace: "nowrap" }}>{overflow ? pct + "%" : "all"}</div>
      {overflow ? (
        <div style={{ position: "relative", width: 3, flex: height ? "0 0 " + height : 1, minHeight: 40, background: "var(--tui-overlay)", borderRadius: 2, marginTop: 3 }}>
          <div style={{
            position: "absolute", left: 0, width: 3, borderRadius: 2, background: "var(--tui-mauve)",
            height: Math.max(8, frac * 100) + "%",
            top: (1 - frac) * (pct / 100) * 100 + "%",
            transition: "top var(--dur-cursor) var(--ease-snappy)",
          }}></div>
        </div>
      ) : null}
    </div>
  );
}
