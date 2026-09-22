import React from "react";

const RAMP = [" ", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586", "\u2587", "\u2588"];

// progress.go RenderSparkline — eight-step block ramp, min-max normalised.
export function Sparkline({ values = [], color = "var(--tui-mauve)" }) {
  const min = Math.min(...values), max = Math.max(...values);
  const out = values.map((v) => {
    if (max === min) return " ";
    let i = Math.floor(((v - min) / (max - min)) * 7);
    if (v > min && i === 0) i = 1;
    return RAMP[Math.max(0, Math.min(7, i))];
  }).join("");
  return <span style={{ color, fontFamily: "var(--font-mono)", whiteSpace: "pre" }}>{out}</span>;
}
