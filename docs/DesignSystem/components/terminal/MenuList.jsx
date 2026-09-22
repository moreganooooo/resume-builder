import React from "react";
import { Glyph } from "./Glyph.jsx";

// The main menu: a Bubbles list with a bold title line and a Subtext
// description, selection shown by the Mauve ┃ bar — drawn as a border so it
// spans the title AND its description, the same as every other list row.
export function MenuList({ items, active = 0, onSelect }) {
  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)" }}>
      {items.map((it, i) => {
        const sel = i === active;
        return (
          <div key={it.title} onClick={() => onSelect && onSelect(i)}
            style={{
              cursor: onSelect ? "pointer" : "default", display: "flex", gap: 8.4,
              paddingLeft: sel ? 15.8 : 16.8,
              borderLeft: sel ? "1px solid var(--tui-mauve)" : "1px solid transparent",
              marginBottom: "var(--tui-line-height)",
            }}>
            <div>
              <div style={{ fontWeight: 700, color: sel ? "var(--tui-mauve)" : "var(--tui-text)" }}>
                <Glyph name={it.icon} />{"  "}{it.title}
              </div>
              <div style={{ color: "var(--tui-subtext)" }}>{it.desc}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
