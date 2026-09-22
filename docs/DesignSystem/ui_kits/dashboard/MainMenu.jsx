const { TuiHeaderBar, TuiFooterBar, MenuList, StarfieldPane } = window.ResumeBuilderDesignSystem_2d03b1;

function MainMenu({ onOpen, profile }) {
  const [active, setActive] = React.useState(0);
  const items = [
    { icon: "pipeline", title: "Pipeline", desc: "Applications, as a list or a board" },
    { icon: "progress", title: "Progress", desc: "Where things stand: funnel & conversion" },
    { icon: "report", title: "Insights", desc: "What's working: sources, trends, streaks" },
    { icon: "jobs", title: "Jobs", desc: "Browse & Manage Jobs" },
    { icon: "search", title: "Knowledge Base", desc: "Claims, metrics & skills tools" },
    { icon: "build", title: "Documents", desc: "Batch runs, recruiter resume & polish" },
    { icon: "quit", title: "Exit", desc: "Leave the dashboard" },
  ];  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* One profile identifier, not two. The old badge printed the
          profile name twice because both slots read profile.name; the
          role is the half that actually tells you something. */}
      <TuiHeaderBar icon="menu" title="✦ MAIN MENU ✧" gradient="menu" iconColor="var(--tui-text)"
        info={<span><span style={{ color: "var(--tui-subtext)" }}>◉ </span>{profile.name}<span style={{ color: "var(--tui-overlay)" }}>{" · "}</span><span style={{ color: "var(--tui-subtext)" }}>{profile.role}</span></span>} />
      <div style={{ background: "var(--tui-surface)", color: "var(--tui-text)", padding: "0 var(--pad-h)" }}>
        Review And Triage Your Job Search — The resume CLI Builds
      </div>
      {/* The menu occupies a column; the rest of the screen is empty, so
          the starfield fills THAT rather than sitting behind the list —
          stars under letters read as noise, not texture. */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: "0 0 auto", padding: "21px 0 0 0" }}>
          <MenuList items={items} active={active}
            onSelect={(i) => { setActive(i); onOpen(items[i].title); }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <StarfieldPane card={false} density={0.03} />
        </div>
      </div>
      <TuiFooterBar brand="resume-builder"
        actions={[{ key: "←↑↓→", desc: "navigate" }, { key: "↩", desc: "select" }, { key: "1-5", desc: "jump" }, { key: "?", desc: "help" }]}
        system={[{ key: "q", desc: "quit" }]} />
    </div>
  );
}

Object.assign(window, { MainMenu });
