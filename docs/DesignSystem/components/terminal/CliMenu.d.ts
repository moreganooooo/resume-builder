export interface CliMenuItem {
  /** Row text. */
  label: string;
  /** Leading Unicode fallback glyph. */
  icon?: string;
  /** Parenthesised explanation after the label. */
  hint?: string;
  /** Set false to suppress the ↳ sub-action hook — the trailing "Back" row does this. */
  hook?: boolean;
}

export interface CliMenuGroup {
  /** Caps section heading with a rule. Omit for the flat main menu. */
  label?: string;
  items: CliMenuItem[];
}

export interface CliMenuProps {
  groups: CliMenuGroup[];
  /** Index of the highlighted row, counted across all groups. */
  cursor?: number;
  /** Called with the flat index when a row is clicked. */
  onSelect?: (index: number) => void;
  /** Prefix grouped rows with the ↳ sub-action hook. Default true. */
  hook?: boolean;
}

/** The CLI's grouped select list — caps group headings, a Green `┃` bar spanning the selected row's both lines, Green selection. */
export declare function CliMenu(props: CliMenuProps): JSX.Element;
