export interface HelpBinding { key: string; desc: string }
export interface HelpBarProps {
  /** Short form. At most five are shown, then "? more" is appended. */
  bindings?: HelpBinding[];
  /** Expanded form, grouped into columns. */
  groups?: { label: string; bindings: HelpBinding[] }[];
  /** ? toggles this. Expanded replaces the bar in place — it does not float. */
  expanded?: boolean;
  style?: React.CSSProperties;
}
export declare function HelpBar(props: HelpBarProps): JSX.Element;
