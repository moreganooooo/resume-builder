The persistent keybinding bar. Three visual tiers so the primary action stays findable in a dense line.

```jsx
<TuiFooterBar
  primary={[{ key: "Tab", desc: "Category" }]}
  actions={[{ key: "↑↓", desc: "Select" }, { key: "/", desc: "Search" }]}
  system={[{ key: "Esc", desc: "Back" }, { key: "q", desc: "Quit" }]} />
```

Descriptions are lower case and terse (`nav`, `sort`, `refresh`). The wordmark always sits flush right.
