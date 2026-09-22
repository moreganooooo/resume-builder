import React from "react";

// A centred dialog over a background stripped of colour and re-rendered in
// Overlay gray — a terminal has no alpha, so no blur and no translucent scrim.
export function Modal({ title, footer, variant = "active", children, backdrop }) {
  const border = variant === "focus" ? "var(--tui-mauve)" : "var(--tui-blue)";
  return (
    <div style={{ position: "relative", height: "100%", fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)" }}>
      <div style={{ color: "var(--tui-overlay)", whiteSpace: "pre", overflow: "hidden", opacity: 0.35, filter: "grayscale(1)", height: "100%" }}>{backdrop}</div>
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: "80%", maxWidth: 840, minWidth: 336 }}>
          {title ? (
            <div style={{ background: "var(--tui-surface)", color: "var(--tui-text)", fontWeight: 700, padding: "0 var(--pad-h)" }}>{title}</div>
          ) : null}
          <div style={{ border: "1px solid " + border, borderRadius: "var(--radius-panel)", background: "var(--tui-base)", padding: "var(--pad-detail)", color: "var(--tui-text)" }}>
            {children}
          </div>
          {footer ? (
            <div style={{ background: "var(--tui-surface)", color: "var(--tui-subtext)", padding: "0 8.4px" }}>{footer}</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
