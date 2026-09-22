Per-character colour gradient on text — every screen title in the dashboard is one.

```jsx
<GradientText gradient="pipeline">✦ CAREER PIPELINE ✧</GradientText>
```

Established pairs, exported as `TITLE_GRADIENTS` and selected with `gradient="pipeline" | "jobs" | "progress" | "menu"`: Pipeline Blue→Mauve, Jobs Blue→Peach, Progress Peach→Teal, Main Menu Mauve→Blue. `from`/`to` remain as an escape hatch and accept token names (`--tui-blue`) as well as hexes; `stops={[...]}` takes an explicit ramp of three or more.

Jobs and Progress carry a Mauve midpoint. Their endpoints sit on opposite sides of the wheel, and a straight two-stop blend between them passes through a muddy brown — route any wide hue jump through a third stop rather than accepting the grey middle. `tracked` spaces the characters out (`✦  P I P E L I N E  ✧`). Never apply a gradient to a background.
