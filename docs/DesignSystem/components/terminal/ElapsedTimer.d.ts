export interface ElapsedTimerProps {
  /** Seconds elapsed (stopwatch) or remaining (countdown). */
  seconds?: number;
  /** Typical duration. Past it, the Yellow overrun sentence appears. Stopwatch only. */
  expected?: number;
  /** stopwatch = bubbles/stopwatch, counts up. countdown = bubbles/timer, only for things that fire on their own. */
  mode?: "stopwatch" | "countdown";
  label?: string;
  /** Spinner frame index; the caller owns the tick. */
  frame?: number;
  /** Key that cancels, shown inline. Pass "" to omit when the work is genuinely uncancellable. */
  cancelKey?: string;
  style?: React.CSSProperties;
}
/** bubbles/stopwatch + timer: elapsed clock that admits when work is taking longer than usual. Never a fake percentage. */
export declare function ElapsedTimer(props: ElapsedTimerProps): JSX.Element;
