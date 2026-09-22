export interface FileEntry {
  name: string;
  dir?: boolean;
  /** Right-aligned size, pre-formatted (e.g. "42 KB"). */
  size?: string;
  /** Replaces `size`; use for the reason an entry is unreadable. */
  note?: string;
  /** Unsupported type — rendered in Overlay and not selectable. Shown, never hidden. */
  disabled?: boolean;
}
export interface FilePickerProps {
  /** Current directory. Truncates from the left. */
  path?: string;
  /** Permitted extensions, stated up front (e.g. [".pdf", ".docx", ".md"]). */
  allowed?: string[];
  entries?: FileEntry[];
  cursor?: number;
  /** Indices checked for import. */
  selected?: number[];
  onSelect?: (index: number) => void;
  height?: number | string;
  style?: React.CSSProperties;
}
/** bubbles/filepicker as onboarding stage one needs it: extension-scoped, multi-select, unreadable files shown greyed. */
export declare function FilePicker(props: FilePickerProps): JSX.Element;
