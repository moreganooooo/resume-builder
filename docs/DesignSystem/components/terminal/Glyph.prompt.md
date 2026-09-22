One character from the product's own icon table — use this instead of hardcoding code points, and never use an emoji.

```jsx
<Glyph name="location" color="var(--tui-sky)" /> On-site · 6.2 mi
```

Names mirror `scripts/theme.py`: success, error, warning, hint/gem, search, skip, location, filter, menu, jobs, pipeline, progress, report, profile, external, prev, next, quit. An unknown name renders verbatim, so `<Glyph name="★" />` also works.
