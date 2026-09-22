The dashboard's top-level command list.

```jsx
<MenuList active={0} onSelect={setActive} items={[
  { icon: "pipeline", title: "Pipeline", desc: "Career pipeline view" },
  { icon: "jobs", title: "Jobs", desc: "Browse & Manage Jobs" },
]} />
```

Titles are Title Case, descriptions are short fragments. Numeric shortcuts 1–5 map to list order.
