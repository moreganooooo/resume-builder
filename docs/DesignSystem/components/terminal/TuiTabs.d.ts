export interface TuiTab { label: string; count?: number }
export interface TuiTabsProps {
  /** Labels are UPPERCASE; counts must agree with the list they label. */
  tabs: TuiTab[];
  active?: number;
  onChange?: (index: number) => void;
}
export declare function TuiTabs(props: TuiTabsProps): JSX.Element;
