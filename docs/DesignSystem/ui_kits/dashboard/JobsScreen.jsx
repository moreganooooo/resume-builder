const { TuiHeaderBar, TuiFooterBar, TuiPanel, SidebarRow, NoticeBar, SearchBar, Glyph, HelpOverlay,
        StatusPill, EmploymentTag, ScoreBadge, ScoreBar, StarfieldPane } = window.ResumeBuilderDesignSystem_2d03b1;

const JOBS_HELP = [
  { label: "Navigation", bindings: [{ key: "↑ ↓ / j k", desc: "Move selection" }, { key: "J / K", desc: "Scroll detail pane down / up" }, { key: "g / G", desc: "Jump to top / bottom" }, { key: "PgUp / PgDn", desc: "Page up / down" }] },
  { label: "Actions", bindings: [{ key: "s", desc: "Scan for new job postings" }, { key: "b", desc: "Batch evaluate pending jobs" }, { key: "L", desc: "Sweep stale postings" }, { key: "o", desc: "Open this job posting in your browser" }, { key: "l", desc: "Check posting liveness" }, { key: "m", desc: "Compute Skills Gap Matrix for this job" }, { key: "M", desc: "Compute Skills Gap Matrix for pending jobs missing one (bulk, capped)" }, { key: "t", desc: "Tailor (or re-tailor) resume for this job" }, { key: "u", desc: "Change application status" }, { key: "a", desc: "Open application answers chat" }, { key: "x", desc: "Archive this job (removes from all filters)" }] },
  { label: "Filters", bindings: [{ key: "f", desc: "Cycle filters: All / Pending / Completed / High Fit / Good Fit / Recent / Local / Low. Only Low shows roles under 3.5" }, { key: "w", desc: "Cycle workplace filter: All → Remote → Hybrid → Onsite" }, { key: "e", desc: "Cycle employment type filter" }, { key: "$", desc: "Cycle pay filter: All → Stated → Unstated" }, { key: "d", desc: "Toggle sort by distance (nearest first, unmeasured last)" }, { key: "p", desc: "Toggle sort by pay (highest first, unstated last)" }, { key: "/", desc: "Search company/title (narrows within active filter)" }, { key: "r", desc: "Toggle manager-track roles only" }, { key: "c", desc: "Toggle experience/degree blocker roles only" }, { key: "n", desc: "Toggle manually-added roles only" }] },
  { label: "Quick Reference", bindings: [{ key: "v", desc: "View terminology definitions" }, { key: "?", desc: "Show this help overlay" }] },
  { label: "Terminology", bindings: [{ key: "Composite Score", desc: "Overall fit (40% Fit + 40% Interview Odds + 20% Practical Pursue)" }, { key: "Fit", desc: "How well your background matches job requirements" }, { key: "Interview Odds", desc: "Likelihood of advancing past initial screening" }, { key: "North Star", desc: "Your target skill/role that guides tailoring" }, { key: "Liveness", desc: "Whether a job posting is still actively being filled" }] },
  { label: "Exit", bindings: [{ key: "Esc", desc: "Clear search, or back to Main Menu" }, { key: "q", desc: "Quit dashboard" }] },
];

