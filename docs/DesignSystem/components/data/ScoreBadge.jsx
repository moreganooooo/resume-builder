import React from "react";

// scoreStyle + scoreIcon: tier is signalled by colour AND glyph, never by
// colour alone. A missing score is muted with an em dash — "not evaluated"
// and "evaluated badly" are different facts.
export function tierOf(score) {
  if (score == null) return { color: "var(--score-none)", glyph: "\u2013", bold: false };
  if (score >= 4.2) return { color: "var(--score-strong)", glyph: "\u2713", bold: true };
  if (score >= 3.8) return { color: "var(--score-good)", glyph: "\u2726", bold: false };
  if (score >= 3.0) return { color: "var(--score-fair)", glyph: "\u2605", bold: false };
  return { color: "var(--score-weak)", glyph: "\u2298", bold: false };
}

export function ScoreBadge({ score, suffix, showGlyph = true }) {
  const t = tierOf(score);
  return (
    <span style={{ color: t.color, fontWeight: t.bold ? 700 : 400, fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
      {showGlyph ? t.glyph + " " : ""}{score == null ? "" : score.toFixed(1)}{suffix || ""}
    </span>
  );
}
