const { CliBanner, TuiPanel, CliMenu } = window.ResumeBuilderDesignSystem_2d03b1;

const PLAYBOOK = [
  ["✥", "var(--tui-blue)", "STEP 1: Find & Pick High-Fit Roles", [
    "Run 'Find Jobs' -> 'Scan for New Jobs' (or paste a job link directly).",
    "The AI scores fit automatically so you never waste energy on low-odds roles.",
  ]],
  ["▶", "var(--tui-green)", "STEP 2: 1-Click Tailor & Build", [
    "Select 'Build Documents' -> 'Build Full Application Package'.",
    "Generates an ATS-optimized PDF resume and tailored cover letter in seconds.",
  ]],
  ["▪", "var(--tui-mauve)", "STEP 3: Apply & Track Effortlessly", [
    "Open 'Command Center' (the Career Dashboard) to review and submit.",
    "Keep track of applications, interview dates, and reminders without stress.",
  ]],
];

const SHORTCUTS = [
  ["Getting started", [
    ["resume", "launch the interactive menu (aliases: rb, jobkit)"],
    ["resume bootstrap", "new-user setup: ingest documents, draft your profile, build the bullet bank"],
    ["resume quickstart", "setup check for a new profile or machine; asks for a missing Gemini API key"],
    ["resume --profile NAME <command>", "run any command against another profile, for this one command only"],
    ["resume --version", "print the installed version"],
    ["resume activate", "cd into the project and activate the venv (stays active in this shell)"],
    ["resume cd", "just cd into the project"],
    ["resume help", "show this cheat sheet"],
  ]],
  ["Find jobs", [
    ["resume scan", "pull new postings into jds/ (verifies each is actually live via headless browser by default)"],
    ["resume scan --source jobright", "pull from just one source (jobright, linkedin, indeed, boards, ats); repeatable"],
    ["resume scan --no-verify", "skip the liveness check on new postings (faster, but stale listings may slip through)"],
    ["resume discover-employers", "find local employers with public ATS boards (dry run; --apply to track them)"],
    ["resume liveness", "check every pending JD's posting URL, move expired ones out (--refresh: recheck all)"],
    ["resume location enrich", "look up office addresses for commute filtering (--all, --limit N, --allow-search-backup)"],
    ["resume dedupe", "find duplicate pending jobs across sources (dry run; --apply to archive them)"],
    ["resume reconcile", "sync job statuses in the database to their folders (dry run; --apply to fix)"],
  ]],
  ["Score jobs", [
    ["resume evaluate", "score every pending JD at once"],
    ["resume evaluate --refresh", "re-score every pending JD, including ones already scored"],
    ["resume evaluate jds/x.txt", "score one JD's fit (go/no-go) without building a resume"],
    ["resume compare A B", "side-by-side comparison of two jobs (IDs or file paths)"],
    ["resume strategy", "application strategy coaching (--jd for one job)"],
  ]],
  ["Build documents", [
    ["resume run", "tailor+render every pending JD in jds/ (batch mode)"],
    ["resume run jds/x.txt", "tailor+render one specific JD file"],
    ["resume run --pick", "interactively select which pending JD(s) to tailor"],
    ["resume tailor jds/x.txt", "same as `resume run jds/x.txt`"],
    ["resume package jds/x.txt", "full application: resume + cover letter, after liveness and fit checks"],
    ["resume build jds/x.txt", "same as `resume package`"],
    ["resume package --pick", "package several pending JDs (--force: build even if scored Skip)"],
    ["resume package --referral \"Name, relation\"", "name a referral contact in the cover letter (also works on coverletter)"],
    ["resume coverletter jds/x.txt", "generate + render a cover letter for one JD"],
    ["resume coverletter --pick", "interactively select which pending JD(s) to generate a cover letter for"],
    ["resume polish", "interactively polish an already-generated resume/cover letter"],
    ["resume sample", "QA smoke test: build a sample resume + cover letter from the fixture JD"],
    ["resume recruiter", "build one role-agnostic resume for a staffing-agency meeting (no specific opening)"],
  ]],
  ["Track and research", [
    ["resume dashboard", "open the Career Dashboard (browse jobs, pipeline, follow-ups)"],
    ["resume stats", "pipeline insights (--platform, --companies, --scatter, --heatmap, --radar, --funnel)"],
    ["resume funnel-drilldown", "where applications stall between stages"],
    ["resume timeline JOB", "one application's full history (job ID or search text)"],
    ["resume agency-view", "staffing agencies you've dealt with and their ghost rates"],
    ["resume rag \"query\"", "search your bullet bank, stories, and knowledge docs by meaning"],
    ["resume evidence list", "show all interview stories and negotiation points"],
    ["resume evidence stories", "browse interview (STAR) stories (--archetype, --tag, -q)"],
    ["resume evidence negotiate", "browse negotiation talking points (--category, -q)"],
  ]],
  ["Maintenance", [
    ["resume doctor", "check dependencies/assets/config, then run the test suite"],
    ["resume doctor --skip-tests", "same, but skip the (slower) test-suite run"],
    ["resume verify-sync", "check Syncthing folders, ignore rules, and database state"],
    ["resume test", "run the full test suite (compact: dots + summary)"],
    ["resume test -v", "same, but lists every test by name"],
    ["resume test -vv", "same, but shows the app's own logging too"],
    ["resume scan-stream", "live viewer for scan progress events (internal; reads from a pipe)"],
  ]],
];

