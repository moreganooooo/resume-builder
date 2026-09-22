const { TuiHeaderBar, TuiFooterBar, TuiTabs, TuiPanel, SidebarRow, SearchBar, NoticeBar,
        HelpOverlay, StatusPill, EmploymentTag, ScoreBadge, StarfieldPane, Modal, Toast } = window.ResumeBuilderDesignSystem_2d03b1;

const PIPELINE_TABS = [
  { label: "ALL", filter: () => true },
  { label: "EVALUATED", filter: (j) => j.status === "evaluated" },
  { label: "APPLIED", filter: (j) => j.status === "applied" },
  { label: "INTERVIEW", filter: (j) => j.status === "interview" },
  { label: "TOP ≥4", filter: (j) => j.score >= 4.0 && j.status !== "skip" },
  { label: "LOW <3.5", filter: (j) => j.score < 3.5 && !["applied", "interview", "offer", "responded", "rejected"].includes(j.status) },
  { label: "SKIP", filter: (j) => j.status === "skip" },
  { label: "REJECTED", filter: (j) => j.status === "rejected" },
];

// Board columns — pipeline order, work-in-flight only. Skip and Rejected
// stay list-only: a board is for what's still moving, and a closed-out
// column would spend a fifth of the width saying nothing happens here.
const BOARD_COLUMNS = [
  { key: "evaluated", label: "EVALUATED", color: "var(--tui-sky)" },
  { key: "applied", label: "APPLIED", color: "var(--tui-blue)" },
  { key: "responded", label: "RESPONDED", color: "var(--tui-peach)" },
  { key: "interview", label: "INTERVIEW", color: "var(--tui-mauve)" },
  { key: "offer", label: "OFFER", color: "var(--tui-green)" },
];

// The kit's six sample jobs cluster at the front of the pipeline, which
// would render a board of empty columns. These board-only rows carry the
// four fields a card shows and nothing else — enough to demonstrate a
// pipeline in flight without pretending they are scored records.
const BOARD_EXTRA = [
  { company: "Ardent Group", title: "Brand Director", score: 4.1, employment: ["full_time"], status: "responded" },
  { company: "Kestrel Foods", title: "Senior Copy Lead", score: 3.8, employment: ["full_time"], status: "responded" },
  { company: "Waypoint Studio", title: "Content Director", score: 4.3, employment: ["contract"], status: "interview" },
  { company: "Brightline Co.", title: "Head of Content", score: 4.6, employment: ["full_time"], status: "offer" },
  { company: "Pallas Media", title: "Strategy Lead", score: 3.6, employment: ["full_time"], status: "applied" },
];

const PIPELINE_HELP = [
  { label: "Navigation", bindings: [{ key: "↑ ↓ / j k", desc: "Move selection" }, { key: "g / G", desc: "Jump to top / bottom" }, { key: "← → / h l", desc: "Cycle tabs (list view) or columns (board view)" }] },
  { label: "Actions", bindings: [{ key: "Enter", desc: "Open report" }, { key: "o", desc: "Open job URL in browser" }, { key: "c", desc: "Change application status" }, { key: "r", desc: "Refresh from disk" }] },
  { label: "View", bindings: [{ key: "/", desc: "Search company/role/notes" }, { key: "s", desc: "Cycle sort mode" }, { key: "v", desc: "Toggle list / board view" }, { key: "p", desc: "Open Progress screen" }] },
  { label: "Filters", bindings: [{ key: "w", desc: "Cycle workplace mode" }, { key: "$", desc: "Cycle pay-disclosure mode" }, { key: "", desc: "Roles you have applied to are never hidden by that bar" }] },
  { label: "Exit", bindings: [{ key: "Esc", desc: "Clear search, or back to Main Menu" }, { key: "q", desc: "Quit dashboard" }] },
];