function JobsDetail({ job }) {
  if (!job) {
    return <StarfieldPane rows={14} cols={44} hints={[
      "To scan for new roles, press [ s ]",
      "To batch evaluate pending, press [ b ]",
      "",
      "Or use the CLI: resume build <jd_file>",
    ]} />;
  }
  const A = ({ children }) => <div style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>{children}</div>;
  const S = ({ k, children }) => <div><span style={{ color: "var(--tui-subtext)" }}>{k}</span>{children}</div>;
  return (
    <div>
      <div style={{ color: "var(--tui-blue)", fontWeight: 700 }}>{job.company}</div>
      <div>{job.title}</div>
      {job.pay ? <div style={{ color: "var(--tui-green)", fontWeight: 700 }}>{job.pay}</div> : null}
      <div style={{ color: "var(--tui-subtext)" }}>via {job.platform}</div>
      <div style={{ color: "var(--tui-sky)" }}>
        <Glyph name="location" /> {job.workplace}{job.miles ? " · " + job.miles.toFixed(1) + " mi" : ""}
      </div>
      <div style={{ color: "var(--tui-blue)" }}>↗ Open job posting</div>
      <div>&nbsp;</div>

      <A>Scores</A>
      <S k="Composite: "><ScoreBadge score={job.score} suffix="/5" /></S>
      <S k="  Fit: "><ScoreBadge score={job.fit} /></S>
      <S k="  Interview odds: "><ScoreBadge score={job.odds} /></S>
      <div>&nbsp;</div>

      <A>Fit subscores</A>
      {job.fitSubscores.map(([label, v]) => <ScoreBar key={label} label={label} value={v} />)}
      <div>&nbsp;</div>

      <A>Interview odds subscores</A>
      {job.oddsSubscores.map(([label, v]) => <ScoreBar key={label} label={label} value={v} />)}
      <div>&nbsp;</div>

      <A>Stress &amp; Stretch</A>
      {job.stress.length ? (
        <>
          <div style={{ color: "var(--tui-yellow)" }}>Stress signals: {job.stress.length}</div>
          {job.stress.map((s) => <div key={s}>{"  • " + s}</div>)}
        </>
      ) : (
        <div style={{ color: "var(--tui-green)" }}>No stress signals detected — earned the low-stress bonus</div>
      )}
      {job.gaps ? <div style={{ color: "var(--tui-subtext)" }}>Experience gaps: {job.gaps} (detailed below)</div>
        : <div style={{ color: "var(--tui-green)" }}>No experience gaps flagged</div>}
      <div>&nbsp;</div>

      <A>Skills Gap Matrix</A>
      {job.matrix.map(([label, v]) => <ScoreBar key={label} label={label} value={v} max={100} />)}
      <div>&nbsp;</div>

      {job.skip ? <div style={{ color: "var(--tui-red)" }}>✗ Skip — flagged as not a viable posting</div> : null}
      <S k="Status: "><StatusPill status={job.status} /></S>
      <div>&nbsp;</div>
      <A>Why</A>
      <div>{job.why}</div>
      <div style={{ color: "var(--tui-subtext)" }}>  J ↓ more</div>
    </div>
  );
}

