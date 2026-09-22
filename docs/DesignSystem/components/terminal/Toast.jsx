import React from "react";

// Output that does not belong to any pane — tea.Printf's above-the-program
// region, rendered as a stack in the bottom-right above the footer.
//
// The rule that decides toast vs. panel: a toast reports something that
// ALREADY happened and needs no answer. Anything the user must act on is
// a panel or an inline error, because a toast that expires takes the
// user's only chance to act with it.
//
//  - Success and info auto-dismiss (4s / 6s). Warnings and errors do not
//    — they wait for a keypress, because an unread failure is worse than
//    a crowded corner.
//  - Maximum three. Older ones collapse into "+2 earlier" rather than
//    scrolling the stack, so the newest is always in the same place.
//  - One line each, with the same ✓ ✗ ⚠ ✦ prefixes as every other
//    message. A toast that needs two lines is a panel.
const TONE = {
  success: { c: "var(--tui-green)", g: "\u2713" },
  error: { c: "var(--tui-red)", g: "\u2717" },
  warning: { c: "var(--tui-yellow)", g: "\u26a0" },
  info: { c: "var(--tui-mauve)", g: "\u2726" },
};

export function Toast({ items = [], overflow = 0, style }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", flexDirection: "column",
      alignItems: "flex-end", gap: 4, ...style,
    }}>
      {overflow > 0 ? <div style={{ color: "var(--tui-subtext)" }}>{"+" + overflow + " earlier"}</div> : null}
      {items.slice(0, 3).map(function (t, i) {
        const tone = TONE[t.tone] || TONE.info;
        const sticky = t.tone === "error" || t.tone === "warning";
        return (
          <div key={i} style={{
            display: "flex", gap: "8.4px", alignItems: "baseline",
            border: "1px solid " + tone.c, borderRadius: "var(--radius-panel)",
            background: "var(--tui-surface)", padding: "2px 10px",
            maxWidth: 440, whiteSpace: "nowrap",
          }}>
            <span style={{ color: tone.c, fontWeight: 700 }}>{tone.g}</span>
            <span style={{ color: "var(--tui-text)", overflow: "hidden", textOverflow: "ellipsis" }}>{t.text}</span>
            {sticky ? <span style={{ color: "var(--tui-subtext)" }}>{t.tone === "error" ? "d details" : "any key"}</span> : null}
          </div>
        );
      })}
    </div>
  );
}
