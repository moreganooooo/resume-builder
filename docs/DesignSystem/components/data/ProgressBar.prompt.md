The determinate work bar. Three rows thick for `tailor`; one row everywhere else.

```jsx
<ProgressBar value={62} thickness={3} label="Tailoring resume... (esc to cancel)" />
<ProgressBar mode="indeterminate" width={30} label="Scanning boards…" />
```

The fill runs Peach → Mauve → Teal, the same ramp as the thinking gradient, so a running bar and a running LLM call read as one activity. The leading edge resolves to eighth-blocks (`▏▎▍▌▋▊▉`) rather than snapping a whole cell.

**Never fake a percent.** `mode="indeterminate"` exists precisely so work without real step signal gets a travelling band and no number. A determinate bar is a promise that the number means something.
