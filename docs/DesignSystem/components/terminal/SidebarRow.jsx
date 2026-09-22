import React from "react";
import { ScoreBadge } from "../data/ScoreBadge.jsx";

// The shared two-line list row: score + company (+ tag) above a Blue
// subtitle. Selection shows a Mauve ┃ left bar; unselected rows are dimmed
// as a whole rather than flattened to one gray.
export function SidebarRow({ score, company, tag, subtitle, selected = false, onClick }) {
  return (
    <div onClick={onClick}
      style={{
        cursor: onClick ? "pointer" : "default",
        fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
        padding: selected ? "3px 8.4px 3px 7.4px" : "3px 8.4px",
        borderLeft: selected ? "1px solid var(--tui-mauve)" : "1px solid transparent",
        display: "flex", gap: 8.4, opacity: selected ? 1 : 0.62,
      }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          <ScoreBadge score={score} />{" "}
          <span style={{ color: "var(--tui-text)", fontWeight: selected ? 700 : 400 }}>{company}</span>
          {tag ? <> {tag}</> : null}
        </div>
        <div style={{ color: "var(--tui-blue)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{subtitle}</div>
      </div>
    </div>
  );
}
