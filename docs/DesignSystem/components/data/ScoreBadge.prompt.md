An interview-probability score with its tier glyph. Use it anywhere a score appears — colour alone is never allowed to carry the tier.

```jsx
<ScoreBadge score={4.4} suffix="/5" />
<ScoreBadge score={null} />   {/* renders the muted "not evaluated" dash */}
```

Bands: ✓ ≥ 4.2 green/bold · ✦ ≥ 3.8 yellow · ★ ≥ 3.0 text · ⊘ below red. `tierOf(score)` is exported if you need the colour directly.
