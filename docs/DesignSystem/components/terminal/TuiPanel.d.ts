export interface TuiPanelProps {
  /** idle = overlay border, active = blue (focused list), focus = mauve, warning = peach. */
  variant?: "idle" | "active" | "focus" | "warning";
  /** tight = Padding(0,1) sidebar box; detail = Padding(1,2) detail pane. */
  pad?: "tight" | "detail";
  /** Fill with Surface. Only the empty-state card does this. */
  filled?: boolean;
  /** Legend set into the top border, centred — the CLI status boxes use this. */
  title?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}
export declare function TuiPanel(props: TuiPanelProps): JSX.Element;
