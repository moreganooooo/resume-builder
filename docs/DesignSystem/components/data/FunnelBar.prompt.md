Horizontal analytics bar for the Progress screen — funnel stages, score buckets, weekly activity, platform yield.

```jsx
{stages.map((s, i) => (
  <FunnelBar key={s.label} label={s.label} count={s.count} max={maxCount}
    pct={i ? s.pct : undefined} color={FUNNEL_COLORS[i]} />
))}
```

Funnel colours run cool → warm across stages. Platform yield uses `glyph="■"` in Mauve. A non-zero count always gets at least one cell.
