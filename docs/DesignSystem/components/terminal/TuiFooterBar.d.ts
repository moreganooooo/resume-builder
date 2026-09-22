export interface KeyBinding { key: string; desc: string }
export interface TuiFooterBarProps {
  /** Bracketed, Mauve — the one action the screen is for. */
  primary?: KeyBinding[];
  /** Blue keys — everything else you can do here. */
  actions?: KeyBinding[];
  /** Overlay keys — back, quit. */
  system?: KeyBinding[];
  brand?: string;
}
export declare function TuiFooterBar(props: TuiFooterBarProps): JSX.Element;
