export interface HuhFieldProps {
  /** Huh field type. input/text render a bordered box; select/multiselect render an option list. */
  kind?: "input" | "text" | "select" | "multiselect";
  /** Field label, Title Case, a bare noun phrase. */
  label?: string;
  /** Current value. Empty renders the placeholder in Overlay. */
  value?: string;
  placeholder?: string;
  /** Helper line under the field. Replaced by `error` when set. */
  help?: string;
  /** Validation message. Plain words, names the fix, never starts with "Invalid". Forces the error state. */
  error?: string;
  /** blurred = idle, focused = Mauve + cursor, complete = green check. `error` overrides. */
  state?: "blurred" | "focused" | "error" | "complete";
  /** select/multiselect options. */
  options?: string[];
  /** multiselect: indices that are checked. */
  selected?: number[];
  /** select/multiselect: index carrying the ┃ cursor. */
  cursor?: number;
  style?: React.CSSProperties;
}
export declare function HuhField(props: HuhFieldProps): JSX.Element;
