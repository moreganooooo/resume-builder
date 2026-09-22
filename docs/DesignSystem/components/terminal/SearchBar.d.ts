export interface SearchBarProps {
  query?: string;
  /** True while the user is typing — shows the prompt pill and block cursor. */
  active?: boolean;
  matched?: number;
  total?: number;
}
export declare function SearchBar(props: SearchBarProps): JSX.Element;
