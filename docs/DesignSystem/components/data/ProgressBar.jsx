import React from "react";

// The Bubbles progress bar as the product configures it: a determinate
// gradient bar, three rows thick for the one action with real step signal
// (tailor), one row for everything else. Fill resolves to eighth-blocks so
// the leading edge moves smoothly instead of snapping a cell at a time.
//
// The track is never gray: the whole bar carries the gradient, with the
// unfilled portion rendered at the same hue blended toward Base. A gray
// remainder read as two unrelated bars butted together; this reads as one
// bar, part of which has happened.
//
// Indeterminate work does NOT use this — a faked percent is worse than an
// honest spinner. Pass mode="indeterminate" for the travelling band.
const EIGHTHS = ["", "\u258f", "\u258e", "\u258d", "\u258c", "\u258b", "\u258a", "\u2589"];

const BASE = [30, 30, 46];
// Unfilled track: the ramp colour blended toward Base, so the bar keeps one
// hue across its whole length.
function track(t, k = 0.72) {
  const c = ramp(t, true);
  return "rgb(" + c.map((v, i) => Math.round(v + (BASE[i] - v) * k)).join(",") + ")";
}

function ramp(t, raw) {
  // Peach → Mauve → Teal, the thinking-gradient family, so a running bar
  // and a running LLM call read as the same activity.
  const stops = [[255, 152, 90], [255, 96, 255], [18, 230, 200]];
  const seg = t < 0.5 ? 0 : 1;
  const l = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  const a = stops[seg], b = stops[seg + 1];
  const mix = a.map((v, i) => Math.round(v + l * (b[i] - v)));
  return raw ? mix : "rgb(" + mix.join(",") + ")";
}

export function ProgressBar({ value = 0, max = 100, width = 40, thickness = 1, mode = "determinate", label, showPercent = true }) {
  const [phase, setPhase] = React.useState(0);
  const indeterminate = mode === "indeterminate";
  React.useEffect(() => {
    if (!indeterminate) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setPhase((p) => (p + 1) % (width + 12)), 60);
    return () => clearInterval(id);
  }, [indeterminate, width]);

  const ratio = Math.max(0, Math.min(1, (value || 0) / max));
  const exact = ratio * width;
  const full = Math.floor(exact);
  const part = Math.floor((exact - full) * 8);

  const row = (key) => (
    <div key={key} style={{ whiteSpace: "pre" }}>
      {Array.from({ length: width }, (_, i) => {
        if (indeterminate) {
          const d = Math.abs(i - (phase - 6));
          const on = d < 6;
          return <span key={i} style={{ color: on ? ramp(i / (width - 1)) : track(i / (width - 1)) }}>{"\u2588"}</span>;
        }
        if (i < full) return <span key={i} style={{ color: ramp(i / (width - 1)) }}>{"\u2588"}</span>;
        if (i === full && part > 0) return <span key={i} style={{ color: ramp(i / (width - 1)) }}>{EIGHTHS[part]}</span>;
        return <span key={i} style={{ color: track(i / (width - 1)) }}>{"\u2588"}</span>;
      })}
    </div>
  );

  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)" }}>
      {label != null ? <div style={{ color: "var(--tui-subtext)", marginBottom: 2 }}>{label}</div> : null}
      <div style={{ display: "flex", alignItems: "center", gap: 8.4 }}>
        <div style={{ flex: "0 0 auto" }}>{Array.from({ length: thickness }, (_, r) => row(r))}</div>
        {showPercent && !indeterminate ? (
          <span style={{ color: "var(--tui-text)", fontWeight: 700 }}>{Math.round(ratio * 100)}%</span>
        ) : null}
      </div>
    </div>
  );
}
