import React from "react";

// The four title gradients the product actually ships, by screen. Prefer
// `gradient="pipeline"` over passing raw colours — it keeps every screen
// title on the same four pairs.
//
// Blue→Peach and Peach→Teal are opposite sides of the wheel, and a straight
// RGB interpolation between them passes through a desaturated brown at the
// midpoint. Both route through Mauve instead: same endpoints, same screen
// identity, but the middle of the string stays chromatic.
export const TITLE_GRADIENTS = {
  pipeline: ["--tui-blue", "--tui-mauve"],
  jobs: ["--tui-blue", "--tui-mauve", "--tui-peach"],
  progress: ["--tui-peach", "--tui-mauve", "--tui-teal"],
  menu: ["--tui-mauve", "--tui-blue"],
};

// Accepts a token name (--tui-blue), a hex, or any CSS colour. Tokens and
// non-hex values are resolved against the live document so the gradient
// follows the palette instead of freezing a copy of it.
function rgb(value) {
  let v = String(value).trim();
  if (v.startsWith("--")) {
    v = (typeof getComputedStyle === "function"
      ? getComputedStyle(document.documentElement).getPropertyValue(v)
      : "").trim() || "#000000";
  }
  if (v.length === 4 && v[0] === "#") v = "#" + [1, 2, 3].map((i) => v[i] + v[i]).join("");
  if (v[0] === "#") return [1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16));
  const m = v.match(/\d+/g);
  return m ? m.slice(0, 3).map(Number) : [0, 0, 0];
}

// theme.RenderColorGradient: blends a string character-by-character across
// a list of palette colours. This is the ONLY gradient in the product — it
// is always on text, never a background. Two stops is the common case;
// three is how a pair that would mix to mud gets a chromatic midpoint.
export function GradientText({ children, gradient, from, to, stops, tracked = false, bold = true }) {
  const pair = stops || TITLE_GRADIENTS[gradient] || [from ?? "--tui-blue", to ?? "--tui-mauve"];
  const ramp = pair.map(rgb);
  let text = String(children ?? "");
  if (tracked) text = text.split("").join(" ");
  const chars = [...text];
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontWeight: bold ? 700 : 400, whiteSpace: "pre" }}>
      {chars.map((c, i) => {
        const t = chars.length > 1 ? i / (chars.length - 1) : 0;
        // Locate t within the ramp, then interpolate inside that segment.
        const seg = Math.min(ramp.length - 2, Math.floor(t * (ramp.length - 1)));
        const local = ramp.length > 1 ? t * (ramp.length - 1) - seg : 0;
        const a = ramp[seg], b = ramp[Math.min(seg + 1, ramp.length - 1)];
        const col = "rgb(" + a.map((v, k) => Math.round(v + local * (b[k] - v))).join(",") + ")";
        return <span key={i} style={{ color: col }}>{c}</span>;
      })}
    </span>
  );
}
