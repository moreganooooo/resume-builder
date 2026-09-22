const { TuiHeaderBar, TuiFooterBar, CliMenu } = window.ResumeBuilderDesignSystem_2d03b1;

// What moved here from the old standalone "Build Documents" menu: only the
// actions that are not about one open role. Tailoring a single role's
// resume happens where that role lives — Jobs and Pipeline both bind [t].
const DOC_GROUPS = [
  { label: "BATCH", items: [
    { icon: "▤", label: "Tailor & Build for All Pending Roles", hint: "Runs the full pipeline unattended over every role awaiting documents" },
  ] },
  { label: "STANDALONE", items: [
    { icon: "●", label: "Generate Recruiter Resume", hint: "No specific role — a general-purpose version for direct recruiter outreach" },
  ] },
  { label: "MAINTENANCE", items: [
    { icon: "⊘", label: "Re-render an Existing Document", hint: "PDF from the saved JSON, no AI — for a template or formatting fix only" },
  ] },
  { label: "REFINE", items: [
    { icon: "✦", label: "Polish a Resume or Cover Letter", hint: "Ask in plain language for an exact wording, layout, or structure change" },
  ] },
];

function DocumentsScreen({ onBack }) {
  const flat = DOC_GROUPS.flatMap((g) => g.items);
  const [cursor, setCursor] = React.useState(0);

  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key === "j" || e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, flat.length - 1));
      else if (e.key === "k" || e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flat.length, onBack]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <TuiHeaderBar icon="jobs" gradient="jobs" title="✦ DOCUMENTS ✧" info="Work that spans roles, or has none" />
      <div style={{ flex: 1, padding: "21px var(--pad-h)", overflowY: "auto" }}>
        <CliMenu groups={DOC_GROUPS} cursor={cursor} onSelect={setCursor} />
      </div>
      <TuiFooterBar actions={[{ key: "↑↓/jk", desc: "nav" }, { key: "Enter", desc: "run" }]} system={[{ key: "Esc", desc: "back" }, { key: "q", desc: "quit" }]} />
    </div>
  );
}

Object.assign(window, { DocumentsScreen });
