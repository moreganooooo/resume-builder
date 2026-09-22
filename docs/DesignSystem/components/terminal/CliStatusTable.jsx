import React from "react";

// cli_art.render_bullet_bank_status: the resumable progress table shared by
// the onboarding wizard and the bullet-bank menu. Status is a closed set of
// four words, each with its own colour, and the detail column always says
// WHY — "3/11 processed (8 pending)", "finish Step 0 (ingestion) first".
// A stage that has never run and a stage that is blocked are different
// facts and must never render the same.
export const STAGE_STATUS_COLORS = {
  "Up to date": "var(--tui-green)",
  "In progress": "var(--tui-blue)",
  "Never run": "var(--tui-subtext)",
  Locked: "var(--tui-yellow)",
};

const STAGE_STATUS_ICONS = {
  "Up to date": "✓",
  "In progress": "▶",
  "Never run": "·",
  Locked: "⊘",
};

export function CliStatusTable({ title = "Onboarding Progress", rows = [], showNumbers = false }) {
  const cell = { padding: "3px 14px", whiteSpace: "nowrap" };
  return (
    <div style={{
      border: "1px solid var(--tui-overlay)", borderRadius: "var(--radius-panel)",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", color: "var(--tui-text)",
      display: "inline-block", minWidth: 560, paddingBottom: 7,
    }}>
      {title ? (
        <div style={{ color: "var(--tui-mauve)", fontWeight: 700, padding: "5px 14px", borderBottom: "1px solid var(--tui-overlay)" }}>{title}</div>
      ) : null}
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ color: "var(--tui-mauve)", fontWeight: 700, textAlign: "left" }}>
            {showNumbers ? <th style={cell}>#</th> : null}
            <th style={cell}>Stage</th>
            <th style={cell}>Status</th>
            <th style={{ ...cell, width: "100%" }}>Detail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {showNumbers ? <td style={{ ...cell, color: "var(--tui-subtext)" }}>{r.number}</td> : null}
              <td style={cell}>{r.label}</td>
              <td style={{ ...cell, color: STAGE_STATUS_COLORS[r.status] || "var(--tui-subtext)", fontWeight: 700 }}>
                {(STAGE_STATUS_ICONS[r.status] || "·") + " " + r.status}
              </td>
              <td style={{ ...cell, color: "var(--tui-subtext)", whiteSpace: "normal" }}>{r.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
