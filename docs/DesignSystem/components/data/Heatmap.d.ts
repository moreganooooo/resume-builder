export interface HeatmapProps {
  /** One entry per week column; each is a 7-length array of daily counts, Sun first. */
  weeks: number[][];
  /** Highest daily count in the range. */
  max?: number;
}
export declare function Heatmap(props: HeatmapProps): JSX.Element;
