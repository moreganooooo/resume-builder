export interface DiffLineProps {
  /** add = green +, remove = red -, same = subtext space, note = mauve ┃ rationale line. */
  kind?: "add" | "remove" | "same" | "note";
  /** Line text. A plain string enables word-level `emphasis`. */
  children?: React.ReactNode;
  /** Substrings to bold inside the line. Bold only — never background fill. */
  emphasis?: string[];
  style?: React.CSSProperties;
}
/** One line of a tailoring redline. Sign column always present; colour is never the only signal. */
export declare function DiffLine(props: DiffLineProps): JSX.Element;
