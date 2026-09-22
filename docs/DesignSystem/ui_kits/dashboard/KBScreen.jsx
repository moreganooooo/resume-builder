const { TuiPanel, TuiFooterBar, TuiTabs, GlamourDoc, HelpOverlay, CliMenu } = window.ResumeBuilderDesignSystem_2d03b1;

const MODES = ["Explore", "Skills"];

// Moved from Settings & Upkeep: anything that surfaces what the program
// found rather than changing how it behaves belongs beside the knowledge
// it's about, not in configuration. Settings keeps the doctor checks and
// anything that changes behavior going forward.
const SKILLS_GROUPS = [
  { label: "REVIEW", items: [
    { icon: "◉", label: "View & Manage Profile Skills", hint: "Your declared skill set — add, remove, or adjust confidence" },
  ] },
  { label: "SCAN", items: [
    { icon: "◈", label: "Scan Pending Pipeline for Skills to Verify", hint: "Finds skills the pipeline references that aren't backed by evidence yet" },
    { icon: "◈", label: "Recompute Stale Skill Gap Matrices", hint: "Refreshes per-job matrices that predate a profile change" },
  ] },
  { label: "DISCOVER", items: [
    { icon: "⌖", label: "Discover Local Employers with ATS Boards", hint: "Finds companies near you that post through a scannable board" },
    { icon: "⌖", label: "Enrich Local Company Addresses", hint: "Fills in missing addresses so distance and commute can be computed" },
  ] },
];

const CATS = ["All", "Tools", "Metrics", "Facts", "Projects"];

const KB_HELP = [
  { label: "Navigation", bindings: [{ key: "↑ ↓ / j k", desc: "Move selection" }, { key: "Tab", desc: "Next category" }, { key: "1–5", desc: "Jump to a category" }] },
  { label: "Search", bindings: [{ key: "/", desc: "Filter by title, body or category" }, { key: "Esc", desc: "Clear the filter" }] },
  { label: "Exit", bindings: [{ key: "Esc", desc: "Back to Main Menu" }, { key: "q", desc: "Quit dashboard" }] },
];

function kbMarkdown(it) {
  return [
    "### " + it.title,
    "",
    "- **Category:** " + it.cat,
    "- **Confidence:** " + it.confidence,
    "- **Evidence Count:** " + it.evidence,
    "",
    "**Usage Notes:** " + it.usage,
    "",
    "**References:** " + it.refs,
    "",
    it.body,
  ].join("\n");
}

