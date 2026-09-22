import React from "react";
import { Modal } from "./Modal.jsx";

// The ? overlay: bindings grouped under Navigation / Actions / View /
// Filters / Exit, so 12-14 single-letter keys are discoverable without
// parsing the footer bar.
export function HelpOverlay({ title, categories = [], backdrop }) {
  return (
    <Modal variant="focus" title={title + " Help"} backdrop={backdrop}
      footer={<><b style={{ color: "var(--tui-text)" }}>? / Esc / q</b> close help</>}>
      {categories.map((cat, i) => (
        <div key={cat.label} style={{ marginTop: i ? "var(--tui-line-height)" : 0 }}>
          <div style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>{cat.label}</div>
          {cat.bindings.map((b, j) => (
            <div key={j} style={{ display: "flex", paddingLeft: 16.8 }}>
              <span style={{ color: "var(--tui-blue)", fontWeight: 700, width: 118, flex: "0 0 118px" }}>{b.key}</span>
              <span style={{ color: "var(--tui-text)" }}>{b.desc}</span>
            </div>
          ))}
        </div>
      ))}
    </Modal>
  );
}
