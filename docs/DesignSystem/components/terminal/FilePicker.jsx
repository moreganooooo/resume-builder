import React from "react";

// bubbles/filepicker, as onboarding stage one needs it. The product is
// asking for resumes, cover letters and job descriptions the user already
// has, so the picker's job is to make the RIGHT files obvious, not to be
// a general file browser.
//
//  - Directories are Blue with a trailing /, files are Text, and a file
//    the product cannot read is Overlay and non-selectable. Showing it
//    greyed is better than hiding it: the user knows it was seen.
//  - Permitted extensions are stated above the list, not discovered by
//    trying. Size is right-aligned in Subtext.
//  - Multi-select uses the same [✓] box as HuhField's multiselect.
//  - The path header truncates from the LEFT — the end of a path is the
//    part that identifies it.
export function FilePicker({ path = "~", allowed = [], entries = [], cursor = 0, selected = [], onSelect, height, style }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)",
      lineHeight: "var(--tui-line-height)", display: "flex", flexDirection: "column", ...style,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "8.4px", color: "var(--tui-subtext)", paddingBottom: 3 }}>
        <span style={{ direction: "rtl", textAlign: "left", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{path}</span>
        {allowed.length ? <span style={{ flex: "0 0 auto" }}>{allowed.join(" ")}</span> : null}
      </div>
      <div style={{ borderTop: "1px solid var(--tui-overlay)", paddingTop: 5, overflowY: "auto", maxHeight: height }}>
        {entries.map(function (e, i) {
          const on = i === cursor;
          const checked = selected.indexOf(i) > -1;
          const dim = e.disabled;
          return (
            <div key={i} onClick={onSelect && !dim ? function () { onSelect(i); } : undefined}
              style={{
                display: "flex", gap: "8.4px", alignItems: "baseline",
                cursor: onSelect && !dim ? "pointer" : "default",
                padding: "2px 8.4px 2px " + (on ? "7.4px" : "8.4px"),
                borderLeft: on ? "1px solid var(--tui-mauve)" : "1px solid transparent",
                opacity: dim ? 0.45 : 1,
              }}>
              <span style={{ color: checked ? "var(--tui-green)" : "var(--tui-overlay)", flex: "0 0 auto" }}>{checked ? "[\u2713]" : "[ ]"}</span>
              <span style={{
                flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                color: dim ? "var(--tui-overlay)" : e.dir ? "var(--tui-blue)" : "var(--tui-text)",
                fontWeight: on ? 700 : 400,
              }}>{e.name}{e.dir ? "/" : ""}</span>
              <span style={{ flex: "0 0 auto", color: "var(--tui-subtext)" }}>{e.note || e.size || ""}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