function CliHelp({ onBack }) {
  React.useEffect(() => {
    const onKey = (e) => { if (e.key === "Enter" || e.key === "Escape") onBack(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);

  return (
    <>
      <CliBanner lines={window.BANNER_LINES} />
      <div style={{ height: 21 }}></div>
      <TuiPanel variant="focus" style={{ padding: "4px 21px" }}>
        <span style={{ color: "var(--tui-mauve)" }}>✦ </span>
        Did you know? Running low on time? Try 'Express Setup (Auto-pilot)' — it ingests your source files, constructs your bullet bank, and builds a customized resume in a single click!
      </TuiPanel>
      <div style={{ height: 21 }}></div>
      <window.ScreenTitle>What would you like to do?</window.ScreenTitle>
      <CliMenu cursor={-1} groups={[{ items: window.HOME_SUMMARY }]} />
      <div style={{ height: 21 }}></div>

      <TuiPanel variant="focus" title="✦ 3-STEP JOB HUNT PLAYBOOK ✦" style={{ padding: "18px 21px 14px" }}>
        {PLAYBOOK.map(([icon, color, title, bullets], i) => (
          <div key={title} style={{ marginTop: i ? 14 : 0 }}>
            <div style={{ color, fontWeight: 700 }}>{icon} {title}</div>
            {bullets.map((b) => (
              <div key={b} style={{ paddingLeft: 21 }}><span style={{ color: "var(--tui-subtext)" }}>• </span>{b}</div>
            ))}
          </div>
        ))}
      </TuiPanel>
      <div style={{ height: 21 }}></div>

      <TuiPanel variant="focus" title="resume-builder shortcuts" style={{ padding: "18px 21px 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "400px 1fr", color: "var(--tui-mauve)", fontWeight: 700, borderBottom: "1px solid var(--tui-overlay)", paddingBottom: 4 }}>
          <span>Command</span><span>What it does</span>
        </div>
        {SHORTCUTS.map(([section, rows]) => (
          <div key={section} style={{ paddingTop: 14 }}>
            <div style={{ color: "var(--tui-blue)", fontWeight: 700 }}>{section}</div>
            {rows.map(([cmd, desc]) => (
              <div key={cmd} style={{ display: "grid", gridTemplateColumns: "400px 1fr", gap: "8.4px" }}>
                <span style={{ color: "var(--tui-text)" }}>{cmd}</span>
                <span style={{ color: "var(--tui-subtext)", textWrap: "pretty" }}>{desc}</span>
              </div>
            ))}
          </div>
        ))}
      </TuiPanel>
      <div style={{ height: 21 }}></div>
      <div style={{ color: "var(--tui-overlay)", paddingLeft: 12 }}>Press Enter to return to the menu...</div>
    </>
  );
}

Object.assign(window, { CliHelp });
