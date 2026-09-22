The resume canvas. Wrap every print composition in it — it carries the 8.5in cap, the 1.15 line-height and the ligature kill-switch.

```jsx
<PrintPage><PrintHeader … /><PrintSection …>…</PrintSection></PrintPage>
```

Never add colour inside it. Never remove the ligature settings: pypdf and pdfminer extract "ﬁ" verbatim and ATS keyword matching fails.
