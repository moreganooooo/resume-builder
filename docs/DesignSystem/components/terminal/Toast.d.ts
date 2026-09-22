export interface ToastItem {
  /** One line. If it needs two, it is a panel, not a toast. */
  text: string;
  /** success/info auto-dismiss; warning/error persist until a keypress. */
  tone?: "success" | "error" | "warning" | "info";
}
export interface ToastProps {
  /** Newest first. Only the first three render. */
  items?: ToastItem[];
  /** Count collapsed into the "+N earlier" line. */
  overflow?: number;
  style?: React.CSSProperties;
}
/** tea.Printf's above-the-program output as a bottom-right stack. Reports what already happened; never asks for a decision. */
export declare function Toast(props: ToastProps): JSX.Element;