function statusLabel(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

const GROUP_OF = {
  evaluated: "PENDING", pending: "PENDING", skip: "SKIPPED", rejected: "REJECTED",
  applied: "APPLIED", interview: "INTERVIEW", offer: "OFFER", responded: "RESPONDED",
};

function PipelineDetail({ job }) {
  if (!job) {
    return <StarfieldPane rows={16} cols={62} hints={[
      "To change which applications show, press [ f ]",
      "To search by company or role, press [ / ]",
      "",
      "To reload from disk, press [ r ]",
    ]} />;
  }
  const L = ({ k, children }) => (
    <div><span style={{ color: "var(--tui-subtext)" }}>{k}</span>{children}</div>
  );
  return (
    <div>
      <div style={{ color: "var(--tui-blue)", fontWeight: 700 }}>{job.company}</div>
      <div style={{ color: "var(--tui-text)" }}>{job.title}</div>
      {job.pay ? <div style={{ color: "var(--tui-green)", fontWeight: 700 }}>{job.pay}</div> : null}
      <div>&nbsp;</div>
      <L k="Interview Probability: "><ScoreBadge score={job.score} /></L>
      <L k="Status: "><StatusPill status={job.status} /></L>
      <L k="Date Scanned/Posted: "><span style={{ color: "var(--tui-text)" }}>{job.date}</span></L>
      <div>&nbsp;</div>
      <L k="Details: "><span style={{ color: "var(--tui-text)" }}>{job.workplace} {job.location}{job.pay ? " | " + job.pay : ""}</span></L>
      <div>&nbsp;</div>
      <L k="Employment: ">{job.employment.map((e) => <EmploymentTag key={e} type={e} />)}</L>
      {job.stress.length ? <L k="Stress signals: "><span style={{ color: "var(--tui-text)" }}>{job.stress.join(", ")}</span></L> : null}
      <div>&nbsp;</div>
      <div style={{ color: "var(--tui-blue)", fontWeight: 700 }}>Analysis</div>
      <div style={{ color: "var(--tui-text)" }}>{job.why}</div>
    </div>
  );
}

function BoardCard({ job, selected, dimmed, onClick }) {
  return (
    <div onClick={onClick} style={{
      display: "flex", flexDirection: "column", cursor: "pointer",
      borderLeft: selected ? "1px solid var(--tui-mauve)" : "1px solid transparent",
      paddingLeft: selected ? 7.4 : 8.4, paddingRight: 8.4, marginBottom: 8, paddingTop: 2, paddingBottom: 2,
      opacity: dimmed ? 0.45 : 1, whiteSpace: "nowrap", overflow: "hidden",
    }}>
      <div style={{ display: "flex", gap: "8.4px", alignItems: "baseline", minWidth: 0 }}>
        <ScoreBadge score={job.score} />
        <span style={{ fontWeight: selected ? 700 : 400, overflow: "hidden", textOverflow: "ellipsis" }}>{job.company}</span>
      </div>
      <div style={{ color: "var(--tui-subtext)", overflow: "hidden", textOverflow: "ellipsis" }}>{job.title}</div>
      <div><EmploymentTag type={job.employment[0]} /></div>
    </div>
  );
}

// The board view — same screen, same header/footer, a different lens: the
// axis is status, so moving a card and changing status are one gesture.
// It owns its own key handling while mounted; PipelineScreen's listener
// stands down for everything except v/Esc/q while this is up.
function PipelineBoard({ jobs, col, row, setCol, setRow, confirm, setConfirm }) {
  const board = React.useMemo(() => (
    [...jobs, ...BOARD_EXTRA].filter((j) => BOARD_COLUMNS.some((c) => c.key === j.status))
  ), [jobs]);
  const byCol = BOARD_COLUMNS.map((c) => board.filter((j) => j.status === c.key));
  const current = byCol[col][Math.min(row, byCol[col].length - 1)];

  React.useEffect(() => {
    if (!current) return;
    if (row >= byCol[col].length) setRow(Math.max(0, byCol[col].length - 1));
  }, [col, row, byCol, current, setRow]);

  return (
    <>
      <div style={{ flex: 1, display: "flex", gap: 10, padding: "12px var(--pad-h)", minHeight: 0 }}>
        {BOARD_COLUMNS.map((c, ci) => (
          <div key={c.key} style={{ flex: 1, minWidth: 0, display: "flex" }}>
            <TuiPanel variant={ci === col ? "active" : "idle"} pad="tight" style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
              <div style={{ display: "flex", justifyContent: "space-between", color: c.color, fontWeight: 700, marginBottom: 8, whiteSpace: "nowrap" }}>
                <span>{c.label}</span><span style={{ color: "var(--tui-subtext)", fontWeight: 400 }}>{byCol[ci].length}</span>
              </div>
              <div style={{ borderTop: "1px solid var(--tui-overlay)", marginBottom: 10 }}></div>
              <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
                {byCol[ci].length ? byCol[ci].map((j, ri) => (
                  <BoardCard key={j.company} job={j} selected={ci === col && ri === Math.min(row, byCol[ci].length - 1)}
                    dimmed={ci !== col} onClick={() => { setCol(ci); setRow(ri); }} />
                )) : <StarfieldPane card={false} />}
              </div>
            </TuiPanel>
          </div>
        ))}
      </div>
      {confirm ? (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Modal title="Change status">
            <div>Move <span style={{ fontWeight: 700 }}>{confirm.job.company}</span> to <StatusPill status={confirm.to.key} />?</div>
            <div style={{ color: "var(--tui-subtext)", marginTop: 8 }}>Enter/y confirm  Esc/n cancel</div>
          </Modal>
        </div>
      ) : null}
    </>
  );
}

function PipelineScreen({ jobs, metrics, onBack }) {
  const [view, setView] = React.useState("list");
  const [tab, setTab] = React.useState(0);
  const [cursor, setCursor] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [typing, setTyping] = React.useState(false);
  const [help, setHelp] = React.useState(false);
  const [notice, setNotice] = React.useState("");
  const [col, setCol] = React.useState(0);
  const [row, setRow] = React.useState(0);
  const [confirm, setConfirm] = React.useState(null);
  const [celebration, setCelebration] = React.useState("");

  const inTab = jobs.filter(PIPELINE_TABS[tab].filter);
  const rows = inTab.filter((j) => (j.company + j.title).toLowerCase().includes(query.toLowerCase()));
  const job = rows[Math.min(cursor, rows.length - 1)];
  const statusEntries = Object.entries(metrics.byStatus).filter(([, v]) => v > 0);
  const groups = [];
  rows.forEach((j, i) => {
    const g = GROUP_OF[j.status] || "PENDING";
    const last = groups[groups.length - 1];
    if (last && last.label === g) last.rows.push([j, i]);
    else groups.push({ label: g, rows: [[j, i]] });
  });

  const boardJobs = React.useMemo(() => (
    [...jobs, ...BOARD_EXTRA].filter((j) => BOARD_COLUMNS.some((c) => c.key === j.status))
  ), [jobs]);
  const byCol = BOARD_COLUMNS.map((c) => boardJobs.filter((j) => j.status === c.key));
  const boardCurrent = byCol[col] && byCol[col][Math.min(row, byCol[col].length - 1)];
  const proposeStatus = (dir) => {
    if (!boardCurrent) return;
    const target = BOARD_COLUMNS[Math.max(0, Math.min(BOARD_COLUMNS.length - 1, col + dir))];
    if (target.key === boardCurrent.status) return;
    setConfirm({ job: boardCurrent, to: target });
  };
  const commitStatus = () => {
    if (!confirm) return;
    // Moving into Interview or Offer is two of the four moments that earn
    // confetti — a routine status change (e.g. into Applied) gets none.
    if (["interview", "offer"].includes(confirm.to.key)) {
      setCelebration(confirm.job.company + " moved to " + confirm.to.label + "!");
      setTimeout(() => setCelebration(""), 2400);
    }
    setCol(BOARD_COLUMNS.indexOf(confirm.to));
    setRow(0);
    setConfirm(null);
  };

  React.useEffect(() => {
    const onKey = (e) => {
      if (help) { if (["?", "Escape", "q"].includes(e.key)) setHelp(false); return; }

      if (view === "board") {
        if (confirm) {
          if (e.key === "Enter" || e.key === "y") commitStatus();
          else if (e.key === "Escape" || e.key === "n") setConfirm(null);
          return;
        }
        if (e.key === "v") { setView("list"); return; }
        if (e.key === "?") { setHelp(true); return; }
        if (e.key === "j" || e.key === "ArrowDown") setRow((r) => Math.min(r + 1, byCol[col].length - 1));
        else if (e.key === "k" || e.key === "ArrowUp") setRow((r) => Math.max(r - 1, 0));
        else if (e.key === "l" || e.key === "ArrowRight") { setCol((c) => Math.min(c + 1, BOARD_COLUMNS.length - 1)); setRow(0); }
        else if (e.key === "h" || e.key === "ArrowLeft") { setCol((c) => Math.max(c - 1, 0)); setRow(0); }
        else if (e.key === "H") proposeStatus(-1);
        else if (e.key === "L") proposeStatus(1);
        else if (e.key === "Escape") onBack();
        else if (e.key === "q") onBack();
        return;
      }

      if (typing) {
        if (e.key === "Escape") { setTyping(false); setQuery(""); }
        else if (e.key === "Enter") setTyping(false);
        else if (e.key === "Backspace") setQuery((q) => q.slice(0, -1));
        else if (e.key.length === 1) setQuery((q) => q + e.key);
        e.preventDefault(); return;
      }
      if (e.key === "?") setHelp(true);
      else if (e.key === "v") setView("board");
      else if (e.key === "/") { setTyping(true); setCursor(0); }
      else if (e.key === "j" || e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, rows.length - 1));
      else if (e.key === "k" || e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "l" || e.key === "ArrowRight" || e.key === "f") { setTab((t) => (t + 1) % PIPELINE_TABS.length); setCursor(0); }
      else if (e.key === "h" || e.key === "ArrowLeft") { setTab((t) => (t + PIPELINE_TABS.length - 1) % PIPELINE_TABS.length); setCursor(0); }
      else if (e.key === "o") setNotice("No job URL saved for this application");
      else if (e.key === "Escape") { if (query) { setQuery(""); } else onBack(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [help, typing, rows.length, query, onBack, view, col, row, byCol, confirm, boardCurrent]);

  const screen = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      <TuiHeaderBar icon="pipeline" title="✦ CAREER PIPELINE ✧" gradient="pipeline"
        info={metrics.total + " offers | Avg " + metrics.avg.toFixed(1) + "/5"} />
      {view === "list" ? (
        <>
          <TuiTabs active={tab} onChange={(i) => { setTab(i); setCursor(0); }}
            tabs={PIPELINE_TABS.map((t) => ({ label: t.label, count: jobs.filter(t.filter).length }))} />
          <div style={{ background: "var(--tui-surface)", padding: "0 var(--pad-h)", display: "flex", gap: 16 }}>
            {statusEntries.length === 0
              ? <span style={{ color: "var(--tui-subtext)" }}>No applications tracked yet — press [ c ] on a role to set its status</span>
              : statusEntries.map(([k, v]) => (
                  <span key={k} style={{ color: "var(--status-" + k + ")" }}>{statusLabel(k)}:{v}</span>
                ))}
          </div>
          <div style={{ color: "var(--tui-subtext)", padding: "0 var(--pad-h)", display: "flex", gap: 16 }}>
            <span>[Sort: score]</span><span>[View: list — press v for board]</span><span>{rows.length} shown</span>
          </div>
          {typing || query ? <SearchBar active={typing} query={query} matched={rows.length} total={inTab.length} /> : null}
          {notice ? <NoticeBar variant="notice" message={notice} /> : null}
          <div style={{ display: "flex", flex: 1, minHeight: 0, gap: 0 }}>
            <TuiPanel variant="active" style={{ flex: "0 0 35%", overflow: "hidden" }}>
              {rows.length === 0 ? <div style={{ color: "var(--tui-subtext)", padding: "21px 8.4px" }}>No offers match this filter</div> : null}
              {groups.map((g) => (
                <React.Fragment key={g.label}>
                  <div style={{ color: "var(--tui-blue)", fontWeight: 700, padding: "6px 8.4px 2px" }}>{g.label} ({g.rows.length})</div>
                  {g.rows.map(([j, i]) => (
                    <SidebarRow key={j.company + i} score={j.score} company={j.company}
                      tag={<EmploymentTag type={j.employment[0]} />} subtitle={j.title}
                      selected={i === cursor} onClick={() => { setCursor(i); setNotice(""); }} />
                  ))}
                </React.Fragment>
              ))}
            </TuiPanel>
            <TuiPanel variant="idle" pad="detail" style={{ flex: 1, overflow: "hidden" }}>
              <PipelineDetail job={job} />
            </TuiPanel>
          </div>
        </>
      ) : (
        <>
          <div style={{ color: "var(--tui-subtext)", padding: "0 var(--pad-h)", display: "flex", gap: 16 }}>
            <span>[View: board — press v for list]</span><span>H/L move a card between columns</span>
          </div>
          <PipelineBoard jobs={jobs} col={col} row={row} setCol={setCol} setRow={setRow} confirm={confirm} setConfirm={setConfirm} />
          {celebration ? (
            <div style={{ position: "absolute", bottom: 40, left: 0, right: 0 }}><Toast celebrate icon="success" message={celebration} /></div>
          ) : null}
        </>
      )}
      <TuiFooterBar
        actions={view === "list"
          ? [{ key: "↑↓/jk", desc: "nav" }, { key: "←→/hl", desc: "tabs" }, { key: "/", desc: "search" }, { key: "s", desc: "sort" }, { key: "r", desc: "refresh" }, { key: "v", desc: "board view" }, { key: "Enter", desc: "report" }, { key: "o", desc: "url" }, { key: "c", desc: "change" }, { key: "?", desc: "help" }]
          : [{ key: "↑↓←→/hjkl", desc: "nav" }, { key: "H/L", desc: "move card" }, { key: "v", desc: "list view" }, { key: "?", desc: "help" }]}
        system={[{ key: "Esc", desc: "back" }, { key: "q", desc: "quit" }]} />
    </div>
  );

  return help ? <HelpOverlay title="Pipeline" categories={PIPELINE_HELP} backdrop={screen} /> : screen;
}

Object.assign(window, { PipelineScreen });
