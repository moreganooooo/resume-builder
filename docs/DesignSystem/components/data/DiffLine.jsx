import React from "react";

// The tailoring redline: what the model changed in a bullet, and why.
// This is the product's core value made visible, so the rules are strict.
//
//  - Added is Green with +, removed is Red with -, unchanged is Subtext
//    with a space. The sign column is always present, so lines stay
//    aligned and the diff survives being copied into a plain-text email.
//  - Colour is never the only signal. A red/green-blind user reads the
//    signs; a screen reader reads the signs.
//  - Removed text is NOT struck through. Strikethrough is unreliable
//    across terminals and, where it renders, makes the original bullet
//    unreadable — and the user needs to read it to judge the rewrite.
//  - "rewritten" is its own kind: a paired -/+ rendered adjacent with a
//    Mauve rule between, because a rewrite is one decision, not two.
//  - Word-level emphasis inside a changed line is bold, not background
//    fill. Filled spans at 12px in a terminal read as redaction.
const SIGN = { add: "+", remove: "-", same: " ", note: "\u2503" };
const COLOR = {
  add: "var(--tui-green)",
  remove: "var(--tui-red)",
  same: "var(--tui-subtext)",
  note: "var(--tui-mauve)",
};

export function DiffLine({ kind = "same", children, emphasis = [], style }) {
  const text = typeof children === "string" ? children : null;
  let body = children;
  if (text && emphasis.length) {
    // Split on the emphasised substrings, bolding each occurrence.
    const re = new RegExp("(" + emphasis.map(function (e) {
      return e.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|") + ")", "g");
    body = text.split(re).map(function (part, i) {
      return emphasis.indexOf(part) > -1
        ? React.createElement("strong", { key: i, style: { fontWeight: 700 } }, part)
        : React.createElement(React.Fragment, { key: i }, part);
    });
  }
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", gap: "8.4px",
      color: COLOR[kind], padding: "1px 0", ...style,
    }}>
      <span style={{ flex: "0 0 auto", whiteSpace: "pre", opacity: kind === "same" ? 0.6 : 1 }}>{SIGN[kind]}</span>
      <span style={{ flex: 1, minWidth: 0, textWrap: "pretty" }}>{body}</span>
    </div>
  );
}
