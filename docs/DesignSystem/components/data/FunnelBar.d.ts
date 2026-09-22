export declare const FUNNEL_COLORS: string[];
export interface FunnelBarProps {
  label: string;
  count: number;
  /** Largest count in the set — bars scale against it. */
  max?: number;
  /** Conversion percentage, omitted on the first stage. */
  pct?: number;
  color?: string;
  /** Max bar length in cells. */
  width?: number;
  /** "█" for funnels and weekly activity, "■" for platform yield. */
  glyph?: string;
  labelWidth?: number;
}
export declare function FunnelBar(props: FunnelBarProps): JSX.Element;
