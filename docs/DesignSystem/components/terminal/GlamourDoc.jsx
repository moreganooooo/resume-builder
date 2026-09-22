import React from "react";

// Glamour's rendered markdown, as the KB detail pane shows it. Supports the
// subset the product actually emits: `### Heading`, `- ` bullets, blank-line
// paragraphs, and inline `**bold**`. Bold runs are the label colour; body
// text stays --tui-text. Glamour indents the whole block by two cells.
function inline(src, key) {
  const out = [];
  let i = 0, n = 0;
  const re = /\*\*(.+?)\*\*/g;
  let m;
  while ((m = re.exec(src))) {
    if (m.index > i) out.push(src.slice(i, m.index));
    out.push(
      <span key={key + "-b" + n++} style={{ color: "var(--tui-text)", fontWeight: 700 }}>{m[1]}</span>
    );
    i = m.index + m[0].length;
  }
  if (i < src.length) out.push(src.slice(i));
  return out;
}

export function GlamourDoc({ source = "", indent = "16.8px" }) {
  const lines = String(source).replace(/\t/g, "  ").split("\n");
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", color: "var(--tui-subtext)",
      paddingLeft: indent,
    }}>
      {lines.map((raw, i) => {
        const line = raw.trimEnd();
        if (!line.trim()) return <div key={i}>&nbsp;</div>;
        const h = /^(#{1,6})\s+(.*)$/.exec(line);
        if (h) {
          return (
            <div key={i} style={{ color: "var(--tui-blue)", fontWeight: 700 }}>
              {h[1]} {h[2]}
            </div>
          );
        }
        const b = /^\s*[-*]\s+(.*)$/.exec(line);
        if (b) {
          return (
            <div key={i} style={{ display: "flex", gap: "8.4px" }}>
              <span style={{ color: "var(--tui-mauve)" }}>•</span>
              <span>{inline(b[1], i)}</span>
            </div>
          );
        }
        return <div key={i} style={{ textWrap: "pretty" }}>{inline(line, i)}</div>;
      })}
    </div>
  );
}
