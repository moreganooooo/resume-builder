export interface NoticeBarProps {
  /** notice = unavailable action (yellow), error = failure (red),
   *  progress = work in flight, banner = the NEXT BEST MOVE line (mauve, bold). */
  variant?: "notice" | "error" | "progress" | "banner";
  message: React.ReactNode;
  /** Override the default dismissal hint; pass "" to remove it. */
  hint?: string;
  children?: React.ReactNode;
}
export declare function NoticeBar(props: NoticeBarProps): JSX.Element;
