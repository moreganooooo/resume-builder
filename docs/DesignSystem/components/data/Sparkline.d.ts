export interface SparklineProps {
  /** Already downsampled to the available column count. */
  values: number[];
  /** Mauve for score trend, Blue for volume. */
  color?: string;
}
export declare function Sparkline(props: SparklineProps): JSX.Element;
