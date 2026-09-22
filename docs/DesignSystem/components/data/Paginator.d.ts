export interface PaginatorProps {
  /** Zero-based current page. */
  page?: number;
  pages?: number;
  /** Rows per page — drives the "1–20 of 64" range readout. */
  perPage?: number;
  /** Total rows across all pages. Omit to hide the range readout. */
  total?: number;
  style?: React.CSSProperties;
}
export declare function Paginator(props: PaginatorProps): JSX.Element;
