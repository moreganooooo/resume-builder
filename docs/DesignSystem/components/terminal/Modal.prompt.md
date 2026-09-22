Centred dialog at 80% width (cap 100 columns, floor 40). Used for the `?` help overlay and confirmations.

```jsx
<Modal variant="focus" title="Pipeline Help" footer="? / Esc / q close help" backdrop={screen}>
  …categorised bindings…
</Modal>
```

No blur and no alpha scrim — the background is desaturated to Overlay gray instead.
