import React from "react";

// The launcher wordmark, drawn the way the product draws it: the exact
// ANSI Shadow block-letter rows from cli_art.MAIN_BANNER_LINES, painted with
// one diagonal gradient from BRAND (--tui-sky) at top-left to BRAND_ACCENT
// (--tui-mauve) at bottom-right, inside a double-ruled BRAND panel, with a
// sparkle field filling the space to the right. Keep BANNER_ROWS in step
// with cli_art.py if the wordmark ever changes.
const BANNER_ROWS = [
  "██████╗ ███████╗███████╗██╗   ██╗███╗   ███╗███████╗",
  "██╔══██╗██╔════╝██╔════╝██║   ██║████╗ ████║██╔════╝",
  "██████╔╝█████╗  ███████╗██║   ██║██╔████╔██║█████╗  ",
  "██╔══██╗██╔══╝  ╚════██║██║   ██║██║╚██╔╝██║██╔══╝  ",
  "██║  ██║███████╗███████║╚██████╔╝██║ ╚═╝ ██║███████╗",
  "╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝",
  "",
  "██████╗ ██╗   ██╗██╗██╗     ██████╗ ███████╗██████╗ ",
  "██╔══██╗██║   ██║██║██║     ██╔══██╗██╔════╝██╔══██╗",
  "██████╔╝██║   ██║██║██║     ██║  ██║█████╗  ██████╔╝",
  "██╔══██╗██║   ██║██║██║     ██║  ██║██╔══╝  ██╔══██╗",
  "██████╔╝╚██████╔╝██║███████╗██████╔╝███████╗██║  ██║",
  "╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝",
];

const GRADIENT = "linear-gradient(135deg, var(--tui-sky) 0%, var(--tui-mauve) 100%)";

// Same glyph weighting as cli_art._SPARKLE_GLYPHS: mostly small dots, so
// stars stay an accent. Fixed positions (not random) so screenshots are stable.
const STARS = [
  [6, 10, "·"], [14, 34, "⋆"], [9, 58, "·"], [21, 18, "✦"], [26, 44, "·"],
  [18, 76, "✧"], [34, 26, "·"], [30, 66, "⋆"], [41, 8, "·"], [38, 52, "✦"],
  [47, 36, "·"], [44, 84, "·"], [55, 20, "⋆"], [51, 60, "·"], [60, 46, "✧"],
  [66, 30, "·"], [70, 72, "✦"], [74, 14, "·"], [78, 40, "⋆"], [83, 58, "·"],
  [87, 24, "✦"], [91, 50, "·"], [95, 68, "⋆"], [12, 90, "·"], [57, 88, "✧"],
  [81, 86, "·"],
];

export function CliBanner({
  tagline = "Custom Resumes & Cover Letters, Powered by Gemini",
  lines = [],
}) {
  return (
    <div style={{
      border: "3px double var(--tui-sky)", borderRadius: 0,
      padding: "calc(var(--tui-line-height) * 1em) 2ch",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", gap: "3ch",
      overflow: "hidden",
    }}>
      <div style={{ flex: "none" }}>
        <pre aria-label="Resume Builder" style={{
          margin: 0, font: "inherit", lineHeight: 1, whiteSpace: "pre",
          backgroundImage: GRADIENT, WebkitBackgroundClip: "text",
          backgroundClip: "text", color: "transparent",
        }}>{BANNER_ROWS.join("\n")}</pre>
        <div style={{ color: "var(--tui-text)", fontWeight: 700, paddingTop: "0.5em" }}>{tagline}</div>
        {lines.map((l) => (
          <div key={l} style={{ color: "var(--tui-blue)" }}>{l}</div>
        ))}
      </div>
      <div aria-hidden="true" style={{ position: "relative", flex: 1, minWidth: 0 }}>
        {STARS.map(([x, y, g], i) => (
          <span key={i} style={{
            position: "absolute", left: x + "%", top: y * 0.7 + "%",
            color: x + y > 90 ? "var(--tui-mauve)" : "var(--tui-sky)",
          }}>{g}</span>
        ))}
      </div>
    </div>
  );
}
