The subscore and skill-coverage bar: 15 cells of `▆`, coloured by ratio.

```jsx
<ScoreBar label="Skill overlap" value={4.2} max={5} />
<ScoreBar label="Figma" value={65} max={100} />
```

Thresholds: ≥0.8 green, ≥0.6 blue, ≥0.4 yellow, else subtext; the unfilled remainder is Overlay. Keep the same glyph for filled and empty — differing glyphs make the bar look broken.
