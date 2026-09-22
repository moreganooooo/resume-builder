export interface CliBannerProps {
  /** Wordmark. Each space-separated word becomes its own block-letter row. */
  title?: string;
  /** Bold line under the wordmark. */
  tagline?: string;
  /** Live profile counts, rendered in Blue under the tagline. */
  lines?: string[];
}

/** The CLI launcher wordmark: block letters over a starfield, in a Sky-bordered box. */
export declare function CliBanner(props: CliBannerProps): JSX.Element;
