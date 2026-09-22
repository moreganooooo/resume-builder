import React from "react";

// Bubbles' paginator, dots form. Jobs routinely returns 60+ roles and the
// list currently just scrolls, so there is nothing telling you how much
// list there is.
//
// Dots up to 12 pages (●○○○), Arabic past that ("Page 4 of 31") — beyond a
// dozen, dots stop being countable at a glance and become decoration.
export function Paginator({ page = 0, pages = 1, perPage, total, style }) {
  const dots = pages <= 12;
  return (
    <div style={{
      display: "flex", gap: "8.4px", alignItems: "baseline",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
      color: "var(--tui-subtext)", ...style,
    }}>
      {dots ? (
        <span style={{ letterSpacing: "0.18em" }}>
          {Array.from({ length: pages }, (_, i) => (
            <span key={i} style={{ color: i === page ? "var(--tui-mauve)" : "var(--tui-overlay)" }}>{i === page ? "\u25cf" : "\u25cb"}</span>
          ))}
        </span>
      ) : (
        <span><span style={{ color: "var(--tui-text)" }}>Page {page + 1}</span> of {pages}</span>
      )}
      {total != null ? (
        <span>{perPage ? page * perPage + 1 + "\u2013" + Math.min(total, (page + 1) * perPage) + " of " + total : total + " total"}</span>
      ) : null}
      <span style={{ color: "var(--tui-overlay)" }}>h/l \u00b7 pgup/pgdn</span>
    </div>
  );
}
