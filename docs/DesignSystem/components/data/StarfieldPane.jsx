import React from "react";

// renderEmptyDetailPane: a deterministic 2D-hash starfield at ~6.5%
// density, each star twinkling on its own sine phase, with a centred
// Surface-filled card. Hints MUST come from the calling screen — the same
// letter is bound differently on Jobs and Pipeline.
//
// The grid fills its container by default, measured in terminal cells
// (--cell-x by --cell-y) the way the Go original fills the pane it is
// handed. Pass cols/rows only to pin it to a fixed character box.
export function StarfieldPane({ cols, rows, hints = [], title = "\u2726 No active selection \u2727", animate = true, density = 0.065, card = true }) {
  const [t, setT] = React.useState(0);
  const ref = React.useRef(null);
  const [size, setSize] = React.useState({ cols: cols || 60, rows: rows || 16 });

  React.useEffect(() => {
    if (!animate || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setT((x) => x + 0.06), 60);
    return () => clearInterval(id);
  }, [animate]);

  React.useEffect(() => {
    if (cols && rows) { setSize({ cols, rows }); return; }
    const el = ref.current;
    if (!el) return;
    const cs = getComputedStyle(el);
    const cellX = parseFloat(cs.getPropertyValue("--cell-x")) || 8.4;
    const cellY = parseFloat(cs.getPropertyValue("--cell-y")) || 21;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setSize({
        cols: cols || Math.max(1, Math.floor(r.width / cellX)),
        rows: rows || Math.max(1, Math.floor(r.height / cellY)),
      });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [cols, rows]);

  const grid = [];
  for (let y = 0; y < size.rows; y++) {
    const line = [];
    for (let x = 0; x < size.cols; x++) {
      let h = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453123;
      h -= Math.floor(h);
      if (h < density) {
        const type = Math.floor(h * 100) % 3;
        const b = 0.5 + 0.5 * Math.sin(t * (1.5 + h * 3) + h * 10);
        const col = b > 0.85 ? "var(--tui-mauve)" : b > 0.6 ? "var(--tui-sky)" : b > 0.35 ? "var(--tui-blue)" : "var(--tui-overlay)";
        line.push(<span key={x} style={{ color: col }}>{type === 0 ? "\u2726" : type === 1 ? "\u2727" : "\u00b7"}</span>);
      } else line.push(<span key={x}> </span>);
    }
    grid.push(<div key={y} style={{ whiteSpace: "pre" }}>{line}</div>);
  }

  return (
    <div ref={ref} style={{
      position: "relative", width: "100%", height: "100%", overflow: "hidden",
      fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)",
    }}>
      {grid}
      {card && (title || hints.length) ? (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--tui-surface)", textAlign: "center", minWidth: 336 }}>
            <div style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>{title}</div>
            <div>&nbsp;</div>
            {hints.map((h, i) => (
              <div key={i} style={{ color: i === hints.length - 1 ? "var(--tui-subtext)" : "var(--tui-text)" }}>
                {String(h).split(/(\[[^\]]*\])/).map((part, j) =>
                  part.startsWith("[") ? <span key={j} style={{ color: "var(--tui-peach)" }}>{part}</span> : <span key={j}>{part || "\u00a0"}</span>)}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
