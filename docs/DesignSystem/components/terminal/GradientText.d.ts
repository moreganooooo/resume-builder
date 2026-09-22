export interface GradientTextProps {
  children: React.ReactNode;
  /** One of the four shipped title pairs — prefer this over from/to. */
  gradient?: "pipeline" | "jobs" | "progress" | "menu";
  /** Explicit ramp of 2+ colours/token names. Overrides gradient/from/to. */
  stops?: string[];
  /** Start colour. A token name ("--tui-blue") is preferred over a raw hex. */
  from?: string;
  /** End colour. A token name ("--tui-mauve") is preferred over a raw hex. */
  to?: string;
  /** Space out every character (theme.FormatTrackedHeader). */
  tracked?: boolean;
  bold?: boolean;
}
export declare function GradientText(props: GradientTextProps): JSX.Element;