function JobsScreen({ jobs, onBack }) {
  const [cursor, setCursor] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [typing, setTyping] = React.useState(false);
  const [working, setWorking] = React.useState("");
  const [frame, setFrame] = React.useState(0);
  const [help, setHelp] = React.useState(false);

  const rows = jobs.filter((j) => (j.company + j.title).toLowerCase().includes(query.toLowerCase()));
  const job = rows[Math.min(cursor, rows.length - 1)];
  const best = jobs.filter((j) => j.score >= 4.0 && j.status === "evaluated").sort((a, b) => b.score - a.score)[0];

  React.useEffect(() => {
    if (!working) return;
    const id = setInterval(() => setFrame((f) => f + 1), 90);
    const done = setTimeout(() => setWorking(""), 3600);
    return () => { clearInterval(id); clearTimeout(done); };
  }, [working]);

  React.useEffect(() => {
    const onKey = (e) => {
      if (help) { if (["?", "Escape", "q"].includes(e.key)) setHelp(false); return; }
      if (typing) {
        if (e.key === "Escape") { setTyping(false); setQuery(""); }
        else if (e.key === "Enter") setTyping(false);
        else if (e.key === "Backspace") setQuery((q) => q.slice(0, -1));
        else if (e.key.length === 1) setQuery((q) => q + e.key);
        e.preventDefault(); return;
      }
      if (e.key === "/") { setTyping(true); setCursor(0); }
      else if (e.key === "?") setHelp(true);
      else if (e.key === "j" || e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, rows.length - 1));
      else if (e.key === "k" || e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "t") setWorking("tailor");
      else if (e.key === "s") setWorking("scan");
      else if (e.key === "Escape") { if (query) setQuery(""); else onBack(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [typing, help, rows.length, query, onBack]);

  const SPIN = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];
  const pct = Math.min(100, Math.round((frame / 40) * 100));

  const screen = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <TuiHeaderBar icon="jobs" title="✦ JOBS ✧" gradient="jobs"
        info={<>{rows.length} job(s) <span style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>● GOOD FIT (3.5+)</span> <span style={{ color: "var(--tui-subtext)" }}>11 awaiting evaluation</span></>} />
      {best && !working ? (
        <NoticeBar variant="banner"
          message={"★ NEXT BEST MOVE: High match at " + best.company + " (" + best.score.toFixed(1) + ") — Press 't' to tailor now!"} />
      ) : null}
      {typing || query ? <SearchBar active={typing} query={query} matched={rows.length} total={jobs.length} /> : null}
      {working === "tailor" ? (
        <div style={{ background: "var(--tui-surface)", color: "var(--tui-yellow)", padding: "0 var(--pad-h)" }}>
          <div>Step 3/6: Selecting bullets from the bank (esc to cancel)</div>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ color: "var(--tui-mauve)", whiteSpace: "pre" }}>
              {"█".repeat(Math.round(pct / 2.5))}<span style={{ color: "var(--tui-overlay)" }}>{"█".repeat(40 - Math.round(pct / 2.5))}</span>
              {i === 1 ? <span style={{ color: "var(--tui-subtext)" }}>{" " + pct + "%"}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
      {working === "scan" ? (
        <div style={{ background: "var(--tui-surface)", color: "var(--tui-yellow)", padding: "0 var(--pad-h)" }}>
          {SPIN[frame % SPIN.length]} Scanning job boards... (esc to cancel)
        </div>
      ) : null}
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <TuiPanel variant="active" style={{ flex: "0 0 60%", overflow: "hidden" }}>
          {rows.map((j, i) => (
            <SidebarRow key={j.company} score={j.score} company={j.company}
              tag={<EmploymentTag type={j.employment[0]} />}
              subtitle={<>{j.title}<span style={{ color: "var(--tui-subtext)" }}>{"  Fit " + j.fit.toFixed(1) + " / Odds " + j.odds.toFixed(1)}</span></>}
              selected={i === cursor} onClick={() => setCursor(i)} />
          ))}
        </TuiPanel>
        <TuiPanel variant="idle" pad="detail" style={{ flex: 1, overflowY: "auto" }}>
          <JobsDetail job={job} />
        </TuiPanel>
      </div>
      <TuiFooterBar
        actions={[{ key: "↑↓/jk", desc: "nav" }, { key: "J/K", desc: "scroll detail" }, { key: "g/G", desc: "top/bot" }, { key: "PgUp/Dn", desc: "page" }, { key: "/", desc: "search" }, { key: "f", desc: "filter" }, { key: "w", desc: "workplace" }, { key: "e", desc: "emp type" }, { key: "d", desc: "nearest" }, { key: "p", desc: "pay" }, { key: "r", desc: "managers" }, { key: "o", desc: "open" }, { key: "l", desc: "liveness" }, { key: "m", desc: "matrix" }, { key: "t", desc: "tailor" }, { key: "u", desc: "status" }, { key: "a", desc: "archive" }, { key: "v", desc: "vocabulary" }, { key: "?", desc: "help" }]}
        system={[{ key: "Esc", desc: "back" }, { key: "q", desc: "quit" }]} />
    </div>
  );

  return help ? <HelpOverlay title="Jobs" categories={JOBS_HELP} backdrop={screen} /> : screen;
}

Object.assign(window, { JobsScreen });
