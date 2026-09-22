export interface ScoreBarProps {
  value: number;
  /** 5 for subscores, 100 for skill-coverage percentages. */
  max?: number;
  /** Cells. 15 everywhere in the product. */
  width?: number;
  label?: React.ReactNode;
  valueText?: string;
}
export declare function ScoreBar(props: ScoreBarProps): JSX.Element;
