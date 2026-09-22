export interface SidebarRowProps {
  /** Composite / interview-probability score, 0–5. */
  score: number;
  /** Primary name — company. Truncates before the tag does. */
  company: string;
  /** Already-rendered tag node, e.g. <EmploymentTag />. */
  tag?: React.ReactNode;
  /** Role title, optionally with a "  Fit 4.5 / Odds 3.9" suffix. */
  subtitle?: React.ReactNode;
  selected?: boolean;
  onClick?: () => void;
}
export declare function SidebarRow(props: SidebarRowProps): JSX.Element;
