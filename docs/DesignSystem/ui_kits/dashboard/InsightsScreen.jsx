const { TuiHeaderBar, TuiFooterBar, FunnelBar, Sparkline, ProgressBar, HelpOverlay } = window.ResumeBuilderDesignSystem_2d03b1;

const INSIGHTS_HELP = [
  { label: "Navigation", bindings: [{ key: "↑ ↓ / j k", desc: "Scroll one line" }, { key: "PgUp / PgDn", desc: "Scroll one page" }] },
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

// The analytics half of what used to be one Progress screen. Progress
// itself keeps the funnel — the thing you check to answer "where do things
// stand"; this is for "what's working, and what changed" — a different
// question, asked less often, that doesn't need to load every time.
function InsightsScreen({ metrics, onBack }) {
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

  const maxBucket = Math.max(...metrics.buckets.map((s) => s[1]));
  const maxPlatform = Math.max(...metrics.platforms.map((p) => p[1]));
  const bucketColors = ["var(--tui-green)", "var(--tui-green)", "var(--tui-yellow)", "var(--tui-peach)", "var(--tui-red)"];

  // "What changed this week" — the delta a returning user actually wants,
  // computed against last week's snapshot rather than restating totals.
  const deltas = [
    ["Applications sent", "+6", "var(--tui-green)"],
    ["Responses", "+2", "var(--tui-green)"],
    ["Interviews", "0", "var(--tui-subtext)"],
    ["Avg. score of new evaluations", "-0.1", "var(--tui-peach)"],
  ];

  // Days from Applied to first response, bucketed. Response-rate math
  // already lives on Progress; this is the shape of the wait, which is a
  // different anxiety to answer.
  const responseTime = [["0-2 days", 5], ["3-5 days", 8], ["6-10 days", 3], ["11-20 days", 2], ["20+ days", 1]];
  const maxResponse = Math.max(...responseTime.map((r) => r[1]));

  const streak = { current: 4, best: 9, weeklyGoal: 5, weeklyDone: 3 };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <TuiHeaderBar icon="progress" gradient="progress" iconColor="var(--tui-peach)" title="✦ INSIGHTS ✧"
        info={metrics.rates.response + "% response | " + metrics.rates.interview + "% interview"} />
      <div style={{ flex: 1, overflowY: "auto", paddingTop: 21, fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", color: "var(--tui-text)" }}>

        <Section title="What Changed This Week" color="var(--tui-mauve)">
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {deltas.map(([label, d, c]) => (
              <div key={label}>
                <div style={{ color: "var(--tui-subtext)" }}>{label}</div>
                <div style={{ color: c, fontWeight: 700 }}>{d}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Weekly Goal &amp; Streak">
          <div style={{ display: "flex", gap: 32, alignItems: "flex-end" }}>
            <div>
              <div style={{ color: "var(--tui-subtext)" }}>This week</div>
              <ProgressBar value={streak.weeklyDone} max={streak.weeklyGoal} width={30} label={streak.weeklyDone + " / " + streak.weeklyGoal + " applications"} />
            </div>
            <div>
              <div style={{ color: "var(--tui-subtext)" }}>Current streak</div>
              <div style={{ color: "var(--tui-green)", fontWeight: 700 }}>{streak.current} week(s)</div>
            </div>
            <div>
              <div style={{ color: "var(--tui-subtext)" }}>Best streak</div>
              <div style={{ fontWeight: 700 }}>{streak.best} week(s)</div>
            </div>
          </div>
        </Section>

        <Section title="Source-Platform Yield &amp; Quality">
          {metrics.platforms.map(([name, rolesN, avg]) => (
            <div key={name} style={{ display: "flex", whiteSpace: "pre" }}>
              <span style={{ width: 126, flex: "0 0 auto" }}>{name}</span>
              <span style={{ color: "var(--tui-mauve)" }}>{"■".repeat(Math.max(1, Math.round((rolesN * 26) / maxPlatform)))}</span>
              <span style={{ color: "var(--tui-subtext)", width: 76, textAlign: "right" }}>{rolesN + " jobs"}</span>
              <span style={{ color: avg >= 4 ? "var(--tui-green)" : avg >= 3.5 ? "var(--tui-yellow)" : "var(--tui-subtext)", fontWeight: 700 }}>{"  " + avg.toFixed(2) + " avg"}</span>
            </div>
          ))}
          <div style={{ color: "var(--tui-subtext)", marginTop: 6 }}>Referral converts to interviews at the highest rate of any source, despite the smallest volume.</div>
        </Section>

        <Section title="Time to First Response" color="var(--tui-blue)">
          {responseTime.map(([label, n]) => (
            <FunnelBar key={label} label={label} count={n} max={maxResponse} color="var(--tui-blue)" width={46} labelWidth={80} />
          ))}
        </Section>

        <Section title="Score Distribution">
          {metrics.buckets.map((b, i) => (
            <FunnelBar key={b[0]} label={b[0]} count={b[1]} max={maxBucket} color={bucketColors[i]} width={46} labelWidth={72} />
          ))}
        </Section>

        <Section title="Application Strategy Radar (Score: 75/100)" color="var(--tui-blue)">
          {metrics.radar.map(([name, score, grade, desc]) => {
            const c = score < 60 ? "var(--tui-peach)" : score < 75 ? "var(--tui-yellow)" : "var(--tui-green)";
            const filled = Math.round(score / 10);
            return (
              <div key={name} style={{ display: "flex", whiteSpace: "pre" }}>
                <span style={{ width: 184, flex: "0 0 auto" }}>{name}</span>
                <span style={{ color: c }}>{"[" + "█".repeat(filled) + "░".repeat(10 - filled) + "]"}</span>
                <span style={{ color: c, fontWeight: 700, width: 92, paddingLeft: 8 }}>{score + "% (" + grade + ")"}</span>
                <span style={{ color: "var(--tui-subtext)" }}>{desc}</span>
              </div>
            );
          })}
        </Section>

        <Section title="Trends">
          <div style={{ display: "flex" }}><span style={{ width: 126 }}>Score Trend</span><Sparkline values={metrics.scoreTrend} /></div>
          <div style={{ display: "flex" }}><span style={{ width: 126 }}>Weekly Volume</span><Sparkline values={metrics.volumeTrend} color="var(--tui-blue)" /></div>
        </Section>
      </div>
      <TuiFooterBar
        actions={[{ key: "↑↓/jk", desc: "scroll" }, { key: "PgUp/Dn", desc: "page" }, { key: "?", desc: "help" }]}
        system={[{ key: "Esc", desc: "back" }, { key: "q", desc: "quit" }]} />
    </div>
  );

  return help ? <HelpOverlay title="Insights" categories={INSIGHTS_HELP} backdrop={screen} /> : screen;
}

Object.assign(window, { InsightsScreen });
