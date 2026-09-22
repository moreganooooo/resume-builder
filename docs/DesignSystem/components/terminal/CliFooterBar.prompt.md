The bottom-row footer for any script screen — swap `variant` when execution starts, never leave the nav keys showing while a script runs.

```jsx
<CliFooterBar variant="nav" />
<CliFooterBar variant="execution" />
```

Both are pinned to the last terminal row and stay there: the script's own output scrolls in the region between the compact banner and this bar, never over it. Keys are coloured by consequence — Blue moves, Green commits, Red stops.
