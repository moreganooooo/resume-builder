export interface ClusterNode {
  label: string;
  /** Bullet count. Under 3 is flagged Peach as a likely mis-grouping. */
  count?: number;
  children?: ClusterNode[];
}
export interface ClusterTreeProps {
  nodes?: ClusterNode[];
  /** Flattened, depth-first index of the row carrying the ┃ bar. */
  cursor?: number;
  onSelect?: (index: number) => void;
  style?: React.CSSProperties;
}
export declare function ClusterTree(props: ClusterTreeProps): JSX.Element;
