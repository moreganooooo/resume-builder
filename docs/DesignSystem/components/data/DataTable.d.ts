export interface DataTableColumn {
  key: string;
  /** Rendered uppercased in the header. */
  label: string;
  /** Numeric columns right-align; everything else left-aligns. */
  align?: "left" | "right";
  width?: string | number;
  /** Custom cell renderer. */
  render?: (row: any) => React.ReactNode;
  /** Per-row colour override, e.g. score tiers. */
  color?: (row: any) => string;
}
export interface DataTableProps {
  columns?: DataTableColumn[];
  rows?: any[];
  /** Index carrying the ┃ selection bar. */
  cursor?: number;
  /** Key of the sorted column. Exactly one, so the ▲/▼ is unambiguous. */
  sortKey?: string;
  sortDir?: "asc" | "desc";
  onSelect?: (index: number) => void;
  style?: React.CSSProperties;
}
export declare function DataTable(props: DataTableProps): JSX.Element;
