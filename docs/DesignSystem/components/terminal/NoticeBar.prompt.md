The one-line status bar above the split pane.

```jsx
<NoticeBar variant="notice" message="No job URL saved for this application" />
<NoticeBar variant="error" message="Gemini request failed — check your API key" />
<NoticeBar variant="banner" message="★ NEXT BEST MOVE: High match at Callahan Creek (4.4) — Press 't' to tailor now!" />
```

A no-op is not a failure: keep the "Error:" prefix for genuine failures only, and always say how to dismiss.
