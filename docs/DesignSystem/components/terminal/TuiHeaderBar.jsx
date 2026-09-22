import React from "react";
import { GradientText } from "./GradientText.jsx";
import { Glyph } from "./Glyph.jsx";

// The Surface-backed top bar: icon + gradient title on the left, counts and
// active filters on the right, truncating right-then-left.
export function TuiHeaderBar({ icon, title, gradient, from, to, info, after, iconColor = "var(--tui-blue)" }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      background: "var(--tui-surface)", padding: "0 var(--pad-h)",
      minHeight: "var(--tui-line-height)", fontFamily: "var(--font-mono)",
      fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
      color: "var(--tui-text)", fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden",
    }}>
      <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        {icon ? <Glyph name={icon} color={iconColor} /> : null}
        <GradientText gradient={gradient} from={from} to={to}>{title}</GradientText>
        {after}
      </span>
      <span style={{ color: "var(--tui-subtext)", fontWeight: 400, overflow: "hidden", textOverflow: "ellipsis" }}>{info}</span>
    </div>
  );
}
