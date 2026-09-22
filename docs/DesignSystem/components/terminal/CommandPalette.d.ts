export interface PaletteResult {
  /** Screen or category the command belongs to, e.g. "Pipeline". */
  group?: string;
  label: string;
  /** Character indices in `label` that matched the query — rendered Mauve and bold. */
  match?: number[];
  /** The keybinding this command is equivalent to, so the palette teaches it. */
  key?: string;
}
export interface CommandPaletteProps {
  query?: string;
  results?: PaletteResult[];
  cursor?: number;
  onSelect?: (index: number) => void;
  width?: number | string;
  style?: React.CSSProperties;
}
export declare function CommandPalette(props: CommandPaletteProps): JSX.Element;
