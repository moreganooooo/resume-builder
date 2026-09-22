export interface ModalProps {
  /** Rendered as a Surface header strip above the box. */
  title?: React.ReactNode;
  /** Surface strip below the box — usually the dismissal keys. */
  footer?: React.ReactNode;
  /** active = blue border (dialogs), focus = mauve (the ? help overlay). */
  variant?: "active" | "focus";
  /** The screen behind, rendered in Overlay gray. */
  backdrop?: React.ReactNode;
  children?: React.ReactNode;
}
export declare function Modal(props: ModalProps): JSX.Element;
