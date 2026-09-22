export interface ScrollIndicatorProps {
  /** First visible line index. */
  offset?: number;
  /** How many lines fit in the viewport. */
  visible?: number;
  /** Total lines in the document. When total <= visible the rail hides and the readout says "all". */
  total?: number;
  /** Fixed rail height (CSS length). Omit to fill the parent. */
  height?: string | number;
  style?: React.CSSProperties;
}
export declare function ScrollIndicator(props: ScrollIndicatorProps): JSX.Element;
