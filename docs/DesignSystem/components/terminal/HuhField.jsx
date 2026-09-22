import React from "react";

// A Huh form field in each of its four states. Huh owns the keyboard and
// validation; this is the visual contract the product holds it to.
//
//   blurred   Overlay border, Subtext label, no cursor
//   focused   Mauve border + bold Mauve label + block cursor — the same
//             focus language TuiPanel variant="focus" uses, so a focused
//             field and a focused pane read as the same thing
//   error     Red border, the message ON the field, never in a toast: the
//             user has to fix it here, so it has to be said here
//   complete  Green ✓ in the gutter, value in Text
//
// Errors describe what is wrong in plain words and name the fix. The
// message never leads with "Invalid" or repeats the field label.
const BORDER = { blurred: "var(--tui-overlay)", focused: "var(--tui-mauve)", error: "var(--tui-red)", complete: "var(--tui-overlay)" };
const LABEL = { blurred: "var(--tui-subtext)", focused: "var(--tui-mauve)", error: "var(--tui-red)", complete: "var(--tui-subtext)" };

export function HuhField({ kind = "input", label, value = "", placeholder = "", help, error, state = "blurred", options = [], selected = [], cursor = 0, style }) {
  const st = error ? "error" : state;
  const body = { fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)" };
  return (
    <div style={{ ...body, marginBottom: 14, ...style }}>
      <div style={{ color: LABEL[st], fontWeight: st === "focused" || st === "error" ? 700 : 400, marginBottom: 3 }}>
        {st === "complete" ? <span style={{ color: "var(--tui-green)" }}>{"\u2713 "}</span> : null}{label}
      </div>
      {kind === "select" || kind === "multiselect" ? (
        <div style={{ borderLeft: "1px solid " + BORDER[st], paddingLeft: "8.4px" }}>
          {options.map((o, i) => {
            const on = i === cursor;
            const checked = selected.indexOf(i) > -1;
            return (
              <div key={i} style={{ display: "flex", gap: "8.4px", color: on ? "var(--tui-text)" : "var(--tui-subtext)", fontWeight: on ? 700 : 400, padding: "1px 0" }}>
                <span style={{ color: on ? "var(--tui-mauve)" : "transparent" }}>{"\u2503"}</span>
                {kind === "multiselect" ? <span style={{ color: checked ? "var(--tui-green)" : "var(--tui-overlay)" }}>{checked ? "[\u2713]" : "[ ]"}</span> : null}
                <span>{o}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ border: "1px solid " + BORDER[st], borderRadius: "var(--radius-panel)", padding: "2px 8.4px", color: value ? "var(--tui-text)" : "var(--tui-overlay)", whiteSpace: "pre" }}>
          {value || placeholder}{st === "focused" ? <span style={{ color: "var(--tui-mauve)" }}>{"\u2588"}</span> : null}
        </div>
      )}
      {error ? <div style={{ color: "var(--tui-red)", marginTop: 3 }}>{"\u2717 "}{error}</div>
        : help ? <div style={{ color: "var(--tui-subtext)", marginTop: 3 }}>{help}</div> : null}
    </div>
  );
}
