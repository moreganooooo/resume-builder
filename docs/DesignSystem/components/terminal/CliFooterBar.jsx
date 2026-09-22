import React from "react";

// The two footers every script screen pins to the bottom row. `nav` is the
// menu footer (display_footer_commands); `execution` is what replaces it
// while a script is running (display_execution_footer) — the whole point
// being that the keys on offer change the moment control leaves the menu.
// Both are sparkle-bracketed and pipe-separated, keys bold and coloured
// by consequence: Blue to move, Green to commit, Red to stop.
export function CliFooterBar({ variant = "nav" }) {
  const sparkle = { color: "var(--tui-mauve)" };
  const muted = { color: "var(--tui-subtext)" };
  const pipe = <span style={muted}>{"│  "}</span>;
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", whiteSpace: "pre", overflow: "hidden",
    }}>
      <span style={sparkle}>{"✦ "}</span>
      {variant === "execution" ? (
        <>
          <span style={{ color: "var(--tui-red)", fontWeight: 700 }}>CTRL+C</span>
          <span style={muted}>{" stop active script  "}</span>
          {pipe}
          <span style={muted}>Please wait for execution to complete...</span>
        </>
      ) : (
        <>
          <span style={{ color: "var(--tui-blue)", fontWeight: 700 }}>↑↓ / JK</span>
          <span style={muted}>{" navigate  "}</span>
          {pipe}
          <span style={{ color: "var(--tui-green)", fontWeight: 700 }}>ENTER</span>
          <span style={muted}>{" select  "}</span>
          {pipe}
          <span style={{ color: "var(--tui-red)", fontWeight: 700 }}>CTRL+C</span>
          <span style={muted}>{" cancel / exit "}</span>
        </>
      )}
      <span style={sparkle}>{" ✦"}</span>
    </div>
  );
}
