export interface StarfieldPaneProps {
  /** Pin to a fixed character box. Omit to fill the container in cells. */
  cols?: number;
  /** Pin to a fixed character box. Omit to fill the container in cells. */
  rows?: number;
  /** Screen-specific hints; bracketed keys render in Peach. */
  hints?: string[];
  /** Pass "" with no hints for a bare field — e.g. behind a banner. */
  title?: string;
  /** Twinkle at 60ms. Respects prefers-reduced-motion. */
  animate?: boolean;
  /** Render the centred empty-state card. Pass false for a bare field. */
  card?: boolean;
  /** Star fraction. 0.065 is the product's empty pane; go sparser (0.02–0.03) behind content. */
  density?: number;
}
export declare function StarfieldPane(props: StarfieldPaneProps): JSX.Element;
