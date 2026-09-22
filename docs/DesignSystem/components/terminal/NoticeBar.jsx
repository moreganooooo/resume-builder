import React from "react";

const V = {
  notice: { color: "var(--tui-yellow)", prefix: "", hint: " (press any key to dismiss)" },
  error: { color: "var(--tui-red)", prefix: "Error: ", hint: " (d for details, any other key to dismiss)" },
  progress: { color: "var(--tui-yellow)", prefix: "", hint: " (esc to cancel)" },
  banner: { color: "var(--tui-mauve)", prefix: "", hint: "" },
};

// The full-width Surface bar that explains what just happened. A no-op is a
// yellow notice with no prefix; a failure is red and prefixed "Error:".
export function NoticeBar({ variant = "notice", message, hint, children }) {
  const v = V[variant] || V.notice;
  return (
    <div style={{
      background: "var(--tui-surface)", color: v.color, padding: "0 var(--pad-h)",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
      fontWeight: variant === "banner" ? 700 : 400, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
    }}>
      {v.prefix}{message}
      <span style={{ color: variant === "banner" ? v.color : "var(--tui-subtext)" }}>{hint !== undefined ? hint : v.hint}</span>
      {children}
    </div>
  );
}