function KBScreen({ items, profile, onBack }) {
  const [mode, setMode] = React.useState(0);
  const [skillsCursor, setSkillsCursor] = React.useState(0);
  const [cat, setCat] = React.useState("All");
  const [cursor, setCursor] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [searching, setSearching] = React.useState(false);
  const [help, setHelp] = React.useState(false);

  const vis = items.filter((it) => (cat === "All" || it.cat === cat) &&
    (it.title + it.body + it.cat).toLowerCase().includes(query.toLowerCase()));
  const sel = vis[Math.min(cursor, vis.length - 1)];

  React.useEffect(() => {
    const onKey = (e) => {
      if (help) { if (["?", "Escape", "q"].includes(e.key)) setHelp(false); return; }
      if (e.key === "Tab" && e.shiftKey) { e.preventDefault(); setMode((m) => (m + 1) % MODES.length); return; }
      if (mode === 1) {
        const flat = SKILLS_GROUPS.flatMap((g) => g.items);
        if (e.key === "j" || e.key === "ArrowDown") setSkillsCursor((c) => Math.min(c + 1, flat.length - 1));
        else if (e.key === "k" || e.key === "ArrowUp") setSkillsCursor((c) => Math.max(c - 1, 0));
        else if (e.key === "Escape") onBack();
        return;
      }
      if (searching) {
        if (e.key === "Escape") { setSearching(false); setQuery(""); }
        else if (e.key === "Enter") setSearching(false);
        else if (e.key === "Backspace") setQuery((q) => q.slice(0, -1));
        else if (e.key.length === 1) setQuery((q) => q + e.key);
        e.preventDefault(); return;
      }
      if (e.key === "/") setSearching(true);
      else if (e.key === "?") setHelp(true);
      else if (/^[1-5]$/.test(e.key)) { setCat(CATS[Number(e.key) - 1]); setCursor(0); }
      else if (e.key === "Tab") { e.preventDefault(); setCat((c) => CATS[(CATS.indexOf(c) + 1) % CATS.length]); setCursor(0); }
      else if (e.key === "j" || e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, vis.length - 1));
      else if (e.key === "k" || e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [searching, help, vis.length, onBack]);

  const screen = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)", color: "var(--tui-text)" }}>
      <div style={{ padding: "0 8.4px", display: "flex", justifyContent: "space-between" }}>
        <span style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>✦ KNOWLEDGE BASE</span>
        <span style={{ color: "var(--tui-subtext)" }}>{items.length} total assets</span>
      </div>
      <TuiTabs active={mode} onChange={setMode} tabs={MODES.map((label) => ({ label: label.toUpperCase() }))} />
      {mode === 1 ? (
        <div style={{ flex: 1, padding: "21px 8.4px", overflowY: "auto" }}>
          <CliMenu groups={SKILLS_GROUPS} cursor={skillsCursor} onSelect={setSkillsCursor} />
        </div>
      ) : (
      <>
      <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8.4px" }}>
        <span style={{ display: "flex" }}>
          {CATS.map((c, i) => (
            <button key={c} onClick={() => { setCat(c); setCursor(0); }}
              style={{
                all: "unset", cursor: "pointer", padding: "0 8.4px", fontFamily: "inherit", fontSize: "inherit",
                fontWeight: c === cat ? 700 : 400,
                background: c === cat ? "var(--tui-mauve)" : "transparent",
                color: c === cat ? "var(--tui-base)" : "var(--tui-subtext)",
              }}>{(i + 1) + ":" + c}</button>
          ))}
        </span>
        <span style={{ color: searching ? "var(--tui-peach)" : "var(--tui-subtext)", fontWeight: searching ? 700 : 400 }}>
          {searching ? " Search: " + query + "█" : query ? " Filter: '" + query + "'" : ""}
        </span>
      </div>
      <div>&nbsp;</div>
      <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0, padding: "0 8.4px 8px" }}>
        <TuiPanel variant="idle" style={{ flex: "0 0 33%", borderColor: "var(--tui-surface)", overflow: "hidden" }}>
          {vis.length === 0 ? <div style={{ color: "var(--tui-overlay)", fontStyle: "italic" }}>No matching items found.</div> : null}
          {vis.map((it, i) => (
            <div key={it.title} onClick={() => setCursor(i)}
              style={{
                cursor: "pointer", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                fontWeight: i === cursor ? 700 : 400,
                background: i === cursor ? "var(--tui-sky)" : "transparent",
                color: i === cursor ? "var(--tui-base)" : "var(--tui-text)",
              }}>
              {(i === cursor ? "▶ " : "  ")}
              <span style={{ color: i === cursor ? "var(--tui-base)" : "var(--tui-overlay)" }}>[{it.cat.slice(0, 4)}]</span> {it.title}
            </div>
          ))}
        </TuiPanel>
        <TuiPanel variant="idle" style={{ flex: 1, borderColor: "var(--tui-surface)", overflow: "hidden" }}>
          {sel ? <GlamourDoc source={kbMarkdown(sel)} />
               : <div style={{ color: "var(--tui-overlay)", fontStyle: "italic" }}>Select an item to view verified details and claims.</div>}
        </TuiPanel>
      </div>
      </>
      )}
      <div>&nbsp;</div>
      <TuiFooterBar primary={mode === 1 ? [{ key: "shift+Tab", desc: "Mode" }] : [{ key: "Tab", desc: "Category" }]}
        actions={[{ key: "↑/↓", desc: "Select" }, { key: "shift+Tab", desc: "Explore/Skills" }, { key: "/", desc: "Search" }, { key: "?", desc: "Help" }]}
        system={[{ key: "Esc", desc: "Back" }, { key: "q", desc: "Quit" }]} />
    </div>
  );

  return help ? <HelpOverlay title="Knowledge Base" categories={KB_HELP} backdrop={screen} /> : screen;
}

Object.assign(window, { KBScreen });
