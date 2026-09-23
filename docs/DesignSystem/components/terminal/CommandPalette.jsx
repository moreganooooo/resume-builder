import React from "react";

// A fuzzy command palette on ctrl-k. With nine screens and roughly forty
// bindings, recall is the bottleneck: the palette turns "which key was
// that" into "type what you want".
//
// Matched characters are Mauve and bold inside an otherwise Text label, so
// you can see WHY a result matched — the thing that makes fzf-style
// matching feel intelligent rather than arbitrary. Each row carries its
// own keybinding on the right, so the palette teaches the shortcut it is
// replacing and makes itself progressively unnecessary.
function Highlight({ label, match = [] }) {
  return (
    <span>
      {String(label).split("").map((ch, i) => (
        <span key={i} style={match.indexOf(i) > -1
          ? { color: "var(--tui-mauve)", fontWeight: 700 }
          : undefined}>{ch}</span>
      ))}
    </span>
  );
}

export function CommandPalette({ query = "", results = [], cursor = 0, onSelect, width = 620, style }) {
  return (
    <div style={{
      width, border: "1px solid var(--tui-mauve)", borderRadius: "var(--radius-panel)",
      background: "var(--tui-base)", padding: "8px 0 4px",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", ...style,
    }}>
      <div style={{ display: "flex", gap: "8.4px", padding: "0 12px 8px", borderBottom: "1px solid var(--tui-overlay)" }}>
        <span style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>{"\u276f"}</span>
        <span style={{ color: query ? "var(--tui-text)" : "var(--tui-overlay)" }}>{query || "Search screens and actions"}</span>
        <span style={{ color: "var(--tui-mauve)" }}>{"\u2588"}</span>
      </div>
      <div style={{ padding: "6px 0" }}>
        {results.length === 0 ? (
          <div style={{ color: "var(--tui-subtext)", padding: "4px 12px" }}>No match for “{query}”</div>
        ) : results.map((r, i) => {
          const sel = i === cursor;
          return (
            <div key={i} onClick={onSelect ? () => onSelect(i) : undefined}
              style={{
                display: "flex", gap: "8.4px", alignItems: "baseline", cursor: onSelect ? "pointer" : "default",
                padding: "3px 12px 3px 11px",
                borderLeft: sel ? "1px solid var(--tui-mauve)" : "1px solid transparent",
                fontWeight: sel ? 700 : 400,
              }}>
              <span style={{ color: "var(--tui-subtext)", width: 74, flex: "0 0 74px" }}>{r.group}</span>
              <span style={{ color: "var(--tui-text)", flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                <Highlight label={r.label} match={r.match} />
              </span>
              {r.key ? <span style={{ color: "var(--tui-blue)" }}>{r.key}</span> : null}
            </div>
          );
        })}
      </div>
      <div style={{ color: "var(--tui-subtext)", padding: "4px 12px 0", borderTop: "1px solid var(--tui-overlay)" }}>
        {"\u2191\u2193 move \u00b7 enter run \u00b7 esc close"}
      </div>
    </div>
  );
}
