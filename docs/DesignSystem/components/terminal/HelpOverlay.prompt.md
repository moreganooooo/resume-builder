The `?` keybinding reference. Bindings are per-screen: the same letter legitimately does different things on Jobs and Pipeline, so never share one list.

```jsx
<HelpOverlay title="Pipeline" categories={[
  { label: "Navigation", bindings: [{ key: "↑ ↓ / j k", desc: "Move selection" }] },
  { label: "Exit", bindings: [{ key: "q", desc: "Quit dashboard" }] },
]} />
```

Category order in the product: Navigation, Actions, View, Filters, Exit.
