import React from "react";

// A Bubbles table as the product configures it. The parts Bubbles gives
// you for free and the product should therefore not hand-roll: column
// widths, keyboard row movement, and sort.
//
// Rules this encodes:
//  - Header is Subtext caps with a single Overlay rule under it. Never a
//    filled header bar: that reads as a second chrome row and the budget
//    has no room for one.
//  - The sorted column's header goes Blue and carries ▲/▼. Exactly one
//    column can be sorted, so the arrow is unambiguous.
//  - Numeric columns right-align; everything else left-aligns. Terminal
//    columns only line up if you say so.
//  - Selection is the same ┃ bar as every list, spanning the whole row.
export function DataTable({ columns = [], rows = [], cursor = 0, sortKey, sortDir = "desc", onSelect, style }) {
  const cell = (c, last) => ({
    padding: "3px 14px 3px 0",
    paddingRight: last ? 0 : 14,
    textAlign: c.align === "right" ? "right" : "left",
    whiteSpace: "nowrap",
    width: c.width,
  });
  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", ...style }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          <th style={{ width: 10, padding: 0 }}></th>
          {columns.map((c, i) => {
            const on = c.key === sortKey;
            return (
              <th key={c.key} style={{
                ...cell(c, i === columns.length - 1),
                color: on ? "var(--tui-blue)" : "var(--tui-subtext)",
                fontWeight: on ? 700 : 400,
                letterSpacing: "0.08em",
                borderBottom: "1px solid var(--tui-overlay)",
              }}>{c.label.toUpperCase()}{on ? (sortDir === "asc" ? " \u25b2" : " \u25bc") : ""}</th>
            );
          })}
        </tr></thead>
        <tbody>
          {rows.map((r, ri) => {
            const sel = ri === cursor;
            return (
              <tr key={ri} onClick={onSelect ? () => onSelect(ri) : undefined}
                style={{ cursor: onSelect ? "pointer" : "default", opacity: sel ? 1 : "calc(1 - var(--dim-fraction))" }}>
                <td style={{ width: 10, padding: 0, color: sel ? "var(--tui-mauve)" : "transparent" }}>{"\u2503"}</td>
                {columns.map((c, i) => (
                  <td key={c.key} style={{
                    ...cell(c, i === columns.length - 1),
                    color: c.color ? c.color(r) : (sel ? "var(--tui-text)" : "var(--tui-subtext)"),
                    fontWeight: sel && i === 0 ? 700 : 400,
                  }}>{c.render ? c.render(r) : r[c.key]}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
