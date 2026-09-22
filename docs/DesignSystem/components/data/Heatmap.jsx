import React from "react";

// The Mission Control calendar: 7 rows of ■ cells in five steps,
// Surface (empty) -> Subtext -> Blue -> Peach -> Green.
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function cellColor(count, max) {
  if (!count) return "var(--tui-surface)";
  const pct = max <= 1 ? 1 : count / max;
  if (pct > 0.75) return "var(--tui-green)";
  if (pct > 0.5) return "var(--tui-peach)";
  if (pct > 0.25) return "var(--tui-blue)";
  return "var(--tui-subtext)";
}

export function Heatmap({ weeks = [], max = 1 }) {
  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)" }}>
      {DAYS.map((d, row) => (
        <div key={d} style={{ whiteSpace: "pre" }}>
          <span style={{ color: "var(--tui-subtext)" }}>{d} </span>
          {weeks.map((w, col) => (
            <span key={col} style={{ color: cellColor(w[row] || 0, max) }}>{"\u25a0 "}</span>
          ))}
        </div>
      ))}
    </div>
  );
}
