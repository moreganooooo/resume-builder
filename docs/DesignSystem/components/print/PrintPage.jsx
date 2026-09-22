import React from "react";

// The resume canvas: 100% width, max 8.5in, centred, zero padding.
// Ligatures are disabled deliberately — pypdf/pdfminer extract "ﬁ"
// verbatim and ATS keyword matching fails. Never remove.
export function PrintPage({ children, style }) {
  return (
    <div style={{
      width: "100%", maxWidth: "8.5in", margin: "0 auto", padding: 0,
      background: "var(--print-bg)", color: "var(--print-text)",
      fontFamily: "var(--font-body)", fontSize: "9.75pt", fontWeight: 400,
      lineHeight: 1.15, textWrap: "pretty",
      fontVariantLigatures: "none", fontFeatureSettings: '"liga" 0, "clig" 0',
      ...style,
    }}>{children}</div>
  );
}
