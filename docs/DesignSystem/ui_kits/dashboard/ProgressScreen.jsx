const { TuiHeaderBar, TuiFooterBar, FunnelBar, FUNNEL_COLORS, Sparkline, Heatmap, HelpOverlay } = window.ResumeBuilderDesignSystem_2d03b1;

const PROGRESS_HELP = [
  { label: "Navigation", bindings: [{ key: "↑ ↓ / j k", desc: "Scroll one line" }, { key: "PgUp / PgDn", desc: "Scroll one page" }, { key: "g / G", desc: "Jump to top / bottom" }] },
  { label: "Reading the report", bindings: [{ key: "", desc: "Percentages in the drill-down are stage-to-stage, not cumulative" }, { key: "", desc: "Heatmap cells are counts per day over the last 24 weeks" }] },
  { label: "Exit", bindings: [{ key: "Esc", desc: "Back to Main Menu" }, { key: "q", desc: "Quit dashboard" }] },
];

function Section({ title, color = "var(--tui-sky)", children }) {
  return (
    <div style={{ padding: "0 var(--pad-h)", marginBottom: 28 }}>
      <div style={{ color, fontWeight: 700, marginBottom: 4 }}>{title}</div>
      {children}
    </div>
  );
}

function ProgressScreen({ metrics, onBack }) {
  const [help, setHelp] = React.useState(false);
  React.useEffect(() => {
    const onKey = (e) => {
      if (help) { if (["?", "Escape", "q"].includes(e.key)) setHelp(false); return; }
      if (e.key === "?") setHelp(true);
      else if (e.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [help, onBack]);

  const maxFunnel = Math.max(...metrics.funnel.map((s) => s[1]));
  const rate = (r) => (r >= 30 ? "var(--tui-green)" : r >= 15 ? "var(--tui-yellow)" : r >= 5 ? "var(--tui-peach)" : "var(--tui-red)");

  const weeks = Array.from({ length: 24 }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => {
      const h = Math.abs(Math.sin(w * 3.7 + d * 1.9)) * 6;
      return d === 0 || d === 6 ? Math.floor(h / 3) : Math.floor(h);
    }));

  const screen = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <TuiHeaderBar icon="progress" title="✦ SEARCH PROGRESS ✧" gradient="progress" iconColor="var(--tui-peach)"
        info={metrics.funnel[0][1] + " evaluated | " + metrics.avg.toFixed(1) + " avg score"} />
      <div style={{ flex: 1, overflowY: "auto", paddingTop: 21, fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", color: "var(--tui-text)" }}>
        <Section title="Pipeline Funnel">
          {metrics.funnel.map((s, i) => (
            <FunnelBar key={s[0]} label={s[0]} count={s[1]} max={maxFunnel} color={FUNNEL_COLORS[i]} width={46}
              pct={i ? (s[1] / metrics.funnel[i - 1][1]) * 100 : undefined} />
          ))}
        </Section>

        <Section title="Funnel Drill-Down &amp; Drop-Off Diagnostics" color="var(--tui-mauve)">
          {[["1. Discovered", 247, 100.0, "Initial raw posting pool"],
            ["2. Evaluated", 246, 99.6, "1 pre-filtered"],
            ["3. High-Fit (≥4.0)", 164, 66.7, "82 lower fit (<4.0)"],
            ["4. Applied", 52, 31.7, "112 high-fit pending apply"],
            ["5. Responded", 18, 34.6, "34 awaiting response"],
            ["6. Interview", 7, 38.9, "11 dropped / ghosted"],
            ["7. Offer", 2, 28.6, "Target terminal outcome"]].map((r) => (
            <div key={r[0]} style={{ display: "flex", whiteSpace: "pre" }}>
              <span style={{ width: 168, flex: "0 0 auto" }}>{r[0]}</span>
              <span style={{ color: "var(--tui-subtext)", width: 56, textAlign: "right" }}>{r[1]}</span>
              <span style={{ color: r[2] < 30 ? "var(--tui-yellow)" : "var(--tui-green)", fontWeight: 700, width: 76, textAlign: "right" }}>{r[2].toFixed(1) + "%"}</span>
              <span style={{ color: "var(--tui-subtext)" }}>{"  • " + r[3]}</span>
            </div>
          ))}
        </Section>

        <Section title="Conversion Rates">
          <div>
            Response Rate: <b style={{ color: rate(metrics.rates.response) }}>{metrics.rates.response}%</b>
            <span style={{ color: "var(--tui-subtext)" }}>{"  |  "}</span>
            Interview Rate: <b style={{ color: rate(metrics.rates.interview) }}>{metrics.rates.interview}%</b>
            <span style={{ color: "var(--tui-subtext)" }}>{"  |  "}</span>
            Offer Rate: <b style={{ color: rate(metrics.rates.offer) }}>{metrics.rates.offer}%</b>
          </div>
          <div style={{ color: "var(--tui-subtext)" }}>{metrics.rates.active} active applications | {metrics.total} total offers</div>
        </Section>

        <Section title="Score vs. Bullet Coverage (High-ROI Gap Radar)">
          <div>• Ready to Apply (Score ≥ 4.0, Cov ≥ 70%): <b style={{ color: "var(--tui-green)" }}>{metrics.quadrants.ready} roles</b></div>
          <div>• High-ROI Bullet Gaps (Score ≥ 4.0, Cov &lt; 70%): <b style={{ color: "var(--tui-yellow)" }}>{metrics.quadrants.gap} roles (Write bullets next!)</b></div>
          <div>• Over-Covered / Lower Fit (Score &lt; 4.0, Cov ≥ 70%): <span style={{ color: "var(--tui-subtext)" }}>{metrics.quadrants.over} roles</span></div>
          <div>• Deprioritized (Score &lt; 4.0, Cov &lt; 70%): <span style={{ color: "var(--tui-subtext)" }}>{metrics.quadrants.deprioritized} roles</span></div>
          <div>&nbsp;</div>
          <div style={{ color: "var(--tui-peach)", fontWeight: 700 }}>  Write Bullets For (High Fit, Low Coverage):</div>
          <div>{"  ↳ Content Strategist @ Meridian Labs (Score: 3.9, Cov: 58%)"}</div>
          <div>{"  ↳ Creative Director @ Callahan Creek (Score: 4.4, Cov: 76%)"}</div>
        </Section>

        <Section title="Top Employers &amp; Staffing Detection">
          {metrics.companies.map(([name, rolesN, avg, agency]) => (
            <div key={name} style={{ display: "flex", whiteSpace: "pre" }}>
              <span style={{ color: agency ? "var(--tui-yellow)" : "var(--tui-blue)" }}>{agency ? "[AGENCY]" : "[DIRECT]"}</span>
              <span style={{ width: 202, paddingLeft: 8 }}>{name}</span>
              <span style={{ color: "var(--tui-subtext)", width: 76, textAlign: "right" }}>{rolesN + " roles"}</span>
              <span style={{ color: avg >= 4 ? "var(--tui-green)" : avg >= 3.5 ? "var(--tui-yellow)" : "var(--tui-subtext)", fontWeight: 700 }}>{"  " + avg.toFixed(2) + " avg"}</span>
            </div>
          ))}
        </Section>

        <Section title="Mission Control (Heatmap &amp; Trends)">
          <div>&nbsp;</div>
          <Heatmap weeks={weeks} max={6} />
          <div>&nbsp;</div>
        </Section>

        <div style={{ padding: "0 var(--pad-h)", color: "var(--tui-subtext)" }}>
          Per-source yield, response-time distribution, score histogram and week-over-week deltas moved to <span style={{ color: "var(--tui-peach)" }}>Insights</span> — this screen stays the one you check to see where things stand.
        </div>
      </div>
      <TuiFooterBar
        actions={[{ key: "↑↓/jk", desc: "scroll" }, { key: "PgUp/Dn", desc: "page" }, { key: "?", desc: "help" }]}
        system={[{ key: "Esc", desc: "back" }, { key: "q", desc: "quit" }]} />
    </div>
  );

  return help ? <HelpOverlay title="Search Progress" categories={PROGRESS_HELP} backdrop={screen} /> : screen;
}

Object.assign(window, { ProgressScreen });
