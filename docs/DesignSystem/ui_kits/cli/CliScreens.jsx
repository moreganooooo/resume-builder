const { CliBanner, CliModeBar, CliMenu, TuiPanel } = window.ResumeBuilderDesignSystem_2d03b1;

const BANNER_LINES = [
  "246 Roles Currently Awaiting Resume Creation · 2 Resumes Customized All-Time",
  "11 Roles Awaiting Evaluation",
];

function KeyHints({ hints }) {
  return (
    <div style={{ display: "flex", gap: "8.4px", color: "var(--tui-subtext)", padding: "8px 0 0 12px", fontFamily: "var(--font-mono)", fontSize: "var(--tui-font-size)", lineHeight: "var(--tui-line-height)" }}>
      {hints.map((h, i) => (
        <React.Fragment key={h[0] + h[1]}>
          {i ? <span style={{ color: "var(--tui-overlay)" }}>•</span> : null}
          <span><span style={{ color: "var(--tui-text)" }}>{h[0]}</span> {h[1]}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

function ScreenTitle({ children }) {
  return <div style={{ color: "var(--tui-mauve)", padding: "0 0 2px 12px" }}>{children}</div>;
}

// Shared arrow-key cursor over a flat item count.
function useCursor(count, onEnter, onBack) {
  const [cursor, setCursor] = React.useState(0);
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowDown" || e.key === "j") setCursor((c) => Math.min(c + 1, count - 1));
      else if (e.key === "ArrowUp" || e.key === "k") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "Enter") onEnter && onEnter(cursor);
      else if (e.key === "Escape") onBack && onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, cursor, onEnter, onBack]);
  return [cursor, setCursor];
}

const HOME_ITEMS = [
  { icon: "✥", label: "Find Jobs", hint: "Search job boards or paste a job link you want to apply for", go: "find" },
  { icon: "✂", label: "Build Documents", hint: "Generate tailored resumes & cover letters for specific roles", go: "build" },
  { icon: "◆", label: "Bullet Bank", hint: "Your master career wins, tailored automatically for each job", go: "bullets" },
  { icon: "▤", label: "Command Center", hint: "Live view of every application — status, interview odds, follow-ups due", go: null },
  { icon: "↥", label: "Drop New Knowledge", hint: "Add new source documents, then choose what to rebuild", go: "knowledge" },
  { icon: "⚙", label: "Settings & Upkeep", hint: "Profile settings, health checks & system updates", go: "settings" },
  { icon: "✦", label: "New User? Start Here!", hint: "Resumable 8-step setup — upload documents, draft your profile, build the bullet bank", go: "onboarding" },
  { icon: "✦", label: "Help", go: "help" },
  { icon: "✕", label: "Exit", go: null },
];

function CliHome({ onOpen }) {
  const [cursor, setCursor] = useCursor(HOME_ITEMS.length, (i) => HOME_ITEMS[i].go && onOpen(HOME_ITEMS[i].go));
  return (
    <>
      <CliBanner lines={BANNER_LINES} />
      <div style={{ height: 21 }}></div>
      {/* A tip, not a paragraph: a labelled lead-in, one sentence, and
          the thing you press set in Peach like every other key in the
          product. The old copy stacked two questions before it said
          anything actionable. */}
      <TuiPanel variant="idle" style={{ padding: "2px 21px" }}>
        <span style={{ color: "var(--tui-mauve)", fontWeight: 700 }}>✦ TIP</span>
        <span style={{ color: "var(--tui-overlay)" }}>{"  │  "}</span>
        <span style={{ color: "var(--tui-subtext)" }}>Ask for an exact wording or layout change in plain language with </span>
        <span style={{ color: "var(--tui-peach)" }}>Polish a Resume or Cover Letter</span>
        <span style={{ color: "var(--tui-subtext)" }}>.</span>
      </TuiPanel>
      <div style={{ height: 21 }}></div>
      <ScreenTitle>What would you like to do?</ScreenTitle>
      <CliMenu groups={[{ items: HOME_ITEMS }]} cursor={cursor} onSelect={(i) => { setCursor(i); HOME_ITEMS[i].go && onOpen(HOME_ITEMS[i].go); }} />
      <KeyHints hints={[["↑", "up"], ["↓", "down"], ["/", "filter"], ["enter", "submit"]]} />
    </>
  );
}

// Banner-topped script screens: a titled grouped menu under the wordmark.
function BannerMenu({ title, groups, onBack }) {
  const flat = groups.flatMap((g) => g.items);
  const [cursor, setCursor] = useCursor(flat.length, (i) => flat[i].back && onBack(), onBack);
  return (
    <>
      <CliBanner lines={BANNER_LINES} />
      <div style={{ height: 14 }}></div>
      <ScreenTitle>{title}</ScreenTitle>
      <CliMenu groups={groups} cursor={cursor} onSelect={(i) => { setCursor(i); flat[i].back && onBack(); }} />
    </>
  );
}

const FIND_GROUPS = [
  { label: "FIND", items: [{ icon: "✥", label: "Scan for New Jobs" }, { icon: "⌸", label: "Add Job Description Manually" }] },
  { label: "SCORE", items: [{ icon: "▤", label: "Evaluate Pending Roles" }, { icon: "✂", label: "Re-score Outdated Evaluations" }] },
  { label: "CLEAN UP", items: [{ icon: "✓", label: "Check Job Posting Liveness" }, { icon: "⊘", label: "Archive Stale Postings" }, { label: "Back", hook: false, back: true }] },
];

const BUILD_GROUPS = [
  { label: "ONE ROLE", items: [
    { icon: "✂", label: "Build Full Application Package (Resume + Cover Letter)" },
    { icon: "▶", label: "Customize Resume for Specific Role(s)" },
    { icon: "⌸", label: "Write Cover Letter for Specific Role(s)" },
    { icon: "▪", label: "Application Answers for a Specific Role" },
  ] },
  { label: "MANY ROLES", items: [{ icon: "▤", label: "Customize Resume for All Pending Roles (Batch Run)" }] },
  { label: "REFINE", items: [
    { icon: "✦", label: "Polish a Resume or Cover Letter With Gemini" },
    { icon: "⊘", label: "Re-render an Existing Document (PDF from JSON, no AI)" },
    { label: "Back", hook: false, back: true },
  ] },
];

const SETTINGS_GROUPS = [
  { label: "YOUR SKILLS", items: [
    { icon: "◆", label: "View & Manage Profile Skills" },
    { icon: "▶", label: "Scan Pending Pipeline for Skills to Verify" },
    { icon: "✓", label: "Refresh Skill Embeddings" },
    { icon: "⚠", label: "Recompute Stale (0%) Skill Gap Matrices" },
  ] },
  { label: "JOB SEARCH PREFERENCES", items: [
    { icon: "⌂", label: "Location & Commute Radius (14068 — 5 mi, hybrid+onsite+remote)" },
    { icon: "▽", label: "Role, Language & Travel Limits (languages: English; travel: up to 0%; types: Full-time, Part-time, Contract / free…" },
    { icon: "✦", label: "Scoring Weights & Preferences (defaults (unedited))" },
  ] },
  { label: "JOB SOURCES", items: [
    { icon: "✥", label: "Manage Scraping, Boards & Search Queries" },
    { icon: "▤", label: "Discover Local Employers with ATS Boards" },
  ] },
  { label: "YOUR VOICE & STORY", items: [
    { icon: "⌸", label: "Writing Voice & Samples" },
    { icon: "↥", label: "Personal Narrative & Story (all filled in)" },
  ] },
  { label: "TEST DOCUMENTS", items: [
    { icon: "✂", label: "Generate Sample Resume + Cover Letter (QA)" },
    { icon: "●", label: "Generate Recruiter Resume (no specific role)" },
  ] },
  { label: "SYSTEM & PROFILES", items: [
    { icon: "⚙", label: "Run Doctor Checks (last run: 2026-09-20)" },
    { icon: "❯", label: "Check for GitHub Updates" },
    { icon: "❮", label: "Manage Profiles (Rename / Delete)" },
    { label: "Back", hook: false, back: true },
  ] },
];

const BULLET_STAGES = [
  ["1", "Audit Bullet Bank (Score Quality)", "Up to date", "(as of 2026-09-04 21:26)"],
  ["2", "Cluster & Classify Bullets", "Up to date", "(as of 2026-09-04 21:26)"],
  ["3", "Rewrite Weak Bullets", "Up to date", "(as of 2026-09-16 20:06)"],
  ["4", "Re-Audit Keepers", "Up to date", "(as of 2026-09-16 20:06)"],
  ["5", "Score Hidden Gems", "Up to date", ""],
  ["6", "Embed Bullet Bank (Final Step)", "Up to date", "(as of 2026-09-16 19:15)"],
  ["–", "Triage Needs-Review Queue", "", "59 row(s) waiting"],
  ["–", "Remove Bullets", "", "41 removed so far"],
  ["–", "Retire Abandoned Rewrite-Queue Bullets", "", "none pending"],
  ["–", "Auto-Rewrite Manual Bullets", "", "empty — nothing queued"],
];

const BULLET_ITEMS = [
  { label: "1. Audit Bullet Bank (Score Quality)", hint: "scores every raw bullet for accuracy, clarity, and impact" },
  { label: "2. Cluster & Classify Bullets", hint: "groups near-duplicate bullets, flags which ones need rewriting" },
  { label: "3. Rewrite Weak Bullets", hint: "rewrites flagged bullets via Gemini until each one passes" },
  { label: "↳ Retire Abandoned Rewrite-Queue Bullets (optional follow-up: clears out bullets that ran out of rewrite attempts witho…" },
  { label: "4. Re-Audit Keepers", hint: "rescores keepers, builds a queue of bullets still needing work" },
  { label: "↳ Auto-Rewrite Manual Bullets (optional follow-up: retries bullets still MANUAL after re-audit through the rewriter aga…" },
  { label: "5. Score Hidden Gems", hint: "flags standout bullets worth surfacing more often" },
  { label: "6. Embed Bullet Bank (Final Step)", hint: "builds the embeddings real resume builds match against, plus the backup model's inde…" },
];

const BULLET_MAINT = [
  { label: "Triage Needs-Review Queue", hint: "routes bullets queued during real resume builds into keepers/rewrite/retired" },
  { label: "Remove Bullets", hint: "deletes bullets from the bank for good — every stage remembers, so a rerun never brings them back" },
  { label: "Back to Main Menu", hook: false, back: true },
];

function CliBulletBank({ onBack }) {
  const groups = [{ label: "Bullet Bank Management:", items: BULLET_ITEMS }, { label: "ONGOING MAINTENANCE (OPTIONAL, RUN ANYTIME)", items: BULLET_MAINT }];
  const flat = BULLET_ITEMS.concat(BULLET_MAINT);
  const [cursor, setCursor] = useCursor(flat.length, (i) => flat[i].back && onBack(), onBack);
  return (
    <>
      <CliModeBar screen="BULLET BANK MANAGEMENT" />
      <div style={{ height: 34 }}></div>
      <TuiPanel variant="focus" title="Bullet Bank Pipeline Status" style={{ padding: "14px 21px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "40px 400px 1fr", color: "var(--tui-mauve)", fontWeight: 700, borderBottom: "1px solid var(--tui-overlay)", paddingBottom: 4, marginBottom: 6 }}>
          <span>#</span><span>Stage</span><span>Status</span>
        </div>
        {BULLET_STAGES.map(([n, stage, status, note]) => (
          <div key={stage} style={{ display: "grid", gridTemplateColumns: "40px 400px 1fr" }}>
            <span style={{ color: "var(--tui-subtext)" }}>{n}</span>
            <span>{stage}</span>
            <span>
              {status ? <span style={{ color: "var(--tui-green)" }}>{status} </span> : null}
              <span style={{ color: "var(--tui-text)" }}>{note}</span>
            </span>
          </div>
        ))}
      </TuiPanel>
      <div style={{ height: 34 }}></div>
      <CliMenu groups={groups} cursor={cursor} onSelect={(i) => { setCursor(i); flat[i].back && onBack(); }} hook={false} />
    </>
  );
}

function CliKnowledge({ onBack }) {
  const [yes, setYes] = React.useState(true);
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") setYes((v) => !v);
      else if (e.key === "y") setYes(true);
      else if (e.key === "n") setYes(false);
      else if (e.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);
  const U = ({ children }) => <span style={{ textDecoration: "underline", color: "var(--tui-text)" }}>{children}</span>;
  return (
    <>
      <CliModeBar screen="KNOWLEDGE BASE UPDATE" />
      <div style={{ height: 34 }}></div>
      <TuiPanel variant="focus" title="Setup Instructions" style={{ padding: "14px 21px" }}>
        <div style={{ textWrap: "pretty" }}>
          Go to your source folder (<U>/Users/morganescott/resume-builder/profiles/morgan/knowledge_base/bootstrap/source_documents</U>) and drop in any documentation related to your job search. Your current resume and LinkedIn profile (exporting your profile as a PDF is perfect — <U>see LinkedIn's instructions here</U>) are a great place to start. You can also consider things like:
        </div>
        <div>&nbsp;</div>
        {["Letters of recommendation", "Public LinkedIn recommendations", "Certifications", "Patents you own (look at you go!)", "Writing samples"].map((s) => (
          <div key={s} style={{ paddingLeft: 21 }}><span style={{ color: "var(--tui-mauve)" }}>✦ </span>{s}</div>
        ))}
        <div>&nbsp;</div>
        <div style={{ fontWeight: 700 }}>Once you're finished, restart this program and click New User again to continue!</div>
      </TuiPanel>
      <div style={{ height: 21 }}></div>
      <div style={{ borderLeft: "2px solid var(--tui-overlay)", paddingLeft: 12 }}>
        <div style={{ color: "var(--tui-mauve)" }}>Pick document(s) now with the file browser instead?</div>
        <div style={{ display: "flex", gap: 21, paddingLeft: 160, paddingTop: 4 }}>
          {[["Yes", true], ["No", false]].map(([label, v]) => (
            <button key={label} onClick={() => setYes(v)} style={{
              all: "unset", cursor: "pointer", padding: "0 12px", fontFamily: "inherit", fontSize: "inherit",
              background: yes === v ? "var(--tui-teal)" : "transparent",
              color: yes === v ? "var(--tui-base)" : "var(--tui-text)",
            }}>{label}</button>
          ))}
        </div>
      </div>
      <KeyHints hints={[["←/→", "toggle"], ["enter", "submit"], ["y", "Yes"], ["n", "No"]]} />
    </>
  );
}

Object.assign(window, { CliHome, BannerMenu, CliBulletBank, CliKnowledge, KeyHints, ScreenTitle, BANNER_LINES, FIND_GROUPS, BUILD_GROUPS, SETTINGS_GROUPS, HOME_SUMMARY: HOME_ITEMS.slice(0, 6) });
