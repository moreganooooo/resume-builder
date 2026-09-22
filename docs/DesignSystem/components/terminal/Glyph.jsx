import React from "react";

// The product's Unicode fallback icon table (scripts/theme.py _UNICODE_ICONS).
// Nerd Font PUA code points cannot render in a browser, so this set is what
// the design system uses on the web. Never substitute an emoji.
export const GLYPHS = {
  success: "\u2713", complete: "\u2713", error: "\u2717", warning: "\u26a0",
  hint: "\u2726", gem: "\u2726", magic: "\u2726", discovery: "\u2316",
  search: "\u2316", skip: "\u2298", build: "\u2692", utility: "\u2699",
  pipeline: "\u2699", bullet_bank: "\u25c8", save: "\u21a7", resume: "\u25b6",
  recruiter: "\u25c9", profile: "\u25c9", location: "\u2302", filter: "\u25bd",
  knowledge: "\u21ea", prev: "\u276e", next: "\u276f", back: "\u276e",
  exit: "\u2715", quit: "\u2715", menu: "\u2261", progress: "\u25a4",
  evaluate: "\u25a4", report: "\u25a5", jobs: "\u25a3", source: "\u25b0",
  path: "\u2317", trash: "\u232b", edit: "\u270e", external: "\u2197",
  clock: "\u25f7", graph: "\u25a8", star: "\u2605", sparkOpen: "\u2726",
  sparkClose: "\u2727",
};

// An unknown key used to fall through as literal text, which renders a
// lowercase word where a glyph belongs and looks intentional enough to ship.
// It now warns and renders the Overlay placeholder ◌, so the miss is visible.
export function Glyph({ name, color, size, title }) {
  const known = Object.prototype.hasOwnProperty.call(GLYPHS, name);
  if (!known && typeof console !== "undefined") {
    console.warn('Glyph: unknown name "' + name + '" — valid keys: ' + Object.keys(GLYPHS).join(", "));
  }
  const ch = known ? GLYPHS[name] : "\u25cc";
  return (
    <span role="img" aria-label={title || name} title={title}
      style={{ fontFamily: "var(--font-mono)", color: known ? (color || "inherit") : "var(--tui-overlay)", fontSize: size }}>
      {ch}
    </span>
  );
}
