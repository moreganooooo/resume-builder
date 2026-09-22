export interface TuiHeaderBarProps {
  /** Glyph name, e.g. "pipeline" | "jobs" | "progress". */
  icon?: string;
  /** Usually wrapped in sparkles: "✦ CAREER PIPELINE ✧". */
  title: string;
  /** One of the four shipped title pairs — prefer this over from/to. */
  gradient?: "pipeline" | "jobs" | "progress" | "menu";
  /** Escape hatch. Token names ("--tui-blue") preferred over raw hexes. */
  from?: string;
  to?: string;
  iconColor?: string;
  /** Right-hand readout: counts, avg score, active filters. */
  info?: React.ReactNode;
  /** Rendered immediately after the title, left-aligned — e.g. the profile badge. */
  after?: React.ReactNode;
}
export declare function TuiHeaderBar(props: TuiHeaderBarProps): JSX.Element;
