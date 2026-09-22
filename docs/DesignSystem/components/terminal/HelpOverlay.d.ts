import type { KeyBinding } from "./TuiFooterBar";
export interface HelpCategory { label: string; bindings: KeyBinding[] }
export interface HelpOverlayProps {
  /** Screen name; " Help" is appended. */
  title: string;
  categories: HelpCategory[];
  backdrop?: React.ReactNode;
}
export declare function HelpOverlay(props: HelpOverlayProps): JSX.Element;
