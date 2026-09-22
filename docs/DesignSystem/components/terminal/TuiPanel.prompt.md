The bordered terminal box every pane is made of. Border colour carries focus state; never add a shadow.

```jsx
<TuiPanel variant="active" style={{ height: 420 }}>…rows…</TuiPanel>
<TuiPanel variant="idle" pad="detail">…detail content…</TuiPanel>
```

`active` (blue) is the focused sidebar list, `focus` (mauve) is the help overlay, `warning` (peach) is the too-small-viewport card. `idle` (overlay) is everything else.
