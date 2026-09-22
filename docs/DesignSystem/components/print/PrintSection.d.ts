export interface PrintSectionProps {
  /** ALL CAPS: "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION". */
  title: string;
  /** Short sections set this; WORK EXPERIENCE does not. */
  avoidBreak?: boolean;
  children?: React.ReactNode;
}
export declare function PrintSection(props: PrintSectionProps): JSX.Element;
