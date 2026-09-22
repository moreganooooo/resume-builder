export type StageStatus = "Up to date" | "In progress" | "Never run" | "Locked";
export interface StageRow {
  /** 0, "0.5", 1–6. Internal sequencing — hidden from first-time users. */
  number?: string | number;
  /** Plain-language stage name. Must match the menu row that runs it, verbatim. */
  label: string;
  status: StageStatus;
  /** Why it is in that state, or what it produced. Never blank for a blocked stage. */
  detail?: string;
}
export interface CliStatusTableProps {
  title?: string;
  rows: StageRow[];
  /** Off in the onboarding wizard: row order carries the sequence. */
  showNumbers?: boolean;
}
export declare function CliStatusTable(props: CliStatusTableProps): JSX.Element;
export declare const STAGE_STATUS_COLORS: Record<StageStatus, string>;
