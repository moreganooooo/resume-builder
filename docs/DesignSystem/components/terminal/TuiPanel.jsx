import React from "react";

const BORDER = {
  idle: "var(--tui-overlay)",
  active: "var(--tui-blue)",
  focus: "var(--tui-mauve)",
  warning: "var(--tui-peach)",
};

// A Lip Gloss RoundedBorder box. Border colour IS the state; there is no
// shadow and no distinct fill (Base shows through) unless filled is set.
// `title` sets a legend into the top border, as the CLI status boxes do.
export function TuiPanel({ variant = "idle", pad = "tight", filled = false, title, style, children }) {
  return (
    <div style={{
      position: title ? "relative" : undefined,
      border: "1px solid " + (BORDER[variant] || BORDER.idle),
      borderRadius: "var(--radius-panel)",
      background: filled ? "var(--tui-surface)" : "transparent",
      color: "var(--tui-text)",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)",
      padding: pad === "detail" ? "var(--pad-detail)" : "0 8.4px",
      overflow: title ? "visible" : "hidden",
      ...style,
    }}>
      {title ? (
        <span style={{
          position: "absolute", top: "-0.62em", left: "50%", transform: "translateX(-50%)",
          background: "var(--tui-base)", padding: "0 8.4px", whiteSpace: "nowrap",
          color: "var(--tui-sky)",
        }}>{title}</span>
      ) : null}
      {children}
    </div>
  );
}
