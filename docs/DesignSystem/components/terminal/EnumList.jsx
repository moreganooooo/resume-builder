import React from "react";

// lipgloss/list — flat sequences with a custom enumerator, which is most
// of the ↳ and • prefixes still hand-written across the screens. Distinct
// from ClusterTree: a list has no hierarchy, so it gets no connectors.
//
// Enumerators carry meaning, so they are a fixed set rather than a free
// string:
//   bullet    • unordered, no sequence implied
//   arabic    1. ordered steps the user performs in order
//   dash      - sub-points inside a longer explanation
//   check     ✓/✗ outcomes that have already resolved
//   roman     i. rare; only where a nested ordered list needs a second
//             level and a tree would be too heavy
const MARK = {
  bullet: function () { return "\u2022"; },
  dash: function () { return "-"; },
  arabic: function (i) { return i + 1 + "."; },
  roman: function (i) { return ["i.", "ii.", "iii.", "iv.", "v.", "vi.", "vii.", "viii."][i] || i + 1 + "."; },
  check: function (i, it) { return it && it.ok === false ? "\u2717" : "\u2713"; },
};

export function EnumList({ items = [], enumerator = "bullet", color = "var(--tui-mauve)", style }) {
  const mark = MARK[enumerator] || MARK.bullet;
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", flexDirection: "column", gap: 2, ...style,
    }}>
      {items.map(function (it, i) {
        const o = typeof it === "string" ? { text: it } : it;
        const c = enumerator === "check" ? (o.ok === false ? "var(--tui-red)" : "var(--tui-green)") : color;
        return (
          <div key={i} style={{ display: "flex", gap: "8.4px", alignItems: "baseline" }}>
            <span style={{ flex: "0 0 auto", color: c, whiteSpace: "pre", minWidth: "2ch" }}>{mark(i, o)}</span>
            <span style={{ flex: 1, minWidth: 0, color: "var(--tui-text)", textWrap: "pretty" }}>
              {o.text}
              {o.note ? <span style={{ color: "var(--tui-subtext)" }}>{"  " + o.note}</span> : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}
