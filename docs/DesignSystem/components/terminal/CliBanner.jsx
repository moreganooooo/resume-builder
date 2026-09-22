import React from "react";

// The launcher wordmark: two rows of chunky block letters against a
// starfield, over the profile's live counts. The product draws this with a
// figlet block font; here the same weight comes from a heavy sans with a
// layered offset outline, which is what gives the letters their 3-D lip.
const OUTLINE =
  "2px 2px 0 var(--tui-mauve), 4px 4px 0 var(--tui-base), 5px 5px 0 var(--tui-mauve)";

const STARS = [
  [4, 12], [11, 30], [7, 55], [18, 8], [22, 41], [14, 72], [31, 23], [27, 63],
  [38, 5], [35, 49], [44, 34], [41, 80], [52, 17], [48, 58], [57, 44], [61, 27],
  [66, 69], [70, 11], [74, 38], [79, 56], [83, 21], [88, 47], [92, 64], [96, 31],
  [9, 88], [25, 92], [46, 95], [68, 90], [87, 85], [54, 78],
];

export function CliBanner({
  title = "RESUME BUILDER",
  tagline = "Custom Resumes & Cover Letters, Powered by Gemini",
  lines = [],
}) {
  const words = title.split(" ");
  return (
    <div style={{
      position: "relative", border: "1px solid var(--tui-sky)",
      borderRadius: "var(--radius-panel)", padding: "12px 21px 10px",
      overflow: "hidden", fontFamily: "var(--font-mono)",
      fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
    }}>
      <div aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
        {STARS.map(([x, y], i) => (
          <span key={i} style={{
            position: "absolute", left: x + "%", top: y + "%",
            color: i % 3 === 0 ? "var(--tui-mauve)" : "var(--tui-sky)",
            opacity: i % 2 ? 0.85 : 0.55, fontSize: i % 4 ? 10 : 13,
          }}>{i % 3 === 0 ? "✦" : "·"}</span>
        ))}
      </div>
      <div style={{ position: "relative", width: "44%", minWidth: 380 }}>
        {words.map((w) => (
          <div key={w} style={{
            fontFamily: "var(--font-body)", fontWeight: 800, fontSize: 64,
            lineHeight: 1.05, letterSpacing: "0.04em", color: "var(--cat-mauve)",
            textShadow: OUTLINE,
          }}>{w}</div>
        ))}
        <div style={{ color: "var(--tui-text)", fontWeight: 700, paddingTop: 10 }}>{tagline}</div>
        {lines.map((l) => (
          <div key={l} style={{ color: "var(--tui-blue)" }}>{l}</div>
        ))}
      </div>
    </div>
  );
}
