export interface PrintHeaderProps {
  name: string;
  /** Hard-coded uppercase in the data string; budgeted by character count. */
  tagline?: string;
  /** Phone, email, LinkedIn, location — joined by gray pipes. */
  contacts?: React.ReactNode[];
  /** Optional second row of links. */
  links?: React.ReactNode[];
}
export declare function PrintHeader(props: PrintHeaderProps): JSX.Element;
