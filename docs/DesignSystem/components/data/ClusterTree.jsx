import React from "react";

// Lip Gloss's Tree, carrying the bullet bank's cluster hierarchy. The bank
// is a two-level structure (cluster → bullet, occasionally → variant) that
// the product currently prints flat, which is why 212 bullets are hard to
// audit.
//
// Enumerator is Lip Gloss's rounded set (├── └──) in Overlay: the branch
// lines are structure, not content, and must never out-weigh the labels.
// Cluster rows carry their bullet count; a cluster under 3 bullets is
// flagged Peach, because a thin cluster usually means the extractor
// mis-grouped rather than that the user lacks the experience.
export function ClusterTree({ nodes = [], cursor, onSelect, style }) {
  const out = [];
  let flat = 0;
  const walk = (list, depth, prefix) => {
    list.forEach((n, i) => {
      const last = i === list.length - 1;
      const idx = flat++;
      const sel = idx === cursor;
      const thin = n.count != null && n.count < 3;
      out.push(
        <div key={idx} onClick={onSelect ? () => onSelect(idx) : undefined}
          style={{ display: "flex", gap: "8.4px", cursor: onSelect ? "pointer" : "default", whiteSpace: "pre", padding: "1px 0" }}>
          <span style={{ color: sel ? "var(--tui-mauve)" : "transparent" }}>{"\u2503"}</span>
          <span style={{ color: "var(--tui-overlay)" }}>{prefix + (depth ? (last ? "\u2514\u2500\u2500 " : "\u251c\u2500\u2500 ") : "")}</span>
          <span style={{ color: depth ? "var(--tui-text)" : "var(--tui-blue)", fontWeight: depth ? (sel ? 700 : 400) : 700 }}>{n.label}</span>
          {n.count != null ? <span style={{ color: thin ? "var(--tui-peach)" : "var(--tui-subtext)" }}>{n.count} bullet{n.count === 1 ? "" : "s"}{thin ? " \u2014 thin cluster" : ""}</span> : null}
        </div>
      );
      if (n.children && n.children.length) walk(n.children, depth + 1, prefix + (depth ? (last ? "    " : "\u2502   ") : ""));
    });
  };
  walk(nodes, 0, "");
  return <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", ...style }}>{out}</div>;
}
