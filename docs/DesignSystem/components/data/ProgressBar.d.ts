export interface ProgressBarProps {
  value?: number;
  max?: number;
  /** Width in terminal cells. */
  width?: number;
  /** Rows of block. 3 for `tailor`, the one action with real step signal; 1 otherwise. */
  thickness?: 1 | 2 | 3;
  /** indeterminate renders a travelling band and no percent — never fake a number. */
  mode?: "determinate" | "indeterminate";
  label?: React.ReactNode;
  showPercent?: boolean;
}
export declare function ProgressBar(props: ProgressBarProps): JSX.Element;
