export interface CliModeBarProps {
  /** Product mark on the left. Default "RESUME BUILDER". */
  product?: string;
  /** Active screen, in caps. */
  screen: string;
  /** Execution-mode note. Default "Active Script Execution Mode". */
  mode?: string;
}

/** Compact CLI header for in-script screens: product | screen | mode. */
export declare function CliModeBar(props: CliModeBarProps): JSX.Element;
