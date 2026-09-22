// The "New User? Start Here!" wizard and the frame a script runs inside.
// Both are transcribed from scripts/bootstrap_menu.py and cli_art.py's
// display_compact_banner / display_execution_footer.
const { CliModeBar, CliMenu, CliStatusTable, CliFooterBar, TuiPanel, Toast } = window.ResumeBuilderDesignSystem_2d03b1;

// Stage labels are verbatim from bullet_bank_menu.STAGES — the wizard and
// the bullet-bank menu run the same six scripts and must name them the
// same way. Steps 0 and 0.5 use bootstrap_menu._build_choices()'s
// plain-language wording, not the internal "Phase 0" sequencing.
const ONBOARDING_ROWS = [
  { label: "Upload Your Documents", status: "Up to date", detail: "11 document(s) processed" },
  { label: "Draft Your Profile", status: "In progress", detail: "profile.yml written, cv.md not yet drafted" },
  { label: "Audit Bullet Bank (Score Quality)", status: "Never run", detail: "checkpoint at bullet 40/212 -- resumable" },
  { label: "Cluster & Classify Bullets", status: "Never run", detail: "" },
  { label: "Rewrite Weak Bullets", status: "Never run", detail: "" },
  { label: "Re-Audit Keepers", status: "Never run", detail: "" },
  { label: "Score Hidden Gems", status: "Never run", detail: "" },
  { label: "Embed Bullet Bank (Final Step)", status: "Locked", detail: "finish Step 5 (score hidden gems) first" },
];

const ONBOARDING_GROUPS = [{
  items: [
    { icon: "▶", label: "Express Auto-Pilot (Recommended)", hint: "Sets up your profile & accomplishment vault in 2 minutes automatically so you can start applying!" },
    { icon: "↥", label: "Upload Your Documents", hint: "extract achievements from uploaded files" },
    { icon: "◉", label: "Draft Your Profile", hint: "identity, profile.yml, cv.md draft" },
    { icon: "◈", label: "1. Audit Bullet Bank (Score Quality)", hint: "score every bullet for strength and evidence" },
    { icon: "◈", label: "2. Cluster & Classify Bullets", hint: "group by theme and role track" },
    { icon: "◈", label: "3. Rewrite Weak Bullets", hint: "queue and rewrite everything under the bar" },
    { icon: "◈", label: "4. Re-Audit Keepers", hint: "re-score what survived the rewrite" },
    { icon: "◈", label: "5. Score Hidden Gems", hint: "surface strong bullets the first pass missed" },
    { icon: "◈", label: "6. Embed Bullet Bank (Final Step)", hint: "build the vector index tailoring reads" },
    { icon: "❮", label: "Back to Main Menu", back: true },
  ],
}];

function CliOnboarding({ onBack, onRun }) {
  const items = ONBOARDING_GROUPS[0].items;
  const [cursor, setCursor] = useCursor(items.length, (i) => {
    if (items[i].back) onBack();
    else onRun && onRun();
  }, onBack);
  return (
    <>
      <CliModeBar screen="PROFILE ONBOARDING WIZARD" mode="Resumable — every step remembers where it stopped" />
      <div style={{ height: 21 }}></div>
      <CliStatusTable title="Onboarding Progress" rows={ONBOARDING_ROWS} />
      <div style={{ height: 21 }}></div>
      <ScreenTitle>New User Setup:</ScreenTitle>
      <CliMenu groups={ONBOARDING_GROUPS} cursor={cursor} onSelect={(i) => { setCursor(i); items[i].back && onBack(); }} hook={false} />
      <div style={{ height: 21 }}></div>
      <CliFooterBar variant="nav" />
    </>
  );
}

// What a running script looks like: compact banner frozen at the top, the
// execution footer frozen at the bottom, and the script's own output
// scrolling in the region between them. Stage lines are literal and
// numbered "Stage N of 8"; notices are icon-prefixed and say what to do.
function CliExecution({ onBack }) {
  React.useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onBack(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);
  const line = { whiteSpace: "pre-wrap" };
  return (
    <>
      <CliModeBar screen="ONBOARDING | EXPRESS AUTO-PILOT" />
      <div style={{ height: 21 }}></div>
      <div style={{ color: "var(--tui-text)", fontFamily: "var(--font-mono)", lineHeight: "var(--tui-line-height)", paddingLeft: 12 }}>
        <div style={line}>Stage 1 of 8: Processing source documents...</div>
        <div style={{ ...line, color: "var(--tui-subtext)" }}>    11 document(s) processed · 212 achievements extracted</div>
        <div style={{ height: 21 }}></div>
        <div style={line}>Stage 2 of 8: Drafting your profile (identity, tags, cv.md)...</div>
        <div style={{ height: 21 }}></div>
        <div style={line}>Stages 3-8: Running the six-stage bullet bank pipeline (unattended)...</div>
        <div style={{ ...line, color: "var(--tui-subtext)" }}>    ▏▎▍▌▋▊▉█ Stage 4 of 8 · Re-Audit Keepers</div>
        <div style={{ height: 21 }}></div>
        {/* A no-op is a yellow notice with no "Error:" prefix — this is an
            unavailable action, not a failure. Name the exact file: the
            path is profile-scoped and a new user cannot guess it. */}
        <TuiPanel variant="warning" style={{ padding: "4px 21px", display: "inline-block" }}>
          <span style={{ color: "var(--tui-yellow)", fontWeight: 700 }}>⚠  </span>
          <span>Express setup needs a Gemini API key and this profile doesn't have one yet.</span>
          <div style={{ color: "var(--tui-subtext)", paddingLeft: 24 }}>Key file: profiles/morgan/.env</div>
          <div style={{ color: "var(--tui-subtext)", paddingLeft: 24 }}>Free keys: <a href="https://aistudio.google.com/apikey">https://aistudio.google.com/apikey</a></div>
        </TuiPanel>
        <div style={{ height: 21 }}></div>
        <div style={{ ...line, color: "var(--tui-green)", fontWeight: 700 }}>✓ All done! Express setup complete. Your profile and bullet bank are fully prepared!</div>
      </div>
      <div style={{ height: 21 }}></div>
      {/* Onboarding completing is one of the four moments that earns
          confetti — everything before this point in the run is routine
          progress and gets none. */}
      <Toast celebrate message="Onboarding complete — your profile and bullet bank are ready." />
      <CliFooterBar variant="execution" />
    </>
  );
}
