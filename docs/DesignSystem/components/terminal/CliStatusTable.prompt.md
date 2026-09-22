The resumable progress table — every multi-stage flow (onboarding, bullet bank) opens with one, so a user can see where they stopped.

```jsx
<CliStatusTable title="Onboarding Progress" rows={[
  { label: "Upload Your Documents", status: "Up to date", detail: "11 document(s) processed" },
  { label: "Draft Your Profile", status: "Locked", detail: "finish Step 0 (ingestion) first" },
  { label: "Audit Bullet Bank", status: "Never run", detail: "" },
]} />
```

Status is a closed set of four: `Up to date` (Green), `In progress` (Blue), `Never run` (Subtext), `Locked` (Yellow). Each pairs its colour with a glyph, so the state survives a monochrome terminal.

Two rules carry over from the source:
- **The detail column says why.** `3/11 processed (8 pending)`, `checkpoint at bullet 40/212 -- resumable`, `finish Step 0 (ingestion) first`. A `Locked` row without a reason is a bug.
- **Labels match the menu verbatim.** The row that reports a stage and the row you click to run it must use the same words. `showNumbers` stays off for first-time users — row order carries the sequence, and "Stage 0.5" is internal sequencing.
