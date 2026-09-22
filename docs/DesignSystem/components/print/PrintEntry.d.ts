export interface PrintEntryProps {
  /** Role plus industry descriptor, 800 weight. */
  title: string;
  /** Company | Size | Location | Dates — pipe-separated, 800 weight. */
  meta?: React.ReactNode[];
  /** Optional roster line. */
  clients?: React.ReactNode;
  /** Optional one-sentence italic career note. */
  note?: React.ReactNode;
  /** Achievement bullets. Never bold anything inside them. */
  bullets?: React.ReactNode[];
  /** Optional italic craft-area sub-header above the bullets. */
  groupLabel?: string;
}
export declare function PrintEntry(props: PrintEntryProps): JSX.Element;
