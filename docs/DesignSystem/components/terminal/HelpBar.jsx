import React from "react";

// Bubbles' help model: a short bar that expands on ?. The footer today
// prints every binding at once, so the four that matter compete with the
// twelve that do not.
//
// Short form shows at most five bindings and always ends with "? more".
// Expanded form is columnar and grouped, and REPLACES the short bar in
// place rather than floating over the screen — it is the same component
// growing, so the keys never move horizontally between the two states.
function Binding({ k, desc }) {
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <span style={{ color: "var(--tui-blue)", fontWeight: 700 }}>{k}</span>
      <span style={{ color: "var(--tui-subtext)" }}> {desc}</span>
    </span>
  );
}

export function HelpBar({ bindings = [], groups = [], expanded = false, style }) {
  if (!expanded) {
    return (
      <div style={{
        display: "flex", gap: 18, flexWrap: "nowrap", overflow: "hidden",
        padding: "3px var(--pad-h)", background: "var(--tui-surface)",
        fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", ...style,
      }}>
        {bindings.slice(0, 5).map((b, i) => <Binding key={i} k={b.key} desc={b.desc} />)}
        <Binding k="?" desc="more" />
      </div>
    );
  }
  return (
    <div style={{
      padding: "8px var(--pad-h)", background: "var(--tui-surface)",
      display: "flex", gap: 32, alignItems: "flex-start", flexWrap: "wrap",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", ...style,
    }}>
      {groups.map((g) => (
        <div key={g.label}>
          <div style={{ color: "var(--tui-mauve)", fontWeight: 700, marginBottom: 4 }}>{g.label}</div>
          {g.bindings.map((b, j) => (
            <div key={j} style={{ display: "flex", gap: "8.4px", padding: "1px 0" }}>
              <span style={{ color: "var(--tui-blue)", fontWeight: 700, width: 72, flex: "0 0 72px" }}>{b.key}</span>
              <span style={{ color: "var(--tui-text)" }}>{b.desc}</span>
            </div>
          ))}
        </div>
      ))}
      <div style={{ color: "var(--tui-subtext)", alignSelf: "flex-end" }}>? close</div>
    </div>
  );
}
