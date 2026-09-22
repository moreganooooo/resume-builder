import React from "react";

// bubbles/stopwatch and bubbles/timer. The product's LLM calls take
// anywhere from four seconds to fifteen minutes, and the honest thing is
// to say so rather than imply a percentage nobody can compute.
//
//  - Under the expectation, show the spinner and the elapsed clock only.
//  - Past it, append the overrun sentence in Yellow. Naming the normal
//    duration is what makes the wait tolerable: the user can decide.
//  - The clock is mm:ss, monospace-stable, and never ticks backwards.
//  - Countdown mode (bubbles/timer) counts DOWN and is only for things
//    that will actually fire on their own — an auto-cancel, a retry.
//    Never a fake ETA.
const FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"];

function clock(s) {
  const m = Math.floor(Math.abs(s) / 60);
  const r = Math.abs(s) % 60;
  return m + ":" + (r < 10 ? "0" : "") + r;
}

export function ElapsedTimer({ seconds = 0, expected, mode = "stopwatch", label = "Working", frame = 0, cancelKey = "esc", style }) {
  const over = mode === "stopwatch" && expected != null && seconds > expected;
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", flexDirection: "column", gap: 2, ...style,
    }}>
      <div style={{ display: "flex", gap: "8.4px", alignItems: "baseline" }}>
        <span style={{ color: "var(--tui-blue)" }}>{mode === "stopwatch" ? FRAMES[frame % FRAMES.length] : "\u25f4"}</span>
        <span style={{ color: "var(--tui-text)" }}>{label}</span>
        <span style={{ color: over ? "var(--tui-yellow)" : "var(--tui-subtext)", fontVariantNumeric: "tabular-nums" }}>
          {mode === "countdown" ? "\u2212" : ""}{clock(seconds)}
        </span>
        {cancelKey ? <span style={{ color: "var(--tui-subtext)" }}>{"(" + cancelKey + " to cancel)"}</span> : null}
      </div>
      {over ? (
        <div style={{ color: "var(--tui-yellow)", paddingLeft: "16.8px" }}>
          {"-- still going after " + clock(seconds) + ", which is longer than the usual " + clock(expected)}
        </div>
      ) : null}
    </div>
  );
}
