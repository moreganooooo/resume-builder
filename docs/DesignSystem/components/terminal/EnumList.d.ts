export interface EnumListItem {
  text: string;
  /** Trailing Subtext annotation on the same line. */
  note?: string;
  /** check enumerator only: false renders a red ✗ instead of a green ✓. */
  ok?: boolean;
}
export interface EnumListProps {
  items?: Array<string | EnumListItem>;
  /** Enumerators carry meaning: bullet = unordered, arabic = ordered steps, dash = sub-points, check = resolved outcomes, roman = second-level ordered. */
  enumerator?: "bullet" | "arabic" | "dash" | "check" | "roman";
  /** Marker colour. Ignored by `check`, which derives it from `ok`. */
  color?: string;
  style?: React.CSSProperties;
}
/** lipgloss/list: flat sequences with a meaningful enumerator. Use ClusterTree when there is hierarchy. */
export declare function EnumList(props: EnumListProps): JSX.Element;
