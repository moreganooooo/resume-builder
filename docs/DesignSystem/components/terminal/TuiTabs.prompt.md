Filter tabs with live counts and a box-drawing underline.

```jsx
<TuiTabs active={0} onChange={setTab} tabs={[
  { label: "ALL", count: 128 }, { label: "EVALUATED", count: 64 },
  { label: "TOP ≥4", count: 12 }, { label: "LOW <3.5", count: 30 },
]} />
```

Labels stay uppercase. A count that disagrees with the visible list reads as missing data, so compute both from the same predicate.
