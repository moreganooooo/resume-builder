export declare function tierOf(score: number | null): { color: string; glyph: string; bold: boolean };
export interface ScoreBadgeProps {
  /** 0–5 interview-probability score. null renders the "not evaluated" dash. */
  score: number | null;
  /** e.g. "/5". */
  suffix?: string;
  showGlyph?: boolean;
}
export declare function ScoreBadge(props: ScoreBadgeProps): JSX.Element;
