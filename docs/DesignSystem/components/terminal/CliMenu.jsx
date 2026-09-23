import React from "react";

// The CLI's grouped select list. Groups print a Mauve caps heading with a
// rule running to a fixed column; the cursor row is Green (huh's selected
// option) and carries the same one-cell Mauve `┃` bar the dashboard uses — a full-height border spanning
// the label AND its description, so the two lines read as one selected unit.
// The old `> >` gutter is gone: two chevrons cost four columns, pointed at
// nothing, and named a different selection language than the rest of the
// product. Leaf rows are prefixed with the ↳ hook the product uses for
// sub-actions, and a plain row (no group) is the flat main menu.
function Rule() {
  return <span style={{ flex: 1, height: 1, background: "var(--tui-overlay)", alignSelf: "center", marginLeft: 12 }}></span>;
}

export function CliMenu({ groups = [], cursor = 0, onSelect, hook = true }) {
  let n = -1;
  return (
    <div style={{
      borderLeft: "2px solid var(--tui-overlay)", paddingLeft: 16,
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", color: "var(--tui-text)",
    }}>
      {groups.map((g, gi) => (
        <div key={g.label || "g" + gi} style={{ marginBottom: g.label ? 22 : 6 }}>
          {g.label ? (
            <div style={{ display: "flex", color: "var(--tui-mauve)", fontWeight: 700, maxWidth: 460, marginBottom: 8, paddingLeft: "8.4px" }}>
              <span>{g.label}</span><Rule />
            </div>
          ) : null}
          {g.items.map((it) => {
            n += 1;
            const i = n;
            const on = i === cursor;
            return (
              <div key={it.label} onClick={() => onSelect && onSelect(i)}
                style={{
                  display: "flex", gap: "8.4px", cursor: onSelect ? "pointer" : "default",
                  marginBottom: it.hint ? 10 : 4,
                  paddingLeft: on ? "7.4px" : "8.4px",
                  borderLeft: on ? "1px solid var(--tui-mauve)" : "1px solid transparent",
                  color: on ? "var(--tui-green)" : "var(--tui-text)", fontWeight: on ? 700 : 400,
                }}>
                <span style={{ color: on ? "var(--tui-green)" : "var(--tui-subtext)", width: 14, flex: "0 0 auto" }}>{it.icon || ""}</span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ whiteSpace: "pre" }}>
                    {hook && g.label && it.hook !== false ? <span style={{ color: on ? "var(--tui-green)" : "var(--tui-subtext)" }}>↳ </span> : null}
                    {it.label}
                  </span>
                  {/* The description is a second line, never a parenthetical
                      in the same weight and colour as the label: at ten rows
                      a menu of doubled-up strings reads as a wall. Selected
                      rows keep the description dim so the label still leads. */}
                  {it.hint ? (
                    <div style={{ color: on ? "var(--tui-subtext)" : "var(--tui-overlay)", fontWeight: 400, textWrap: "pretty" }}>{it.hint}</div>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
