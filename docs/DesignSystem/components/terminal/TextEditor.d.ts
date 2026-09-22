export interface TextEditorProps {
  /** Lines as strings, or { text, wrapped } where `wrapped` marks a soft-wrap continuation (↳, no number). */
  lines?: Array<string | { text: string; wrapped?: boolean }>;
  cursorLine?: number;
  cursorCol?: number;
  /** Character count. Characters, not words — ATS forms truncate on characters. */
  count?: number;
  /** Past this the counter goes Yellow. */
  softLimit?: number;
  /** Past this the counter goes Red. */
  hardLimit?: number;
  focused?: boolean;
  height?: number | string;
  style?: React.CSSProperties;
}
/** bubbles/textarea for cover letters and hand-corrected bullets: numbered gutter, Mauve current line, character counter. */
export declare function TextEditor(props: TextEditorProps): JSX.Element;
