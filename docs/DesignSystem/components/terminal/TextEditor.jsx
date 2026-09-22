import React from "react";

// bubbles/textarea, for the two places the user writes prose: the cover
// letter and a tailored bullet they want to hand-correct.
//
//  - A gutter of line numbers in Overlay, right-aligned. It makes the
//    "line 6 is too long" feedback in review actionable.
//  - The focused line's number goes Mauve. The line itself is not
//    highlighted: a filled row behind text the user is editing fights
//    the block cursor.
//  - Soft-wrapped continuations get no number and a ↳ in Overlay, so a
//    wrapped line is never mistaken for a new one.
//  - The counter is characters, not words, and turns Yellow past the
//    soft limit and Red past the hard one. Cover letters get truncated
//    by ATS forms at a character count, so characters are the honest
//    unit.
export function TextEditor({ lines = [], cursorLine = 0, cursorCol = 0, count, softLimit, hardLimit, focused = true, height, style }) {
  const over = hardLimit != null && count > hardLimit;
  const warn = !over && softLimit != null && count > softLimit;
  const gutter = String(lines.length).length;
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", flexDirection: "column",
      border: "1px solid " + (focused ? "var(--tui-mauve)" : "var(--tui-overlay)"),
      borderRadius: "var(--radius-panel)", ...style,
    }}>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "5px 0", maxHeight: height }}>
        {lines.map(function (l, i) {
          const text = typeof l === "string" ? l : l.text;
          const wrapped = typeof l === "object" && l.wrapped;
          const on = i === cursorLine && focused;
          return (
            <div key={i} style={{ display: "flex", gap: "8.4px", padding: "0 8.4px" }}>
              <span style={{
                flex: "0 0 auto", width: gutter + "ch", textAlign: "right", whiteSpace: "pre",
                color: wrapped ? "var(--tui-overlay)" : on ? "var(--tui-mauve)" : "var(--tui-overlay)",
                fontWeight: on ? 700 : 400,
              }}>{wrapped ? "\u21b3" : i + 1}</span>
              <span style={{ flex: 1, minWidth: 0, color: "var(--tui-text)", textWrap: "pretty" }}>
                {on ? <>{text.slice(0, cursorCol)}<span style={{ color: "var(--tui-mauve)" }}>{"\u2588"}</span>{text.slice(cursorCol)}</> : text}
              </span>
            </div>
          );
        })}
      </div>
      {count != null ? (
        <div style={{
          display: "flex", justifyContent: "space-between", gap: "8.4px",
          borderTop: "1px solid var(--tui-overlay)", padding: "3px 8.4px",
          color: over ? "var(--tui-red)" : warn ? "var(--tui-yellow)" : "var(--tui-subtext)",
        }}>
          <span>{count}{hardLimit != null ? " / " + hardLimit : ""} characters</span>
          <span>{over ? "over the hard limit" : warn ? "past the recommended length" : "ctrl-s save \u00b7 esc discard"}</span>
        </div>
      ) : null}
    </div>
  );
}
